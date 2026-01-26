"""
Language Fallback Lexical Extractor
===================================

Fallback lexical pour extraire langues quand IA/ML confidence < seuil.
Détecte sections langues, certifications, et niveaux CEFR explicites.
"""

import re
from typing import List, Dict, Set, Optional, Tuple
from dataclasses import dataclass
from ..logging.safe_logger import get_safe_logger
from ..config import DEFAULT_PII_CONFIG

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)

@dataclass
class LanguageExtractionResult:
    """Résultat d'extraction de langues"""
    languages: List[Dict[str, any]]
    confidence: float
    extraction_method: str
    header_detected: Optional[str] = None
    certifications_found: List[str] = None
    raw_text: str = ""
    
    def __post_init__(self):
        if self.certifications_found is None:
            self.certifications_found = []

# Langues principales avec variantes (ENRICHI Phase 3.2)
LANGUAGES_LEXICON = {
    # Langues européennes principales
    "français", "francais", "french", "france",
    "anglais", "english", "english language", "eng",
    "espagnol", "spanish", "español", "castellano", 
    "allemand", "german", "deutsch", "germany",
    "italien", "italian", "italiano", "italy",
    "portugais", "portuguese", "português", "portugal",
    "néerlandais", "dutch", "nederlands", "holland",
    "suédois", "swedish", "svenska", "sweden",
    "norvégien", "norwegian", "norsk", "norway", 
    "danois", "danish", "dansk", "denmark",
    "finnois", "finnish", "suomi", "finland",
    "grec", "greek", "ελληνικά", "greece",
    "polonais", "polish", "polski", "poland",
    "russe", "russian", "русский", "russia",
    
    # Langues asiatiques
    "chinois", "chinese", "mandarin", "中文", "china",
    "japonais", "japanese", "nihongo", "日本語", "japan",
    "coréen", "korean", "한국어", "korea",
    "hindi", "हिन्दी", "india",
    "arabe", "arabic", "عربي",
    
    # Autres langues importantes
    "turc", "turkish", "türkçe", "turkey",
    "hébreu", "hebrew", "עברית",
    "thaï", "thai", "ไทย", "thailand",
    "vietnamien", "vietnamese", "tiếng việt", "vietnam"
}

# Patterns pour header de section langues (Phase 3.2)
LANGUAGE_HEADER_PATTERNS = [
    # French
    r'\b(?:LANGUES?)\b',
    r'\b(?:LANGUAGE?S?)\b', 
    r'\b(?:COMPÉTENCES?\s+LINGUISTIQUES?)\b',
    r'\b(?:COMPETENCES?\s+LINGUISTIQUES?)\b',
    r'\b(?:LANGUES?\s+PARLÉES?)\b',
    r'\b(?:LANGUES?\s+PARLEES?)\b',
    r'\b(?:LINGUISTIC\s+SKILLS?)\b',
    r'\b(?:SPOKEN\s+LANGUAGES?)\b',
    r'\b(?:FOREIGN\s+LANGUAGES?)\b'
]

# Niveaux CEFR et équivalents
LANGUAGE_LEVELS = {
    "a1", "a2", "b1", "b2", "c1", "c2",
    "débutant", "beginner", "elementary",
    "intermédiaire", "intermediate", "conversationnel", "conversational", 
    "avancé", "advanced", "courant", "fluent",
    "bilingue", "bilingual", "natif", "native", "langue maternelle", "mother tongue",
    "professionnel", "professional", "business level",
    "scolaire", "school level", "notions", "basic"
}

# Certifications langues (Phase 3.2)
LANGUAGE_CERTIFICATIONS = {
    # Anglais
    "toefl", "toeic", "ielts", "cambridge", "cae", "cpe", "first", "pet", "ket", "bulats",
    # Français  
    "delf", "dalf", "tcf", "tef", "delf-dalf",
    # Espagnol
    "dele", "siele", "ccse",
    # Allemand
    "goethe", "testdaf", "dsh", "telc",
    # Italien
    "cils", "celi", "plida", "dit",
    # Autres
    "hsk", "jlpt", "topik", "torfl"
}

class LanguageFallbackExtractor:
    """Extracteur fallback lexical pour langues"""
    
    def __init__(self, ai_threshold: float = 0.40, max_languages: int = 10):
        self.ai_threshold = ai_threshold
        self.max_languages = max_languages
        self.lexicon = LANGUAGES_LEXICON
        self.header_patterns = LANGUAGE_HEADER_PATTERNS
        self.levels = LANGUAGE_LEVELS
        self.certifications = LANGUAGE_CERTIFICATIONS
    
    def should_use_fallback(self, ai_score: float, text: str, title: str = "") -> bool:
        """
        Détermine si le fallback lexical doit être utilisé
        
        Args:
            ai_score: Score de confiance IA/ML
            text: Texte de la section
            title: Titre de la section
            
        Returns:
            True si fallback recommandé
        """
        if ai_score >= self.ai_threshold:
            return False
        
        full_text = text + " " + title
        
        # Check for language header
        has_header = self._detect_language_header(full_text)
        
        # Check for language certifications
        has_certifications = self._detect_certifications(full_text)
        
        # Check for CEFR levels
        has_levels = self._detect_cefr_levels(full_text)
        
        # Phase 3.2: Logique plus permissive - any indicator triggers fallback
        should_fallback = has_header or has_certifications or has_levels
        
        if should_fallback:
            logger.info(f"LANG_FALLBACK: triggered with ai_score={ai_score:.3f} < {self.ai_threshold}, "
                       f"header={has_header}, certs={has_certifications}, levels={has_levels}")
        
        return should_fallback
    
    def _detect_language_header(self, text: str) -> bool:
        """Détecte la présence d'un header langues"""
        text_upper = text.upper()
        
        for pattern in self.header_patterns:
            if re.search(pattern, text_upper, re.IGNORECASE | re.MULTILINE):
                return True
        
        return False
    
    def _detect_certifications(self, text: str) -> bool:
        """Détecte la présence de certifications langues"""
        text_lower = text.lower()
        
        for cert in self.certifications:
            if re.search(rf'\b{re.escape(cert)}\b', text_lower, re.IGNORECASE):
                return True
        
        return False
    
    def _detect_cefr_levels(self, text: str) -> bool:
        """Détecte la présence de niveaux CEFR"""
        text_lower = text.lower()
        
        # CEFR levels (A1, B2, etc.)
        if re.search(r'\b[abcABC][12]\b', text):
            return True
        
        # Level words
        for level in self.levels:
            if re.search(rf'\b{re.escape(level)}\b', text_lower, re.IGNORECASE):
                return True
        
        return False
    
    def extract_languages(self, text: str, title: str = "", ai_score: float = 0.0) -> LanguageExtractionResult:
        """
        Extrait les langues avec fallback lexical
        
        Args:
            text: Texte de la section
            title: Titre de la section  
            ai_score: Score IA (pour validation threshold)
            
        Returns:
            LanguageExtractionResult avec langues extraites
        """
        full_text = text + " " + title
        
        # Detect header and certifications
        detected_header = self._extract_header_text(full_text)
        certifications_found = self._extract_certifications(full_text)
        
        # Extract language candidates
        language_candidates = self._extract_language_candidates(full_text)
        
        # Filter and validate candidates
        validated_languages = self._validate_language_candidates(language_candidates, full_text)
        
        # Limit to max languages
        final_languages = validated_languages[:self.max_languages]
        
        # Calculate confidence
        confidence = self._calculate_extraction_confidence(
            final_languages, certifications_found, detected_header, ai_score
        )
        
        extraction_method = "fallback_lexical" if ai_score < self.ai_threshold else "hybrid"
        
        return LanguageExtractionResult(
            languages=final_languages,
            confidence=confidence,
            extraction_method=extraction_method,
            header_detected=detected_header,
            certifications_found=certifications_found,
            raw_text=full_text
        )
    
    def _extract_header_text(self, text: str) -> Optional[str]:
        """Extrait le texte du header langues détecté"""
        text_upper = text.upper()
        
        for pattern in self.header_patterns:
            match = re.search(pattern, text_upper, re.IGNORECASE | re.MULTILINE)
            if match:
                return match.group(0)
        
        return None
    
    def _extract_certifications(self, text: str) -> List[str]:
        """Extrait les certifications trouvées"""
        found_certs = []
        text_lower = text.lower()
        
        for cert in self.certifications:
            if re.search(rf'\b{re.escape(cert)}\b', text_lower, re.IGNORECASE):
                found_certs.append(cert)
        
        return found_certs
    
    def _extract_language_candidates(self, text: str) -> List[Dict[str, any]]:
        """Extrait les candidats langues du texte"""
        candidates = []
        text_lower = text.lower()
        
        # Mapping certifications → langues
        cert_to_lang = {
            "toefl": "English", "toeic": "English", "ielts": "English", 
            "cambridge": "English", "cae": "English", "cpe": "English",
            "delf": "French", "dalf": "French", "tcf": "French", "tef": "French",
            "dele": "Spanish", "siele": "Spanish",
            "goethe": "German", "testdaf": "German", "dsh": "German",
            "cils": "Italian", "celi": "Italian", "plida": "Italian",
            "hsk": "Chinese", "jlpt": "Japanese", "topik": "Korean"
        }
        
        # 1. Extract from certifications (priority)
        for cert, language in cert_to_lang.items():
            if re.search(rf'\b{re.escape(cert)}\b', text_lower, re.IGNORECASE):
                level = self._extract_level_from_context(text, cert)
                candidates.append({
                    "language": language,
                    "level": level,
                    "source": "certification",
                    "evidence": cert,
                    "confidence": 0.9
                })
        
        # 2. Extract from lexicon
        for lang_term in self.lexicon:
            if re.search(rf'\b{re.escape(lang_term)}\b', text_lower, re.IGNORECASE):
                # Map to canonical name
                canonical = self._map_to_canonical(lang_term)
                if canonical:
                    level = self._extract_level_from_context(text, lang_term)
                    candidates.append({
                        "language": canonical,
                        "level": level,
                        "source": "lexical",
                        "evidence": lang_term,
                        "confidence": 0.7
                    })
        
        return candidates
    
    def _map_to_canonical(self, lang_term: str) -> Optional[str]:
        """Mappe un terme de langue vers son nom canonique"""
        mapping = {
            "français": "French", "francais": "French", "french": "French",
            "anglais": "English", "english": "English",
            "espagnol": "Spanish", "spanish": "Spanish", "español": "Spanish",
            "allemand": "German", "german": "German", "deutsch": "German",
            "italien": "Italian", "italian": "Italian", "italiano": "Italian",
            "portugais": "Portuguese", "portuguese": "Portuguese", "português": "Portuguese",
            "chinois": "Chinese", "chinese": "Chinese", "mandarin": "Chinese",
            "japonais": "Japanese", "japanese": "Japanese",
            "coréen": "Korean", "korean": "Korean",
            "arabe": "Arabic", "arabic": "Arabic",
            "russe": "Russian", "russian": "Russian",
            "néerlandais": "Dutch", "dutch": "Dutch", "nederlands": "Dutch"
        }
        
        return mapping.get(lang_term.lower())
    
    def _extract_level_from_context(self, text: str, lang_context: str) -> Optional[str]:
        """Extrait le niveau de langue du contexte"""
        # Find the line containing the language
        lines = text.split('\n')
        context_line = None
        
        for line in lines:
            if lang_context.lower() in line.lower():
                context_line = line
                break
        
        if not context_line:
            return None
        
        # Extract CEFR levels (A1, B2, etc.)
        cefr_match = re.search(r'\b([abcABC][12])\b', context_line, re.IGNORECASE)
        if cefr_match:
            return cefr_match.group(1).upper()
        
        # Extract level synonyms
        context_lower = context_line.lower()
        level_map = {
            "débutant": "A1", "beginner": "A1", "elementary": "A1", "notions": "A1", "scolaire": "A1",
            "intermédiaire": "B1", "intermediate": "B1", "conversationnel": "B1",
            "avancé": "B2", "advanced": "B2", "courant": "C1", "fluent": "C1",
            "bilingue": "C2", "bilingual": "C2", "natif": "C2", "native": "C2", "langue maternelle": "C2"
        }
        
        for synonym, level in level_map.items():
            if synonym in context_lower:
                return level
        
        return None
    
    def _validate_language_candidates(self, candidates: List[Dict[str, any]], text: str) -> List[Dict[str, any]]:
        """Valide et déduplique les candidats langues"""
        validated = []
        seen_languages = set()
        
        # Sort by confidence (certifications first)
        candidates.sort(key=lambda x: x.get('confidence', 0), reverse=True)
        
        for candidate in candidates:
            language = candidate['language']
            
            if language and language not in seen_languages:
                seen_languages.add(language)
                validated.append(candidate)
        
        return validated
    
    def _calculate_extraction_confidence(self, languages: List[Dict[str, any]], 
                                       certifications: List[str], 
                                       header: Optional[str],
                                       ai_score: float) -> float:
        """Calcule la confiance de l'extraction"""
        base_confidence = 0.6
        
        # Bonus pour header spécialisé
        if header:
            base_confidence += 0.1
        
        # Bonus pour certifications
        if certifications:
            base_confidence += 0.15
        
        # Bonus pour nombre raisonnable de langues
        lang_count = len(languages)
        if 1 <= lang_count <= 5:  # Sweet spot
            base_confidence += 0.1
        elif lang_count > 8:  # Suspect
            base_confidence -= 0.2
        
        # Malus si AI score très bas (extraction difficile)
        if ai_score < 0.1:
            base_confidence -= 0.1
        
        return min(0.95, max(0.3, base_confidence))


def extract_languages_fallback(text_lines: List[str], 
                              ml_confidence_threshold: float = 0.1) -> List[Dict[str, any]]:
    """
    Interface principale pour l'extraction langues fallback
    Compatible avec l'intégration cv_extractor.py
    
    Args:
        text_lines: Liste des lignes de texte du CV
        ml_confidence_threshold: Seuil en dessous duquel utiliser le fallback
        
    Returns:
        Liste de dictionnaires avec les langues extraites
    """
    results = []
    
    # Simuler un score ML faible pour déclencher le fallback
    ai_score = ml_confidence_threshold - 0.01
    
    # Joindre les lignes pour former le texte complet
    full_text = "\n".join(text_lines)
    
    # Utiliser l'extracteur avec fallback
    extractor = LanguageFallbackExtractor(ai_threshold=ml_confidence_threshold + 0.1)
    
    if extractor.should_use_fallback(ai_score, full_text, ""):
        extraction_result = extractor.extract_languages(full_text, "", ai_score)
        
        if extraction_result and extraction_result.languages:
            for lang in extraction_result.languages:
                results.append({
                    'language': lang['language'],
                    'level': lang.get('level', 'unknown'),
                    'confidence': lang.get('confidence', 0.7),
                    'detection_method': extraction_result.extraction_method,
                    'evidence': lang.get('evidence', ''),
                    'source': lang.get('source', 'fallback')
                })
    
    logger.info(f"LANG_FALLBACK: extracted {len(results)} languages")
    
    return results