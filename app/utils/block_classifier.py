"""
Block Classifier - Classification intelligente des blocs selon leur contexte métier.

Détermine si un bloc contient une expérience professionnelle, une formation,
une certification ou autre contenu en analysant le contexte titre-organisation.
"""

import re
import unicodedata
from typing import List, Dict, Any, Optional, Tuple, Set
from dataclasses import dataclass
from enum import Enum

from ..logging.safe_logger import get_safe_logger
from ..config import DEFAULT_PII_CONFIG, EMPLOYMENT_KEYWORDS, ACTION_VERBS_FR
from ..utils.pii import validate_no_pii_leakage
from .block_analyzer import InformationBlock, BlockType
from .element_extractor import ExtractedElement, ElementType, get_element_extractor

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


@dataclass
class ClassificationResult:
    """Résultat de classification d'un bloc."""
    block_type: BlockType
    confidence: float
    reasoning: List[str]
    title_org_context: Optional[Tuple[str, str]] = None
    professional_signals: int = 0
    academic_signals: int = 0
    certification_signals: int = 0
    context_override: bool = False


class BlockClassifier:
    """Classificateur contextuel de blocs d'information CV."""
    
    def __init__(self):
        self.logger = get_safe_logger(f"{__name__}.BlockClassifier", cfg=DEFAULT_PII_CONFIG)
        
        # Charger les patterns de classification
        self._compile_classification_patterns()
        
        # Statistiques de classification
        self.classification_stats = {
            "blocks_classified": 0,
            "classification_by_type": {},
            "context_overrides": 0,
            "high_confidence_classifications": 0
        }
    
    def _compile_classification_patterns(self):
        """Compile les patterns pour la classification contextuelle."""
        
        # === ROLES PROFESSIONNELS ===
        self.professional_roles = [
            # Enseignement (professionnel dans éducation)
            r'\b(?:professeur|enseignant|maître\s+de\s+conférences|chargé\s+de\s+cours)\b',
            
            # Management et direction
            r'\b(?:directeur|chef|manager|responsable|coordinateur|supervisor)\b',
            
            # Technique et ingénierie
            r'\b(?:développeur|developer|ingénieur|engineer|architecte|architect)\b',
            r'\b(?:technicien|administrateur|analyst|analyste|consultant)\b',
            
            # Commercial et support
            r'\b(?:commercial|vendeur|conseiller|assistant|adjoint)\b',
            
            # Stages et alternances (expériences professionnelles)
            r'\b(?:stagiaire|stage|alternant|alternance|apprenti|apprentissage)\b',
            
            # Autres rôles pro
            r'\b(?:expert|spécialiste|lead|senior|junior|intern)\b'
        ]
        
        # === ROLES ÉTUDIANTS/ACADÉMIQUES ===
        self.student_roles = [
            # Diplômes et cursus
            r'\b(?:bachelor|licence|license|master|mba|doctorat|phd|thèse|mémoire)\b',
            
            # Niveaux éducatifs
            r'\b(?:bac|baccalauréat|bts|dut|but|cap|bep)\b',
            
            # Statuts étudiants
            r'\b(?:étudiant|élève|candidat|doctorant|thésard)\b',
            
            # Contexte académique
            r'\b(?:formation|cursus|parcours|spécialisation)\b'
        ]
        
        # === ORGANISATIONS ÉDUCATIVES ===
        self.educational_organizations = [
            r'\b(?:université|university|college|faculté|faculty)\b',
            r'\b(?:école|ecole|school|institut|institute|academy)\b',
            r'\b(?:lycée|lycee|collège|college)\b',
            r'\b(?:conservatoire|iut|cnam|cned)\b',
            
            # Grandes écoles
            r'\b(?:polytechnique|hec|essec|escp|insead|sciences\s+po)\b',
            r'\b(?:ens|insa|ensta|supelec|mines|ponts)\b',
            r'\b(?:epitech|supinfo|efrei|esme|esiee|epita|iseg)\b'
        ]
        
        # === ORGANISATIONS BUSINESS ===
        self.business_organizations = [
            # Types juridiques
            r'\b(?:sas|sarl|sa|eurl|sci|inc|corp|corporation|ltd|llc|gmbh|ag)\b',
            
            # Secteurs business
            r'\b(?:consulting|conseil|services|solutions|technologies|tech)\b',
            r'\b(?:systems|group|groupe|holding|international)\b',
            r'\b(?:startup|start-up|entreprise|company|firm|agency|agence)\b',
            
            # Organismes publics (expérience pro)
            r'\b(?:cnrs|inserm|cea|inra|cnam|edf|ratp|sncf|aphp)\b'
        ]
        
        # === CERTIFICATIONS ===
        self.certification_patterns = [
            # Certifications linguistiques
            r'\b(?:toefl|toeic|ielts|bulats|cambridge|delf|dalf|tcf|tef)\b',
            r'\b(?:goethe|testdaf|dele|siele|hsk|jlpt)\b',
            
            # Certifications IT
            r'\b(?:aws|amazon\s+web\s+services|azure|microsoft|google\s+cloud|gcp)\b',
            r'\b(?:cisco|ccna|ccnp|ccie|comptia|security\+|network\+)\b',
            r'\b(?:pmp|prince2|itil|scrum|agile|six\s+sigma)\b',
            
            # Mentions de certification
            r'\b(?:certified|certification|certificate|diplôme|attestation)\b',
            r'\b(?:score|niveau|level|grade|points?)\s+\d+\b',
            r'\b(?:réussi|obtenu|passé|validé)\b.*(?:examen|test|certification)\b'
        ]
        
        # === CONTEXTES PROFESSIONNELS ===
        self.professional_context = [
            # Activités professionnelles
            r'\b(?:mission|projet|client|customer|équipe|team)\b',
            r'\b(?:objectif|résultat|achievement|performance|kpi)\b',
            r'\b(?:budget|chiffre\s+d\'affaires|revenue|profit)\b',
            
            # Relations professionnelles
            r'\b(?:manager|superviseur|collègue|colleague|partenaire)\b',
            r'\b(?:hiérarchie|reporting|encadrement|supervision)\b',
            
            # Contractuel
            r'\b(?:contrat|contract|cdd|cdi|temps\s+plein|temps\s+partiel)\b',
            r'\b(?:salaire|rémunération|salary|benefits|avantages)\b'
        ] + EMPLOYMENT_KEYWORDS + ACTION_VERBS_FR
        
        # === CONTEXTES ACADÉMIQUES ===
        self.academic_context = [
            # Activités académiques
            r'\b(?:cours|class|enseignement|teaching|recherche|research)\b',
            r'\b(?:projet\s+étudiant|student\s+project|travaux\s+pratiques|tp)\b',
            r'\b(?:mémoire|thèse|dissertation|thesis|rapport\s+de\s+stage)\b',
            
            # Évaluation académique
            r'\b(?:examen|exam|note|grade|évaluation|assessment)\b',
            r'\b(?:ects|crédit|unité\s+d\'enseignement|ue|module)\b',
            
            # Progression académique
            r'\b(?:semestre|trimestre|année\s+d\'étude|niveau\s+d\'étude)\b',
            r'\b(?:spécialisation|majeure|mineure|option|parcours)\b'
        ]
        
        # Compiler les patterns
        self.professional_patterns = [re.compile(p, re.IGNORECASE) for p in self.professional_roles]
        self.student_patterns = [re.compile(p, re.IGNORECASE) for p in self.student_roles]
        self.edu_org_patterns = [re.compile(p, re.IGNORECASE) for p in self.educational_organizations]
        self.business_patterns = [re.compile(p, re.IGNORECASE) for p in self.business_organizations]
        self.cert_patterns = [re.compile(p, re.IGNORECASE) for p in self.certification_patterns]
        self.prof_context_patterns = [re.compile(p, re.IGNORECASE) for p in self.professional_context]
        self.acad_context_patterns = [re.compile(p, re.IGNORECASE) for p in self.academic_context]
    
    def classify_block(self, block: InformationBlock) -> ClassificationResult:
        """
        Classifie un bloc d'information selon son contexte métier.
        
        Args:
            block: Bloc à classifier
            
        Returns:
            Résultat de classification avec type, confiance et raisonnement
        """
        self.classification_stats["blocks_classified"] += 1
        
        # Extraire les éléments du bloc si pas encore fait
        if not block.detected_elements or not block.detected_elements.get("title"):
            extractor = get_element_extractor()
            extractor.extract_elements_from_block(block)
        
        title = block.detected_elements.get("title", "")
        organization = block.detected_elements.get("organization", "")
        description = block.detected_elements.get("description", "")
        
        self.logger.debug(f"BLOCK_CLASSIFICATION: starting | title='{validate_no_pii_leakage(title[:30], DEFAULT_PII_CONFIG.HASH_SALT)}' org='{validate_no_pii_leakage(organization[:30], DEFAULT_PII_CONFIG.HASH_SALT)}'")
        
        # Analyser les signaux de classification
        signals = self._analyze_classification_signals(block, title, organization, description)
        
        # Appliquer la logique de classification contextuelle
        result = self._apply_classification_logic(block, title, organization, signals)
        
        # Mettre à jour les statistiques
        self._update_classification_stats(result)
        
        self.logger.debug(f"BLOCK_CLASSIFICATION: completed | type={result.block_type.value} confidence={result.confidence:.3f} reasoning={result.reasoning}")
        
        return result
    
    def _analyze_classification_signals(self, block: InformationBlock, title: str, organization: str, description: str) -> Dict[str, int]:
        """Analyse les signaux de classification dans le bloc."""
        signals = {
            "professional_role": 0,
            "student_role": 0,
            "educational_org": 0,
            "business_org": 0,
            "certification": 0,
            "professional_context": 0,
            "academic_context": 0
        }
        
        full_text = f"{title} {organization} {description}".lower()
        
        # Signaux de rôles professionnels
        signals["professional_role"] = sum(1 for p in self.professional_patterns if p.search(title))
        
        # Signaux de rôles étudiants
        signals["student_role"] = sum(1 for p in self.student_patterns if p.search(title))
        
        # Signaux d'organisations éducatives
        signals["educational_org"] = sum(1 for p in self.edu_org_patterns if p.search(organization))
        
        # Signaux d'organisations business
        signals["business_org"] = sum(1 for p in self.business_patterns if p.search(organization))
        
        # Signaux de certifications
        signals["certification"] = sum(1 for p in self.cert_patterns if p.search(full_text))
        
        # Signaux de contexte professionnel
        signals["professional_context"] = sum(1 for p in self.prof_context_patterns if p.search(full_text))
        
        # Signaux de contexte académique  
        signals["academic_context"] = sum(1 for p in self.acad_context_patterns if p.search(full_text))
        
        return signals
    
    def _apply_classification_logic(self, block: InformationBlock, title: str, organization: str, signals: Dict[str, int]) -> ClassificationResult:
        """Applique la logique de classification contextuelle."""
        reasoning = []
        confidence = 0.5  # Confiance de base
        
        # === RÈGLE 1: CERTIFICATIONS (priorité haute) ===
        if signals["certification"] >= 2:
            reasoning.append(f"certification_signals_{signals['certification']}")
            return ClassificationResult(
                block_type=BlockType.CERTIFICATION,
                confidence=0.8 + min(0.2, signals["certification"] * 0.05),
                reasoning=reasoning,
                certification_signals=signals["certification"]
            )
        
        # === RÈGLE 2: RÔLE PROFESSIONNEL + CONTEXTE (priorité haute) ===
        if signals["professional_role"] >= 1 and signals["professional_context"] >= 1:
            reasoning.append(f"professional_role_with_context")
            confidence = 0.7 + min(0.3, (signals["professional_role"] + signals["professional_context"]) * 0.05)
            
            # Override: Même si organisation éducative, rôle pro = EXP
            if signals["educational_org"] >= 1:
                reasoning.append("professional_override_educational_org")
                confidence += 0.1  # Bonus pour override contextuel
                
            return ClassificationResult(
                block_type=BlockType.EXPERIENCE,
                confidence=confidence,
                reasoning=reasoning,
                title_org_context=(title, organization),
                professional_signals=signals["professional_role"] + signals["professional_context"],
                context_override=signals["educational_org"] >= 1
            )
        
        # === RÈGLE 3: RÔLE ÉTUDIANT + ORGANISATION ÉDUCATIVE (priorité moyenne) ===
        if signals["student_role"] >= 1 and signals["educational_org"] >= 1:
            reasoning.append(f"student_role_in_educational_org")
            confidence = 0.8 + min(0.2, (signals["student_role"] + signals["educational_org"]) * 0.05)
            
            return ClassificationResult(
                block_type=BlockType.EDUCATION,
                confidence=confidence,
                reasoning=reasoning,
                title_org_context=(title, organization),
                academic_signals=signals["student_role"] + signals["educational_org"]
            )
        
        # === RÈGLE 4: RÔLE PROFESSIONNEL SANS CONTEXTE (priorité faible) ===
        if signals["professional_role"] >= 1:
            reasoning.append(f"professional_role_weak_context")
            
            # Si organisation business, renforce EXP
            if signals["business_org"] >= 1:
                reasoning.append("business_org_support")
                confidence = 0.6 + min(0.2, signals["business_org"] * 0.1)
            else:
                confidence = 0.4  # Faible sans contexte business
            
            return ClassificationResult(
                block_type=BlockType.EXPERIENCE,
                confidence=confidence,
                reasoning=reasoning,
                title_org_context=(title, organization),
                professional_signals=signals["professional_role"]
            )
        
        # === RÈGLE 5: ORGANISATION ÉDUCATIVE DOMINANTE (priorité faible) ===
        if signals["educational_org"] >= 1 and signals["academic_context"] >= 1:
            reasoning.append(f"educational_org_with_academic_context")
            confidence = 0.5 + min(0.2, (signals["educational_org"] + signals["academic_context"]) * 0.05)
            
            return ClassificationResult(
                block_type=BlockType.EDUCATION,
                confidence=confidence,
                reasoning=reasoning,
                title_org_context=(title, organization),
                academic_signals=signals["educational_org"] + signals["academic_context"]
            )
        
        # === RÈGLE 6: ORGANISATION BUSINESS DOMINANTE ===
        if signals["business_org"] >= 1:
            reasoning.append(f"business_org_default")
            confidence = 0.5 + min(0.2, signals["business_org"] * 0.1)
            
            return ClassificationResult(
                block_type=BlockType.EXPERIENCE,
                confidence=confidence,
                reasoning=reasoning,
                title_org_context=(title, organization),
                professional_signals=signals["business_org"]
            )
        
        # === RÈGLE 7: ANALYSE CONTEXTUELLE APPROFONDIE ===
        if signals["professional_context"] > signals["academic_context"]:
            reasoning.append("professional_context_dominance")
            return ClassificationResult(
                block_type=BlockType.EXPERIENCE,
                confidence=0.4 + min(0.2, signals["professional_context"] * 0.05),
                reasoning=reasoning,
                professional_signals=signals["professional_context"]
            )
        
        elif signals["academic_context"] > signals["professional_context"]:
            reasoning.append("academic_context_dominance")
            return ClassificationResult(
                block_type=BlockType.EDUCATION,
                confidence=0.4 + min(0.2, signals["academic_context"] * 0.05),
                reasoning=reasoning,
                academic_signals=signals["academic_context"]
            )
        
        # === RÈGLE DEFAULT: INCONNU ===
        reasoning.append("insufficient_signals_for_classification")
        return ClassificationResult(
            block_type=BlockType.UNKNOWN,
            confidence=0.1,
            reasoning=reasoning
        )
    
    def classify_title_organization_pair(self, title: str, org: str, context_lines: List[str] = None) -> str:
        """
        Classification rapide d'une paire titre-organisation.
        
        Args:
            title: Titre/rôle extrait
            org: Organisation extraite
            context_lines: Lignes de contexte pour analyse
            
        Returns:
            Type de bloc: "experience", "education", "certification", "unknown"
        """
        # Créer un bloc temporaire pour la classification
        lines = [title, org] + (context_lines[:3] if context_lines else [])
        temp_block = InformationBlock(
            lines=lines,
            start_idx=0,
            end_idx=len(lines) - 1
        )
        
        # Définir les éléments détectés
        temp_block.detected_elements = {
            "title": title,
            "organization": org,
            "description": " ".join(context_lines[:5]) if context_lines else ""
        }
        
        # Classifier
        result = self.classify_block(temp_block)
        
        return result.block_type.value
    
    def _update_classification_stats(self, result: ClassificationResult):
        """Met à jour les statistiques de classification."""
        block_type = result.block_type.value
        self.classification_stats["classification_by_type"][block_type] = (
            self.classification_stats["classification_by_type"].get(block_type, 0) + 1
        )
        
        if result.context_override:
            self.classification_stats["context_overrides"] += 1
        
        if result.confidence >= 0.7:
            self.classification_stats["high_confidence_classifications"] += 1
    
    def get_classification_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques de classification."""
        return dict(self.classification_stats)


# === PATTERNS SPÉCIALISÉS POUR CAS COMPLEXES ===

class SpecializedClassifier:
    """Classificateur spécialisé pour cas complexes et ambigus."""
    
    @staticmethod
    def is_professor_in_school(title: str, org: str) -> bool:
        """Détecte le cas Professeur - École (→ EXP)."""
        title_lower = title.lower()
        org_lower = org.lower()
        
        is_teaching_role = any(role in title_lower for role in [
            "professeur", "enseignant", "maître de conférences", 
            "directeur", "responsable pédagogique"
        ])
        
        is_educational_org = any(edu in org_lower for edu in [
            "université", "école", "college", "institut", "lycée"
        ])
        
        return is_teaching_role and is_educational_org
    
    @staticmethod  
    def is_student_at_school(title: str, org: str) -> bool:
        """Détecte le cas Étudiant - École (→ EDU)."""
        title_lower = title.lower()
        org_lower = org.lower()
        
        is_student_role = any(role in title_lower for role in [
            "bachelor", "master", "licence", "bts", "dut", 
            "étudiant", "élève", "doctorant", "thèse"
        ])
        
        is_educational_org = any(edu in org_lower for edu in [
            "université", "école", "college", "institut", "lycée"
        ])
        
        return is_student_role and is_educational_org
    
    @staticmethod
    def is_internship_at_company(title: str, org: str) -> bool:
        """Détecte le cas Stage - Entreprise (→ EXP)."""
        title_lower = title.lower()
        
        is_internship = any(intern in title_lower for intern in [
            "stage", "stagiaire", "alternant", "alternance", "apprenti"
        ])
        
        return is_internship  # Stage = toujours expérience, peu importe l'org


# Instance globale
_block_classifier = None

def get_block_classifier() -> BlockClassifier:
    """Retourne l'instance singleton de BlockClassifier."""
    global _block_classifier
    if _block_classifier is None:
        _block_classifier = BlockClassifier()
    return _block_classifier


# Fonctions utilitaires
def classify_block(block: InformationBlock) -> ClassificationResult:
    """Classifie un bloc d'information."""
    classifier = get_block_classifier()
    return classifier.classify_block(block)


def classify_title_organization_pair(title: str, org: str, context: List[str] = None) -> str:
    """Classification rapide d'une paire titre-organisation."""
    classifier = get_block_classifier()
    return classifier.classify_title_organization_pair(title, org, context)


def is_professional_context(title: str, org: str) -> bool:
    """Vérifie si c'est un contexte professionnel."""
    # Cas spécialisés
    if SpecializedClassifier.is_professor_in_school(title, org):
        return True  # Professeur = travail professionnel
    
    if SpecializedClassifier.is_internship_at_company(title, org):
        return True  # Stage = expérience professionnelle
    
    if SpecializedClassifier.is_student_at_school(title, org):
        return False  # Étudiant = formation
    
    # Classification générale
    classification = classify_title_organization_pair(title, org)
    return classification == "experience"