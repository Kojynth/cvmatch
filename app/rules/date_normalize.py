"""
Normalisation des plages de dates avec support multi-langues.
Gestion spéciale des tokens "PRESENT" multi-langues.
"""

import re
from typing import Tuple, Optional, Union, List, Dict
from loguru import logger


# === TOKENS PRESENT MULTI-LANGUES ===
PRESENT_TOKENS = {
    'fr': [
        'à ce jour', 'présent', 'actuel', 'actuellement',
        'en cours', 'toujours', 'maintenant'
    ],
    'en': [
        'present', 'current', 'currently', 'ongoing', 'now',
        'to date', 'to present', 'till now'
    ],
    'zh': [
        '至今', '现在', '目前', '当前', '至今为止'
    ],
    'ar': [
        'حتى الآن', 'الآن', 'حاليا', 'حالياً', 'إلى الآن'
    ],
    'ja': [
        '現在', '現在まで', '今', '今まで', '継続中', '在職中'
    ],
    'ko': [
        '현재', '현재까지', '지금', '지금까지', '진행중', '진행 중', '재직중', '재직 중'
    ]
}

# Pattern consolidé pour tous les tokens present
ALL_PRESENT_TOKENS = []
for lang_tokens in PRESENT_TOKENS.values():
    ALL_PRESENT_TOKENS.extend(lang_tokens)

PRESENT_PATTERN = re.compile(
    r'\b(' + '|'.join(re.escape(token) for token in ALL_PRESENT_TOKENS) + r')\b',
    re.IGNORECASE
)


def normalize_present_token(text: str) -> str:
    """
    Normalise les tokens 'present' multi-langues vers 'PRESENT'.
    
    Args:
        text: Texte contenant potentiellement un token present
    
    Returns:
        Texte avec tokens present normalisés
    """
    if not text:
        return text
    
    # Normaliser Unicode et espaces spéciaux
    import unicodedata
    normalized_text = unicodedata.normalize('NFKC', text).replace('\u00A0', ' ')
    
    def replace_present(match):
        original = match.group(1)
        logger.debug(f"DATE_NORM_PRESENT: '{original}' -> 'PRESENT'")
        return 'PRESENT'
    
    result = PRESENT_PATTERN.sub(replace_present, normalized_text)
    return result


def normalize_date_span(text: str) -> Tuple[Optional[str], Optional[str], bool]:
    """
    Normalise une plage de dates en extractant début, fin et statut current.
    
    Args:
        text: Texte de la plage de dates
    
    Returns:
        Tuple (start_date, end_date, is_current)
    """
    if not text:
        return None, None, False
    
    # Normaliser les tokens present d'abord
    normalized_text = normalize_present_token(text)
    
    # Détecter si current/present
    is_current = 'PRESENT' in normalized_text
    
    # Patterns d'extraction de dates
    patterns = [
        # Format "YYYY-YYYY" ou "YYYY-PRESENT"
        r'(\d{4})\s*[-–—]\s*(\d{4}|PRESENT)',
        
        # Format "MM/YYYY - MM/YYYY"
        r'(\d{1,2}/\d{4})\s*[-–—]\s*(\d{1,2}/\d{4}|PRESENT)',
        
        # Format "DD/MM/YYYY - DD/MM/YYYY"
        r'(\d{1,2}/\d{1,2}/\d{4})\s*[-–—]\s*(\d{1,2}/\d{1,2}/\d{4}|PRESENT)',
        
        # Format "De YYYY à YYYY"
        r'[Dd]e\s+(\d{4})\s+[àa]\s+(\d{4}|PRESENT)',
        
        # Format "Année YYYY-YYYY"
        r'[Aa]nn(?:ée|\.?)\s*(\d{4})\s*[-–—]\s*(\d{4}|PRESENT)'
    ]
    
    start_date = None
    end_date = None
    
    for pattern in patterns:
        match = re.search(pattern, normalized_text, re.IGNORECASE)
        if match:
            start_raw, end_raw = match.groups()
            start_date = _normalize_single_date(start_raw)
            end_date = None if end_raw == 'PRESENT' else _normalize_single_date(end_raw)
            break
    
    return start_date, end_date, is_current


def _normalize_single_date(date_str: str) -> Optional[str]:
    """
    Normalise une date individuelle vers le format YYYY-MM.
    
    Args:
        date_str: Date brute (YYYY, MM/YYYY, DD/MM/YYYY, etc.)
    
    Returns:
        Date normalisée en format YYYY-MM ou None
    """
    if not date_str or date_str == 'PRESENT':
        return None
    
    # Format YYYY seul
    if re.match(r'^\d{4}$', date_str):
        return f"{date_str}-01"  # Premier janvier par défaut
    
    # Format MM/YYYY
    mm_yyyy_match = re.match(r'^(\d{1,2})/(\d{4})$', date_str)
    if mm_yyyy_match:
        month, year = mm_yyyy_match.groups()
        return f"{year}-{month.zfill(2)}"
    
    # Format DD/MM/YYYY
    dd_mm_yyyy_match = re.match(r'^(\d{1,2})/(\d{1,2})/(\d{4})$', date_str)
    if dd_mm_yyyy_match:
        day, month, year = dd_mm_yyyy_match.groups()
        return f"{year}-{month.zfill(2)}"
    
    # Formats additionnels (YYYY年, etc.)
    chinese_match = re.match(r'^(\d{4})年$', date_str)
    if chinese_match:
        return f"{chinese_match.group(1)}-01"
    
    # Fallback: retourner tel quel si pas reconnu
    logger.warning(f"DATE_NORMALIZE: unrecognized format '{date_str}'")
    return date_str


def extract_and_normalize_dates(text: str) -> List[Dict]:
    """
    Extrait et normalise toutes les dates d'un texte.
    
    Args:
        text: Texte à analyser
    
    Returns:
        Liste des dates normalisées avec méta-données
    """
    from .date_patterns import extract_date_spans
    
    spans = extract_date_spans(text)
    normalized_dates = []
    
    for span in spans:
        start_date, end_date, is_current = normalize_date_span(span['text'])
        
        if start_date:  # Seulement si on a pu extraire au moins une date de début
            normalized_dates.append({
                'original_text': span['text'],
                'start_date': start_date,
                'end_date': end_date,
                'is_current': is_current,
                'span_start': span['start'],
                'span_end': span['end'],
                'pattern_type': span['pattern_type']
            })
    
    return normalized_dates


# === FONCTIONS UTILITAIRES ===

def is_valid_date_range(start_date: str, end_date: Optional[str]) -> bool:
    """Vérifie la validité d'une plage de dates."""
    if not start_date:
        return False
    
    # Vérifier format YYYY-MM
    if not re.match(r'^\d{4}-\d{2}$', start_date):
        return False
    
    if end_date and not re.match(r'^\d{4}-\d{2}$', end_date):
        return False
    
    # Vérifier ordre chronologique
    if end_date and start_date > end_date:
        return False
    
    # Vérifier années réalistes (1970-2030)
    start_year = int(start_date[:4])
    if not (1970 <= start_year <= 2030):
        return False
    
    if end_date:
        end_year = int(end_date[:4])
        if not (1970 <= end_year <= 2030):
            return False
    
    return True


def format_date_for_display(date_str: Optional[str], is_current: bool = False) -> str:
    """Formate une date pour l'affichage."""
    if not date_str:
        return "Présent" if is_current else "N/A"
    
    # Format YYYY-MM -> MM/YYYY
    if re.match(r'^\d{4}-\d{2}$', date_str):
        year, month = date_str.split('-')
        return f"{month}/{year}"
    
    return date_str
