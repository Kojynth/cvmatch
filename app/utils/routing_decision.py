"""
Routing Decision Engine pour internships et corrections
======================================================

Gère les décisions de routing avec source_signals, ai_score, et override_reason.
Corrige particulièrement le routing internships école → EXPERIENCE.
"""

import re
from typing import Dict, Any, List, Optional, Set, Tuple
from dataclasses import dataclass
from enum import Enum
from ..logging.safe_logger import get_safe_logger
from ..config import DEFAULT_PII_CONFIG

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)

class SignalType(Enum):
    """Types de signaux pour structured validation"""
    DATE = "date"
    TITLE = "title" 
    ORG = "org"
    KEYWORD = "keyword"
    DURATION = "duration"
    DESCRIPTION = "description"

@dataclass
class RoutingDecision:
    """Décision de routing avec provenance et overrides"""
    final_section: str
    ai_score: float
    source_signals: Dict[SignalType, bool]
    override_reason: Optional[str] = None
    confidence: float = 0.0
    structured_signals_count: int = 0
    employment_keywords_found: List[str] = None
    school_org_detected: bool = False
    original_section: Optional[str] = None
    
    def __post_init__(self):
        if self.employment_keywords_found is None:
            self.employment_keywords_found = []
        self.structured_signals_count = sum(1 for signal in [SignalType.DATE, SignalType.TITLE, SignalType.ORG] 
                                          if self.source_signals.get(signal, False))

# Employment keywords étendus avec patterns d'internship
EMPLOYMENT_KEYWORDS_EXTENDED = {
    # Internship patterns - route vers EXPERIENCE par défaut
    "stagiaire", "stage", "alternance", "apprentissage", "apprenti",
    "intern", "internship", "trainee", "work-study",
    
    # Standard employment
    "CDI", "CDD", "freelance", "contractuel", "intérim", "consultant",
    "développeur", "developer", "ingénieur", "engineer", 
    "manager", "chef", "lead", "senior", "junior",
    "analyste", "analyst", "architecte", "architect"
}

# School organization patterns
SCHOOL_ORG_PATTERNS = {
    # French
    "école", "université", "institut", "lycée", "IUT", "BTS",
    "ENSAM", "INSA", "Polytech", "Supélec", "Centrale",
    
    # English  
    "school", "university", "college", "institute", "academy",
    "MIT", "Stanford", "Harvard", "Berkeley",
    
    # Generic academic
    "campus", "faculté", "department", "lab", "laboratory"
}

class InternshipRouter:
    """Router spécialisé pour les internships école → EXPERIENCE"""
    
    def __init__(self):
        self.employment_keywords = EMPLOYMENT_KEYWORDS_EXTENDED
        self.school_patterns = SCHOOL_ORG_PATTERNS
    
    def route_internship(self, text: str, title: str = "", ai_score: float = 0.0,
                        original_section: str = "experience") -> RoutingDecision:
        """
        Route internship vers EXPERIENCE par défaut, démote vers EDUCATION seulement si ALL conditions:
        - no employment keyword AND
        - no detectable date interval AND  
        - description length ≤ 1 ligne AND
        - org matches school lexicon
        """
        
        full_text = (text + " " + title).lower()
        source_signals = self._analyze_signals(full_text)
        
        # Step 1: Check employment keywords (should route to EXPERIENCE)
        employment_keywords_found = []
        for keyword in self.employment_keywords:
            if keyword.lower() in full_text:
                employment_keywords_found.append(keyword)
        
        has_employment_keyword = len(employment_keywords_found) > 0
        
        # Step 2: Check date interval
        has_date_interval = source_signals.get(SignalType.DATE, False)
        
        # Step 3: Check description length
        text_lines = text.strip().split('\n')
        non_empty_lines = [line for line in text_lines if line.strip()]
        description_short = len(non_empty_lines) <= 1
        
        # Step 4: Check school organization
        school_org_detected = False
        for pattern in self.school_patterns:
            if pattern.lower() in full_text:
                school_org_detected = True
                break
        
        # ROUTING LOGIC: Default to EXPERIENCE, demote only if ALL conditions met
        if (not has_employment_keyword and 
            not has_date_interval and 
            description_short and 
            school_org_detected):
            
            # Demote to EDUCATION
            final_section = "education"
            override_reason = f"internship_demoted_to_education: no_emp_keyword={not has_employment_keyword}, no_date={not has_date_interval}, short_desc={description_short}, school_org={school_org_detected}"
            logger.info(f"INTERNSHIP_DEMOTED: {override_reason}")
            
        else:
            # Keep as EXPERIENCE (default route)
            final_section = "experience"
            override_reason = f"internship_routed_to_experience: emp_keywords={employment_keywords_found}, has_date={has_date_interval}, desc_lines={len(non_empty_lines)}, school_org={school_org_detected}"
            logger.info(f"INTERNSHIP_ROUTED: {override_reason}")
        
        return RoutingDecision(
            final_section=final_section,
            ai_score=ai_score,
            source_signals=source_signals,
            override_reason=override_reason,
            confidence=0.8,  # High confidence for internship routing
            structured_signals_count=sum(1 for s in [SignalType.DATE, SignalType.TITLE, SignalType.ORG] 
                                       if source_signals.get(s, False)),
            employment_keywords_found=employment_keywords_found,
            school_org_detected=school_org_detected,
            original_section=original_section
        )
    
    def _analyze_signals(self, text: str) -> Dict[SignalType, bool]:
        """Analyse les signaux structurels dans le texte"""
        signals = {}
        
        # DATE signal
        date_patterns = [
            r'\d{4}\s*[-–—]\s*\d{4}',
            r'\d{4}\s*[-–—]\s*(?:présent|present|actuel|ongoing)',
            r'(?:janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)\s+\d{4}',
            r'(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{4}',
            r'\d{1,2}/\d{4}\s*[-–—]\s*\d{1,2}/\d{4}',
            r'\d+\s*(?:mois|months|ans|years)'  # Duration indicators
        ]
        
        signals[SignalType.DATE] = any(re.search(pattern, text, re.IGNORECASE) 
                                     for pattern in date_patterns)
        
        # TITLE signal (job titles, roles)
        title_patterns = [
            r'\b(?:développeur|developer|ingénieur|engineer|consultant|analyst|architect)\b',
            r'\b(?:manager|chef|lead|senior|junior|assistant|coordinator)\b',
            r'\b(?:stagiaire|intern|trainee|apprenti|alternant)\b'
        ]
        
        signals[SignalType.TITLE] = any(re.search(pattern, text, re.IGNORECASE) 
                                      for pattern in title_patterns)
        
        # ORG signal (company/organization names)
        org_patterns = [
            r'\b(?:chez|at|@)\s+[A-Z][a-zA-Z]+',  # "chez TechCorp"
            r'\b[A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*)*\s+(?:SA|SAS|SARL|Inc|Ltd|Corp|GmbH)\b',  # Company suffixes
            r'\b(?:société|entreprise|company|corporation|startup|cabinet|groupe)\s+[A-Z]'
        ]
        
        signals[SignalType.ORG] = any(re.search(pattern, text) 
                                    for pattern in org_patterns)
        
        # KEYWORD signal (employment keywords)
        signals[SignalType.KEYWORD] = any(keyword.lower() in text.lower() 
                                        for keyword in self.employment_keywords)
        
        # DURATION signal 
        duration_patterns = [
            r'\d+\s*(?:mois|months|semaines|weeks|ans|years)',
            r'(?:pendant|during|for)\s+\d+',
            r'\d+\s*(?:h|heures|hours)\s*(?:par|per)\s*(?:semaine|week)'
        ]
        
        signals[SignalType.DURATION] = any(re.search(pattern, text, re.IGNORECASE)
                                         for pattern in duration_patterns)
        
        # DESCRIPTION signal (substantial content)
        text_lines = [line.strip() for line in text.split('\n') if line.strip()]
        signals[SignalType.DESCRIPTION] = len(text_lines) > 1 or (len(text_lines) == 1 and len(text_lines[0]) > 80)
        
        return signals


class HeuristicOverrideEngine:
    """Engine pour les overrides heuristiques quand ML est low"""
    
    def __init__(self, ml_gate_soft: float = 0.40, ml_gate_min: float = 0.50):
        self.ml_gate_soft = ml_gate_soft
        self.ml_gate_min = ml_gate_min
        self.internship_router = InternshipRouter()
    
    def should_override(self, section_type: str, text: str, title: str, 
                       ai_score: float) -> Optional[RoutingDecision]:
        """
        Détermine s'il faut override la décision ML basée sur les heuristiques
        
        Returns:
            RoutingDecision if override needed, None otherwise
        """
        
        full_text = (text + " " + title).lower()
        
        # EXPERIENCE overrides
        if section_type in ["experience", "experiences"]:
            return self._check_experience_override(full_text, ai_score, section_type)
        
        # PROJECTS overrides  
        elif section_type in ["project", "projects"]:
            return self._check_project_override(full_text, ai_score, section_type)
        
        # INTERNSHIP routing (special case)
        elif self._is_internship_content(full_text):
            return self.internship_router.route_internship(text, title, ai_score, section_type)
        
        return None
    
    def _check_experience_override(self, text: str, ai_score: float, 
                                 original_section: str) -> Optional[RoutingDecision]:
        """Override EXPERIENCE si 2/3 structured signals OU employment keyword"""
        
        router = InternshipRouter()
        signals = router._analyze_signals(text)
        
        # Count structured signals (date, title, org)
        structured_count = sum(1 for signal in [SignalType.DATE, SignalType.TITLE, SignalType.ORG]
                             if signals.get(signal, False))
        
        has_employment_keyword = signals.get(SignalType.KEYWORD, False)
        
        # Override conditions
        should_override = (
            (structured_count >= 2) or  # 2/3 structured signals
            has_employment_keyword      # OR employment keyword
        )
        
        if should_override and ai_score < self.ml_gate_min:
            override_reason = f"exp_strong_structure: structured_signals={structured_count}/3, employment_keyword={has_employment_keyword}, ai_score={ai_score:.3f} < {self.ml_gate_min}"
            
            logger.info(f"EXPERIENCE_OVERRIDE: {override_reason}")
            
            return RoutingDecision(
                final_section="experience",
                ai_score=ai_score,
                source_signals=signals,
                override_reason=override_reason,
                confidence=0.75,
                structured_signals_count=structured_count,
                original_section=original_section
            )
        
        return None
    
    def _check_project_override(self, text: str, ai_score: float,
                               original_section: str) -> Optional[RoutingDecision]:
        """Override PROJECTS: accepter si title=True AND (bullets=True OR description≥80 chars), URL optionnel"""
        
        router = InternshipRouter()  
        signals = router._analyze_signals(text)
        
        # Check for project title
        title_patterns = [
            r'\b(?:projet|project|réalisation|development|app|application|site|website|système)\b',
            r'\b[A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*)*\s*[:]\s*',  # "Project Name: description"
            r'^\s*[\-\*\+]\s*[A-Z]'  # Bullet point with capitalized content
        ]
        
        has_title = any(re.search(pattern, text, re.IGNORECASE) for pattern in title_patterns)
        
        # Check for bullets
        bullet_patterns = [
            r'^\s*[\-\*\+•]\s+',
            r'^\s*\d+[\.\)]\s+',
            r'[\-\*\+•]\s+\w+'
        ]
        
        has_bullets = any(re.search(pattern, text, re.MULTILINE) for pattern in bullet_patterns)
        
        # Check description length  
        clean_text = re.sub(r'^\s*[\-\*\+•]\s*', '', text, flags=re.MULTILINE)
        has_long_description = len(clean_text.strip()) >= 80
        
        # URL is optional - don't block on missing URL
        
        should_override = has_title and (has_bullets or has_long_description)
        
        if should_override and ai_score < self.ml_gate_min:
            override_reason = f"project_structure_valid: title={has_title}, bullets={has_bullets}, long_desc={has_long_description}, ai_score={ai_score:.3f} < {self.ml_gate_min}"
            
            logger.info(f"PROJECT_OVERRIDE: {override_reason}")
            
            return RoutingDecision(
                final_section="projects", 
                ai_score=ai_score,
                source_signals=signals,
                override_reason=override_reason,
                confidence=0.70,
                original_section=original_section
            )
        
        return None
    
    def _is_internship_content(self, text: str) -> bool:
        """Détecte si le contenu semble être un internship/stage"""
        
        internship_indicators = [
            "stage", "stagiaire", "alternance", "apprentissage", "apprenti",
            "intern", "internship", "trainee", "work-study"
        ]
        
        return any(indicator in text.lower() for indicator in internship_indicators)


# Factory functions
def create_routing_decision(text: str, title: str = "", ai_score: float = 0.0,
                          section_type: str = "experience", 
                          ml_gate_soft: float = 0.40, 
                          ml_gate_min: float = 0.50) -> RoutingDecision:
    """
    Factory function pour créer une décision de routing
    
    Returns:
        RoutingDecision with overrides applied if needed
    """
    override_engine = HeuristicOverrideEngine(ml_gate_soft, ml_gate_min)
    
    # Check for heuristic overrides
    override_decision = override_engine.should_override(section_type, text, title, ai_score)
    
    if override_decision:
        return override_decision
    
    # No override needed, return standard decision
    router = InternshipRouter()
    signals = router._analyze_signals(text + " " + title)
    
    return RoutingDecision(
        final_section=section_type,
        ai_score=ai_score,
        source_signals=signals,
        confidence=min(ai_score, 1.0),
        original_section=section_type
    )
