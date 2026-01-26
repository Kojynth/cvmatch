"""
Extraction Thresholds Configuration
==================================

Single source of truth for deterministic offline extraction thresholds.
All values are configurable via environment variables for flexibility.

This module defines the core thresholds and gates used by the extraction
pipeline to prevent contamination, ensure quality, and maintain deterministic
behavior across runs.
"""

import os
from typing import Dict, Any, List
from dataclasses import dataclass


@dataclass
class ExtractionThresholds:
    """Centralized extraction thresholds configuration."""
    
    # === Contact Protection & Quarantine ===
    MIN_EXP_DATE_PROXIMITY_LINES: int = 5
    """±K lines around candidate must contain a valid date"""
    
    CONTACT_POST_BUFFER_LINES: int = 8
    """Lines after contact block not scanned for Experience"""
    
    DENY_EMAIL_AS_COMPANY: bool = True
    """Prevent email addresses from being extracted as company names"""
    
    DENY_URL_TOKENS_IN_COMPANY: bool = True
    """Prevent URL/domain tokens from being extracted as company names"""
    
    DENY_PHONE_LINES_IN_EXP: bool = True
    """Prevent phone number lines from being processed as experience"""
    
    MIN_DATE_PRESENCE_REQUIRED: bool = True
    """Hard gate for Experience acceptance - require nearby dates"""
    
    # === Pattern Quality Gates ===
    MIN_PATTERN_DIVERSITY: float = 0.30
    """Below this threshold → degrade to 'uncertain', do not commit"""
    
    MAX_CROSS_COLUMN_DISTANCE: int = 0
    """Forbid cross-column adjacency merges (0 = no cross-column)"""
    
    MIN_COMPANY_TOKEN_LENGTH: int = 2
    """Minimum length for valid company tokens"""
    
    MIN_TITLE_TOKEN_LENGTH: int = 3
    """Minimum length for valid title tokens"""
    
    # === Date Processing ===
    MIN_DATE_PRECISION: str = "year"
    """Minimum date precision required (year/month/day)"""
    
    DATE_PROXIMITY_WINDOW: int = 3
    """Window size for date proximity validation"""
    
    REQUIRE_DATE_FOR_CURRENT: bool = True
    """Require at least start date for current positions"""
    
    # === Section Analysis ===
    CONTACT_DENSITY_THRESHOLD: float = 0.6
    """Minimum contact token density to identify contact blocks"""
    
    TIMELINE_DENSITY_THRESHOLD: float = 0.45
    """Date/connector token density threshold for timeline detection"""
    
    HEADER_DETECTION_WINDOW: int = 10
    """Lines from document start to scan for headers"""
    
    SIDEBAR_WIDTH_RATIO: float = 0.25
    """Maximum width ratio for sidebar detection"""
    
    # === Experience Validation ===
    MIN_EXPERIENCE_SCORE: float = 0.5
    """Minimum score threshold for experience acceptance"""
    
    MAX_EXTRACTION_PASSES: int = 3
    """Maximum number of extraction passes to prevent loops"""
    
    DEDUP_SIMILARITY_THRESHOLD: float = 0.85
    """Similarity threshold for duplicate detection"""
    
    EXPERIENCE_CONTEXT_WINDOW: int = 5
    """Context window for experience validation"""
    
    # === Multilingual & Internationalization ===
    SCRIPT_DIRECTION_AUTO: bool = True
    """Auto-detect script direction (LTR/RTL)"""
    
    RTL_HEURISTICS: bool = True
    """Enable RTL-specific processing heuristics"""
    
    MULTILINGUAL_DATE_PARSING: bool = True
    """Enable multilingual date format parsing"""
    
    CJK_TEXT_PROCESSING: bool = True
    """Enable CJK (Chinese/Japanese/Korean) text processing"""
    
    # === Logging & Debugging ===
    MASK_PII_IN_LOGS: bool = True
    """Mask personally identifiable information in logs"""
    
    ENABLE_DETAILED_METRICS: bool = True
    """Enable detailed extraction metrics collection"""
    
    DEBUG_SECTION_BOUNDARIES: bool = False
    """Enable debug output for section boundary detection"""
    
    LOG_REJECTED_CANDIDATES: bool = False
    """Log rejected candidates for debugging (PII-safe)"""
    
    # === Performance ===
    MAX_DOCUMENT_LINES: int = 10000
    """Maximum document lines to process (prevents memory issues)"""
    
    CACHE_EXTRACTION_RESULTS: bool = True
    """Enable caching of extraction intermediate results"""
    
    BATCH_PROCESSING_SIZE: int = 100
    """Batch size for processing large documents"""
    
    @classmethod
    def from_env(cls) -> 'ExtractionThresholds':
        """Create configuration from environment variables."""
        return cls(
            MIN_EXP_DATE_PROXIMITY_LINES=int(os.environ.get('MIN_EXP_DATE_PROXIMITY_LINES', '5')),
            CONTACT_POST_BUFFER_LINES=int(os.environ.get('CONTACT_POST_BUFFER_LINES', '8')),
            DENY_EMAIL_AS_COMPANY=os.environ.get('DENY_EMAIL_AS_COMPANY', 'true').lower() == 'true',
            DENY_URL_TOKENS_IN_COMPANY=os.environ.get('DENY_URL_TOKENS_IN_COMPANY', 'true').lower() == 'true',
            DENY_PHONE_LINES_IN_EXP=os.environ.get('DENY_PHONE_LINES_IN_EXP', 'true').lower() == 'true',
            MIN_DATE_PRESENCE_REQUIRED=os.environ.get('MIN_DATE_PRESENCE_REQUIRED', 'true').lower() == 'true',
            MIN_PATTERN_DIVERSITY=float(os.environ.get('MIN_PATTERN_DIVERSITY', '0.30')),
            MAX_CROSS_COLUMN_DISTANCE=int(os.environ.get('MAX_CROSS_COLUMN_DISTANCE', '0')),
            MIN_COMPANY_TOKEN_LENGTH=int(os.environ.get('MIN_COMPANY_TOKEN_LENGTH', '2')),
            MIN_TITLE_TOKEN_LENGTH=int(os.environ.get('MIN_TITLE_TOKEN_LENGTH', '3')),
            MIN_DATE_PRECISION=os.environ.get('MIN_DATE_PRECISION', 'year'),
            DATE_PROXIMITY_WINDOW=int(os.environ.get('DATE_PROXIMITY_WINDOW', '3')),
            REQUIRE_DATE_FOR_CURRENT=os.environ.get('REQUIRE_DATE_FOR_CURRENT', 'true').lower() == 'true',
            CONTACT_DENSITY_THRESHOLD=float(os.environ.get('CONTACT_DENSITY_THRESHOLD', '0.6')),
            TIMELINE_DENSITY_THRESHOLD=float(os.environ.get('TIMELINE_DENSITY_THRESHOLD', '0.45')),
            HEADER_DETECTION_WINDOW=int(os.environ.get('HEADER_DETECTION_WINDOW', '10')),
            SIDEBAR_WIDTH_RATIO=float(os.environ.get('SIDEBAR_WIDTH_RATIO', '0.25')),
            MIN_EXPERIENCE_SCORE=float(os.environ.get('MIN_EXPERIENCE_SCORE', '0.5')),
            MAX_EXTRACTION_PASSES=int(os.environ.get('MAX_EXTRACTION_PASSES', '3')),
            DEDUP_SIMILARITY_THRESHOLD=float(os.environ.get('DEDUP_SIMILARITY_THRESHOLD', '0.85')),
            EXPERIENCE_CONTEXT_WINDOW=int(os.environ.get('EXPERIENCE_CONTEXT_WINDOW', '5')),
            SCRIPT_DIRECTION_AUTO=os.environ.get('SCRIPT_DIRECTION_AUTO', 'true').lower() == 'true',
            RTL_HEURISTICS=os.environ.get('RTL_HEURISTICS', 'true').lower() == 'true',
            MULTILINGUAL_DATE_PARSING=os.environ.get('MULTILINGUAL_DATE_PARSING', 'true').lower() == 'true',
            CJK_TEXT_PROCESSING=os.environ.get('CJK_TEXT_PROCESSING', 'true').lower() == 'true',
            MASK_PII_IN_LOGS=os.environ.get('MASK_PII_IN_LOGS', 'true').lower() == 'true',
            ENABLE_DETAILED_METRICS=os.environ.get('ENABLE_DETAILED_METRICS', 'true').lower() == 'true',
            DEBUG_SECTION_BOUNDARIES=os.environ.get('DEBUG_SECTION_BOUNDARIES', 'false').lower() == 'true',
            LOG_REJECTED_CANDIDATES=os.environ.get('LOG_REJECTED_CANDIDATES', 'false').lower() == 'true',
            MAX_DOCUMENT_LINES=int(os.environ.get('MAX_DOCUMENT_LINES', '10000')),
            CACHE_EXTRACTION_RESULTS=os.environ.get('CACHE_EXTRACTION_RESULTS', 'true').lower() == 'true',
            BATCH_PROCESSING_SIZE=int(os.environ.get('BATCH_PROCESSING_SIZE', '100'))
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary for JSON serialization."""
        return {
            'min_exp_date_proximity_lines': self.MIN_EXP_DATE_PROXIMITY_LINES,
            'contact_post_buffer_lines': self.CONTACT_POST_BUFFER_LINES,
            'deny_email_as_company': self.DENY_EMAIL_AS_COMPANY,
            'deny_url_tokens_in_company': self.DENY_URL_TOKENS_IN_COMPANY,
            'deny_phone_lines_in_exp': self.DENY_PHONE_LINES_IN_EXP,
            'min_date_presence_required': self.MIN_DATE_PRESENCE_REQUIRED,
            'min_pattern_diversity': self.MIN_PATTERN_DIVERSITY,
            'max_cross_column_distance': self.MAX_CROSS_COLUMN_DISTANCE,
            'min_company_token_length': self.MIN_COMPANY_TOKEN_LENGTH,
            'min_title_token_length': self.MIN_TITLE_TOKEN_LENGTH,
            'min_date_precision': self.MIN_DATE_PRECISION,
            'date_proximity_window': self.DATE_PROXIMITY_WINDOW,
            'require_date_for_current': self.REQUIRE_DATE_FOR_CURRENT,
            'contact_density_threshold': self.CONTACT_DENSITY_THRESHOLD,
            'timeline_density_threshold': self.TIMELINE_DENSITY_THRESHOLD,
            'header_detection_window': self.HEADER_DETECTION_WINDOW,
            'sidebar_width_ratio': self.SIDEBAR_WIDTH_RATIO,
            'min_experience_score': self.MIN_EXPERIENCE_SCORE,
            'max_extraction_passes': self.MAX_EXTRACTION_PASSES,
            'dedup_similarity_threshold': self.DEDUP_SIMILARITY_THRESHOLD,
            'experience_context_window': self.EXPERIENCE_CONTEXT_WINDOW,
            'script_direction_auto': self.SCRIPT_DIRECTION_AUTO,
            'rtl_heuristics': self.RTL_HEURISTICS,
            'multilingual_date_parsing': self.MULTILINGUAL_DATE_PARSING,
            'cjk_text_processing': self.CJK_TEXT_PROCESSING,
            'mask_pii_in_logs': self.MASK_PII_IN_LOGS,
            'enable_detailed_metrics': self.ENABLE_DETAILED_METRICS,
            'debug_section_boundaries': self.DEBUG_SECTION_BOUNDARIES,
            'log_rejected_candidates': self.LOG_REJECTED_CANDIDATES,
            'max_document_lines': self.MAX_DOCUMENT_LINES,
            'cache_extraction_results': self.CACHE_EXTRACTION_RESULTS,
            'batch_processing_size': self.BATCH_PROCESSING_SIZE
        }


# Global default configuration instance
DEFAULT_EXTRACTION_THRESHOLDS = ExtractionThresholds.from_env()


# === Helper Functions ===

def get_threshold(key: str, default: Any = None) -> Any:
    """Get a threshold value by key name."""
    return getattr(DEFAULT_EXTRACTION_THRESHOLDS, key, default)


def update_threshold(key: str, value: Any) -> bool:
    """Update a threshold value dynamically."""
    if hasattr(DEFAULT_EXTRACTION_THRESHOLDS, key):
        setattr(DEFAULT_EXTRACTION_THRESHOLDS, key, value)
        return True
    return False


def validate_thresholds() -> List[str]:
    """Validate threshold configuration and return any warnings."""
    warnings = []
    
    cfg = DEFAULT_EXTRACTION_THRESHOLDS
    
    # Validate numeric ranges
    if cfg.MIN_PATTERN_DIVERSITY < 0.0 or cfg.MIN_PATTERN_DIVERSITY > 1.0:
        warnings.append("MIN_PATTERN_DIVERSITY should be between 0.0 and 1.0")
    
    if cfg.CONTACT_DENSITY_THRESHOLD < 0.0 or cfg.CONTACT_DENSITY_THRESHOLD > 1.0:
        warnings.append("CONTACT_DENSITY_THRESHOLD should be between 0.0 and 1.0")
    
    if cfg.TIMELINE_DENSITY_THRESHOLD < 0.0 or cfg.TIMELINE_DENSITY_THRESHOLD > 1.0:
        warnings.append("TIMELINE_DENSITY_THRESHOLD should be between 0.0 and 1.0")
    
    if cfg.MIN_EXP_DATE_PROXIMITY_LINES < 1:
        warnings.append("MIN_EXP_DATE_PROXIMITY_LINES should be at least 1")
    
    if cfg.CONTACT_POST_BUFFER_LINES < 0:
        warnings.append("CONTACT_POST_BUFFER_LINES should be non-negative")
    
    if cfg.MAX_EXTRACTION_PASSES < 1:
        warnings.append("MAX_EXTRACTION_PASSES should be at least 1")
    
    if cfg.MIN_DATE_PRECISION not in ['year', 'month', 'day']:
        warnings.append("MIN_DATE_PRECISION should be 'year', 'month', or 'day'")
    
    # Performance warnings
    if cfg.MAX_DOCUMENT_LINES > 50000:
        warnings.append("MAX_DOCUMENT_LINES is very high - may cause memory issues")
    
    if cfg.BATCH_PROCESSING_SIZE < 10:
        warnings.append("BATCH_PROCESSING_SIZE is very low - may impact performance")
    
    return warnings


# === Contact Token Patterns ===

EMAIL_PATTERNS = [
    r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
    r'\b[A-Za-z0-9._%+-]+\s*@\s*[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
]

PHONE_PATTERNS = [
    r'\+?[\d\s\(\)\-\.]{8,20}',
    r'\b\d{2,4}[\s\-\.]\d{2,4}[\s\-\.]\d{2,4}[\s\-\.]\d{2,4}\b',
    r'\(\d{2,4}\)[\s\-\.]\d{2,4}[\s\-\.]\d{2,4}'
]

URL_PATTERNS = [
    r'https?://[^\s]+',
    r'www\.[^\s]+',
    r'\b[a-zA-Z0-9-]+\.[a-zA-Z]{2,}(?:/[^\s]*)?\b'
]

# === Multilingual Keywords ===

EXPERIENCE_SECTION_KEYWORDS = {
    'french': [
        'expérience', 'expériences', 'professionnel', 'professionnelle', 
        'emploi', 'emplois', 'poste', 'postes', 'carrière', 'travail', 
        'parcours professionnel'
    ],
    'english': [
        'experience', 'experiences', 'employment', 'work', 'career', 
        'job', 'jobs', 'professional', 'work experience', 'employment history'
    ],
    'spanish': [
        'experiencia', 'experiencia profesional', 'trabajo', 'empleo', 'carrera'
    ],
    'german': [
        'erfahrung', 'berufserfahrung', 'arbeit', 'beschäftigung', 'karriere'
    ],
    'portuguese': [
        'experiência', 'experiência profissional', 'trabalho', 'emprego', 'carreira'
    ],
    'italian': [
        'esperienza', 'lavoro', 'impiego', 'carriera'
    ],
    'arabic': [
        'خبرة', 'عمل', 'وظيفة', 'مهنة'
    ],
    'chinese': [
        '经验', '工作经验', '职业经历', '工作', '职位'
    ],
    'japanese': [
        '経験', '職歴', '仕事', '職業', '勤務'
    ]
}

PRESENT_TOKENS = {
    'french': ['présent', 'actuel', 'en cours', 'aujourd\'hui'],
    'english': ['present', 'current', 'now', 'today'],
    'spanish': ['presente', 'actual', 'ahora'],
    'german': ['gegenwart', 'aktuell', 'heute'],
    'portuguese': ['presente', 'atual', 'agora'],
    'italian': ['presente', 'attuale', 'ora'],
    'arabic': ['الآن', 'حالي', 'اليوم'],
    'chinese': ['至今', '现在', '当前'],
    'japanese': ['現在', '今', '現職']
}

# Validate configuration on import
_validation_warnings = validate_thresholds()
if _validation_warnings:
    import warnings
    for warning in _validation_warnings:
        warnings.warn(f"ExtractionThresholds: {warning}", UserWarning)