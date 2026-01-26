"""Détection de langue légère pour CVs."""

import logging
import re
from typing import Optional
from ..logging.safe_logger import get_safe_logger
from ..config import DEFAULT_PII_CONFIG

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)

# Mots-clés communs par langue
FR_KEYWORDS = {
    'education': ['formation', 'diplôme', 'université', 'école', 'licence', 'master', 'doctorat'],
    'experience': ['expérience', 'emploi', 'stage', 'poste', 'entreprise', 'société'],
    'skills': ['compétences', 'savoir-faire', 'maîtrise'],
    'projects': ['projets', 'réalisations'],
    'volunteering': ['bénévolat', 'volontariat', 'associatif'],
    'common': ['et', 'de', 'du', 'des', 'le', 'la', 'les', 'un', 'une', 'avec', 'pour', 'dans', 'sur']
}

EN_KEYWORDS = {
    'education': ['education', 'degree', 'university', 'college', 'school', 'bachelor', 'master', 'phd'],
    'experience': ['experience', 'work', 'job', 'position', 'company', 'corporation'],
    'skills': ['skills', 'expertise', 'proficiency'],
    'projects': ['projects', 'achievements'],
    'volunteering': ['volunteering', 'volunteer', 'charity'],
    'common': ['and', 'of', 'the', 'in', 'at', 'with', 'for', 'on', 'to', 'from']
}

# Pattern pour détecter les accents français
FRENCH_ACCENTS_PATTERN = re.compile(r'[àáâãäåçèéêëìíîïñòóôõöùúûüýÿ]', re.IGNORECASE)

# Pattern pour les dates françaises
FRENCH_DATE_PATTERN = re.compile(r'\b\d{1,2}/\d{1,2}/\d{4}\b')

# Pattern pour les dates anglaises  
ENGLISH_DATE_PATTERN = re.compile(r'\b\d{1,2}-\d{1,2}-\d{4}\b|\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b', re.IGNORECASE)


def detect_lang(text: str) -> Optional[str]:
    """
    Détecte la langue principale du texte.
    
    Args:
        text: Texte à analyser
        
    Returns:
        'fr', 'en', 'multi' ou None si indéterminé
    """
    if not text or len(text.strip()) < 10:
        logger.debug("LANG: detect | text_too_short")
        return None
    
    method = "unknown"
    confidence = 0.0
    
    # Tentative avec langdetect si disponible
    try:
        import langdetect
        detected = langdetect.detect(text)
        confidence = langdetect.detect_langs(text)[0].prob
        method = "langdetect"
        
        if detected == 'fr' and confidence > 0.7:
            logger.info(f"LANG: detect | guess=fr | method={method} | conf={confidence:.2f} | chars={len(text)}")
            return 'fr'
        elif detected == 'en' and confidence > 0.7:
            logger.info(f"LANG: detect | guess=en | method={method} | conf={confidence:.2f} | chars={len(text)}")
            return 'en'
        else:
            # Confiance faible, utiliser heuristiques
            pass
            
    except ImportError:
        logger.debug("LANG: langdetect not available, using heuristics")
    except Exception as e:
        logger.debug(f"LANG: langdetect failed: {e}")
    
    # Fallback heuristique
    return _detect_lang_heuristic(text)


def _detect_lang_heuristic(text: str) -> str:
    """
    Détection heuristique basée sur les mots-clés et patterns.
    
    Args:
        text: Texte à analyser
        
    Returns:
        'fr', 'en' ou 'multi'
    """
    text_lower = text.lower()
    
    fr_score = 0
    en_score = 0
    
    # Score basé sur les accents français
    accent_matches = len(FRENCH_ACCENTS_PATTERN.findall(text))
    if accent_matches > 0:
        fr_score += min(accent_matches * 2, 20)  # Cap à 20 points
    
    # Score basé sur les patterns de dates
    fr_dates = len(FRENCH_DATE_PATTERN.findall(text))
    en_dates = len(ENGLISH_DATE_PATTERN.findall(text))
    fr_score += fr_dates * 3
    en_score += en_dates * 3
    
    # Score basé sur les mots-clés par catégorie
    for category, keywords in FR_KEYWORDS.items():
        weight = 5 if category == 'common' else 3
        for keyword in keywords:
            # Recherche mot entier
            pattern = r'\b' + re.escape(keyword) + r'\b'
            matches = len(re.findall(pattern, text_lower))
            fr_score += matches * weight
    
    for category, keywords in EN_KEYWORDS.items():
        weight = 5 if category == 'common' else 3
        for keyword in keywords:
            pattern = r'\b' + re.escape(keyword) + r'\b'
            matches = len(re.findall(pattern, text_lower))
            en_score += matches * weight
    
    # Normalisation par longueur de texte
    text_words = len(text_lower.split())
    if text_words > 0:
        fr_score = fr_score / text_words
        en_score = en_score / text_words
    
    # Détermination finale
    total_score = fr_score + en_score
    if total_score == 0:
        confidence = 0.0
        result = "multi"
    else:
        confidence = max(fr_score, en_score) / total_score
        
        # Seuils pour décision
        if fr_score > en_score and confidence > 0.6:
            result = "fr"
        elif en_score > fr_score and confidence > 0.6:
            result = "en"
        else:
            result = "multi"
    
    logger.info(f"LANG: detect | guess={result} | method=heuristic | conf={confidence:.2f} | chars={len(text)} | fr_score={fr_score:.2f} | en_score={en_score:.2f}")
    
    return result


def is_french_text(text: str) -> bool:
    """
    Test rapide si le texte est probablement français.
    
    Args:
        text: Texte à tester
        
    Returns:
        True si français probable
    """
    detected = detect_lang(text)
    return detected == 'fr'


def is_english_text(text: str) -> bool:
    """
    Test rapide si le texte est probablement anglais.
    
    Args:
        text: Texte à tester
        
    Returns:
        True si anglais probable
    """
    detected = detect_lang(text)
    return detected == 'en'
