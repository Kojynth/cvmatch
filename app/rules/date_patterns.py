"""
Patterns de dates étendus pour extraction CV multi-langues.
Support formats français étendus avec normalisation PRESENT.
"""

import re
from typing import List, Tuple, Optional, Dict


# === PATTERNS FRANÇAIS ÉTENDUS ===
DATE_FR = [
    # Format "Année YYYY-YYYY"
    r"\bAnn(?:ée|\.?)\s?\d{4}\s?[-–—]\s?\d{4}\b",
    
    # Format "MM/YYYY - à ce jour"  
    r"\b(0[1-9]|1[0-2])/[0-9]{4}\s?[-–—]\s?(?:à\s?ce\s?jour|présent|aujourd'?hui)\b",
    
    # Format "DD/MM/YYYY - DD/MM/YYYY"
    r"\b(0[1-9]|[12][0-9]|3[01])/(0[1-9]|1[0-2])/\d{4}\s?[-–—]\s?(0[1-9]|[12][0-9]|3[01])/(0[1-9]|1[0-2])/\d{4}\b",
    
    # Format "De YYYY à YYYY"
    r"\b[Dd]e\s+(\d{4})\s+[àa]\s+(\d{4}|à\s+ce\s+jour|présent|actuel)\b",
    
    # Format "YYYY-YYYY" simple
    r"\b(\d{4})\s?[-–—]\s?(\d{4}|à\s+ce\s+jour|présent|actuel|aujourd'?hui)\b",
    
    # Format "MM/YYYY - MM/YYYY"
    r"\b(0[1-9]|1[0-2])/(\d{4})\s?[-–—]\s?(?:(0[1-9]|1[0-2])/)?(\d{4}|à\s+ce\s+jour|présent)\b"
]

# === PATTERNS MULTI-LANGUES ===
DATE_EN = [
    r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}\s?[-–—]\s?(present|current|now)\b",
    r"\b\d{4}\s?[-–—]\s?(present|current|ongoing|now)\b",
    r"\b(0[1-9]|1[0-2])/\d{4}\s?[-–—]\s?(present|current)\b"
]

DATE_ZH = [
    r"\b\d{4}年\s?[-–—至]\s?(\d{4}年|至今|现在|目前)\b",
    r"\b\d{4}\s?[-–—至]\s?(至今|现在|目前)\b"
]

DATE_AR = [
    r"\b\d{4}\s?[-–—]\s?(حتى\s+الآن|الآن|حاليا)\b"
]

# === PATTERNS JAPONAIS ===
DATE_JA = [
    # "YYYY年 - YYYY年|現在|今|現在まで|今まで|継続中|在職中"
    r"\b\d{4}年\s?[-–—〜~至]\s?(\d{4}年|現在|今|現在まで|今まで|継続中|在職中)\b",
    # "YYYY - 現在|今|…"
    r"\b\d{4}\s?[-–—〜~至]\s?(現在|今|現在まで|今まで|継続中|在職中)\b",
    # "YYYY/MM - 現在|今|…"
    r"\b\d{4}/(0[1-9]|1[0-2])\s?[-–—〜~至]\s?(現在|今|現在まで|今まで|継続中|在職中)\b",
]

# === PATTERNS CORÉENS ===
DATE_KO = [
    # "YYYY - 현재|지금|현재까지|지금까지|진행중|진행 중|재직중|재직 중"
    r"\b\d{4}\s?[-–—~]\s?(현재|지금|현재까지|지금까지|진행중|진행\s*중|재직중|재직\s*중)\b",
    # "YYYY/MM - 현재|…"
    r"\b\d{4}/(0[1-9]|1[0-2])\s?[-–—~]\s?(현재|지금|현재까지|지금까지|진행중|진행\s*중|재직중|재직\s*중)\b",
]

# === PATTERNS COMBINÉS ===
ALL_DATE_PATTERNS = DATE_FR + DATE_EN + DATE_ZH + DATE_AR + DATE_JA + DATE_KO


def compile_date_patterns() -> List[re.Pattern]:
    """Compile tous les patterns de dates."""
    return [re.compile(pattern, re.IGNORECASE | re.VERBOSE) for pattern in ALL_DATE_PATTERNS]


def extract_date_spans(text: str, patterns: Optional[List[re.Pattern]] = None) -> List[Dict]:
    """
    Extrait toutes les plages de dates d'un texte.
    
    Args:
        text: Texte à analyser
        patterns: Patterns compilés (optionnel)
    
    Returns:
        Liste des plages trouvées avec méta-données
    """
    if not patterns:
        patterns = compile_date_patterns()
    
    spans = []
    
    for i, pattern in enumerate(patterns):
        for match in pattern.finditer(text):
            span_info = {
                'text': match.group(0),
                'start': match.start(),
                'end': match.end(),
                'pattern_idx': i,
                'pattern_type': _get_pattern_type(i),
                'groups': match.groups()
            }
            spans.append(span_info)
    
    # Trier par position et dédupliquer les chevauchements
    spans.sort(key=lambda x: (x['start'], -x['end']))
    
    # Retirer les chevauchements (garder le plus long)
    deduped_spans = []
    for span in spans:
        overlap = False
        for existing in deduped_spans:
            if (span['start'] < existing['end'] and span['end'] > existing['start']):
                overlap = True
                break
        if not overlap:
            deduped_spans.append(span)
    
    return deduped_spans


def _get_pattern_type(pattern_idx: int) -> str:
    """Détermine le type de pattern basé sur l'index."""
    if pattern_idx < len(DATE_FR):
        return "french"
    elif pattern_idx < len(DATE_FR) + len(DATE_EN):
        return "english"
    elif pattern_idx < len(DATE_FR) + len(DATE_EN) + len(DATE_ZH):
        return "chinese"
    elif pattern_idx < len(DATE_FR) + len(DATE_EN) + len(DATE_ZH) + len(DATE_AR):
        return "arabic"
    elif pattern_idx < len(DATE_FR) + len(DATE_EN) + len(DATE_ZH) + len(DATE_AR) + len(DATE_JA):
        return "japanese"
    else:
        return "korean"


def find_date_patterns_in_line(line: str) -> List[Dict]:
    """
    Trouve tous les patterns de dates dans une ligne.
    
    Args:
        line: Ligne de texte
    
    Returns:
        Liste des patterns trouvés
    """
    return extract_date_spans(line)
