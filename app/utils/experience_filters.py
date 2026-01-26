"""
Enhanced Experience Filters with Anti-Contamination Guards
========================================================

Filtres et utilitaires pour l'extraction d'expériences professionnelles.
Implémente la logique de filtrage organisation/école et pattern diversity.

NEW: Anti-contamination guards to prevent contact/header line extraction as experiences.
"""

import re
import unicodedata
from typing import List, Dict, Any, Optional, Tuple, Set, Iterable
from ..logging.safe_logger import get_safe_logger
from .text_norm import normalize_text_for_matching
from ..config import (
    DEFAULT_PII_CONFIG, EXPERIENCE_CONF, SCHOOL_BLACKLIST,
    EMPLOYMENT_KEYWORDS, ACTION_VERBS_FR, CERT_CANON, CERT_TYPO
)

try:
    from ..config_thresholds.extraction_thresholds import DEFAULT_EXTRACTION_THRESHOLDS
except ImportError:
    # Fallback if extraction_thresholds not available
    class DefaultThresholds:
        MIN_EXP_DATE_PROXIMITY_LINES = 5
        CONTACT_POST_BUFFER_LINES = 8
        DENY_EMAIL_AS_COMPANY = True
        DENY_URL_TOKENS_IN_COMPANY = True  
        DENY_PHONE_LINES_IN_EXP = True
        MIN_DATE_PRESENCE_REQUIRED = True
        MIN_PATTERN_DIVERSITY = 0.30
        MAX_CROSS_COLUMN_DISTANCE = 0
        MIN_COMPANY_TOKEN_LENGTH = 2
        MIN_TITLE_TOKEN_LENGTH = 3
    
    DEFAULT_EXTRACTION_THRESHOLDS = DefaultThresholds()

# Initialisation du logger global pour les fonctions standalone
logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)

_VALIDATION_CACHE = None


def _get_experience_validator():
    """Lazy-load the shared ExperienceValidator."""
    global _VALIDATION_CACHE
    if _VALIDATION_CACHE is None:
        from .experience_validation import get_experience_validator

        _VALIDATION_CACHE = get_experience_validator()
    return _VALIDATION_CACHE

DATE_RANGE_PREFIX_RE = re.compile(
    r"^\s*(?P<start>(?:\d{1,2}[/.]\d{1,2}[/.]\d{2,4})|\d{4})\s*[-–]\s*(?P<end>(?:\d{1,2}[/.]\d{1,2}[/.]\d{2,4})|\d{4}|(?:à|a)?\s*(?:ce\s*jour|aujourd\'hui|présent|present|en\s*cours))",
    re.IGNORECASE,
)

DATE_TOKEN_RE = re.compile(
    r"^(?:\d{1,2}[/.]\d{1,2}[/.]\d{2,4}|\d{4})$",
    re.IGNORECASE,
)

CURRENT_STATUS_TOKENS = {
    'présent', 'present', 'en cours', 'en-cours', 'ce jour', 'a ce jour', "à ce jour", "aujourd'hui"
}
CURRENT_STATUS_TOKENS_NORMALIZED = {normalize_text_for_matching(token) for token in CURRENT_STATUS_TOKENS}


def _strip_leading_date_tokens(value: str) -> tuple[str, list[str]]:
    """Retire les tokens de date ou d'état courant en début de chaîne."""
    if not value:
        return '', []

    tokens: list[str] = []
    working = value.strip()
    pattern_local = re.compile(
        r"^(?P<token>(?:\d{1,2}[/.]\d{1,2}[/.]\d{2,4})|\d{4}|(?:présent|present|en cours|en-cours|à ce jour|a ce jour|ce jour|aujourd\'hui))\b",
        re.IGNORECASE,
    )

    while working:
        match = pattern_local.match(working)
        if not match:
            break
        token = match.group('token')
        tokens.append(token)
        working = working[match.end():].lstrip(' -–|•,;')

    return working, tokens


def contains_school_lexeme(text: str) -> bool:
    """Detecte si un texte contient un lexique lié à une école/formation."""
    if not text:
        return False
    normalized = normalize_text_for_matching(text)
    if not normalized:
        return False

    for entry in SCHOOL_BLACKLIST:
        if normalize_text_for_matching(entry) in normalized:
            return True

    school_tokens = {
        'ecole', 'école', 'universite', 'université', 'lycee', 'lycée',
        'college', 'collège', 'academy', 'institut', 'campus', 'faculte', 'faculté'
    }
    return any(token in normalized for token in school_tokens)


def contains_employment_keywords(text_lines: List[str], target_line_idx: int, window: int = 2) -> Tuple[bool, List[str]]:
    """Cherche des mots-clés d'expérience pro autour d'une ligne cible."""
    if text_lines is None or target_line_idx is None:
        return False, []

    start = max(0, target_line_idx - window)
    end = min(len(text_lines), target_line_idx + window + 1)
    found: Set[str] = set()

    for idx in range(start, end):
        candidate = normalize_text_for_matching(text_lines[idx])
        if not candidate:
            continue
        for keyword in EMPLOYMENT_KEYWORDS:
            if keyword and keyword in candidate:
                found.add(keyword)

    return (bool(found), sorted(found))


def find_alternate_org_entities(entities: Optional[List[Dict[str, Any]]], index: int) -> Optional[str]:
    """Retourne une autre entité ORG détectée à proximité."""
    if not entities:
        return None

    for offset in range(1, 4):
        for candidate_idx in (index - offset, index + offset):
            if candidate_idx < 0 or candidate_idx >= len(entities):
                continue
            entity = entities[candidate_idx] or {}
            label = entity.get('label') or entity.get('entity')
            if not label:
                continue
            if 'ORG' not in label.upper():
                continue
            text = entity.get('text') or entity.get('word')
            if not text:
                continue
            if contains_school_lexeme(text):
                continue
            return text.strip()
    return None



def extract_title_company_patterns(text_lines: List[str]) -> List[Dict[str, Any]]:
    """Extrait des patterns titre/entreprise depuis les lignes de texte."""
    patterns: List[Dict[str, Any]] = []

    title_company_pattern = re.compile(
        r'(?P<title>[^@|]{2,120})\s*[@\-–|]\s*(?P<company>[^@|]{2,160})',
        re.IGNORECASE
    )
    company_title_pattern = re.compile(
        r'(?P<company>[^@|]{2,160})\s*[@\-–|]\s*(?P<title>[^@|]{2,120})',
        re.IGNORECASE
    )

    for line_idx, raw_line in enumerate(text_lines):
        if not raw_line or not raw_line.strip():
            continue

        working_line = raw_line.strip()
        line_meta: Dict[str, Any] = {}

        prefix_match = DATE_RANGE_PREFIX_RE.match(working_line)
        if prefix_match:
            start_token = prefix_match.group('start').strip()
            end_token = prefix_match.group('end').strip()
            line_meta['date_prefix'] = {
                'start': start_token,
                'end': end_token,
                'raw': prefix_match.group(0).strip()
            }
            working_line = working_line[prefix_match.end():].lstrip(' -–|•')

            end_norm = normalize_text_for_matching(end_token)
            if end_norm in CURRENT_STATUS_TOKENS_NORMALIZED:
                line_meta['is_current'] = True

        if not working_line:
            continue

        def build_entry(title: str, company: str, pattern_type: str) -> Optional[Dict[str, Any]]:
            cleaned_title, title_tokens = _strip_leading_date_tokens(title)
            cleaned_company, company_tokens = _strip_leading_date_tokens(company)

            cleaned_title = cleaned_title.strip(' -–|•')
            cleaned_company = cleaned_company.strip(' -–|•')

            if len(cleaned_title) < 3 or len(cleaned_company) < 3:
                return None

            if DATE_TOKEN_RE.fullmatch(cleaned_title) or DATE_TOKEN_RE.fullmatch(cleaned_company):
                return None

            if (looks_like_email(cleaned_title) or looks_like_email(cleaned_company) or
                    looks_like_url_or_domain(cleaned_title) or looks_like_url_or_domain(cleaned_company) or
                    looks_like_language_certificate(cleaned_title) or looks_like_language_certificate(cleaned_company) or
                    not is_valid_company_token(cleaned_company, {'strict_validation': True})):
                return None

            entry: Dict[str, Any] = {
                'title': cleaned_title,
                'company': cleaned_company,
                'line_idx': line_idx,
                'pattern_type': pattern_type,
                'confidence': 0.8 if pattern_type == 'title_company_inline' else 0.75
            }

            meta: Dict[str, Any] = {}
            if line_meta:
                meta.update(line_meta)
            stripped_tokens: Dict[str, List[str]] = {}
            if title_tokens:
                stripped_tokens['title'] = title_tokens
            if company_tokens:
                stripped_tokens['company'] = company_tokens
            if stripped_tokens:
                meta['stripped_tokens'] = stripped_tokens
            if meta:
                entry['meta'] = meta
            return entry

        match = title_company_pattern.search(working_line)
        if match:
            entry = build_entry(match.group('title'), match.group('company'), 'title_company_inline')
            if entry:
                patterns.append(entry)
                logger.debug(
                    "PATTERN: title_company | line=%s title='%s...' company='%s...'",
                    line_idx,
                    entry['title'][:15],
                    entry['company'][:15]
                )

        inverse_match = company_title_pattern.search(working_line)
        if inverse_match and (not match or match.start() != inverse_match.start()):
            entry = build_entry(inverse_match.group('title'), inverse_match.group('company'), 'company_title_inline')
            if entry:
                patterns.append(entry)
                logger.debug(
                    "PATTERN: company_title | line=%s company='%s...' title='%s...'",
                    line_idx,
                    entry['company'][:15],
                    entry['title'][:15]
                )

    return patterns


def extract_validated_title_company_patterns(
    text_lines: List[str],
    *,
    max_patterns: int = 4,
) -> List[Dict[str, Any]]:
    """
    Extract title/company pairs and run them through the hardened validator.

    This prevents education/certification lines or bare date patterns from leaking
    into the experience pipeline. The result list is capped to keep noise low.
    """

    validator = _get_experience_validator()
    raw_patterns = extract_title_company_patterns(text_lines)
    filtered: List[Dict[str, Any]] = []
    seen_pairs: Set[Tuple[str, str]] = set()

    for entry in raw_patterns:
        title = entry.get("title", "")
        company = entry.get("company", "")
        line_idx = entry.get("line_idx", 0)

        pair_key = (title, company)
        if pair_key in seen_pairs:
            continue

        route_edu, _ = validator.should_route_to_education(title, company, text_lines)
        if route_edu:
            continue

        route_cert, _ = validator.should_route_to_certification(title, company, text_lines)
        if route_cert:
            continue

        company_valid, _ = validator.is_proper_company_name(company)
        title_valid, _ = validator.is_plausible_title(title)
        has_context, context_keywords = validator.has_context_keywords(text_lines, line_idx)

        if not (company_valid and title_valid and has_context):
            continue

        validated_entry = dict(entry)
        if context_keywords:
            validated_entry["context_keywords"] = context_keywords

        filtered.append(validated_entry)
        seen_pairs.add(pair_key)
        if len(filtered) >= max_patterns:
            break

    return filtered


def extract_bullet_action_patterns(text_lines: List[str]) -> List[Dict[str, Any]]:
    """
    Extrait des patterns d'action à puces (lignes commençant par bullet + verbe d'action).
    
    Returns:
        Liste de dictionnaires avec 'action', 'line_idx', 'pattern_type'
    """
    patterns = []
    bullet_pattern = re.compile(r'^\s*[•\-–*▪▫‣⁃]\s*', re.UNICODE)
    
    for i, line in enumerate(text_lines):
        if not line.strip():
            continue
            
        # Vérifie si la ligne commence par une puce
        if not bullet_pattern.match(line):
            continue
            
        # Supprime la puce et normalise
        clean_line = bullet_pattern.sub('', line).strip()
        normalized_line = normalize_text_for_matching(clean_line)
        
        # Vérifie la présence d'un verbe d'action
        found_verbs = []
        for verb in ACTION_VERBS_FR:
            verb_normalized = normalize_text_for_matching(verb)
            if normalized_line.startswith(verb_normalized) or f' {verb_normalized} ' in normalized_line:
                found_verbs.append(verb)
        
        if found_verbs:
            patterns.append({
                'action': clean_line,
                'verbs': found_verbs,
                'line_idx': i,
                'pattern_type': 'bullet_action',
                'confidence': 0.7
            })
            logger.debug(f"PATTERN: bullet_action | line={i} verbs={found_verbs} action='{clean_line[:30]}...'")
    
    return patterns


def calculate_pattern_diversity(extraction_results: Dict[str, Any]) -> float:
    """
    Calcule la diversité des patterns utilisés dans l'extraction.
    
    Args:
        extraction_results: Résultats d'extraction avec métadonnées des patterns
    
    Returns:
        Score de diversité entre 0.0 et 1.0
    """
    pattern_types_used = set()
    total_items = 0
    
    # Compte les différents types de patterns utilisés
    for section_name, items in extraction_results.items():
        if not isinstance(items, list):
            continue
            
        for item in items:
            total_items += 1
            pattern_type = item.get('pattern_type', 'unknown')
            pattern_types_used.add(pattern_type)
    
    if total_items == 0:
        return 0.0
    
    # Patterns possibles
    possible_patterns = {
        'date_first_fallback', 'title_company_inline', 'company_title_inline', 
        'bullet_action', 'ner_entity', 'section_extraction', 'assignment_based'
    }
    
    diversity_score = len(pattern_types_used) / len(possible_patterns)
    
    logger.info(f"PATTERN_DIVERSITY: score={diversity_score:.3f} | types_used={list(pattern_types_used)} | total_items={total_items}")
    
    return diversity_score


def normalize_certification_name(cert_text: str) -> Optional[str]:
    """
    Normalise et corrige le nom d'une certification.
    
    Args:
        cert_text: Texte potentiel de certification
    
    Returns:
        Nom canonique de la certification ou None si pas trouvé
    """
    if not cert_text:
        return None
    
    normalized = normalize_text_for_matching(cert_text)
    
    # Vérifie d'abord les corrections typographiques
    for typo, correct in CERT_TYPO.items():
        if typo in normalized:
            logger.debug(f"CERT_TYPO: corrected | '{typo}' -> '{correct}' in '{cert_text}'")
            normalized = normalized.replace(typo, correct)
    
    # Vérifie les certifications canoniques
    for canon_cert in CERT_CANON:
        canon_normalized = normalize_text_for_matching(canon_cert)
        if canon_normalized in normalized:
            logger.debug(f"CERT_CANONICAL: matched | '{canon_cert}' in '{cert_text}'")
            return canon_cert
    
    return None


def is_certification_text(text: str) -> bool:
    """Vérifie si un texte fait référence à une certification."""
    return normalize_certification_name(text) is not None


def detect_header_proximity(text_lines: List[str], target_line_idx: int, 
                          education_headers: List[str] = None) -> Tuple[bool, Optional[str], int]:
    """
    Détecte la proximité d'en-têtes d'éducation autour d'une ligne cible.
    
    Args:
        text_lines: Liste des lignes de texte
        target_line_idx: Index de la ligne cible
        education_headers: Liste des en-têtes d'éducation (défaut fourni)
    
    Returns:
        (is_near_education_header, closest_header, distance)
    """
    if education_headers is None:
        education_headers = ["FORMATION", "ÉDUCATION", "EDUCATION", "DIPLÔMES", "DIPLOMES", "ÉTUDES", "ETUDES"]
    
    guard_distance = EXPERIENCE_CONF["header_guard_distance"]
    start_idx = max(0, target_line_idx - guard_distance)
    end_idx = min(len(text_lines), target_line_idx + guard_distance + 1)
    
    for i in range(start_idx, end_idx):
        if i >= len(text_lines):
            continue
            
        line_normalized = normalize_text_for_matching(text_lines[i])
        
        for header in education_headers:
            header_normalized = normalize_text_for_matching(header)
            if header_normalized in line_normalized:
                distance = abs(i - target_line_idx)
                logger.debug(f"HEADER_GUARD: education_header_detected | line={i} header='{header}' distance={distance}")
                return True, header, distance
    
    return False, None, -1


class ExperienceQualityAssessor:
    """Évalue la qualité des expériences extraites et suggère des rétrogradations."""
    
    def __init__(self):
        self.logger = get_safe_logger(f"{__name__}.QualityAssessor", cfg=DEFAULT_PII_CONFIG)
    
    def assess_experience_quality(self, experience: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Évalue la qualité d'une expérience et détermine si elle doit être rétrogradée.
        
        Args:
            experience: Dictionnaire de l'expérience
            context: Contexte additionnel (lignes de texte, entités NER, etc.)
        
        Returns:
            Dictionnaire avec 'should_demote', 'target_section', 'confidence_penalty', 'reasons'
        """
        reasons = []
        confidence_penalty = 0.0
        should_demote = False
        target_section = 'experiences'
        
        company = experience.get('company', '').strip()
        title = experience.get('title', '').strip()
        
        # Vérifications pour rétrogradation
        company_is_school = company and contains_school_lexeme(company)
        if company_is_school:
            reasons.append('company_is_school')
            confidence_penalty += 0.25
        
        if not company or company_is_school:
            reasons.append('missing_or_suspect_company')
            confidence_penalty += EXPERIENCE_CONF["confidence_penalty_missing_company"]
        
        if not title:
            reasons.append('missing_title')
            confidence_penalty += 0.1
        
        # Vérifie la présence de mots-clés d'emploi dans le contexte
        has_employment_context = False
        if context and 'text_lines' in context:
            text_lines = context['text_lines']
            line_idx = experience.get('line_start', 0)
            has_employment_context, _ = contains_employment_keywords(text_lines, line_idx)
        
        if not has_employment_context:
            reasons.append('no_employment_keywords')
            confidence_penalty += 0.15
        
        # Critères de rétrogradation (au moins 3 sur 4 doivent être vrais)
        demote_criteria = [
            not company or company_is_school,  # Pas d'entreprise ou entreprise scolaire
            not has_employment_context,        # Pas de mots-clés d'emploi vraiment pertinents
            not title,                        # Pas de titre
            not experience.get('has_bullet_actions', False)  # Pas d'actions à puces
        ]
        
        met_criteria_count = sum(demote_criteria)
        
        # Rétrogradation si au moins 3 critères sur 4 sont remplis ET l'entreprise est une école
        if met_criteria_count >= 3 and company_is_school:
            should_demote = True
            target_section = 'education'
            reasons.append('demote_criteria_met_with_school_company')
            self.logger.info(f"QA_DEMOTE: experience_to_education | reasons={reasons} criteria_met={met_criteria_count}/4")
        
        return {
            'should_demote': should_demote,
            'target_section': target_section,
            'confidence_penalty': confidence_penalty,
            'reasons': reasons,
            'quality_score': max(0.0, 1.0 - confidence_penalty)
        }


# Alias pour compatibilité avec l'interface attendue


# === NEW: Anti-Contamination Guards ===

def looks_like_email(text: str) -> bool:
    """Check if text looks like an email address."""
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    return bool(re.search(email_pattern, text, re.IGNORECASE))


def looks_like_phone(text: str) -> bool:
    """Check if text looks like a phone number."""
    # Exclude date ranges like "2020 - 2023" or "2020-2023"
    if re.match(r'^\d{4}\s*-\s*\d{4}$', text.strip()):
        return False
    
    phone_patterns = [
        r'\+\d[\d\s\(\)\-\.]{7,19}',  # International format starting with +
        r'\b0\d[\d\s\-\.]{8,15}\b',   # National format starting with 0
        r'\(\d{2,4}\)[\s\-\.]\d{2,4}[\s\-\.]\d{2,4}',  # Parenthesized area code
        r'\b\d{3}[\.\-]\d{3}[\.\-]\d{4}\b',  # US format like 555.123.4567 or 555-123-4567
        r'\b\d{2,3}[\s\-\.]\d{2,3}[\s\-\.]\d{2,3}[\s\-\.]\d{2,3}\b'  # General format but not years
    ]
    
    for pattern in phone_patterns:
        if re.search(pattern, text):
            # Additional check to avoid year ranges
            match = re.search(pattern, text)
            matched_text = match.group(0)
            # If it's all 4-digit numbers, likely a year range
            if all(len(part.strip()) == 4 for part in re.split(r'[\s\-\.]', matched_text) if part.strip().isdigit()):
                continue
            return True
    return False


def looks_like_url_or_domain(text: str) -> bool:
    """Check if text looks like a URL or domain."""
    url_patterns = [
        r'https?://[^\s]+',
        r'www\.[^\s]+',
        r'\b[a-zA-Z0-9-]+\.[a-zA-Z]{2,}\b'  # domain.tld
    ]
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in url_patterns)



LANGUAGE_CERT_KEYWORDS = {
    "niveau", "certificat", "certification", "score", "language", "langue",
    "toefl", "toeic", "ielts", "cambridge", "bulats", "first", "cpe", "cae",
    "delf", "dalf", "tcf", "tef", "dele", "siele", "goethe", "testdaf",
    "plida", "cils", "celi", "jlpt", "hsk", "topik", "torfl"
}

LANGUAGE_LEVEL_TOKENS = ("a1", "a2", "b1", "b2", "c1", "c2")


def looks_like_language_certificate(text: str) -> bool:
    """Heuristic to detect language proficiency statements (CEFR levels, exams)."""
    if not text:
        return False

    lowered = text.lower()

    if 'b2b' in lowered or 'b2c' in lowered:
        lowered = lowered.replace('b2b', '').replace('b2c', '')

    if any(keyword in lowered for keyword in LANGUAGE_CERT_KEYWORDS):
        return True

    if 'niveau' in lowered and any(token in lowered for token in LANGUAGE_LEVEL_TOKENS):
        return True

    if any(token in lowered for token in LANGUAGE_LEVEL_TOKENS) and any(trigger in lowered for trigger in ("obtention", "score", "certificat", "certificate")):
        return True

    if re.search(r'\b[abcABC][12]\b', text):
        return True

    return False



def has_tld_suffix(text: str) -> bool:
    """Check if text ends with a simple TLD (top-level domain) suffix.

    Multi-level country-code endings (e.g. ".co.uk") are treated as full domains and rejected,
    because they almost always indicate a URL rather than a company name token.
    """
    if not text:
        return False

    candidate = text.strip().lower()
    if not candidate or " " in candidate:
        return False

    # Reject compound endings such as .co.uk or .gov.in
    if re.search(r"\.[a-z]{2,4}\.[a-z]{2,4}$", candidate):
        return False

    common_tlds = {
        'com', 'org', 'net', 'edu', 'gov', 'mil', 'int', 'co', 'uk', 'ca', 'au', 'de', 'fr', 'es',
        'it', 'nl', 'be', 'ch', 'at', 'se', 'no', 'dk', 'fi', 'pl', 'ru', 'jp', 'cn', 'kr', 'in',
        'br', 'mx', 'ar', 'cl', 'pe', 'co', 'info', 'biz', 'name', 'pro', 'tv', 'cc', 'ws', 'io'
    }

    match = re.search(r"\.([a-z]{2,4})$", candidate)
    if not match:
        return False

    tld = match.group(1)
    return tld in common_tlds



def looks_like_email_localpart(text: str) -> bool:
    """Check if text looks like an email local-part (before @) that got separated."""
    # Typical patterns of email local-parts
    if len(text) < 3:
        return False
    
    # Contains typical email username patterns
    email_patterns = [
        r'^[a-zA-Z]+\.[a-zA-Z]+$',  # firstname.lastname
        r'^[a-zA-Z]+\d+$',          # name123
        r'^[a-zA-Z]+_[a-zA-Z]+$',   # name_surname
        r'^[a-zA-Z]+[-][a-zA-Z]+$'  # name-surname
    ]
    
    return any(re.match(pattern, text) for pattern in email_patterns)


def has_org_shape(token: str) -> bool:
    """Check if token has organization-like characteristics."""
    if len(token) < DEFAULT_EXTRACTION_THRESHOLDS.MIN_COMPANY_TOKEN_LENGTH:
        return False
    
    # Reject if looks like email domain
    if '.' in token and looks_like_url_or_domain(token):
        return False
    
    # Reject if contains @ symbol (email fragments)
    if '@' in token:
        return False
    
    # Check for organization indicators
    org_indicators = [
        'inc', 'ltd', 'corp', 'company', 'groupe', 'group', 'sa', 'sarl',
        'gmbh', 'bv', 'ag', 'spa', 'srl', 'pty', 'llc', 'organization'
    ]
    
    token_lower = token.lower()
    has_org_indicator = any(indicator in token_lower for indicator in org_indicators)
    
    # Accept if has organization indicator or is reasonably long
    return has_org_indicator or len(token) >= 3


def is_valid_company_token(token: str, context: Dict[str, Any]) -> bool:
    """Validate if token is acceptable as company name."""
    cfg = DEFAULT_EXTRACTION_THRESHOLDS
    strict_mode = context.get('strict_validation', False)
    
    # Email rejection (always strict)
    if cfg.DENY_EMAIL_AS_COMPANY and looks_like_email(token):
        logger.debug(f"CONTAMINATION_GUARD: email_rejected_as_company | token='[REDACTED]'")
        return False
    
    # URL/domain rejection (always strict)
    if cfg.DENY_URL_TOKENS_IN_COMPANY and looks_like_url_or_domain(token):
        logger.debug(f"CONTAMINATION_GUARD: url_domain_rejected_as_company | token='[REDACTED]'") 
        return False
    
    # Enhanced domain-like token rejection with TLD detection
    if strict_mode and has_tld_suffix(token):
        logger.debug(f"CONTAMINATION_GUARD: tld_suffix_rejected_as_company | token='[REDACTED]'")
        return False
    
    # Reject bare email local-parts (username without @)
    if strict_mode and looks_like_email_localpart(token):
        logger.debug(f"CONTAMINATION_GUARD: email_localpart_rejected_as_company | token='[REDACTED]'")
        return False
    
    # Basic organization shape validation
    return has_org_shape(token)


def discard_contact_lines(line: str) -> bool:
    """Check if line should be discarded as contact information."""
    cfg = DEFAULT_EXTRACTION_THRESHOLDS
    
    if cfg.DENY_EMAIL_AS_COMPANY and looks_like_email(line):
        return True
    
    if cfg.DENY_PHONE_LINES_IN_EXP and looks_like_phone(line):
        return True
    
    if cfg.DENY_URL_TOKENS_IN_COMPANY and looks_like_url_or_domain(line):
        return True
    
    return False


def has_date_nearby(candidate: Dict[str, Any], context: Dict[str, Any], k: int = 5) -> bool:
    """Check if candidate has a date within k lines."""
    lines = context.get('text_lines', [])
    source_line_idx = candidate.get('source_line_idx', -1)
    
    if source_line_idx < 0 or source_line_idx >= len(lines):
        return False
    
    # Define date patterns
    date_patterns = [
        r'\b\d{4}\b',  # Year
        r'\b\d{1,2}[-/\.]\d{1,2}[-/\.]\d{2,4}\b',  # DD/MM/YYYY
        r'\b\d{1,2}[-/\.]\d{4}\b',  # MM/YYYY
        r'\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{2,4}\b',  # Mon YYYY
        r'\b\d{2,4}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b',  # YYYY Mon
        r'\b(depuis|since|from|à|to|until|présent|present|current|actuel)\b'
    ]
    
    # Check within window
    start_idx = max(0, source_line_idx - k)
    end_idx = min(len(lines), source_line_idx + k + 1)
    
    for i in range(start_idx, end_idx):
        line = lines[i].lower()
        for pattern in date_patterns:
            if re.search(pattern, line, re.IGNORECASE):
                logger.debug(f"DATE_PROXIMITY: found_date | line={i} | pattern_matched")
                return True
    
    return False


def accept_experience(candidate: Dict[str, Any], context: Dict[str, Any]) -> bool:
    """Apply acceptance gates for experience candidates."""
    cfg = DEFAULT_EXTRACTION_THRESHOLDS
    
    # Date proximity gate
    if cfg.MIN_DATE_PRESENCE_REQUIRED:
        if not has_date_nearby(candidate, context, cfg.MIN_EXP_DATE_PROXIMITY_LINES):
            candidate["reject_reason"] = "no_date_proximity"
            logger.debug(f"EXP_GATE: rejected_no_date_proximity | source_line={candidate.get('source_line_idx', -1)}")
            return False
    
    # Basic quality gates
    title = candidate.get('title', '')
    company = candidate.get('company', '')
    
    if len(title) < cfg.MIN_TITLE_TOKEN_LENGTH or len(company) < cfg.MIN_COMPANY_TOKEN_LENGTH:
        candidate["reject_reason"] = "insufficient_content_length"
        return False
    
    # Company token validation
    if not is_valid_company_token(company, context):
        candidate["reject_reason"] = "invalid_company_token"
        return False
    
    return True


def iter_experience_candidate_windows(lines: List[str], context: Dict[str, Any]):
    """Iterate over experience candidate windows, respecting contact quarantine."""
    cfg = DEFAULT_EXTRACTION_THRESHOLDS
    quarantine_zones = context.get('contact_quarantine_zones', [])
    post_buffer = cfg.CONTACT_POST_BUFFER_LINES
    
    # Expand quarantine zones with post-buffer
    expanded_zones = []
    for start, end in quarantine_zones:
        expanded_zones.append((start, end + post_buffer))
    
    window_size = context.get('window_size', 5)
    
    for i in range(len(lines)):
        # Check if window overlaps with quarantine zones
        window_start = i
        window_end = min(i + window_size, len(lines))
        
        # Skip if window overlaps with any expanded quarantine zone
        skip_window = False
        for qz_start, qz_end in expanded_zones:
            if not (window_end <= qz_start or window_start >= qz_end):  # Overlaps
                skip_window = True
                break
        
        if not skip_window:
            yield (window_start, window_end)


def finalize_experiences(items: List[Dict[str, Any]], context: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Finalize experience items with pattern diversity and deduplication."""
    if not items:
        return items
    
    cfg = DEFAULT_EXTRACTION_THRESHOLDS
    
    # Calculate pattern diversity
    pattern_counts = {}
    for item in items:
        pattern = item.get('source_pattern', 'unknown')
        pattern_counts[pattern] = pattern_counts.get(pattern, 0) + 1
    
    total_items = len(items)
    unique_patterns = len(pattern_counts)
    diversity = unique_patterns / total_items if total_items > 0 else 0.0
    
    # Apply diversity gate
    if diversity < cfg.MIN_PATTERN_DIVERSITY:
        context.setdefault('warnings', []).append(f"low_pattern_diversity={diversity:.2f}")
        logger.warning(f"PATTERN_DIVERSITY: low_diversity={diversity:.2f} | removing_title_company_patterns")
        
        # Remove title_company patterns that are likely over-permissive
        items = [item for item in items if item.get('source_pattern') != 'title_company']
    
    # Deduplication by key fields
    items = dedup_by(['title', 'company', 'start_date', 'end_date', 'current'], items)
    
    # Record metrics
    if 'metrics' in context:
        context['metrics']['pattern_diversity'] = diversity
        context['metrics']['final_experience_count'] = len(items)
    
    return items


def dedup_by(fields: List[str], items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Deduplicate items by specified fields."""
    seen_keys = set()
    unique_items = []
    
    for item in items:
        # Create key from specified fields
        key_parts = []
        for field in fields:
            value = item.get(field, '')
            if isinstance(value, str):
                key_parts.append(value.lower().strip())
            else:
                key_parts.append(str(value))
        
        key = tuple(key_parts)
        
        if key not in seen_keys:
            seen_keys.add(key)
            unique_items.append(item)
        else:
            logger.debug(f"DEDUP: duplicate_removed | fields={fields}")
    
    return unique_items


def commit_experience(item: Dict[str, Any], context: Dict[str, Any]) -> bool:
    """Commit experience item with oscillation guard."""
    # Create normalized key for deduplication
    title = normalize_text_for_matching(item.get('title', ''))
    company = normalize_text_for_matching(item.get('company', ''))
    start = str(item.get('start_date', ''))
    end = str(item.get('end_date', ''))
    current = bool(item.get('current', False))
    
    key = (title, company, start, end, current)
    
    # Check if already seen
    seen_keys = context.setdefault('exp_seen', set())
    if key in seen_keys:
        logger.debug(f"EXP_COMMIT: oscillation_guard_prevented_duplicate")
        return False  # Prevent re-adding same item
    
    # Add to seen keys and commit
    seen_keys.add(key)
    context.setdefault('committed_experiences', []).append(item)
    
    logger.debug(f"EXP_COMMIT: committed | title_len={len(item.get('title', ''))} company_len={len(item.get('company', ''))}")
    return True


def pattern_diversity(items: List[Dict[str, Any]]) -> float:
    """Calculate pattern diversity ratio."""
    if not items:
        return 0.0
    
    patterns = set(item.get('source_pattern', 'unknown') for item in items)
    return len(patterns) / len(items)



class PatternQualityAnalyzer:
    """Compatibility shim used by legacy tests."""

    def __init__(self) -> None:
        self.metrics = {}

    def evaluate(self, patterns: Iterable[str]) -> Dict[str, float]:
        count = len(list(patterns or []))
        score = min(count / 10.0, 1.0)
        self.metrics = {'count': count, 'score': score}
        return self.metrics
