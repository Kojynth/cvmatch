"""
Intelligent Routing - Système de routage intelligent pour classification CV.

Implémente les règles prioritaires pour résoudre les conflits de classification:
- Stage vs Formation
- Projet vs Expérience  
- Certification vs Expérience
"""

import re
from typing import Dict, Any, Optional, List, Tuple
from enum import Enum
from dataclasses import dataclass

from ..logging.safe_logger import get_safe_logger
from ..config import DEFAULT_PII_CONFIG
from .feature_flags import get_extraction_fixes_flags

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


class ContentType(Enum):
    """Types de contenu CV identifiés."""
    EXPERIENCE = "experience"
    EDUCATION = "education"
    PROJECT = "project"
    CERTIFICATION = "certification"
    INTERNSHIP = "internship"  # Stage - sous-type d'expérience
    LANGUAGE = "language"
    SOFT_SKILL = "soft_skill"
    INTEREST = "interest"
    UNKNOWN = "unknown"


@dataclass
class RouteDecision:
    """Décision de routage avec justification."""
    target_type: ContentType
    confidence: float
    reason: str
    metadata: Dict[str, Any]


class IntelligentRouter:
    """Router intelligent avec règles prioritaires."""
    
    def __init__(self):
        self.logger = get_safe_logger(f"{__name__}.IntelligentRouter", cfg=DEFAULT_PII_CONFIG)
        self.flags = get_extraction_fixes_flags()
        
        # Patterns pour identification des stages/internships
        self.internship_patterns = [
            r'\b(stage|internship|stagiaire|intern)\b',
            r'\b(alternance|apprentissage|apprenti)\b',
            r'\b(contrat\s+pro|contrat\s+de\s+professionnalisation)\b'
        ]
        
        # Patterns pour diplomes explicites (priorite formation)
        self.degree_patterns = [
            r'\b(licence|bachelor|master|doctorat|phd)\b',
            r'\b(dut|but|bts|cap|bep|bac)\b',
            r'\b(diplome|degree|certification)\b',
            r'\b(ects|credits?\s+ects)\b',
            r'\b(memoire|pfe|projet\s+de\s+fin\s+d.*etudes)\b',
            r'\b(soutenance|defence|thesis)\b'
        ]
        
        # Patterns pour projets
        self.project_patterns = [
            r'\b(projet|project|poc|proof\s+of\s+concept)\b',
            r'\b(hackathon|hack\s+day|coding\s+challenge)\b',
            r'\b(memoire|pfe|projet\s+de\s+fin\s+d.*etudes)\b',
            r'\b(projet\s+academique|academic\s+project)\b',
            r'\b(side\s+project|personal\s+project)\b'
        ]
        
        # Patterns pour certifications langues
        self.lang_cert_patterns = [
            r'\b(toefl|toeic|ielts|delf|dalf|tcf)\b',
            r'\b(tofl|toelf|teofl)\b',  # Typos courantes
            r'\b(cambridge|cae|cpe|fce|ket|pet)\b',
            r'\b(dele|siele|ccse)\b',  # Espagnol
            r'\b(testdaf|goethe|telc)\b',  # Allemand
            r'\b(hsk|bcpt)\b',  # Chinois
            r'\b(jlpt|j-test)\b'  # Japonais
        ]
        
        # Verbes d'action professionnels (exclus des interets)
        self.action_verbs = [
            r'\b(dirige|developpe|concu|gere|livre|implemente)\b',
            r'\b(pilote|coordonne|encadre|forme|recrute)\b',
            r'\b(optimise|ameliore|cree|realise|lance)\b',
            r'\b(supervised|managed|developed|implemented|led)\b',
            r'\b(coordinated|designed|built|deployed|launched)\b'
        ]
    
    def is_internship_line(self, text: str) -> bool:
        """Détecte si une ligne concerne un stage/internship."""
        if not text:
            return False
        
        text_lower = text.lower()
        return any(re.search(pattern, text_lower, re.IGNORECASE) 
                  for pattern in self.internship_patterns)
    
    def has_explicit_degree(self, text: str) -> bool:
        """Détecte la présence d'un diplôme explicite."""
        if not text:
            return False
        
        text_lower = text.lower()
        return any(re.search(pattern, text_lower, re.IGNORECASE) 
                  for pattern in self.degree_patterns)
    
    def is_project_line(self, text: str) -> bool:
        """Détecte si une ligne concerne un projet."""
        if not text:
            return False
        
        text_lower = text.lower()
        return any(re.search(pattern, text_lower, re.IGNORECASE) 
                  for pattern in self.project_patterns)
    
    def is_language_certification(self, text: str) -> bool:
        """Détecte les certifications de langue."""
        if not text:
            return False
        
        text_lower = text.lower()
        return any(re.search(pattern, text_lower, re.IGNORECASE) 
                  for pattern in self.lang_cert_patterns)
    
    def has_professional_action_verbs(self, text: str) -> bool:
        """Détecte la présence de verbes d'action professionnels."""
        if not text:
            return False
        
        text_lower = text.lower()
        return any(re.search(pattern, text_lower, re.IGNORECASE) 
                  for pattern in self.action_verbs)
    
    def route_stage_vs_education(self, text: str, has_company: bool = False, 
                                has_school: bool = False) -> RouteDecision:
        """
        Route Stage vs Formation selon les règles prioritaires.
        
        Règle: Stage/internship → expériences, même avec nom d'école,
        SAUF si diplôme explicite détecté.
        """
        if not text:
            return RouteDecision(ContentType.UNKNOWN, 0.0, "empty_text", {})
        
        # Test prioritaire: est-ce un stage ?
        is_internship = self.is_internship_line(text)
        
        if is_internship:
            # Stage détecté - vérifier s'il y a diplôme explicite
            has_degree = self.has_explicit_degree(text)
            
            if has_degree:
                return RouteDecision(
                    ContentType.EDUCATION,
                    0.9,
                    "stage_with_explicit_degree",
                    {"has_internship": True, "has_degree": True, "has_school": has_school}
                )
            else:
                # Stage sans diplôme → expérience (même avec école)
                return RouteDecision(
                    ContentType.INTERNSHIP,  # Sous-type d'expérience
                    0.95,
                    "stage_priority_rule",
                    {"has_internship": True, "has_school": has_school, "has_company": has_company}
                )
        
        # Pas de stage - logique normale école/entreprise
        if has_school and not has_company:
            return RouteDecision(
                ContentType.EDUCATION,
                0.7,
                "school_only",
                {"has_school": True, "has_company": False}
            )
        elif has_company and not has_school:
            return RouteDecision(
                ContentType.EXPERIENCE,
                0.8,
                "company_only", 
                {"has_company": True, "has_school": False}
            )
        elif has_school and has_company:
            return RouteDecision(
                ContentType.EXPERIENCE,
                0.6,
                "mixed_company_priority",
                {"has_company": True, "has_school": True}
            )
        
        return RouteDecision(ContentType.UNKNOWN, 0.0, "no_indicators", {})
    
    def route_project_vs_experience(self, text: str, has_company: bool = False,
                                  has_dates: bool = False) -> RouteDecision:
        """
        Route Projet vs Expérience.
        
        Règle: projet|POC|hackathon + dates mais pas de société valide → projects
        """
        if not text:
            return RouteDecision(ContentType.UNKNOWN, 0.0, "empty_text", {})
        
        is_project = self.is_project_line(text)
        
        if is_project:
            if has_dates and not has_company:
                return RouteDecision(
                    ContentType.PROJECT,
                    0.9,
                    "project_with_dates_no_company",
                    {"is_project": True, "has_dates": has_dates, "has_company": has_company}
                )
            elif text.lower().startswith(("projet académique", "projet de fin", "pfe", "mémoire")):
                return RouteDecision(
                    ContentType.PROJECT,
                    0.95,
                    "academic_project_explicit",
                    {"is_project": True, "is_academic": True}
                )
            elif has_company:
                # Projet avec entreprise → peut-être expérience
                return RouteDecision(
                    ContentType.EXPERIENCE,
                    0.6,
                    "project_in_company_context",
                    {"is_project": True, "has_company": has_company}
                )
        
        # Logique normale expérience
        if has_company:
            return RouteDecision(
                ContentType.EXPERIENCE,
                0.8,
                "company_experience",
                {"has_company": has_company}
            )
        
        return RouteDecision(ContentType.UNKNOWN, 0.3, "insufficient_indicators", {})
    
    def route_certification_vs_experience(self, text: str) -> RouteDecision:
        """
        Route Certification vs Expérience.
        
        Règle: TOEFL/IELTS/etc → certifications (jamais expériences)
        """
        if not text:
            return RouteDecision(ContentType.UNKNOWN, 0.0, "empty_text", {})
        
        if self.is_language_certification(text):
            return RouteDecision(
                ContentType.CERTIFICATION,
                0.98,
                "language_certification_detected",
                {"cert_type": "language"}
            )
        
        return RouteDecision(ContentType.UNKNOWN, 0.0, "not_certification", {})
    
    def can_reclass_to_interest(self, text: str, has_dates: bool = False,
                               has_company: bool = False, has_role: bool = False) -> bool:
        """
        Détermine si un élément peut être reclassé en centre d'intérêt.
        
        Anti-fantômes: empêche la création d'intérêts artificiels.
        """
        if has_dates or has_company or has_role:
            return False
        
        if self.has_professional_action_verbs(text):
            return False
        
        return True
    
    def route_content(self, text: str, metadata: Dict[str, Any] = None) -> RouteDecision:
        """
        Route le contenu selon toutes les règles prioritaires.
        
        Args:
            text: Texte à classifier
            metadata: Métadonnées (has_company, has_school, has_dates, etc.)
        """
        if not text:
            return RouteDecision(ContentType.UNKNOWN, 0.0, "empty_text", {})
        
        meta = metadata or {}
        has_company = meta.get('has_company', False)
        has_school = meta.get('has_school', False) 
        has_dates = meta.get('has_dates', False)
        has_role = meta.get('has_role', False)
        
        # 1. Test certifications en premier (priorité absolue)
        cert_decision = self.route_certification_vs_experience(text)
        if cert_decision.target_type == ContentType.CERTIFICATION:
            return cert_decision
        
        # 2. Test stages vs formation
        stage_decision = self.route_stage_vs_education(text, has_company, has_school)
        if stage_decision.target_type in [ContentType.INTERNSHIP, ContentType.EDUCATION]:
            return stage_decision
        
        # 3. Test projets vs expériences
        project_decision = self.route_project_vs_experience(text, has_company, has_dates)
        if project_decision.target_type == ContentType.PROJECT:
            return project_decision
        
        # 4. Logique expérience par défaut
        if has_company or has_role:
            return RouteDecision(
                ContentType.EXPERIENCE,
                0.7,
                "default_experience",
                meta
            )
        
        # 5. Peut-être un intérêt ?
        if self.can_reclass_to_interest(text, has_dates, has_company, has_role):
            return RouteDecision(
                ContentType.INTEREST,
                0.4,
                "potential_interest",
                meta
            )
        
        return RouteDecision(ContentType.UNKNOWN, 0.2, "no_clear_classification", meta)


# Instance globale
_intelligent_router = None


def get_intelligent_router() -> IntelligentRouter:
    """Obtient l'instance globale du router intelligent."""
    global _intelligent_router
    if _intelligent_router is None:
        _intelligent_router = IntelligentRouter()
    return _intelligent_router


# Fonctions de convenance
def route_stage_vs_formation(text: str, has_company: bool = False, has_school: bool = False) -> str:
    """Route Stage vs Formation - retourne le type cible."""
    router = get_intelligent_router()
    decision = router.route_stage_vs_education(text, has_company, has_school)
    
    if decision.target_type == ContentType.INTERNSHIP:
        return "experiences"  # Stage → expérience
    elif decision.target_type == ContentType.EDUCATION:
        return "education"
    else:
        return "experiences"  # Par défaut


def is_language_certification_line(text: str) -> bool:
    """Détecte les certifications de langue."""
    router = get_intelligent_router()
    return router.is_language_certification(text)


def should_route_to_projects(text: str, has_company: bool = False, has_dates: bool = False) -> bool:
    """Détermine si le contenu doit aller en projets."""
    router = get_intelligent_router()
    decision = router.route_project_vs_experience(text, has_company, has_dates)
    return decision.target_type == ContentType.PROJECT


if __name__ == "__main__":
    # Tests du router intelligent
    router = IntelligentRouter()
    
    test_cases = [
        # Stage vs Formation
        ("Stage chez ACME (École Centrale)", {"has_company": True, "has_school": True}),
        ("Stage développeur web", {"has_company": False, "has_school": False}),
        ("Master en informatique", {"has_company": False, "has_school": True}),
        ("Licence stage obligatoire ECTS", {"has_company": False, "has_school": True}),
        
        # Projets
        ("Projet de fin d'études - 2023", {"has_dates": True, "has_company": False}),
        ("Hackathon blockchain", {"has_dates": False, "has_company": False}),
        ("Développement app mobile chez Google", {"has_company": True, "has_dates": True}),
        
        # Certifications
        ("TOEFL B2 - Janvier 2023", {}),
        ("TOFL niveau intermédiaire", {}),
        ("IELTS Academic 7.5", {}),
    ]
    
    print("Test du router intelligent")
    print("=" * 50)
    
    for text, metadata in test_cases:
        decision = router.route_content(text, metadata)
        print(f"Texte: '{text}'")
        print(f"  -> {decision.target_type.value} (conf: {decision.confidence:.2f})")
        print(f"  Raison: {decision.reason}")
        print()