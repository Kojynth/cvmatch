"""
Element Extractor - Extraction intelligente d'éléments depuis des blocs cohérents.

Extrait et lie les éléments (titre, organisation, dates, description) à travers
plusieurs lignes d'un bloc, permettant une reconnaissance contextuelle précise.
"""

import re
import unicodedata
from typing import List, Dict, Any, Optional, Tuple, Set, NamedTuple
from dataclasses import dataclass
from datetime import datetime, date
from enum import Enum

from ..logging.safe_logger import get_safe_logger
from ..config import DEFAULT_PII_CONFIG, EMPLOYMENT_KEYWORDS, ACTION_VERBS_FR
from ..utils.pii import validate_no_pii_leakage
from .block_analyzer import InformationBlock, BlockType

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


class ElementType(Enum):
    """Types d'éléments extractibles."""
    TITLE = "title"
    ORGANIZATION = "organization"  
    DATES = "dates"
    LOCATION = "location"
    DESCRIPTION = "description"
    SKILLS = "skills"
    ACHIEVEMENTS = "achievements"


@dataclass
class ExtractedElement:
    """Représente un élément extrait avec ses métadonnées."""
    element_type: ElementType
    content: str
    confidence: float
    line_idx: int
    start_pos: int = 0
    end_pos: int = 0
    supporting_evidence: List[str] = None
    
    def __post_init__(self):
        if self.supporting_evidence is None:
            self.supporting_evidence = []


class ElementExtractor:
    """Extracteur d'éléments contextuel pour blocs d'information."""
    
    def __init__(self):
        self.logger = get_safe_logger(f"{__name__}.ElementExtractor", cfg=DEFAULT_PII_CONFIG)
        
        # Compile les patterns d'extraction
        self._compile_extraction_patterns()
        
        # Compile les listes de mots-clés
        self._compile_keyword_lists()
        
        # Statistiques d'extraction
        self.extraction_stats = {
            "blocks_processed": 0,
            "elements_extracted": 0,
            "successful_links": 0,
            "extraction_failures": 0
        }
    
    def _compile_extraction_patterns(self):
        """Compile les patterns regex pour l'extraction d'éléments."""
        
        # === PATTERNS DE TITRES/ROLES ===
        self.title_patterns = [
            # Rôles professionnels directs
            re.compile(r'\b(?:professeur|enseignant|maître de conférences)\s+(?:de\s+|en\s+)?([^,\n]+)', re.IGNORECASE),
            re.compile(r'\b(?:directeur|chef|manager|responsable)\s+(?:de\s+|du\s+|des\s+)?([^,\n]+)', re.IGNORECASE),
            re.compile(r'\b(?:développeur|developer|ingénieur|engineer)\s+([^,\n]+)', re.IGNORECASE),
            re.compile(r'\b(?:consultant|analyste|technicien)\s+(?:en\s+|sur\s+)?([^,\n]+)', re.IGNORECASE),
            re.compile(r'\b(?:stagiaire|stage|alternance|apprenti)\s+([^,\n]+)', re.IGNORECASE),
            re.compile(r'\b(?:assistant|adjoint)\s+([^,\n]+)', re.IGNORECASE),
            
            # Patterns avec séparateurs
            re.compile(r'^([^•\-–|@\n]{3,40})\s*[-–|@]\s*([^•\-–|@\n]{3,40})$', re.MULTILINE),
            
            # Rôles simples en début de ligne
            re.compile(r'^\s*([A-Z][a-zA-Z\s]{2,30}(?:eur|ant|ien|eur|ste|tor|ger))(?:\s|$)', re.MULTILINE)
        ]
        
        # === PATTERNS D'ORGANISATIONS ===
        self.organization_patterns = [
            # Entreprises avec suffixes juridiques
            re.compile(r'\b([A-Za-zÀ-ÿ\s]+(?:SAS|SARL|SA|EURL|SCI|Inc|Corp|Ltd|LLC|GmbH))\b', re.IGNORECASE),
            
            # Établissements éducatifs
            re.compile(r'\b((?:Université|École|Lycée|Institut|College|University)\s+[A-Za-zÀ-ÿ\s\-]+)', re.IGNORECASE),
            re.compile(r'\b([A-Za-zÀ-ÿ]+(?:\s+[A-Za-zÀ-ÿ]+)*\s+(?:Université|École|University|College|Institute))', re.IGNORECASE),
            
            # Organismes publics/gouvernementaux
            re.compile(r'\b((?:CNRS|INSERM|CEA|INRA|CNAM|EDF|RATP|SNCF)[A-Za-zÀ-ÿ\s]*)', re.IGNORECASE),
            
            # Entreprises avec mots-clés business
            re.compile(r'\b([A-Za-zÀ-ÿ]+(?:\s+[A-Za-zÀ-ÿ]+)*\s+(?:Consulting|Technologies|Solutions|Services|Systems|Group|Groupe))', re.IGNORECASE),
            
            # Noms propres avec majuscules (heuristique)
            re.compile(r'\b([A-Z][a-zA-ZÀ-ÿ]*(?:\s+[A-Z][a-zA-ZÀ-ÿ]*){1,3})\b')
        ]
        
        # === PATTERNS DE DATES ===
        self.date_patterns = [
            # Formats français complets
            re.compile(r'\b(?:janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)\s+\d{4}\b', re.IGNORECASE),
            re.compile(r'\b(?:jan|fév|mar|avr|mai|jun|jul|aoû|sep|oct|nov|déc)\.?\s+\d{4}\b', re.IGNORECASE),
            
            # Formats numériques
            re.compile(r'\b\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4}\b'),
            re.compile(r'\b\d{1,2}[\/\-\.]\d{4}\b'),
            re.compile(r'\b\d{4}\b'),
            
            # Périodes et durées
            re.compile(r'\b\d{4}\s*[-–—]\s*\d{4}\b'),
            re.compile(r'\b\d{1,2}[\/\-\.]\d{4}\s*[-–—]\s*\d{1,2}[\/\-\.]\d{4}\b'),
            
            # Expressions temporelles
            re.compile(r'\b(?:depuis|until|jusqu\'à|à\s+ce\s+jour|actuellement|en\s+cours)\b', re.IGNORECASE),
            re.compile(r'\b(?:pendant|durant)\s+\d+\s+(?:mois|ans|années)\b', re.IGNORECASE)
        ]
        
        # === PATTERNS DE LIEUX ===
        self.location_patterns = [
            re.compile(r'\b(?:Paris|Lyon|Marseille|Toulouse|Nice|Nantes|Strasbourg|Montpellier|Bordeaux|Lille|Rennes|Reims|Le Havre|Saint-Étienne|Toulon|Grenoble|Dijon|Angers|Nîmes|Villeurbanne)\b', re.IGNORECASE),
            re.compile(r'\b\d{5}\s+[A-Za-zÀ-ÿ\-\s]+\b'),  # Code postal + ville
            re.compile(r'\b[A-Za-zÀ-ÿ\-\s]+,\s+(?:France|Paris|Lyon|Marseille)\b', re.IGNORECASE)
        ]
        
        # === PATTERNS DE COMPÉTENCES ===
        self.skills_patterns = [
            re.compile(r'\b(?:Python|Java|JavaScript|C\+\+|C#|PHP|Ruby|Go|Rust|SQL|HTML|CSS|React|Angular|Vue|Node\.js|Django|Flask|Spring|Laravel)\b', re.IGNORECASE),
            re.compile(r'\b(?:Machine Learning|AI|Artificial Intelligence|Data Science|Big Data|Cloud|AWS|Azure|GCP|Docker|Kubernetes|DevOps)\b', re.IGNORECASE)
        ]
    
    def _compile_keyword_lists(self):
        """Compile les listes de mots-clés pour la classification."""
        
        # Mots-clés professionnels
        self.professional_keywords = set([
            "développement", "gestion", "management", "pilotage", "coordination",
            "supervision", "encadrement", "formation", "conseil", "expertise",
            "analyse", "conception", "réalisation", "maintenance", "support",
            "vente", "commercial", "marketing", "communication", "recherche"
        ] + EMPLOYMENT_KEYWORDS + ACTION_VERBS_FR)
        
        # Mots-clés académiques
        self.academic_keywords = set([
            "cours", "enseignement", "recherche", "thèse", "mémoire", "stage",
            "projet", "étude", "formation", "diplôme", "certification", "examen",
            "université", "école", "faculté", "département", "laboratoire"
        ])
        
        # Mots-clés de certifications
        self.certification_keywords = set([
            "toefl", "toeic", "ielts", "cambridge", "voltaire", "pix",
            "aws", "azure", "gcp", "cisco", "microsoft", "oracle",
            "pmp", "scrum", "itil", "prince2", "comptia", "cissp"
        ])
    
    def extract_elements_from_block(self, block: InformationBlock) -> Dict[str, ExtractedElement]:
        """
        Extrait tous les éléments d'un bloc d'information.
        
        Args:
            block: Bloc d'information à analyser
            
        Returns:
            Dictionnaire des éléments extraits par type
        """
        self.extraction_stats["blocks_processed"] += 1
        
        extracted_elements = {}
        block_text = block.raw_text
        
        self.logger.debug(f"ELEMENT_EXTRACTION: starting | block_lines={len(block.lines)} | preview='{block.get_safe_preview()}'")
        
        try:
            # Extraire chaque type d'élément
            extracted_elements[ElementType.TITLE.value] = self._extract_titles(block)
            extracted_elements[ElementType.ORGANIZATION.value] = self._extract_organizations(block)
            extracted_elements[ElementType.DATES.value] = self._extract_dates(block)
            extracted_elements[ElementType.LOCATION.value] = self._extract_locations(block)
            extracted_elements[ElementType.DESCRIPTION.value] = self._extract_descriptions(block)
            extracted_elements[ElementType.SKILLS.value] = self._extract_skills(block)
            
            # Filtrer les éléments vides
            extracted_elements = {k: v for k, v in extracted_elements.items() if v and v.content.strip()}
            
            # Mettre à jour le bloc avec les éléments extraits
            for element_type, element in extracted_elements.items():
                block.detected_elements[element_type] = element.content
                block.confidence_scores[element_type] = element.confidence
            
            self.extraction_stats["elements_extracted"] += len(extracted_elements)
            
            self.logger.debug(f"ELEMENT_EXTRACTION: completed | elements_found={list(extracted_elements.keys())}")
            
        except Exception as e:
            self.logger.error(f"ELEMENT_EXTRACTION: failed | error={e}")
            self.extraction_stats["extraction_failures"] += 1
        
        return extracted_elements
    
    def _extract_titles(self, block: InformationBlock) -> Optional[ExtractedElement]:
        """Extrait les titres/rôles professionnels du bloc."""
        best_match = None
        best_confidence = 0.0
        
        for line_idx, line in enumerate(block.lines):
            line_stripped = line.strip()
            if not line_stripped or len(line_stripped) < 3:
                continue
            
            # Chercher avec les patterns de titres
            for pattern in self.title_patterns:
                match = pattern.search(line)
                if match:
                    title_text = match.group(1) if match.lastindex and match.lastindex >= 1 else match.group(0)
                    title_text = title_text.strip()
                    
                    if len(title_text) < 3 or len(title_text) > 100:
                        continue
                    
                    # Calculer la confiance basée sur les mots-clés professionnels
                    confidence = self._calculate_title_confidence(title_text, block)
                    
                    if confidence > best_confidence:
                        best_match = ExtractedElement(
                            element_type=ElementType.TITLE,
                            content=title_text,
                            confidence=confidence,
                            line_idx=line_idx,
                            start_pos=match.start(),
                            end_pos=match.end()
                        )
                        best_confidence = confidence
        
        # Si pas de match avec patterns, chercher heuristiquement
        if best_confidence < 0.3:
            heuristic_match = self._extract_title_heuristic(block)
            if heuristic_match and heuristic_match.confidence > best_confidence:
                best_match = heuristic_match
        
        return best_match
    
    def _extract_organizations(self, block: InformationBlock) -> Optional[ExtractedElement]:
        """Extrait les noms d'organisations du bloc."""
        best_match = None
        best_confidence = 0.0
        
        for line_idx, line in enumerate(block.lines):
            line_stripped = line.strip()
            if not line_stripped or len(line_stripped) < 2:
                continue
            
            # Chercher avec les patterns d'organisations
            for pattern in self.organization_patterns:
                match = pattern.search(line)
                if match:
                    org_text = match.group(1) if match.lastindex and match.lastindex >= 1 else match.group(0)
                    org_text = org_text.strip()
                    
                    if len(org_text) < 2 or len(org_text) > 100:
                        continue
                    
                    # Calculer la confiance
                    confidence = self._calculate_organization_confidence(org_text, block)
                    
                    if confidence > best_confidence:
                        best_match = ExtractedElement(
                            element_type=ElementType.ORGANIZATION,
                            content=org_text,
                            confidence=confidence,
                            line_idx=line_idx,
                            start_pos=match.start(),
                            end_pos=match.end()
                        )
                        best_confidence = confidence
        
        return best_match
    
    def _extract_dates(self, block: InformationBlock) -> Optional[ExtractedElement]:
        """Extrait les informations temporelles du bloc."""
        date_matches = []
        
        for line_idx, line in enumerate(block.lines):
            for pattern in self.date_patterns:
                for match in pattern.finditer(line):
                    date_text = match.group(0).strip()
                    confidence = self._calculate_date_confidence(date_text)
                    
                    date_matches.append(ExtractedElement(
                        element_type=ElementType.DATES,
                        content=date_text,
                        confidence=confidence,
                        line_idx=line_idx,
                        start_pos=match.start(),
                        end_pos=match.end()
                    ))
        
        if not date_matches:
            return None
        
        # Combiner toutes les dates trouvées si elles semblent cohérentes
        if len(date_matches) == 1:
            return date_matches[0]
        
        # Pour plusieurs dates, prendre la ligne avec le meilleur score
        best_match = max(date_matches, key=lambda x: x.confidence)
        
        # Combiner les dates de la même ligne
        same_line_dates = [dm for dm in date_matches if dm.line_idx == best_match.line_idx]
        if len(same_line_dates) > 1:
            combined_content = " ".join([dm.content for dm in same_line_dates])
            best_match.content = combined_content
        
        return best_match
    
    def _extract_locations(self, block: InformationBlock) -> Optional[ExtractedElement]:
        """Extrait les informations de lieu du bloc."""
        best_match = None
        best_confidence = 0.0
        
        for line_idx, line in enumerate(block.lines):
            for pattern in self.location_patterns:
                match = pattern.search(line)
                if match:
                    location_text = match.group(0).strip()
                    confidence = 0.7  # Confiance de base pour les lieux
                    
                    if confidence > best_confidence:
                        best_match = ExtractedElement(
                            element_type=ElementType.LOCATION,
                            content=location_text,
                            confidence=confidence,
                            line_idx=line_idx,
                            start_pos=match.start(),
                            end_pos=match.end()
                        )
                        best_confidence = confidence
        
        return best_match
    
    def _extract_descriptions(self, block: InformationBlock) -> Optional[ExtractedElement]:
        """Extrait les descriptions/contenus du bloc."""
        description_lines = []
        
        for line_idx, line in enumerate(block.lines):
            line_stripped = line.strip()
            
            # Ignorer les lignes qui sont probablement des titres ou organisations
            if self._line_looks_like_title_or_org(line_stripped):
                continue
            
            # Ignorer les lignes qui sont juste des dates
            if any(pattern.fullmatch(line_stripped) for pattern in self.date_patterns):
                continue
            
            # Ajouter les lignes de contenu
            if line_stripped and len(line_stripped) >= 10:  # Minimum de contenu
                description_lines.append(line_stripped)
        
        if not description_lines:
            return None
        
        combined_description = " ".join(description_lines)
        confidence = self._calculate_description_confidence(combined_description)
        
        return ExtractedElement(
            element_type=ElementType.DESCRIPTION,
            content=combined_description,
            confidence=confidence,
            line_idx=0  # Première ligne du bloc
        )
    
    def _extract_skills(self, block: InformationBlock) -> Optional[ExtractedElement]:
        """Extrait les compétences techniques du bloc."""
        skills_found = []
        
        for line_idx, line in enumerate(block.lines):
            for pattern in self.skills_patterns:
                for match in pattern.finditer(line):
                    skill = match.group(0)
                    skills_found.append(skill)
        
        if not skills_found:
            return None
        
        # Dédupliquer et combiner
        unique_skills = list(set(skills_found))
        skills_text = ", ".join(unique_skills)
        
        return ExtractedElement(
            element_type=ElementType.SKILLS,
            content=skills_text,
            confidence=0.8,
            line_idx=0
        )
    
    def _calculate_title_confidence(self, title_text: str, block: InformationBlock) -> float:
        """Calcule la confiance pour un titre extrait."""
        confidence = 0.5  # Base
        
        title_lower = title_text.lower()
        
        # Bonus pour mots-clés professionnels
        professional_matches = sum(1 for kw in self.professional_keywords if kw in title_lower)
        confidence += min(0.3, professional_matches * 0.1)
        
        # Bonus pour longueur appropriée
        if 10 <= len(title_text) <= 50:
            confidence += 0.1
        
        # Malus pour contenu suspect
        if any(char.isdigit() for char in title_text[:5]):  # Commence par des chiffres
            confidence -= 0.2
        
        # Bonus pour contexte professionnel dans le bloc
        block_text = block.raw_text.lower()
        context_matches = sum(1 for kw in ["mission", "projet", "équipe", "client", "objectif"] if kw in block_text)
        confidence += min(0.2, context_matches * 0.05)
        
        return min(1.0, max(0.0, confidence))
    
    def _calculate_organization_confidence(self, org_text: str, block: InformationBlock) -> float:
        """Calcule la confiance pour une organisation extraite."""
        confidence = 0.4  # Base
        
        org_lower = org_text.lower()
        
        # Bonus pour suffixes juridiques
        if re.search(r'\b(?:sas|sarl|sa|inc|corp|ltd|llc|gmbh)\b', org_lower):
            confidence += 0.3
        
        # Bonus pour mots-clés business/éducatifs
        if re.search(r'\b(?:université|école|college|university|consulting|technologies|solutions|services)\b', org_lower):
            confidence += 0.2
        
        # Bonus pour noms propres avec majuscules
        if re.match(r'^[A-Z][a-zA-ZÀ-ÿ]+(?:\s+[A-Z][a-zA-ZÀ-ÿ]+)*', org_text):
            confidence += 0.1
        
        # Malus pour contenu suspect
        if org_text.isdigit() or len(org_text) < 3:
            confidence -= 0.3
        
        return min(1.0, max(0.0, confidence))
    
    def _calculate_date_confidence(self, date_text: str) -> float:
        """Calcule la confiance pour une date extraite."""
        confidence = 0.6  # Base pour les dates
        
        # Bonus pour formats complets
        if re.search(r'\b(?:janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)\s+\d{4}\b', date_text, re.IGNORECASE):
            confidence += 0.2
        
        # Bonus pour périodes
        if re.search(r'\d{4}\s*[-–—]\s*\d{4}', date_text):
            confidence += 0.2
        
        # Bonus pour expressions temporelles
        if re.search(r'\b(?:depuis|à\s+ce\s+jour|actuellement)\b', date_text, re.IGNORECASE):
            confidence += 0.1
        
        return min(1.0, confidence)
    
    def _calculate_description_confidence(self, description: str) -> float:
        """Calcule la confiance pour une description extraite."""
        confidence = 0.3  # Base faible
        
        # Bonus pour longueur appropriée
        word_count = len(description.split())
        if 5 <= word_count <= 100:
            confidence += 0.3
        elif word_count > 100:
            confidence += 0.2
        
        # Bonus pour verbes d'action
        action_verbs_found = sum(1 for verb in ACTION_VERBS_FR if verb in description.lower())
        confidence += min(0.3, action_verbs_found * 0.05)
        
        # Bonus pour structure avec puces
        if re.search(r'[•\-–*]', description):
            confidence += 0.1
        
        return min(1.0, confidence)
    
    def _line_looks_like_title_or_org(self, line: str) -> bool:
        """Vérifie si une ligne ressemble à un titre ou une organisation."""
        # Très courte et en majuscules
        if len(line) <= 30 and line.isupper():
            return True
        
        # Contient des patterns de titre
        for pattern in self.title_patterns:
            if pattern.search(line):
                return True
        
        # Contient des patterns d'organisation
        for pattern in self.organization_patterns:
            if pattern.search(line):
                return True
        
        return False
    
    def _extract_title_heuristic(self, block: InformationBlock) -> Optional[ExtractedElement]:
        """Extraction heuristique de titre quand les patterns échouent."""
        for line_idx, line in enumerate(block.lines):
            line_stripped = line.strip()
            
            # Chercher des lignes courtes avec des mots professionnels
            if 5 <= len(line_stripped) <= 50:
                word_matches = sum(1 for kw in self.professional_keywords if kw in line_stripped.lower())
                if word_matches >= 1:
                    return ExtractedElement(
                        element_type=ElementType.TITLE,
                        content=line_stripped,
                        confidence=0.4 + (word_matches * 0.1),
                        line_idx=line_idx
                    )
        
        return None
    
    def link_title_to_organization(self, title_element: ExtractedElement, 
                                 org_element: ExtractedElement, 
                                 block: InformationBlock) -> Tuple[str, str, float]:
        """
        Lie un titre à une organisation en calculant la pertinence du lien.
        
        Returns:
            Tuple (title, organization, link_confidence)
        """
        if not title_element or not org_element:
            return "", "", 0.0
        
        # Distance entre les éléments (plus proche = meilleur lien)
        line_distance = abs(title_element.line_idx - org_element.line_idx)
        distance_penalty = min(0.3, line_distance * 0.1)
        
        # Confiance combinée des éléments
        element_confidence = (title_element.confidence + org_element.confidence) / 2
        
        # Confiance contextuelle (cohérence sémantique)
        context_confidence = self._calculate_context_coherence(title_element.content, org_element.content, block)
        
        # Score final de liaison
        link_confidence = element_confidence + context_confidence - distance_penalty
        link_confidence = min(1.0, max(0.0, link_confidence))
        
        if link_confidence >= 0.3:
            self.extraction_stats["successful_links"] += 1
            self.logger.debug(f"ELEMENT_LINK: title='{validate_no_pii_leakage(title_element.content[:20], DEFAULT_PII_CONFIG.HASH_SALT)}' org='{validate_no_pii_leakage(org_element.content[:20], DEFAULT_PII_CONFIG.HASH_SALT)}' confidence={link_confidence:.3f}")
        
        return title_element.content, org_element.content, link_confidence
    
    def _calculate_context_coherence(self, title: str, organization: str, block: InformationBlock) -> float:
        """Calcule la cohérence contextuelle entre un titre et une organisation."""
        coherence = 0.0
        
        title_lower = title.lower()
        org_lower = organization.lower()
        
        # Cohérence éducative : professeur + université
        if "professeur" in title_lower or "enseignant" in title_lower:
            if any(edu_word in org_lower for edu_word in ["université", "école", "college", "institut"]):
                coherence += 0.3
        
        # Cohérence business : rôles tech + entreprises tech
        if any(tech_word in title_lower for tech_word in ["développeur", "engineer", "tech", "data"]):
            if any(biz_word in org_lower for biz_word in ["technologies", "solutions", "consulting", "corp"]):
                coherence += 0.2
        
        # Cohérence par mots-clés communs
        title_words = set(title_lower.split())
        org_words = set(org_lower.split())
        common_words = title_words.intersection(org_words)
        if common_words:
            coherence += min(0.2, len(common_words) * 0.05)
        
        return coherence
    
    def get_extraction_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques d'extraction."""
        return dict(self.extraction_stats)


# Instance globale
_element_extractor = None

def get_element_extractor() -> ElementExtractor:
    """Retourne l'instance singleton de ElementExtractor."""
    global _element_extractor
    if _element_extractor is None:
        _element_extractor = ElementExtractor()
    return _element_extractor


# Fonctions utilitaires
def extract_elements_from_block(block: InformationBlock) -> Dict[str, ExtractedElement]:
    """Extrait les éléments d'un bloc."""
    extractor = get_element_extractor()
    return extractor.extract_elements_from_block(block)