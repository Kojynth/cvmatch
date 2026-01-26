"""
Experience Gate - Porte de validation intelligente pour les blocs d'expérience.

Valide les blocs d'information avant qu'ils deviennent des expériences,
avec scoring composé et filtrage des faux positifs basé sur le contexte.
"""

import re
import unicodedata
from typing import List, Dict, Any, Optional, Tuple, Set
from dataclasses import dataclass
from datetime import datetime, date, timedelta
from enum import Enum

from ..logging.safe_logger import get_safe_logger
from ..config import DEFAULT_PII_CONFIG, EMPLOYMENT_KEYWORDS, ACTION_VERBS_FR
from ..utils.pii import validate_no_pii_leakage
from .block_analyzer import InformationBlock, BlockType
from .block_classifier import ClassificationResult, get_block_classifier
from .element_extractor import ExtractedElement, ElementType, get_element_extractor
from .experience_validation import get_experience_validator

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


class GateDecision(Enum):
    """Décisions possibles de la porte de validation."""
    ACCEPT_AS_EXPERIENCE = "accept_experience"
    ROUTE_TO_EDUCATION = "route_education"
    ROUTE_TO_CERTIFICATION = "route_certification"
    REJECT_AS_NOISE = "reject_noise"


@dataclass
class GateScores:
    """Scores détaillés de la porte de validation."""
    exp_score: float = 0.0
    edu_score: float = 0.0
    cert_score: float = 0.0
    org_score: float = 0.0
    date_score: float = 0.0
    title_penalty: float = 0.0
    context_bonus: float = 0.0
    final_score: float = 0.0
    
    # Détails pour debugging
    breakdown: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.breakdown is None:
            self.breakdown = {}


@dataclass
class GateResult:
    """Résultat complet de validation par la porte."""
    decision: GateDecision
    scores: GateScores
    confidence: float
    reasoning: List[str]
    title_org_link: Optional[Tuple[str, str]] = None
    should_route_to: Optional[str] = None
    hard_reject_reasons: List[str] = None
    
    def __post_init__(self):
        if self.hard_reject_reasons is None:
            self.hard_reject_reasons = []


class ExperienceGate:
    """Porte de validation intelligente pour blocs d'expérience."""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.logger = get_safe_logger(f"{__name__}.ExperienceGate", cfg=DEFAULT_PII_CONFIG)
        self.config = config or {}
        
        # Seuils de validation (HARDENED: ajustés pour meilleure couverture)
        self.thresholds = {
            "final_score_accept": self.config.get("final_score_accept", 1.0),  # Réduit de 1.5 à 1.0
            "cert_route_threshold": self.config.get("cert_route_threshold", 1.5),  # Réduit de 2.0 à 1.5
            "edu_route_threshold": self.config.get("edu_route_threshold", 1.5),   # Réduit de 2.0 à 1.5
            "min_confidence": self.config.get("min_confidence", 0.3)  # Réduit de 0.4 à 0.3
        }
        
        # Listes de mots-clés et patterns
        self._initialize_keywords_and_patterns()
        
        # Statistiques de validation
        self.gate_stats = {
            "blocks_processed": 0,
            "accepted_as_experience": 0,
            "routed_to_education": 0,
            "routed_to_certification": 0,
            "rejected_as_noise": 0,
            "hard_rejections": 0,
            "context_overrides": 0
        }
    
    def _initialize_keywords_and_patterns(self):
        """Initialise les listes de mots-clés et patterns."""
        
        # Mots-clés d'emploi (score EXP)
        self.employment_keywords = set([
            "stage", "stagiaire", "intern", "internship", "alternance", "apprenti",
            "cdd", "cdi", "freelance", "mission", "intérim", "consultant",
            "temps plein", "temps partiel", "full time", "part time",
            "contract", "contractor", "consulting", "developer", "développeur",
            "engineer", "ingénieur", "manager", "chef de projet", "responsable",
            "directeur", "assistant", "technicien", "analyst", "analyste",
            "specialist", "spécialiste", "coordinator", "coordinateur",
            "supervisor", "superviseur", "team lead", "chef d'équipe"
        ] + EMPLOYMENT_KEYWORDS)
        
        # Mots-clés éducatifs (score EDU)
        self.education_keywords = set([
            "bachelor", "licence", "license", "master", "mba", "phd",
            "doctorat", "thèse", "bac", "baccalauréat", "bts", "dut", "but",
            "cap", "bep", "formation", "diplôme", "degree", "certification",
            "université", "university", "école", "ecole", "school", "college",
            "lycée", "lycee", "institut", "institute", "faculté", "faculty",
            "cours", "class", "étudiant", "student", "élève", "candidat"
        ])
        
        # Mots-clés de certifications (score CERT)
        self.certification_keywords = set([
            "toefl", "toeic", "ielts", "cambridge", "voltaire", "pix",
            "aws", "azure", "gcp", "cisco", "microsoft", "oracle",
            "comptia", "cissp", "pmp", "scrum", "itil", "prince2",
            "certified", "certification", "certificate", "exam", "test",
            "score", "niveau", "level", "grade", "points"
        ])
        
        # Patterns de titres négatifs (pénalités)
        self.negative_title_patterns = [
            re.compile(r'^\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4}$'),  # Date seule
            re.compile(r'^\d{4}$'),                                    # Année seule
            re.compile(r'^[A-Z]{2,6}$'),                              # Acronyme court
            re.compile(r'^\s*activités?\s+extra', re.IGNORECASE),     # Header bruit
            re.compile(r'^\s*divers\s*$', re.IGNORECASE),            # Section divers
        ]
        
        # Patterns d'organisations écoles
        self.school_patterns = [
            re.compile(r'\b(?:école|ecole|lycée|université|university|faculty|faculté|institut|institute|college)\b', re.IGNORECASE),
            re.compile(r'\b(?:epsaa|ens|insa|polytech|hec|escp|arts\s+et\s+métiers|sciences\s+po)\b', re.IGNORECASE)
        ]
        
        # Liste blanche d'acronymes autorisés
        self.acronym_allowlist = {
            "IBM", "SAP", "AWS", "BNP", "BNPP", "SNCF", "EDF", "GDF", "RATP",
            "CNRS", "INRA", "CEA", "INSERM", "CNES", "APHP", "INRIA", "IRCAM"
        }
    
    def validate_block(self, block: InformationBlock) -> GateResult:
        """
        Valide un bloc d'information et détermine son routage.
        HARDENED: Utilise le nouveau système ExperienceValidator pour une validation renforcée.
        
        Args:
            block: Bloc à valider
            
        Returns:
            Résultat de validation avec décision de routage
        """
        self.gate_stats["blocks_processed"] += 1
        
        self.logger.debug(f"GATE_VALIDATION: starting | block_lines={len(block.lines)} | preview='{block.get_safe_preview()}'")
        
        # Extraire les éléments du bloc si nécessaire
        if not block.detected_elements or not block.detected_elements.get("title"):
            extractor = get_element_extractor()
            extractor.extract_elements_from_block(block)
        
        # Obtenir la classification du bloc
        classifier = get_block_classifier()
        classification = classifier.classify_block(block)
        
        # HARDENED: Utiliser le nouveau système de validation
        title = block.detected_elements.get("title", "")
        organization = block.detected_elements.get("organization", "")
        
        # Créer un contexte de lignes pour la validation
        context_lines = [line.strip() for line in block.lines if line.strip()]
        target_idx = 0  # Index du bloc principal
        
        # Obtenir le validator amélioré
        validator = get_experience_validator()
        validation_result = validator.validate_experience_candidate(
            title=title,
            company=organization,
            text_lines=context_lines,
            target_line_idx=target_idx
        )
        
        # Convertir le résultat ExperienceValidator vers GateResult
        result = self._convert_validation_result_to_gate_result(
            validation_result, block, classification
        )
        
        # Calculer les scores traditionnels pour compatibilité
        scores = self._calculate_gate_scores(block, classification)
        result.scores = scores
        
        # Mettre à jour les statistiques
        self._update_gate_stats(result)
        
        self.logger.debug(f"GATE_VALIDATION: completed | decision={result.decision.value} | validator_confidence={validation_result['confidence']:.3f} | is_valid={validation_result['is_valid']}")
        
        return result
    
    def _convert_validation_result_to_gate_result(self, validation_result: Dict[str, Any], 
                                                block: InformationBlock,
                                                classification: ClassificationResult) -> GateResult:
        """
        Convertit le résultat d'ExperienceValidator vers un GateResult.
        
        Args:
            validation_result: Résultat du ExperienceValidator
            block: Bloc d'origine
            classification: Classification du bloc
            
        Returns:
            GateResult correspondant
        """
        scores = GateScores()
        reasoning = []
        
        # Déterminer la décision basée sur le validation result
        if validation_result.get('should_route_to_certification', False):
            decision = GateDecision.ROUTE_TO_CERTIFICATION
            reasoning.append(f"routed_to_cert: {validation_result.get('routing_reason', '')}")
            
        elif validation_result.get('should_route_to_education', False):
            decision = GateDecision.ROUTE_TO_EDUCATION
            reasoning.append(f"routed_to_edu: {validation_result.get('routing_reason', '')}")
            
        elif validation_result.get('is_valid', False):
            decision = GateDecision.ACCEPT_AS_EXPERIENCE
            reasoning.append(f"accepted: confidence={validation_result.get('confidence', 0):.3f}")
            
        else:
            decision = GateDecision.REJECT_AS_NOISE
            rejection_reasons = validation_result.get('rejection_reasons', [])
            reasoning.extend([f"rejected: {reason}" for reason in rejection_reasons[:2]])
        
        # Phase 4.1: Calcul de confiance avec ajustements date-only et organisations solides
        base_confidence = validation_result.get('confidence', 0.0)
        
        # Phase 4.2: Pénalité très agressive pour titres date-only détectés
        date_penalty = 0.0
        title = block.detected_elements.get("title", "")
        if title:
            validator = get_experience_validator()
            if validator.is_date_only_token(title):
                date_penalty = -0.60  # Pénalité très agressive pour forcer rejet des "Mois YYYY" 
                reasoning.append("date_only_title_aggressive_penalty")
        
        # Phase 4.1: Bonus pour organisations tech solides/reconnues
        org_bonus = 0.0
        organization = block.detected_elements.get("organization", "")
        if organization:
            solid_orgs = {
                'amazon web services', 'aws', 'netflix', 'uber technologies', 
                'microsoft', 'google', 'facebook', 'apple', 'ibm', 'oracle',
                'sap', 'salesforce', 'adobe', 'nvidia', 'intel'
            }
            org_normalized = organization.lower().strip()
            if any(solid in org_normalized for solid in solid_orgs):
                org_bonus = 0.25  # Bonus pour organisations reconnues
                reasoning.append("solid_tech_organization_bonus")
        
        # Phase 4.1: Confiance finale avec ajustements
        confidence = max(0.0, min(0.95, base_confidence + date_penalty + org_bonus))
        
        # Phase 4.1: Réajuster la décision si confiance trop faible après pénalités
        if decision == GateDecision.ACCEPT_AS_EXPERIENCE and confidence < 0.3:
            decision = GateDecision.REJECT_AS_NOISE
            reasoning.append(f"rejected_after_phase4_adjustments_conf={confidence:.2f}")
        
        scores.final_score = confidence * 4.0  # Scale to traditional scoring range
        
        # Ajouter détails de validation
        validation_details = validation_result.get('validation_details', {})
        if validation_details:
            scores.breakdown = validation_details.get('breakdown', {})
        
        return GateResult(
            decision=decision,
            scores=scores,
            confidence=confidence,
            reasoning=reasoning,
            title_org_link=(
                block.detected_elements.get("title", ""),
                block.detected_elements.get("organization", "")
            )
        )
    
    def _calculate_gate_scores(self, block: InformationBlock, classification: ClassificationResult) -> GateScores:
        """Calcule les scores détaillés pour la validation."""
        scores = GateScores()
        
        title = block.detected_elements.get("title", "")
        organization = block.detected_elements.get("organization", "")
        description = block.detected_elements.get("description", "")
        dates = block.detected_elements.get("dates", "")
        
        full_text = f"{title} {organization} {description}".lower()
        
        # Score EXP : mots-clés d'emploi
        exp_keywords_found = sum(1 for kw in self.employment_keywords if kw.lower() in full_text)
        scores.exp_score = min(4.0, exp_keywords_found * 0.5)
        
        # Score EDU : mots-clés éducatifs
        edu_keywords_found = sum(1 for kw in self.education_keywords if kw.lower() in full_text)
        scores.edu_score = min(4.0, edu_keywords_found * 0.5)
        
        # Score CERT : mots-clés de certification
        cert_keywords_found = sum(1 for kw in self.certification_keywords if kw.lower() in full_text)
        scores.cert_score = min(4.0, cert_keywords_found * 0.6)
        
        # Score ORG : qualité de l'organisation
        scores.org_score = self._calculate_org_score(organization)
        
        # Score DATE : qualité et plausibilité des dates
        scores.date_score = self._calculate_date_score(dates, block)
        
        # Pénalité TITLE : patterns de titre négatifs
        scores.title_penalty = self._calculate_title_penalty(title)
        
        # Bonus CONTEXT : cohérence contextuelle
        scores.context_bonus = self._calculate_context_bonus(block, classification)
        
        # Score final
        scores.final_score = (
            scores.exp_score + scores.org_score + scores.date_score + 
            scores.context_bonus - max(0, scores.title_penalty)
        )
        
        # Détails pour debugging
        scores.breakdown = {
            "exp_keywords": exp_keywords_found,
            "edu_keywords": edu_keywords_found,
            "cert_keywords": cert_keywords_found,
            "classification_confidence": classification.confidence,
            "classification_type": classification.block_type.value
        }
        
        return scores
    
    def _calculate_org_score(self, organization: str) -> float:
        """Calcule le score de qualité de l'organisation."""
        if not organization or len(organization) < 2:
            return 0.0
        
        score = 0.5  # Base
        org_lower = organization.lower()
        
        # Bonus pour indicateurs business
        if re.search(r'\b(?:sas|sarl|sa|inc|corp|ltd|consulting|technologies|solutions|services)\b', org_lower):
            score += 1.0
        
        # Bonus pour organismes publics/reconnus
        if any(acr in organization.upper() for acr in self.acronym_allowlist):
            score += 0.5
        
        # Malus pour patterns d'école si pas de contexte professionnel
        if any(pattern.search(organization) for pattern in self.school_patterns):
            score -= 0.3  # Peut être compensé par contexte professionnel
        
        # Bonus pour longueur et structure appropriées
        if 5 <= len(organization) <= 60 and not organization.isdigit():
            score += 0.5
        
        return max(0.0, min(2.0, score))
    
    def _calculate_date_score(self, dates: str, block: InformationBlock) -> float:
        """Calcule le score de qualité des dates."""
        if not dates:
            return 0.0
        
        score = 1.0  # Base pour présence de dates
        
        # Bonus pour formats de date riches
        if re.search(r'\b(?:janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)\s+\d{4}\b', dates, re.IGNORECASE):
            score += 0.5
        
        # Bonus pour périodes (début-fin)
        if re.search(r'\d{4}\s*[-–—]\s*\d{4}', dates):
            score += 0.5
        
        # Bonus pour position actuelle
        if re.search(r'\b(?:à\s+ce\s+jour|actuellement|en\s+cours|depuis)\b', dates, re.IGNORECASE):
            score += 0.3
        
        # Malus pour dates suspectes (trop courtes, trop anciennes)
        if len(dates.strip()) <= 4:  # Juste une année
            score -= 0.3
        
        # Vérification de plausibilité temporelle
        try:
            # Extraire années pour vérification basique
            years = re.findall(r'\b(19|20)\d{2}\b', dates)
            if years:
                years_int = [int(y) for y in years]
                current_year = datetime.now().year
                
                # Malus pour dates futures
                if any(y > current_year + 1 for y in years_int):
                    score -= 0.5
                
                # Malus pour dates trop anciennes (>30 ans)
                if any(y < current_year - 30 for y in years_int):
                    score -= 0.2
                
                # Bonus pour durée raisonnable
                if len(years_int) >= 2:
                    duration_years = max(years_int) - min(years_int)
                    if 0.1 <= duration_years <= 10:  # Durée raisonnable
                        score += 0.3
        except:
            pass
        
        return max(0.0, min(2.0, score))
    
    def _calculate_title_penalty(self, title: str) -> float:
        """Calcule les pénalités pour titres problématiques."""
        if not title:
            return 1.0  # Pénalité pour titre manquant
        
        penalty = 0.0
        
        # Patterns de titre négatifs
        for pattern in self.negative_title_patterns:
            if pattern.match(title.strip()):
                penalty += 2.0
                break  # Une seule pénalité forte
        
        # Acronyme court non autorisé
        if re.match(r'^[A-Z]{2,6}$', title.strip()):
            if title.upper() not in self.acronym_allowlist:
                penalty += 1.0
        
        # Titre trop court sans contexte
        if len(title.strip()) <= 3:
            penalty += 0.5
        
        # Titre avec beaucoup de chiffres
        digit_ratio = sum(1 for c in title if c.isdigit()) / max(len(title), 1)
        if digit_ratio > 0.3:
            penalty += 1.0
        
        return penalty
    
    def _calculate_context_bonus(self, block: InformationBlock, classification: ClassificationResult) -> float:
        """Calcule le bonus de contexte basé sur la classification."""
        bonus = 0.0
        
        # Bonus pour classification haute confiance
        if classification.confidence >= 0.8:
            bonus += 0.5
        elif classification.confidence >= 0.6:
            bonus += 0.3
        
        # Bonus pour override contextuel (ex: Professeur - École)
        if classification.context_override:
            bonus += 1.0
        
        # Bonus pour signaux professionnels forts
        if classification.professional_signals >= 2:
            bonus += 0.5
        
        # Bonus pour présence de verbes d'action
        full_text = block.raw_text.lower()
        action_verbs_found = sum(1 for verb in ACTION_VERBS_FR if verb in full_text)
        bonus += min(0.5, action_verbs_found * 0.1)
        
        return bonus
    
    def _apply_gate_rules(self, block: InformationBlock, classification: ClassificationResult, scores: GateScores) -> GateResult:
        """Applique les règles de validation et détermine la décision finale."""
        reasoning = []
        hard_reject_reasons = []
        
        title = block.detected_elements.get("title", "")
        organization = block.detected_elements.get("organization", "")
        
        # === RÈGLES DE REJET DUR ===
        
        # Rejet 1 : Titre est une date pure
        if any(pattern.match(title.strip()) for pattern in self.negative_title_patterns):
            hard_reject_reasons.append("title_is_date_only")
            reasoning.append("hard_reject_date_only_title")
        
        # Rejet 2 : Acronyme court non autorisé sans contexte
        if re.match(r'^[A-Z]{2,6}$', title.strip()) and title.upper() not in self.acronym_allowlist:
            if scores.exp_score < 1.0:  # Pas de contexte professionnel fort
                hard_reject_reasons.append("short_acronym_no_context")
                reasoning.append("hard_reject_unwhitelisted_acronym")
        
        # Si rejet dur, retourner rejet
        if hard_reject_reasons:
            self.gate_stats["hard_rejections"] += 1
            return GateResult(
                decision=GateDecision.REJECT_AS_NOISE,
                scores=scores,
                confidence=0.1,
                reasoning=reasoning,
                hard_reject_reasons=hard_reject_reasons
            )
        
        # === RÈGLES DE ROUTAGE ===
        
        # Règle 1 : Certification dominante
        if scores.cert_score >= self.thresholds["cert_route_threshold"] and scores.cert_score > max(scores.exp_score, scores.edu_score):
            reasoning.append(f"certification_signals_{scores.cert_score:.1f}")
            return GateResult(
                decision=GateDecision.ROUTE_TO_CERTIFICATION,
                scores=scores,
                confidence=0.7 + min(0.3, scores.cert_score * 0.1),
                reasoning=reasoning,
                should_route_to="certification"
            )
        
        # Règle 2 : Classification forte vers éducation sans override
        if (classification.block_type == BlockType.EDUCATION and 
            classification.confidence >= 0.7 and 
            not classification.context_override and
            scores.edu_score >= self.thresholds["edu_route_threshold"]):
            
            reasoning.append(f"strong_education_classification_{classification.confidence:.2f}")
            return GateResult(
                decision=GateDecision.ROUTE_TO_EDUCATION,
                scores=scores,
                confidence=classification.confidence,
                reasoning=reasoning,
                should_route_to="education"
            )
        
        # Règle 3 : Score final suffisant pour expérience
        if scores.final_score >= self.thresholds["final_score_accept"]:
            # Phase 4.1: Calcul de confiance avec pénalités date-only et bonus organisations solides
            base_confidence = min(0.9, 0.4 + (scores.final_score / 10.0) + (classification.confidence * 0.3))
            
            # Phase 4.1: Pénalité forte pour titres date-only détectés
            date_penalty = 0.0
            if title:
                validator = get_experience_validator()
                if validator.is_date_only_token(title):
                    date_penalty = -0.45  # Forte pénalité pour forcer rejet des "Mois YYYY"
                    reasoning.append("date_only_title_penalty")
            
            # Phase 4.1: Bonus pour organisations tech solides/reconnues
            org_bonus = 0.0
            if organization:
                solid_orgs = {
                    'amazon web services', 'aws', 'netflix', 'uber technologies', 
                    'microsoft', 'google', 'facebook', 'apple', 'ibm', 'oracle',
                    'sap', 'salesforce', 'adobe', 'nvidia', 'intel'
                }
                org_normalized = organization.lower().strip()
                if any(solid in org_normalized for solid in solid_orgs):
                    org_bonus = 0.25  # Bonus pour organisations reconnues
                    reasoning.append("solid_tech_organization_bonus")
            
            # Phase 4.1: Calcul de confiance final avec ajustements
            confidence = max(0.0, min(0.95, base_confidence + date_penalty + org_bonus))
            
            if confidence >= self.thresholds["min_confidence"]:
                reasoning.append(f"final_score_{scores.final_score:.1f}_sufficient")
                if classification.context_override:
                    reasoning.append("professional_context_override")
                
                return GateResult(
                    decision=GateDecision.ACCEPT_AS_EXPERIENCE,
                    scores=scores,
                    confidence=confidence,
                    reasoning=reasoning,
                    title_org_link=(title, organization)
                )
            else:
                # Phase 4.1: Rejet explicite si confiance trop faible après ajustements
                reasoning.append(f"confidence_too_low_after_adjustments_{confidence:.2f}")
                return GateResult(
                    decision=GateDecision.REJECT_AS_NOISE,
                    scores=scores,
                    confidence=confidence,
                    reasoning=reasoning
                )
        
        # Règle 4 : Score faible mais classification forte EXP avec override
        if (classification.block_type == BlockType.EXPERIENCE and 
            classification.context_override and 
            classification.confidence >= 0.6):
            
            reasoning.append("context_override_rescue")
            return GateResult(
                decision=GateDecision.ACCEPT_AS_EXPERIENCE,
                scores=scores,
                confidence=classification.confidence,
                reasoning=reasoning,
                title_org_link=(title, organization)
            )
        
        # Règle par défaut : Rejet comme bruit
        reasoning.append(f"insufficient_score_{scores.final_score:.1f}")
        return GateResult(
            decision=GateDecision.REJECT_AS_NOISE,
            scores=scores,
            confidence=0.2,
            reasoning=reasoning
        )
    
    def _update_gate_stats(self, result: GateResult):
        """Met à jour les statistiques de la porte."""
        if result.decision == GateDecision.ACCEPT_AS_EXPERIENCE:
            self.gate_stats["accepted_as_experience"] += 1
        elif result.decision == GateDecision.ROUTE_TO_EDUCATION:
            self.gate_stats["routed_to_education"] += 1
        elif result.decision == GateDecision.ROUTE_TO_CERTIFICATION:
            self.gate_stats["routed_to_certification"] += 1
        elif result.decision == GateDecision.REJECT_AS_NOISE:
            self.gate_stats["rejected_as_noise"] += 1
    
    def score_candidate(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        """
        Version legacy pour compatibilité avec le code existant.
        Score un candidat extrait par les patterns title_company.
        """
        # Créer un bloc temporaire à partir du candidat
        title = candidate.get('title', '')
        company = candidate.get('company', '')
        description = candidate.get('description', '')
        
        lines = [title, company]
        if description:
            lines.append(description)
        
        temp_block = InformationBlock(
            lines=lines,
            start_idx=candidate.get('line_idx', 0),
            end_idx=candidate.get('line_idx', 0) + len(lines) - 1
        )
        
        temp_block.detected_elements = {
            "title": title,
            "organization": company,
            "description": description
        }
        
        # Valider le bloc
        result = self.validate_block(temp_block)
        
        # Retourner au format legacy
        return {
            "exp_score": result.scores.exp_score,
            "edu_score": result.scores.edu_score,
            "cert_score": result.scores.cert_score,
            "org_score": result.scores.org_score,
            "date_score": result.scores.date_score,
            "title_penalty": result.scores.title_penalty,
            "final_score": result.scores.final_score,
            "decision": result.decision.value,
            "confidence": result.confidence,
            "should_route_to": result.should_route_to
        }
    
    def is_reject(self, scores: Dict[str, Any]) -> bool:
        """Version legacy pour compatibilité."""
        decision = scores.get("decision", "")
        return decision == GateDecision.REJECT_AS_NOISE.value
    
    def get_gate_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques de la porte."""
        total_processed = self.gate_stats["blocks_processed"]
        if total_processed == 0:
            return dict(self.gate_stats)
        
        stats_with_rates = dict(self.gate_stats)
        stats_with_rates.update({
            "acceptance_rate": self.gate_stats["accepted_as_experience"] / total_processed,
            "education_route_rate": self.gate_stats["routed_to_education"] / total_processed,
            "certification_route_rate": self.gate_stats["routed_to_certification"] / total_processed,
            "rejection_rate": self.gate_stats["rejected_as_noise"] / total_processed,
            "hard_rejection_rate": self.gate_stats["hard_rejections"] / total_processed
        })
        
        return stats_with_rates


# Instance globale
_experience_gate = None

def get_experience_gate(config: Dict[str, Any] = None) -> ExperienceGate:
    """Retourne l'instance singleton de ExperienceGate."""
    global _experience_gate
    if _experience_gate is None:
        _experience_gate = ExperienceGate(config)
    return _experience_gate


# Fonctions utilitaires
def validate_experience_block(block: InformationBlock) -> GateResult:
    """Valide un bloc pour l'expérience."""
    gate = get_experience_gate()
    return gate.validate_block(block)


def score_experience_candidate(candidate: Dict[str, Any]) -> Dict[str, Any]:
    """Score un candidat d'expérience (compatibilité legacy)."""
    gate = get_experience_gate()
    return gate.score_candidate(candidate)