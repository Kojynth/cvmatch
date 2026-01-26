"""
Experience Validation Module
===========================

Composable validators to prevent spurious experience creation from:
- Date-only tokens (07/06/22, 30/01/17)
- Education lines (Bachelor, EPSAA, Cambridge, TOEFL)
- Short acronyms (AEPCR, DASCO)  
- Inverted date ranges (end < start)

Implements 3-gate validation: company + title + context + dates
"""

import re
import unicodedata
from typing import List, Dict, Any, Optional, Tuple, Set
from pathlib import Path
from datetime import datetime

from ..logging.safe_logger import get_safe_logger
from ..config import DEFAULT_PII_CONFIG, EXPERIENCE_CONF, SCHOOL_TOKENS, EMPLOYMENT_KEYWORDS, ACTION_VERBS_FR
from .robust_date_parser import ParsedDate, DateType, parse_dates_with_validation
from .text_norm import normalize_text_for_matching

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


## centralized in text_norm.normalize_text_for_matching


class ExperienceValidator:
    """Validateur composable pour les extractions d'expériences."""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = dict(config or EXPERIENCE_CONF or {})
        self.logger = get_safe_logger(f"{__name__}.Validator", cfg=DEFAULT_PII_CONFIG)
        
        # Load education lexicon
        self._load_education_lexicon()
        
        # Load acronym policy
        self.acronym_allowlist = set(self.config.get("ACRONYM_ALLOWLIST", {"IBM", "SAP", "AWS", "BNP", "SNCF"}))
        self.acronym_max_length = self.config.get("ACRONYM_BLOCKLEN_MAX", 5)
        
        # Compile patterns for efficiency
        self._compile_patterns()
        
        # Enhanced strictness mode for better quality control
        self.strict_mode = self.config.get("STRICT_VALIDATION_MODE", True)
        self.min_confidence_strict = self.config.get("MIN_CONFIDENCE_STRICT", 0.7)
        self.min_confidence_normal = self.config.get("MIN_CONFIDENCE_NORMAL", 0.6)
        
        # Metrics tracking
        self.stats = {
            'total_validations': 0,
            'rejected_date_only': 0,
            'rejected_education_like': 0,
            'rejected_acronym_short': 0,
            'rejected_no_context': 0,
            'rejected_bad_dates': 0,
            'rejected_low_confidence': 0,
            'rejected_duplicate_content': 0,
            'rejected_insufficient_info': 0,
            'rejected_suspicious_patterns': 0,
            'accepted_count': 0,
            'avg_confidence': 0.0,
            'quality_distribution': {'high': 0, 'medium': 0, 'low': 0}
        }
    
    def _load_education_lexicon(self):
        """Charge le lexique des organisations éducatives."""
        self.education_keywords = set()
        
        # Base keywords from config
        base_keywords = SCHOOL_TOKENS + [
            # Degree keywords  
            "bachelor", "licence", "master", "bac", "bts", "dut",
            "bac stmg", "bac pro", "bac s", "bac es", "bac l",
            # Certifications often mistaken for companies
            "toefl", "toeic", "cambridge", "ielts", "voltaire", "pix",
            # Common French education terms
            "université", "école", "lycée", "collège", "institut",
            "formation", "diplôme", "certification", "niveau",
            # Specific institutions that create false positives
            "sorbonne", "epsaa", "insa", "ensta", "polytech", "epitech",
            "supinfo", "efrei", "esme", "esiee", "epita", "iseg"
        ]
        
        # Normalize and store
        for keyword in base_keywords:
            normalized = normalize_text_for_matching(keyword)
            self.education_keywords.add(normalized)
            
        # Try to load additional lexicon file if available
        lexicon_path = self.config.get("EDUCATION_LEXICON_PATH", "app/data/edu_org_lexicon.txt")
        try:
            if Path(lexicon_path).exists():
                with open(lexicon_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            normalized = normalize_text_for_matching(line)
                            self.education_keywords.add(normalized)
                self.logger.info(f"VALIDATION: loaded_education_lexicon | count={len(self.education_keywords)}")
        except Exception as e:
            self.logger.warning(f"VALIDATION: failed_to_load_lexicon | path={lexicon_path} error={e}")
    
    def _compile_patterns(self):
        """Compile regex patterns for performance."""
        # Enhanced date-only patterns (various formats)
        self.date_only_patterns = [
            re.compile(r'^\s*\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4}\s*$'),  # dd/mm/yy, dd-mm-yyyy
            re.compile(r'^\s*\d{1,2}[\/\-\.]\d{4}\s*$'),                    # mm/yyyy
            re.compile(r'^\s*\d{4}\s*$'),                                    # yyyy only
            re.compile(r'^\s*\d{1,2}[\/\-\.]\d{1,2}\s*$'),                 # dd/mm
            re.compile(r'^\s*\d{2,4}[\s\-–—]\d{2,4}\s*$'),                 # yyyy-yyyy, yy-yy
            # ENHANCED: French month names with years (problematic patterns from results)
            re.compile(r'^\s*(janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)\s+\d{4}\s*$', re.IGNORECASE),
            re.compile(r'^\s*\d{4}\s+(janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)\s*$', re.IGNORECASE),
            # English months
            re.compile(r'^\s*(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{4}\s*$', re.IGNORECASE),
            re.compile(r'^\s*\d{4}\s+(january|february|march|april|may|june|july|august|september|october|november|december)\s*$', re.IGNORECASE),
        ]
        
        # Work role/title patterns (positive indicators)
        work_role_patterns = [
            r'\b(stagiaire|alternant|apprenti|intern|assistant)\b',
            r'\b(développeur|developer|dev|engineer|ingénieur)\b', 
            r'\b(manager|chef|responsable|directeur|coordinator)\b',
            r'\b(consultant|technicien|analyste|specialist)\b',
            r'\b(designer|architect|lead|senior|junior)\b'
        ]
        
        self.work_role_pattern = re.compile('|'.join(work_role_patterns), re.IGNORECASE)
        
        # Short acronym pattern
        self.short_acronym_pattern = re.compile(r'^[A-Z]{2,' + str(self.acronym_max_length) + r'}$')
        
        # Enhanced validation patterns
        self.pure_numeric_pattern = re.compile(r'^\d+$')
        self.mixed_numeric_pattern = re.compile(r'^\d+[a-zA-Z]{0,2}$')  # 2023a, 123b, etc.
        
        # ENHANCED: Month-year patterns that are often false positives
        self.month_year_title_pattern = re.compile(
            r'^\s*(janvier|février|fevrier|mars|avril|mai|juin|juillet|aout|août|septembre|octobre|novembre|decembre|décembre|january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{4}\s*$', 
            re.IGNORECASE
        )
        
        # ENHANCED: Suspicious content patterns
        self.suspicious_patterns = [
            re.compile(r'^[^a-zA-Z]*$'),  # Only punctuation/numbers
            re.compile(r'^.{1,2}$'),      # Too short (1-2 chars)
            re.compile(r'^\d+[a-z]?$'),   # Just numbers with optional letter
            re.compile(r'^[A-Z]{2,6}$'),  # Short all-caps (likely acronyms)
            re.compile(r'^\W+$'),         # Only special characters
            re.compile(r'^(null|undefined|n/a|na|none|empty)$', re.IGNORECASE),
        ]
        
        # Content duplication patterns
        self.generic_titles = set([
            'stagiaire', 'intern', 'assistant', 'employee', 'worker',
            'stage', 'internship', 'work', 'job', 'poste', 'emploi'
        ])
        
        # Enhanced context indicators  
        self.strong_work_indicators = [
            r'\b(mission|projet|développement|création|gestion|management)\b',
            r'\b(responsable|chargé|en charge|lead|senior|junior)\b',
            r'\b(équipe|team|collaboration|partenariat)\b',
            r'\b(client|customer|utilisateur|user)\b',
            r'\b(budget|chiffre|objectif|résultat|performance)\b'
        ]
        
        self.strong_work_pattern = re.compile('|'.join(self.strong_work_indicators), re.IGNORECASE)
    
    def _is_education_keyword_match(self, normalized_text: str, edu_keyword: str) -> bool:
        """
        Détermine si un mot-clé d'éducation correspond vraiment au texte (évite faux positifs).
        
        Args:
            normalized_text: Texte normalisé à analyser
            edu_keyword: Mot-clé d'éducation à vérifier
            
        Returns:
            True si correspondance légitime, False pour faux positif
        """
        # Filtres pour éviter les faux positifs courants
        
        # 1. Mots-clés trop courts (1-2 chars) nécessitent correspondance exacte ou en début
        if len(edu_keyword) <= 2:
            # "x" (Polytechnique) ne doit matcher que si isolé ou en début
            words = normalized_text.split()
            return edu_keyword in words or normalized_text.startswith(edu_keyword + ' ')
        
        # 2. Mots-clés de 3 chars nécessitent bordures de mots
        elif len(edu_keyword) <= 3:
            import re
            pattern = r'\b' + re.escape(edu_keyword) + r'\b'
            return bool(re.search(pattern, normalized_text))
        
        # 3. Mots-clés plus longs peuvent utiliser la logique standard
        else:
            return edu_keyword in normalized_text or normalized_text.startswith(edu_keyword)
    
    def is_date_only_token(self, text: str) -> bool:
        """Vérifie si le texte est uniquement une date."""
        if not text or len(text.strip()) < 2:
            return False
            
        text = text.strip()
        
        for pattern in self.date_only_patterns:
            if pattern.match(text):
                self.logger.debug(f"VALIDATION: date_only_detected | text='{text}'")
                return True
        
        return False
    
    def _is_numeric_or_date_only(self, text: str) -> bool:
        """
        Enhanced numeric/date detection for hardened validation.
        
        Detects:
        - Pure numbers: 123, 2023, 456789
        - Mixed numeric: 2023a, 123b, 456c
        - Date patterns: dd/mm/yy, mm/yyyy, yyyy-mm-dd
        - Year ranges: 2020-2023, 21-22
        """
        if not text:
            return False
            
        text = text.strip()
        
        # Check pure numeric
        if self.pure_numeric_pattern.match(text):
            self.logger.debug(f"VALIDATION: pure_numeric_detected | text='{text}'")
            return True
        
        # Check mixed numeric (like 2023a, 123b)
        if self.mixed_numeric_pattern.match(text):
            self.logger.debug(f"VALIDATION: mixed_numeric_detected | text='{text}'")
            return True
        
        # Use existing date-only patterns
        return self.is_date_only_token(text)
    
    def _is_address_or_contact(self, text: str) -> bool:
        """Check if text looks like an address or contact info."""
        if not text:
            return False
        
        from .address_detector import get_address_detector
        detector = get_address_detector()
        is_address, _ = detector.is_address_or_contact(text)
        
        return is_address
    
    def _is_section_header(self, text: str) -> bool:
        """Check if text looks like a section header."""
        if not text:
            return False
            
        from .address_detector import get_address_detector
        detector = get_address_detector()
        is_header, _ = detector.is_section_header(text)
        
        return is_header
    
    def is_proper_company_name(self, company_text: str) -> Tuple[bool, List[str]]:
        """
        Valide si le texte est un nom d'entreprise plausible.
        
        Returns:
            (is_valid, rejection_reasons)
        """
        if not company_text:
            return False, ["empty_company"]
            
        company_text = company_text.strip()
        rejection_reasons = []
        
        # Check if it's a date-only token
        if self.is_date_only_token(company_text):
            rejection_reasons.append("company_is_date_only")
        
        # Enhanced education/school detection
        normalized_company = normalize_text_for_matching(company_text)
        
        # Check for pure numeric/date patterns first
        if self._is_numeric_or_date_only(company_text):
            rejection_reasons.append("company_is_numeric_or_date")
        
        # Check for addresses and contact info (from logs issue)
        if self._is_address_or_contact(company_text):
            rejection_reasons.append("company_is_address_or_contact")
        
        # Check for section headers
        if self._is_section_header(company_text):
            rejection_reasons.append("company_is_section_header")
        
        # Check education keywords (with hardened matching to avoid false positives)
        for edu_keyword in self.education_keywords:
            if self._is_education_keyword_match(normalized_company, edu_keyword):
                rejection_reasons.append("company_is_education")
                self.logger.debug(f"VALIDATION: company_education_match | company='{company_text[:20]}...' keyword='{edu_keyword}'")
                break
        
        # Check short acronyms (unless allowlisted)
        if self.short_acronym_pattern.match(company_text):
            if company_text.upper() not in self.acronym_allowlist:
                rejection_reasons.append("company_is_short_acronym")
                self.logger.debug(f"VALIDATION: company_short_acronym | text='{company_text}' not_in_allowlist")
        
        # Company must have minimum length and complexity
        if len(company_text) < 2:
            rejection_reasons.append("company_too_short")
        
        is_valid = len(rejection_reasons) == 0
        return is_valid, rejection_reasons
    
    def is_plausible_title(self, title_text: str) -> Tuple[bool, List[str]]:
        """
        Valide si le texte est un titre de poste plausible.
        
        Enhanced validation rejects:
        - Pure numeric tokens (123, 2023, etc.)
        - Date-only patterns (07/06/22, 30/01/17, etc.)
        - Month-year patterns (Janvier 2021, Mars 2022, etc.) - NEW HARDENING
        - Education markers without clear role indication
        - Titles that lack employment context indicators
        
        Returns:
            (is_valid, rejection_reasons)
        """
        if not title_text:
            return False, ["empty_title"]
            
        title_text = title_text.strip()
        rejection_reasons = []
        
        # Enhanced numeric/date rejection
        if self._is_numeric_or_date_only(title_text):
            rejection_reasons.append("title_is_numeric_or_date")
        
        # HARDENED: Check for month-year patterns (major false positive source)
        if self.month_year_title_pattern.match(title_text):
            rejection_reasons.append("title_is_month_year_only")
            self.logger.debug(f"VALIDATION: title_month_year_rejected | title='{title_text}'")
        
        # Check for addresses and contact info (from logs issue)
        if self._is_address_or_contact(title_text):
            rejection_reasons.append("title_is_address_or_contact")
        
        # Check for section headers
        if self._is_section_header(title_text):
            rejection_reasons.append("title_is_section_header")
        
        # Check education keywords (with hardened matching to avoid false positives)
        normalized_title = normalize_text_for_matching(title_text)
        for edu_keyword in self.education_keywords:
            if self._is_education_keyword_match(normalized_title, edu_keyword):
                rejection_reasons.append("title_is_education")
                self.logger.debug(f"VALIDATION: title_education_match | title='{title_text[:20]}...' keyword='{edu_keyword}'")
                break
        
        # Check short acronyms (unless allowlisted)
        if self.short_acronym_pattern.match(title_text):
            if title_text.upper() not in self.acronym_allowlist:
                rejection_reasons.append("title_is_short_acronym")
        
        # HARDENED: Title should contain work-related terms (more restrictive)
        has_work_terms = self.work_role_pattern.search(title_text) is not None
        if not has_work_terms and len(title_text) < 15:  # Increased from 10 to 15 chars
            rejection_reasons.append("title_lacks_work_terms")
        
        # Title must have minimum length
        if len(title_text) < 2:
            rejection_reasons.append("title_too_short")
        
        is_valid = len(rejection_reasons) == 0
        return is_valid, rejection_reasons
    
    def should_route_to_education(self, title: str, company: str, context_lines: List[str] = None) -> Tuple[bool, str]:
        """
        Détermine si un élément devrait être routé vers la section éducation.
        
        Returns:
            (should_route, reason)
        """
        # Check if company name contains strong education indicators
        if company:
            company_normalized = normalize_text_for_matching(company)
            for edu_keyword in self.education_keywords:
                if self._is_education_keyword_match(company_normalized, edu_keyword):
                    return True, f"education_company_match:{edu_keyword}"
        
        # Check if title contains education/degree keywords
        if title:
            title_normalized = normalize_text_for_matching(title)
            degree_patterns = [
                'bachelor', 'licence', 'master', 'bac', 'bts', 'dut', 'diplome',
                'formation', 'etudes', 'cursus', 'ecole', 'universite'
            ]
            for degree in degree_patterns:
                if self._is_education_keyword_match(title_normalized, degree):
                    return True, f"education_title_match:{degree}"
        
        return False, ""
    
    def should_route_to_certification(self, title: str, company: str, context_lines: List[str] = None) -> Tuple[bool, str]:
        """
        Détermine si un élément devrait être routé vers la section certifications.
        NOTE: Cette fonction a priorité sur should_route_to_education pour éviter les conflits.
        
        Returns:
            (should_route, reason)
        """
        cert_keywords = [
            # Language certifications (high priority - often misrouted to education)
            'toefl', 'toeic', 'ielts', 'cambridge english', 'cambridge', 'voltaire', 'pix',
            # Cloud certifications
            'aws certified', 'aws solutions', 'azure', 'gcp', 'google cloud', 'google certified',
            # Tech certifications  
            'microsoft certified', 'oracle certified', 'cisco certified', 'comptia',
            # Project management
            'scrum master', 'scrum', 'pmi', 'prince2', 'itil', 'safe',
            # Security
            'ceh', 'cissp', 'cism', 'cisa', 
            # Other professional certs
            'certification', 'certified', 'certificate'
        ]
        
        # Check title first (higher priority)
        if title:
            title_normalized = normalize_text_for_matching(title)
            # Exact matches for key certifications
            for cert in ['toefl', 'toeic', 'ielts', 'voltaire', 'pix']:
                if cert == title_normalized.strip():
                    return True, f"certification_exact_match:{cert}"
            
            # Partial matches
            for cert in cert_keywords:
                if cert in title_normalized:
                    return True, f"certification_title_match:{cert}"
        
        # Check company/organization
        if company:
            company_normalized = normalize_text_for_matching(company)
            # Known certification bodies
            cert_orgs = ['educational testing service', 'cambridge assessment', 'ets global']
            for org in cert_orgs:
                if org in company_normalized:
                    return True, f"certification_org_match:{org}"
                    
            for cert in cert_keywords:
                if cert in company_normalized:
                    return True, f"certification_company_match:{cert}"
        
        return False, ""
    
    def _is_suspicious_content(self, text: str) -> Tuple[bool, List[str]]:
        """
        Enhanced suspicious content detection.
        
        Returns:
            (is_suspicious, reasons)
        """
        if not text:
            return True, ["empty_content"]
        
        text = text.strip()
        reasons = []
        
        # Check against suspicious patterns
        for pattern in self.suspicious_patterns:
            if pattern.match(text):
                reasons.append("matches_suspicious_pattern")
                break
        
        # Check for generic/placeholder content
        normalized = normalize_text_for_matching(text)
        if normalized in self.generic_titles:
            reasons.append("generic_title")
        
        # Check content richness (too simple)
        if len(set(text.lower().split())) < 2 and len(text) > 3:
            reasons.append("low_lexical_diversity")
        
        # Check for repeated characters (likely parsing artifacts)
        if len(text) > 3 and any(c * 3 in text for c in text):
            reasons.append("repeated_characters")
        
        is_suspicious = len(reasons) > 0
        return is_suspicious, reasons
    
    def _has_sufficient_information_density(self, title: str, company: str, 
                                          description: str = "") -> Tuple[bool, float]:
        """
        Check if the experience has sufficient information density.
        
        Returns:
            (has_sufficient_info, info_density_score)
        """
        total_chars = len(title or "") + len(company or "") + len(description or "")
        
        if total_chars < 10:
            return False, 0.1
        
        # Count meaningful tokens
        all_text = f"{title or ''} {company or ''} {description or ''}"
        tokens = [t for t in all_text.lower().split() if len(t) > 2]
        unique_tokens = set(tokens)
        
        if len(tokens) < 3:
            return False, 0.2
        
        if len(unique_tokens) < 2:
            return False, 0.3
        
        # Calculate information density
        density_score = min(1.0, len(unique_tokens) / max(len(tokens), 1))
        
        # Bonus for variety in field content
        field_count = sum(1 for field in [title, company, description] if field and field.strip())
        field_bonus = field_count * 0.1
        
        final_score = min(1.0, density_score + field_bonus)
        
        has_sufficient = final_score >= 0.4
        return has_sufficient, final_score
    
    def _detect_content_duplication(self, title: str, company: str) -> Tuple[bool, str]:
        """
        Detect if title and company have suspicious duplication.
        
        Returns:
            (is_duplicated, duplication_type)
        """
        if not title or not company:
            return False, ""
        
        title_norm = normalize_text_for_matching(title)
        company_norm = normalize_text_for_matching(company)
        
        # Exact duplication
        if title_norm == company_norm:
            return True, "exact_match"
        
        # Substantial overlap (>70%)
        title_words = set(title_norm.split())
        company_words = set(company_norm.split())
        
        if title_words and company_words:
            intersection = title_words.intersection(company_words)
            overlap_ratio = len(intersection) / min(len(title_words), len(company_words))
            
            if overlap_ratio > 0.7:
                return True, f"high_overlap_{overlap_ratio:.1f}"
        
        # Substring containment
        if len(title_norm) > 5 and title_norm in company_norm:
            return True, "title_in_company"
        
        if len(company_norm) > 5 and company_norm in title_norm:
            return True, "company_in_title"
        
        return False, ""
    
    def _calculate_temporal_quality_score(self, start_date: Optional[datetime], 
                                        end_date: Optional[datetime],
                                        is_current: bool = False) -> Tuple[float, List[str]]:
        """
        Enhanced temporal quality assessment.
        
        Returns:
            (quality_score, quality_indicators)
        """
        quality_score = 0.5  # Base score
        indicators = []
        
        current_date = datetime.now()
        
        if start_date:
            # Bonus for having start date
            quality_score += 0.2
            indicators.append("has_start_date")
            
            # Check if start date is reasonable
            years_from_now = (current_date - start_date).days / 365.25
            if 0 <= years_from_now <= 15:  # Reasonable work history span
                quality_score += 0.1
                indicators.append("reasonable_start_date")
            
            if end_date:
                # Bonus for complete date range
                quality_score += 0.2
                indicators.append("has_complete_range")
                
                # Duration assessment
                duration_years = (end_date - start_date).days / 365.25
                if 0.1 <= duration_years <= 5:  # Sweet spot duration
                    quality_score += 0.15
                    indicators.append("optimal_duration")
                elif duration_years < 0.1:
                    quality_score -= 0.1
                    indicators.append("very_short_duration")
                elif duration_years > 10:
                    quality_score -= 0.1
                    indicators.append("very_long_duration")
            
            elif is_current:
                # Bonus for current position
                quality_score += 0.1
                indicators.append("current_position")
        
        return min(1.0, quality_score), indicators
    
    def has_context_keywords(self, text_lines: List[str], target_line_idx: int, 
                           window: int = None) -> Tuple[bool, List[str]]:
        """
        Enhanced context keyword detection with stronger validation.
        
        Args:
            text_lines: Liste des lignes de texte
            target_line_idx: Index de la ligne cible  
            window: Taille de la fenêtre (défaut depuis config)
        
        Returns:
            (has_context, found_keywords)
        """
        if window is None:
            window = self.config.get("keyword_window", 4)
        
        start_idx = max(0, target_line_idx - window)
        end_idx = min(len(text_lines), target_line_idx + window + 1)
        
        found_keywords = []
        strong_indicators = []
        
        for i in range(start_idx, end_idx):
            if i >= len(text_lines):
                continue
                
            line_normalized = normalize_text_for_matching(text_lines[i])
            
            # Check employment keywords
            for keyword in EMPLOYMENT_KEYWORDS:
                keyword_normalized = normalize_text_for_matching(keyword)
                if keyword_normalized in line_normalized:
                    found_keywords.append(keyword)
                    
            # Check action verbs (additional context)
            for verb in ACTION_VERBS_FR:
                verb_normalized = normalize_text_for_matching(verb)
                if verb_normalized in line_normalized:
                    found_keywords.append(f"action:{verb}")
            
            # Check for strong work indicators (enhanced)
            if self.strong_work_pattern.search(line_normalized):
                strong_indicators.append(f"strong:{i-target_line_idx}")
        
        # Enhanced context evaluation
        has_basic_context = len(found_keywords) > 0
        has_strong_context = len(strong_indicators) > 0 or len(found_keywords) >= 2
        
        # Add strong indicators to found keywords
        found_keywords.extend(strong_indicators)
        
        # In strict mode, require stronger context
        if self.strict_mode:
            has_context = has_strong_context
        else:
            has_context = has_basic_context
        
        if has_context:
            self.logger.debug(f"VALIDATION: enhanced_context_found | line={target_line_idx} "
                            f"keywords={len(found_keywords)} strong={len(strong_indicators)} "
                            f"strict_mode={self.strict_mode}")
        
        return has_context, found_keywords
    
    def looks_like_education(self, line: str, context_lines: List[str] = None, 
                           line_idx: int = 0) -> Tuple[bool, List[str]]:
        """
        Détermine si une ligne ressemble à du contenu éducatif.
        
        Args:
            line: Ligne à analyser
            context_lines: Lignes de contexte pour analyse fenêtre
            line_idx: Index de la ligne dans le contexte
            
        Returns:
            (is_education, indicators_found)
        """
        indicators = []
        
        if not line:
            return False, indicators
            
        normalized_line = normalize_text_for_matching(line)
        
        # Check direct education keywords
        raw_indicator_added = False
        for edu_keyword in self.education_keywords:
            if edu_keyword in normalized_line:
                indicators.append(f"keyword:{edu_keyword}")
                if not raw_indicator_added:
                    indicators.append(f"keyword_line:{line.lower()}")
                    raw_indicator_added = True
        
        # Check context for education headers if available
        if context_lines and line_idx >= 0:
            education_headers = ["formation", "éducation", "education", "diplômes", "diplomes", "études", "etudes"]
            window = 3  # smaller window for header detection
            
            start_idx = max(0, line_idx - window)
            end_idx = min(len(context_lines), line_idx + window + 1)
            
            for i in range(start_idx, end_idx):
                if i >= len(context_lines):
                    continue
                    
                context_normalized = normalize_text_for_matching(context_lines[i])
                for header in education_headers:
                    if normalize_text_for_matching(header) in context_normalized:
                        indicators.append(f"header:{header}")
                        break
        
        is_education = len(indicators) > 0
        
        if is_education:
            self.logger.debug(f"VALIDATION: education_detected | line='{line[:30]}...' indicators={indicators}")
        
        return is_education, indicators
    
    def validate_dates_temporal_consistency(self, start_date: Optional[datetime], 
                                          end_date: Optional[datetime],
                                          is_current: bool = False) -> Tuple[bool, List[str], float]:
        """
        Valide la cohérence temporelle des dates.
        
        Returns:
            (is_valid, validation_issues, quality_score)
        """
        issues = []
        quality_score = 1.0
        
        if start_date and end_date:
            # Check for inverted dates (end before start)
            if end_date < start_date:
                issues.append("end_before_start")
                self.logger.debug(f"VALIDATION: date_inversion | start={start_date} end={end_date}")
                return False, issues, 0.0  # Hard reject
            
            # Check for reasonable duration (not too long)
            duration_years = (end_date - start_date).days / 365.25
            if duration_years > 20:
                issues.append("duration_too_long")
                quality_score *= 0.7
            
            # Bonus for reasonable duration
            if 0.1 <= duration_years <= 10:
                quality_score *= 1.1
        
        elif start_date and is_current:
            # Current position validation
            current_date = datetime.now()
            if start_date > current_date:
                issues.append("future_start_date")
                quality_score *= 0.5
                
        elif not start_date and not end_date:
            issues.append("no_dates")
            quality_score *= 0.3
        
        is_valid = "end_before_start" not in issues  # Only hard reject for inversion
        
        return is_valid, issues, min(quality_score, 1.0)
    
    def calculate_experience_confidence(self, company_valid: bool, company_reasons: List[str],
                                      title_valid: bool, title_reasons: List[str], 
                                      has_context: bool, context_keywords: List[str],
                                      date_quality_score: float) -> Tuple[float, Dict[str, Any]]:
        """
        Calcule le score de confiance global d'une expérience.
        
        Returns:
            (confidence_score, scoring_details)
        """
        score = 0.0
        details = {
            'company_score': 0.0,
            'title_score': 0.0, 
            'context_score': 0.0,
            'date_score': 0.0,
            'breakdown': {}
        }
        
        # HARDENED SCORING: Updated weights for better coverage while maintaining precision
        # Company validation (35% weight, reduced from 40%)
        if company_valid:
            details['company_score'] = 0.35
            score += 0.35
        details['breakdown']['company'] = {'valid': company_valid, 'reasons': company_reasons}
        
        # Title validation (25% weight, reduced from 30%)
        if title_valid:
            details['title_score'] = 0.25
            score += 0.25
        details['breakdown']['title'] = {'valid': title_valid, 'reasons': title_reasons}
        
        # Context keywords (30% weight, increased from 20% for better coverage)
        context_base_score = 0.30 if has_context else 0.0
        
        # Enhanced context scoring with more granular bonuses
        if has_context:
            # Bonus for multiple employment keywords
            employment_keywords_count = sum(1 for kw in context_keywords if not kw.startswith('action:'))
            if employment_keywords_count > 1:
                context_base_score *= 1.1
                
            # Bonus for action verbs (strong experience indicators)
            action_verbs_count = sum(1 for kw in context_keywords if kw.startswith('action:'))
            if action_verbs_count > 0:
                context_base_score *= 1.15
                
            # Bonus for diverse context (both employment + action indicators)
            if employment_keywords_count > 0 and action_verbs_count > 0:
                context_base_score *= 1.1
        
        context_score = min(context_base_score, 0.35)  # Cap at 35% to prevent over-weighting
        details['context_score'] = context_score
        score += context_score
        details['breakdown']['context'] = {
            'has_context': has_context, 
            'keywords': context_keywords,
            'employment_count': sum(1 for kw in context_keywords if not kw.startswith('action:')),
            'action_count': sum(1 for kw in context_keywords if kw.startswith('action:'))
        }
        
        # Date quality (10% weight, unchanged)
        date_score = 0.1 * date_quality_score
        details['date_score'] = date_score
        score += date_score
        details['breakdown']['dates'] = {'quality_score': date_quality_score}
        
        return min(score, 1.0), details
    
    def validate_experience_candidate(self, title: str, company: str, 
                                    text_lines: List[str], target_line_idx: int,
                                    start_date: Optional[datetime] = None,
                                    end_date: Optional[datetime] = None, 
                                    is_current: bool = False,
                                    date_text: Optional[str] = None,
                                    description: str = "") -> Dict[str, Any]:
        """
        Enhanced validation complete d'un candidat expérience avec validation stricte.
        
        Returns:
            Dict avec is_valid, confidence, rejection_reasons, validation_details, routing_decision
        """
        self.stats['total_validations'] += 1
        
        validation_result = {
            'is_valid': False,
            'confidence': 0.0,
            'rejection_reasons': [],
            'validation_details': {},
            'should_route_to_education': False,
            'should_route_to_certification': False,
            'routing_reason': '',
            'quality_category': 'low'
        }
        
        # Immediate routing (education/certifications) before heavy validation
        should_route_edu, edu_reason = self.should_route_to_education(title, company, text_lines)
        if should_route_edu:
            validation_result['should_route_to_education'] = True
            validation_result['routing_reason'] = edu_reason
            validation_result['rejection_reasons'].append("education_content_without_work_context")
            validation_result['rejection_reasons'].append(f"routed_to_education:{edu_reason}")
            return validation_result

        should_route_cert, cert_reason = self.should_route_to_certification(title, company, text_lines)
        if should_route_cert:
            validation_result['should_route_to_certification'] = True
            validation_result['routing_reason'] = cert_reason
            validation_result['rejection_reasons'].append(f"routed_to_certification:{cert_reason}")
            return validation_result

        # PHASE 0: Enhanced pre-validation checks
        # Check for suspicious content patterns first
        title_suspicious, title_suspicious_reasons = self._is_suspicious_content(title)
        if title_suspicious:
            validation_result['rejection_reasons'].extend([f"suspicious_title:{r}" for r in title_suspicious_reasons])
            self.stats['rejected_suspicious_patterns'] += 1
            return validation_result
        
        company_suspicious, company_suspicious_reasons = self._is_suspicious_content(company)
        if company_suspicious:
            validation_result['rejection_reasons'].extend([f"suspicious_company:{r}" for r in company_suspicious_reasons])
            self.stats['rejected_suspicious_patterns'] += 1
            return validation_result
        
        # Check for content duplication
        is_duplicated, duplication_type = self._detect_content_duplication(title, company)
        if is_duplicated:
            validation_result['rejection_reasons'].append(f"content_duplication:{duplication_type}")
            self.stats['rejected_duplicate_content'] += 1
            return validation_result
        
        # Check information density
        has_sufficient_info, info_density = self._has_sufficient_information_density(title, company, description)
        if not has_sufficient_info:
            validation_result['rejection_reasons'].append(f"insufficient_info_density:{info_density:.2f}")
            self.stats['rejected_insufficient_info'] += 1
            return validation_result
        
        # Gate 1: Company validation
        company_valid, company_reasons = self.is_proper_company_name(company)
        
        # Gate 2: Title validation  
        title_valid, title_reasons = self.is_plausible_title(title)
        
        # Gate 3: Context validation
        has_context, context_keywords = self.has_context_keywords(text_lines, target_line_idx)
        
        # Gate 4: Enhanced date validation with parsing
        date_valid = True
        date_issues = []
        date_quality = 1.0
        
        # If we have date_text, parse it with temporal validation
        if date_text:
            context_window = []
            if target_line_idx >= 0 and target_line_idx < len(text_lines):
                window_start = max(0, target_line_idx - 2)
                window_end = min(len(text_lines), target_line_idx + 3)
                context_window = text_lines[window_start:window_end]
            
            parsed_start, parsed_end, parsed_current, validation_flags = parse_dates_with_validation(
                date_text, context_window
            )
            
            # Use parsed dates if available
            if parsed_start:
                start_date = parsed_start
            if parsed_end:
                end_date = parsed_end
            if validation_flags.get('temporal_valid', True) == False:
                date_valid = False
            
            date_quality = validation_flags.get('quality_score', 1.0)
            date_issues = validation_flags.get('issues', [])
            
            self.logger.debug(f"VALIDATION: enhanced_date_parsing | valid={date_valid} quality={date_quality:.3f} issues={date_issues}")
        
        # Fallback to basic temporal validation if no enhanced parsing
        elif start_date or end_date:
            date_valid, date_issues, date_quality = self.validate_dates_temporal_consistency(
                start_date, end_date, is_current
            )
        
        # Early rejection for hard constraints
        if not date_valid and "end_before_start" in date_issues:
            validation_result['rejection_reasons'].append("temporal_inconsistency")
            self.stats['rejected_bad_dates'] += 1
            return validation_result
        
        # Check if looks like education content
        line_text = f"{title} {company}" if title and company else (title or company or "")
        is_education, edu_indicators = self.looks_like_education(
            line_text, text_lines, target_line_idx
        )
        
        if is_education and not has_context:
            validation_result['should_route_to_education'] = True
            validation_result['rejection_reasons'].append("education_content_without_work_context")
            self.stats['rejected_education_like'] += 1
            return validation_result
        
        # Enhanced date quality assessment
        temporal_quality, temporal_indicators = self._calculate_temporal_quality_score(
            start_date, end_date, is_current
        )
        
        # Override date_quality with enhanced temporal assessment
        date_quality = max(date_quality, temporal_quality)
        
        # Calculate confidence score with enhanced factors
        confidence, confidence_details = self.calculate_experience_confidence(
            company_valid, company_reasons, title_valid, title_reasons,
            has_context, context_keywords, date_quality
        )
        
        # Add information density bonus to confidence
        confidence *= (1.0 + (info_density - 0.4) * 0.2)  # Bonus up to 12%
        confidence = min(1.0, confidence)
        
        # Apply dynamic confidence threshold based on strictness mode
        if self.strict_mode:
            min_confidence = self.min_confidence_strict
        else:
            min_confidence = self.min_confidence_normal
        
        if confidence < min_confidence:
            validation_result['rejection_reasons'].append(f"low_confidence_{confidence:.2f}")
            validation_result['confidence'] = confidence
            validation_result['validation_details'] = confidence_details
            
            # Categorize rejections for metrics
            if not company_valid and "company_is_date_only" in company_reasons:
                self.stats['rejected_date_only'] += 1
            elif not company_valid and "company_is_short_acronym" in company_reasons:
                self.stats['rejected_acronym_short'] += 1  
            elif not has_context:
                self.stats['rejected_no_context'] += 1
            else:
                self.stats['rejected_low_confidence'] += 1
            
            return validation_result
        
        # Validation passed - determine quality category
        validation_result['is_valid'] = True
        validation_result['confidence'] = confidence
        validation_result['validation_details'] = confidence_details
        
        # Enhanced quality categorization
        if confidence >= 0.8:
            quality_category = 'high'
            self.stats['quality_distribution']['high'] += 1
        elif confidence >= 0.65:
            quality_category = 'medium'
            self.stats['quality_distribution']['medium'] += 1
        else:
            quality_category = 'low'
            self.stats['quality_distribution']['low'] += 1
        
        validation_result['quality_category'] = quality_category
        
        # Add detailed validation breakdown
        validation_result['validation_details'].update({
            'info_density': info_density,
            'temporal_quality': temporal_quality,
            'temporal_indicators': temporal_indicators,
            'strict_mode': self.strict_mode,
            'threshold_used': min_confidence
        })
        
        self.stats['accepted_count'] += 1
        
        # Update running average confidence
        if self.stats['accepted_count'] > 0:
            self.stats['avg_confidence'] = (
                (self.stats['avg_confidence'] * (self.stats['accepted_count'] - 1) + confidence) 
                / self.stats['accepted_count']
            )
        
        self.logger.debug(f"VALIDATION: experience_accepted_enhanced | confidence={confidence:.3f} "
                         f"quality={quality_category} info_density={info_density:.2f} "
                         f"title='{title[:20]}...' company='{company[:20]}...' "
                         f"strict_mode={self.strict_mode}")
        
        return validation_result
    
    def get_validation_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques de validation."""
        return dict(self.stats)
    
    def reset_stats(self):
        """Remet à zéro les statistiques."""
        for key in self.stats:
            if isinstance(self.stats[key], (int, float)):
                self.stats[key] = 0


# Default configuration for when config is None or invalid
DEFAULT_EXPERIENCE_VALIDATOR_CONFIG = {
    "STRICT_VALIDATION_MODE": True,
    "reject_date_only_titles": True,
    "reject_short_acronyms": True,
    "min_title_tokens": 2,
    "MIN_CONFIDENCE_STRICT": 0.7,
    "MIN_CONFIDENCE_NORMAL": 0.6,
    "keyword_window": 4,
    "ACRONYM_ALLOWLIST": {"IBM", "SAP", "AWS", "BNP", "SNCF"},
    "ACRONYM_BLOCKLEN_MAX": 4
}


class MinimalExperienceValidator:
    """Minimal fallback validator that only accepts candidates with basic requirements."""
    
    def __init__(self):
        self.logger = get_safe_logger(f"{__name__}.MinimalValidator", cfg=DEFAULT_PII_CONFIG)
        self.stats = {'total_validations': 0, 'accepted_count': 0, 'rejected_count': 0}
        
    def validate_experience_candidate(self, title: str, company: str, 
                                    text_lines: List[str], target_line_idx: int,
                                    start_date: Optional[datetime] = None,
                                    end_date: Optional[datetime] = None, 
                                    is_current: bool = False,
                                    date_text: Optional[str] = None,
                                    description: str = "") -> Dict[str, Any]:
        """Minimal validation: only requires (dates AND (role OR org))."""
        self.stats['total_validations'] += 1
        
        has_dates = bool(start_date or end_date or date_text)
        has_role = bool(title and title.strip())
        has_org = bool(company and company.strip())
        
        is_valid = has_dates and (has_role or has_org)
        
        if is_valid:
            self.stats['accepted_count'] += 1
        else:
            self.stats['rejected_count'] += 1
            
        result = {
            'is_valid': is_valid,
            'confidence': 0.6 if is_valid else 0.0,
            'rejection_reasons': [] if is_valid else ["minimal_requirements_not_met"],
            'validation_details': {
                'has_dates': has_dates,
                'has_role': has_role,
                'has_org': has_org,
                'fallback_validator': True
            },
            'should_route_to_education': False,
            'should_route_to_certification': False,
            'routing_reason': '',
            'quality_category': 'low' if is_valid else 'rejected'
        }
        
        self.logger.debug(f"MINIMAL_VALIDATION: {'accepted' if is_valid else 'rejected'} | "
                         f"dates={has_dates} role={has_role} org={has_org}")
        
        return result
    
    def get_validation_stats(self) -> Dict[str, Any]:
        return dict(self.stats)
    
    def reset_stats(self):
        for key in self.stats:
            self.stats[key] = 0


# Global validator instance
_validator_instance = None

def get_experience_validator(config: Dict[str, Any] = None) -> ExperienceValidator:
    """
    Retourne une instance globale du validateur avec fallback robuste.
    
    Args:
        config: Configuration du validateur. Si None, utilise DEFAULT_EXPERIENCE_VALIDATOR_CONFIG
        
    Returns:
        ExperienceValidator ou MinimalExperienceValidator en cas d'erreur
    """
    global _validator_instance
    
    if _validator_instance is None:
        # Use default config if None provided
        if config is None:
            config = DEFAULT_EXPERIENCE_VALIDATOR_CONFIG
            logger.info("VALIDATOR: using_default_config | reason=config_none")
        
        try:
            _validator_instance = ExperienceValidator(config)
            logger.info("VALIDATOR: initialized_successfully | type=ExperienceValidator")
        except Exception as e:
            logger.warning(f"VALIDATOR: fallback_to_minimal | error={str(e)} | "
                          f"config_keys={list(config.keys()) if config else 'None'}")
            _validator_instance = MinimalExperienceValidator()
    
    return _validator_instance
