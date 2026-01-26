"""
SectionWindow utility avec stop-conditions pour EDUCATION
========================================================

Implémente des fenêtres de sections avec bornage header → next header
et des conditions d'arrêt spécialisées pour éviter l'over-absorption.
"""

import re
from typing import List, Tuple, Optional, Set
from dataclasses import dataclass
from ..logging.safe_logger import get_safe_logger
from ..config import DEFAULT_PII_CONFIG

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)

@dataclass
class StopCondition:
    """Condition d'arrêt pour une fenêtre de section"""
    name: str
    pattern: Optional[str] = None
    keywords: Optional[List[str]] = None
    max_lines_without_signals: Optional[int] = None
    required_signals: Optional[List[str]] = None

# Stop conditions pour EDUCATION
EDUCATION_STOP_CONDITIONS = [
    StopCondition(
        name="employment_keyword",
        keywords=[
            "stagiaire", "stage", "alternance", "apprentissage", 
            "CDI", "CDD", "mission", "projet pro", "consultant",
            "développeur", "ingénieur", "manager", "chef", "lead"
        ]
    ),
    StopCondition(
        name="no_education_signals",
        max_lines_without_signals=15,
        required_signals=["degree", "school", "date"]
    )
]

# Employment keywords pour détection rapide
EMPLOYMENT_KEYWORDS = {
    "stagiaire", "stage", "alternance", "apprentissage", 
    "CDI", "CDD", "mission", "projet pro", "consultant",
    "développeur", "developer", "ingénieur", "engineer",
    "manager", "chef", "lead", "senior", "junior",
    "freelance", "contractuel", "interim"
}

# School keywords pour validation éducation
SCHOOL_KEYWORDS = {
    "école", "université", "institut", "lycée", "collège",
    "IUT", "BTS", "master", "licence", "doctorat", 
    "school", "university", "college", "institute"
}

# Degree keywords
DEGREE_KEYWORDS = {
    "diplôme", "bac", "licence", "master", "doctorat", "PhD",
    "degree", "bachelor", "MBA", "certification", "titre"
}

class SectionWindow:
    """Gestionnaire de fenêtres de sections avec stop-conditions"""
    
    def __init__(self):
        self.stop_conditions = {
            'education': EDUCATION_STOP_CONDITIONS
        }
    
    def create_window(self, lines: List[str], start: int, end: int, 
                     section_type: str) -> Tuple[int, int]:
        """
        Crée une fenêtre optimisée avec stop-conditions
        
        Args:
            lines: Lignes du document
            start: Index de début
            end: Index de fin initial  
            section_type: Type de section (education, experience, etc.)
            
        Returns:
            Tuple (new_start, new_end) avec bornage optimisé
        """
        if section_type not in self.stop_conditions:
            return start, end
            
        stop_conditions = self.stop_conditions[section_type]
        new_end = end
        
        for condition in stop_conditions:
            condition_end = self._apply_stop_condition(
                lines, start, new_end, condition
            )
            if condition_end is not None and condition_end < new_end:
                new_end = condition_end
                logger.debug(f"STOP_CONDITION: {condition.name} triggered at line {condition_end}")
        
        return start, max(start + 1, new_end)  # Ensure minimum window size
    
    def _apply_stop_condition(self, lines: List[str], start: int, end: int,
                             condition: StopCondition) -> Optional[int]:
        """Applique une condition d'arrêt spécifique"""
        
        if condition.name == "employment_keyword":
            return self._find_employment_keyword_stop(lines, start, end, condition.keywords)
        
        elif condition.name == "no_education_signals":
            return self._find_education_signal_stop(
                lines, start, end, 
                condition.max_lines_without_signals,
                condition.required_signals
            )
        
        return None
    
    def _find_employment_keyword_stop(self, lines: List[str], start: int, 
                                    end: int, keywords: List[str]) -> Optional[int]:
        """Trouve le point d'arrêt basé sur les keywords d'emploi"""
        
        for i in range(start, min(end, len(lines))):
            line = lines[i].lower().strip()
            if not line:
                continue
                
            # Check if line contains employment keywords
            for keyword in keywords:
                if keyword.lower() in line:
                    # Verify it's a strong employment signal, not just mention
                    if self._is_strong_employment_signal(line, keyword):
                        logger.debug(f"EMPLOYMENT_STOP: found '{keyword}' at line {i}")
                        return i
        
        return None
    
    def _find_education_signal_stop(self, lines: List[str], start: int, end: int,
                                  max_lines: int, required_signals: List[str]) -> Optional[int]:
        """
        Trouve le point d'arrêt basé sur l'absence de signaux éducation
        Cap à max_lines si pas de (degree OR school OR date) sur 3 lignes consécutives
        """
        
        consecutive_check_size = 3
        lines_checked = 0
        
        for i in range(start, min(end, len(lines))):
            lines_checked += 1
            
            # Check every 3 consecutive lines
            if lines_checked >= consecutive_check_size:
                window_start = max(start, i - consecutive_check_size + 1)
                window_lines = lines[window_start:i + 1]
                
                has_signals = self._has_education_signals(window_lines, required_signals)
                
                if not has_signals and lines_checked >= max_lines:
                    logger.debug(f"EDUCATION_SIGNAL_STOP: no signals in {consecutive_check_size} lines, "
                               f"stopping at line {i} after {lines_checked} lines")
                    return i
                
                if has_signals:
                    # Reset counter if we found signals
                    lines_checked = 0
        
        return None
    
    def _is_strong_employment_signal(self, line: str, keyword: str) -> bool:
        """Vérifie si c'est un signal d'emploi fort, pas juste une mention"""
        
        line_lower = line.lower()
        
        # Strong patterns indicating employment
        employment_patterns = [
            r'\b' + re.escape(keyword.lower()) + r'\s+(?:chez|at|@)\s+\w+',  # "stage chez TechCorp"
            r'\b' + re.escape(keyword.lower()) + r'\s+\w+',  # "stage développeur"
            r'\b' + re.escape(keyword.lower()) + r'.*\d+\s*(?:mois|months|ans|years)',  # "stage 6 mois"
            r'\d{4}\s*[-–—]\s*(?:\d{4}|présent|actuel|present).*' + re.escape(keyword.lower()),  # dates with keyword
        ]
        
        for pattern in employment_patterns:
            if re.search(pattern, line_lower):
                return True
        
        # Also check if line has employment context indicators
        employment_indicators = [
            "responsabilités", "missions", "tâches", "équipe", "projet",
            "développement", "gestion", "coordination", "encadrement"
        ]
        
        if any(indicator in line_lower for indicator in employment_indicators):
            return True
        
        return False
    
    def _has_education_signals(self, window_lines: List[str], 
                             required_signals: List[str]) -> bool:
        """Vérifie la présence de signaux éducation dans une fenêtre"""
        
        window_text = " ".join(window_lines).lower()
        signals_found = set()
        
        # Check for degree signals
        if "degree" in required_signals:
            if any(keyword in window_text for keyword in DEGREE_KEYWORDS):
                signals_found.add("degree")
        
        # Check for school signals  
        if "school" in required_signals:
            if any(keyword in window_text for keyword in SCHOOL_KEYWORDS):
                signals_found.add("school")
        
        # Check for date signals
        if "date" in required_signals:
            date_patterns = [
                r'\d{4}\s*[-–—]\s*\d{4}',
                r'\d{4}\s*[-–—]\s*(?:présent|present|actuel)',
                r'(?:janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)\s+\d{4}',
                r'(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{4}'
            ]
            
            for pattern in date_patterns:
                if re.search(pattern, window_text, re.IGNORECASE):
                    signals_found.add("date")
                    break
        
        # Return True if ANY of the required signals is found (OR logic)
        return len(signals_found) > 0


def detect_section_headers(lines: List[str]) -> List[Tuple[int, str]]:
    """
    Détecte les headers de sections dans les lignes
    
    Returns:
        List[(line_index, section_type)]
    """
    headers = []
    
    header_patterns = {
        'education': [
            r'\b(?:FORMATIONS?|ÉDUCATIONS?|EDUCATION|STUDIES)\b',
            r'\b(?:DIPLÔMES?|SCOLARITÉ|ACADEMIC)\b'
        ],
        'experience': [
            r'\b(?:EXPÉRIENCES?|EXPERIENCE[S]?|WORK\s+EXPERIENCE)\b',
            r'\b(?:EMPLOIS?|CARRIÈRE|CAREER|PROFESSIONAL)\b'
        ],
        'skills': [
            r'\b(?:COMPÉTENCES?|SKILLS?|APTITUDES?)\b'
        ],
        'projects': [
            r'\b(?:PROJETS?|PROJECTS?|RÉALISATIONS?)\b'
        ]
    }
    
    for i, line in enumerate(lines):
        line_upper = line.upper().strip()
        
        # Skip empty or very short lines
        if len(line_upper) < 3:
            continue
            
        # Check if it looks like a header
        is_header_format = (
            line_upper.isupper() or
            line.strip().endswith(':') or
            re.match(r'^[A-ZÀÂÄÉÈÊËÏÎÔÖÙÛÜŸÇ\s]+[:\-=]{1,3}$', line_upper)
        )
        
        if is_header_format:
            for section_type, patterns in header_patterns.items():
                for pattern in patterns:
                    if re.search(pattern, line_upper, re.IGNORECASE):
                        headers.append((i, section_type))
                        logger.debug(f"HEADER_DETECT: line={i} section={section_type} text='{line.strip()[:50]}'")
                        break
                if headers and headers[-1][0] == i:  # Already found for this line
                    break
    
    return headers


def find_next_header(current_line: int, headers: List[Tuple[int, str]]) -> Optional[int]:
    """Trouve le prochain header après la ligne courante"""
    
    next_headers = [line_idx for line_idx, _ in headers if line_idx > current_line]
    return min(next_headers) if next_headers else None


# Factory function for easy usage
def create_section_window_with_conditions(lines: List[str], start: int, end: int, 
                                        section_type: str) -> Tuple[int, int]:
    """
    Factory function pour créer une fenêtre avec conditions d'arrêt
    
    Returns:
        Tuple (optimized_start, optimized_end)
    """
    window_manager = SectionWindow()
    return window_manager.create_window(lines, start, end, section_type)
