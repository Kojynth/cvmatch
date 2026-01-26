"""
Fuzzy Certification Matcher avec Levenshtein distance ≤ 2
=========================================================

Corrige les typos courantes dans les certifications (TOEFL/TOEIC/IELTS/DELF/DALF)
et route les patterns single-line ou two-line vers CERTIFICATIONS.
"""

import re
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass
from ..logging.safe_logger import get_safe_logger
from ..config import DEFAULT_PII_CONFIG

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)

def levenshtein_distance(s1: str, s2: str) -> int:
    """Calcul optimisé de la distance de Levenshtein"""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    
    if len(s2) == 0:
        return len(s1)
    
    previous_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    
    return previous_row[-1]

@dataclass
class CertificationMatch:
    """Résultat d'un match de certification"""
    original_name: str
    matched_name: str
    canonical_name: str
    distance: int
    level: Optional[str] = None
    date: Optional[str] = None
    confidence: float = 0.0
    line_text: str = ""

# Dictionnaire des certifications avec aliases et typos courants
CERTIFICATION_REGISTRY = {
    # TOEFL variants
    "TOEFL": {
        "canonical": "TOEFL",
        "aliases": ["TOEFL", "TOFL", "TOFLE", "TOEFL IBT", "TOEFL ITP", "TEOFL", "TOFFL"],
        "full_name": "Test of English as a Foreign Language",
        "category": "english"
    },
    
    # TOEIC variants  
    "TOEIC": {
        "canonical": "TOEIC",
        "aliases": ["TOEIC", "TOIC", "TOEIC L&R", "TOEIC S&W", "TOEIC BRIDGE", "TOIEC"],
        "full_name": "Test of English for International Communication",
        "category": "english"
    },
    
    # IELTS variants
    "IELTS": {
        "canonical": "IELTS", 
        "aliases": ["IELTS", "ILETS", "IELTS Academic", "IELTS General", "IELTS GT", "ILETLS"],
        "full_name": "International English Language Testing System",
        "category": "english"
    },
    
    # DELF variants
    "DELF": {
        "canonical": "DELF",
        "aliases": ["DELF", "DELP", "DELF A1", "DELF A2", "DELF B1", "DELF B2"],
        "full_name": "Diplôme d'Études en Langue Française", 
        "category": "french"
    },
    
    # DALF variants
    "DALF": {
        "canonical": "DALF",
        "aliases": ["DALF", "DALP", "DALF C1", "DALF C2"],
        "full_name": "Diplôme Approfondi de Langue Française",
        "category": "french"
    },
    
    # Additional certifications
    "Cambridge": {
        "canonical": "Cambridge English",
        "aliases": ["Cambridge", "CAE", "CPE", "FCE", "PET", "KET", "Cambridge English"],
        "full_name": "Cambridge English Qualifications",
        "category": "english"
    },
    
    "BULATS": {
        "canonical": "BULATS",
        "aliases": ["BULATS", "Business Language Testing Service"],
        "full_name": "Business Language Testing Service",
        "category": "english"
    }
}

# CEFR levels for validation
CEFR_LEVELS = {"A1", "A2", "B1", "B2", "C1", "C2"}

class FuzzyCertMatcher:
    """Matcher avec distance de Levenshtein pour certifications"""
    
    def __init__(self, max_distance: int = 2):
        self.max_distance = max_distance
        self.registry = CERTIFICATION_REGISTRY
        self._build_lookup_table()
    
    def _build_lookup_table(self):
        """Construit une table de lookup optimisée"""
        self.lookup_table = {}
        
        for canonical, cert_info in self.registry.items():
            for alias in cert_info["aliases"]:
                self.lookup_table[alias.upper()] = {
                    "canonical": canonical,
                    "category": cert_info["category"],
                    "full_name": cert_info["full_name"]
                }
    
    def find_certification_matches(self, text: str) -> List[CertificationMatch]:
        """
        Trouve toutes les certifications dans le texte avec fuzzy matching
        
        Args:
            text: Texte à analyser
            
        Returns:
            Liste des matches trouvés
        """
        matches = []
        lines = text.split('\n')
        
        for line_idx, line in enumerate(lines):
            line_matches = self._match_line(line.strip(), line_idx)
            matches.extend(line_matches)
        
        return self._deduplicate_matches(matches)
    
    def _match_line(self, line: str, line_idx: int) -> List[CertificationMatch]:
        """Match les certifications dans une ligne"""
        matches = []
        
        # Patterns pour extraire certifications avec contexte
        cert_patterns = [
            # "TOEFL 550" ou "TOEFL: 550 points"
            r'\b([A-Z]{3,7})(?:\s*[:]\s*)?(\d{2,4})\s*(?:points?|pts?)?\b',
            
            # "TOEFL niveau B2" ou "TOEFL level B2" 
            r'\b([A-Z]{3,7})\s+(?:niveau|level|score)\s*[:]\s*([A-C][12]|\d{2,4})\b',
            
            # "Obtention TOEFL en mars 2023"
            r'(?:obtention|obtained?|passed?)\s+([A-Z]{3,7})(?:\s+en|\s+in)?\s*([A-Za-z]+\s+\d{4})',
            
            # "TOEFL (2023)" ou "TOEFL - mars 2023"
            r'\b([A-Z]{3,7})\s*[\(\-]\s*([A-Za-z]*\s*\d{4})\s*[\)]?',
            
            # Simple "TOEFL B2" ou "TOEFL 850"
            r'\b([A-Z]{3,7})\s+([A-C][12]|\d{2,4})\b',
            
            # Standalone certification name
            r'\b([A-Z]{3,7})\b'
        ]
        
        for pattern in cert_patterns:
            for match in re.finditer(pattern, line, re.IGNORECASE):
                cert_candidate = match.group(1).upper()
                
                # Try exact match first
                if cert_candidate in self.lookup_table:
                    cert_match = self._create_match_from_regex(
                        match, cert_candidate, line, line_idx, distance=0
                    )
                    matches.append(cert_match)
                    continue
                
                # Try fuzzy matching
                best_match = self._find_best_fuzzy_match(cert_candidate)
                if best_match:
                    cert_match = self._create_match_from_regex(
                        match, cert_candidate, line, line_idx, 
                        distance=best_match["distance"],
                        canonical=best_match["canonical"]
                    )
                    matches.append(cert_match)
        
        return matches
    
    def _find_best_fuzzy_match(self, candidate: str) -> Optional[Dict]:
        """Trouve le meilleur match fuzzy pour un candidat"""
        best_match = None
        best_distance = float('inf')
        
        for registered_alias, info in self.lookup_table.items():
            distance = levenshtein_distance(candidate, registered_alias)
            
            if distance <= self.max_distance and distance < best_distance:
                best_distance = distance
                best_match = {
                    "canonical": info["canonical"],
                    "category": info["category"],
                    "distance": distance,
                    "matched_alias": registered_alias
                }
        
        return best_match
    
    def _create_match_from_regex(self, regex_match, original: str, line: str, 
                               line_idx: int, distance: int = 0, 
                               canonical: str = None) -> CertificationMatch:
        """Crée un CertificationMatch à partir d'un match regex"""
        
        if canonical is None:
            canonical = self.lookup_table.get(original, {}).get("canonical", original)
        
        # Extract level/score/date if present
        level = None
        date = None
        
        if len(regex_match.groups()) > 1:
            second_group = regex_match.group(2)
            
            # Check if it's a CEFR level
            if second_group.upper() in CEFR_LEVELS:
                level = second_group.upper()
            # Check if it's a score
            elif re.match(r'^\d{2,4}$', second_group):
                level = f"score:{second_group}"
            # Check if it's a date
            elif re.search(r'\d{4}', second_group):
                date = second_group
        
        # Calculate confidence based on distance and context
        confidence = self._calculate_confidence(distance, line, canonical)
        
        return CertificationMatch(
            original_name=original,
            matched_name=canonical,
            canonical_name=canonical,
            distance=distance,
            level=level,
            date=date,
            confidence=confidence,
            line_text=line
        )
    
    def _calculate_confidence(self, distance: int, line: str, canonical: str) -> float:
        """Calcule la confiance du match"""
        base_confidence = max(0.5, 1.0 - (distance * 0.2))  # Pénalité distance
        
        # Bonus pour contexte riche
        context_indicators = [
            r'\b(?:niveau|level|score|points?|obtention|obtained?|passed?)\b',
            r'\b(?:[A-C][12]|\d{2,4})\b',  # CEFR levels ou scores
            r'\b\d{4}\b',  # Années
            r'(?:mars|avril|mai|juin|janvier|february|march|april)\s+\d{4}'  # Dates
        ]
        
        context_bonus = sum(0.1 for pattern in context_indicators 
                          if re.search(pattern, line, re.IGNORECASE))
        
        return min(1.0, base_confidence + context_bonus)
    
    def _deduplicate_matches(self, matches: List[CertificationMatch]) -> List[CertificationMatch]:
        """Déduplique les matches en gardant les meilleurs"""
        if not matches:
            return matches
        
        # Group by canonical name
        grouped = {}
        for match in matches:
            key = match.canonical_name
            if key not in grouped or match.confidence > grouped[key].confidence:
                grouped[key] = match
        
        return list(grouped.values())
    
    def should_route_to_certifications(self, text: str) -> bool:
        """
        Détermine si un texte doit être routé vers CERTIFICATIONS
        Single-line ou two-line patterns [CertName] + level/date
        """
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        # Must be 1-2 lines max
        if len(lines) > 2:
            return False
        
        matches = self.find_certification_matches(text)
        
        if not matches:
            return False
        
        # At least one match with decent confidence
        best_match = max(matches, key=lambda m: m.confidence)
        
        # High confidence match with level or date context
        if best_match.confidence >= 0.7 and (best_match.level or best_match.date):
            return True
        
        # Or multiple matches (comprehensive certification listing)
        if len(matches) >= 2:
            return True
        
        return False


# Factory functions
def find_fuzzy_certifications(text: str, max_distance: int = 2) -> List[CertificationMatch]:
    """
    Factory function pour trouver les certifications avec fuzzy matching
    
    Args:
        text: Texte à analyser
        max_distance: Distance Levenshtein max (défaut: 2)
        
    Returns:
        Liste des certifications trouvées
    """
    matcher = FuzzyCertMatcher(max_distance)
    return matcher.find_certification_matches(text)


def correct_certification_typos(text: str, max_distance: int = 2) -> str:
    """
    Corrige les typos de certifications dans un texte
    
    Args:
        text: Texte à corriger
        max_distance: Distance max pour corrections
        
    Returns:
        Texte avec typos corrigés
    """
    matcher = FuzzyCertMatcher(max_distance)
    matches = matcher.find_certification_matches(text)
    
    corrected_text = text
    
    # Sort by position (descending) to avoid offset issues
    matches_with_positions = []
    for match in matches:
        if match.distance > 0:  # Only correct actual typos
            # Find position of original in text
            pattern = r'\b' + re.escape(match.original_name) + r'\b'
            for regex_match in re.finditer(pattern, text, re.IGNORECASE):
                matches_with_positions.append((regex_match.start(), regex_match.end(), match))
    
    # Sort by start position descending
    matches_with_positions.sort(key=lambda x: x[0], reverse=True)
    
    for start, end, match in matches_with_positions:
        corrected_text = corrected_text[:start] + match.canonical_name + corrected_text[end:]
        logger.debug(f"TYPO_CORRECTED: {match.original_name} → {match.canonical_name} (distance: {match.distance})")
    
    return corrected_text


def extract_certification_metadata(text: str) -> Dict[str, any]:
    """
    Extrait les métadonnées détaillées des certifications
    
    Returns:
        Dict avec certifications, niveaux, dates, etc.
    """
    matcher = FuzzyCertMatcher()
    matches = matcher.find_certification_matches(text)
    
    metadata = {
        "certifications": [],
        "total_found": len(matches),
        "categories": set(),
        "levels": [],
        "dates": []
    }
    
    for match in matches:
        cert_data = {
            "name": match.canonical_name,
            "confidence": match.confidence,
            "level": match.level,
            "date": match.date,
            "line": match.line_text,
            "typo_corrected": match.distance > 0
        }
        
        metadata["certifications"].append(cert_data)
        
        # Collect categories
        if match.canonical_name in CERTIFICATION_REGISTRY:
            category = CERTIFICATION_REGISTRY[match.canonical_name]["category"]
            metadata["categories"].add(category)
        
        # Collect levels and dates
        if match.level:
            metadata["levels"].append(match.level)
        if match.date:
            metadata["dates"].append(match.date)
    
    metadata["categories"] = list(metadata["categories"])
    
    return metadata
