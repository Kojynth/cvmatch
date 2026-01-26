# PATCH-PII: Configuration de protection des données personnelles
from dataclasses import dataclass, field
from typing import List
import os

@dataclass
class PIIConfig:
    """Configuration pour la protection des données personnelles identifiables (PII)."""
    
    # Protection activée par défaut
    ENFORCED: bool = True
    
    # Clé de développement optionnelle pour démasquage local
    DEV_REVEAL_KEY: str | None = os.environ.get("PII_DEV_REVEAL_KEY", None)
    
    # Sel pour hachage stable et non ré-identifiant
    HASH_SALT: str = os.environ.get("PII_HASH_SALT", "cvmatch_local_salt_v1_2025")
    
    # Préfixe pour les tokens PII
    TOKEN_PREFIX: str = "PII"
    
    # Nombre maximum de caractères échantillons dans les logs
    MAX_SAMPLE_CHARS: int = 80
    
    # Langues supportées pour la détection PII
    LANGS: tuple[str, ...] = ("fr", "en", "es", "de", "ja", "zh", "ko", "ar", "he", "ru", "it", "pt", "nl")
    
    # Patterns supplémentaires pour OCR bruité
    OCR_NOISE_TOLERANCE: bool = True
    
    # Conservation de forme pour masquage (garder N premiers caractères)
    MASK_KEEP_CHARS: int = 2
    
    @classmethod
    def from_env(cls) -> 'PIIConfig':
        """Crée une configuration PII à partir des variables d'environnement."""
        return cls(
            ENFORCED=os.environ.get("PII_ENFORCED", "true").lower() == "true",
            DEV_REVEAL_KEY=os.environ.get("PII_DEV_REVEAL_KEY"),
            HASH_SALT=os.environ.get("PII_HASH_SALT", "cvmatch_local_salt_v1_2025"),
            TOKEN_PREFIX=os.environ.get("PII_TOKEN_PREFIX", "PII"),
            MAX_SAMPLE_CHARS=int(os.environ.get("PII_MAX_SAMPLE_CHARS", "80")),
            OCR_NOISE_TOLERANCE=os.environ.get("PII_OCR_TOLERANCE", "true").lower() == "true",
            MASK_KEEP_CHARS=int(os.environ.get("PII_MASK_KEEP_CHARS", "2"))
        )
    
    def is_dev_mode(self) -> bool:
        """Vérifie si le mode développement est activé via la clé de révélation."""
        return self.DEV_REVEAL_KEY is not None and len(self.DEV_REVEAL_KEY) > 0
    
    def should_redact(self) -> bool:
        """Détermine si la redaction PII doit être appliquée."""
        return self.ENFORCED and not self.is_dev_mode()

# Instance globale par défaut
DEFAULT_PII_CONFIG = PIIConfig.from_env()


@dataclass
class ContactProtectionConfig:
    """Configuration for contact/header line protection system."""
    
    # Enable/disable protection features
    enable_section_guards: bool = True
    enable_hardened_patterns: bool = True
    enable_domain_validation: bool = True
    enable_contact_protection: bool = True
    enable_duplicate_detection: bool = True
    
    # Hardened pattern settings
    require_spaced_at_for_role_company: bool = True
    exp_fallback_window_size: int = 30
    
    # Contact detection settings
    strict_header_block_protection: bool = True
    header_block_threshold: float = 0.7
    header_block_max_lines: int = 10
    address_min_words: int = 3
    
    # Domain validation settings
    extra_tlds: List[str] = field(default_factory=list)
    
    # Duplicate detection settings
    enable_deduplication_metrics: bool = True
    
    @classmethod
    def from_env(cls) -> 'ContactProtectionConfig':
        """Create configuration from environment variables."""
        return cls(
            enable_section_guards=os.environ.get("CONTACT_ENABLE_SECTION_GUARDS", "true").lower() == "true",
            enable_hardened_patterns=os.environ.get("CONTACT_ENABLE_HARDENED_PATTERNS", "true").lower() == "true",
            enable_domain_validation=os.environ.get("CONTACT_ENABLE_DOMAIN_VALIDATION", "true").lower() == "true",
            enable_contact_protection=os.environ.get("CONTACT_ENABLE_PROTECTION", "true").lower() == "true",
            enable_duplicate_detection=os.environ.get("CONTACT_ENABLE_DEDUP", "true").lower() == "true",
            require_spaced_at_for_role_company=os.environ.get("CONTACT_REQUIRE_SPACED_AT", "true").lower() == "true",
            exp_fallback_window_size=int(os.environ.get("CONTACT_EXP_FALLBACK_WINDOW", "30")),
            strict_header_block_protection=os.environ.get("CONTACT_STRICT_HEADER_BLOCK", "true").lower() == "true",
            header_block_threshold=float(os.environ.get("CONTACT_HEADER_BLOCK_THRESHOLD", "0.7")),
            header_block_max_lines=int(os.environ.get("CONTACT_HEADER_BLOCK_MAX_LINES", "10")),
            address_min_words=int(os.environ.get("CONTACT_ADDRESS_MIN_WORDS", "3")),
            extra_tlds=os.environ.get("CONTACT_EXTRA_TLDS", "").split(",") if os.environ.get("CONTACT_EXTRA_TLDS") else [],
            enable_deduplication_metrics=os.environ.get("CONTACT_ENABLE_DEDUP_METRICS", "true").lower() == "true"
        )

# Global contact protection configuration
DEFAULT_CONTACT_PROTECTION_CONFIG = ContactProtectionConfig.from_env()

# Feature flags compatibility function
def get_feature_flag(flag_name: str, default: bool = False) -> bool:
    """
    Compatibility function for feature flags access.
    
    Args:
        flag_name: The name of the feature flag to check
        default: Default value if flag is not found
    
    Returns:
        bool: The feature flag value
    """
    try:
        from .utils.feature_flags import is_feature_enabled
        
        # Map common flag names to their categories
        flag_mappings = {
            'boundary_guards_enabled': ('phases_a_to_h', 'boundary_guards_enabled'),
            'enhanced_extraction_pipeline': ('extraction_fixes', 'enhanced_extraction_pipeline'),
            'fallback_date_parser': ('extraction_fixes', 'fallback_date_parser'),
            'french_date_normalization_enabled': ('phases_a_to_h', 'french_date_normalization_enabled'),
            'org_sieve_filtering_enabled': ('phases_a_to_h', 'org_sieve_filtering_enabled'),
            'enable_qa_guardrails': ('experience_extraction', 'enable_qa_guardrails'),
            'enable_three_gate_validation': ('experience_extraction', 'enable_three_gate_validation'),
        }
        
        if flag_name in flag_mappings:
            category, actual_flag_name = flag_mappings[flag_name]
            return is_feature_enabled(category, actual_flag_name)
        else:
            # Try to find it in experience_extraction first
            if is_feature_enabled('experience_extraction', flag_name):
                return True
            # Then try other categories
            for category in ['performance', 'quality_guardrails', 'debugging', 'extraction_fixes', 'phases_a_to_h']:
                try:
                    return is_feature_enabled(category, flag_name)
                except:
                    continue
                    
        return default
        
    except ImportError:
        # Feature flags not available, return default
        return default
    except Exception:
        # Any other error, return default
        return default

# Configuration pour l'extraction d'expériences avec gestion des stages académiques
EXPERIENCE_CONF = {
    # Legacy compatibility
    "context_window": 5,
    "org_rebind_window": 6,
    "edu_header_guard": 5,
    "course_token_demote_min": 2,
    "edu_bias_near_header": 0.35,
    "min_action_verbs_for_strong_exp": 1,
    "date_overlap_iou_for_link": 0.30,
    "header_guard_distance": 5,  # Keep for compatibility
    "keyword_window": 4,
    "min_bullet_actions_for_exp": 2,
    "title_company_accept": True,
    "internship_override_requires_role_or_action": True,
    "confidence_penalty_missing_company": 0.15,
    
    # NEW THRESHOLDS AND GATES (from prompt requirements)
    # A) Boundary & Header-Conflict Guards
    "header_conflict_killradius_lines": 8,        # Terminate window expansion if education header within ±8 lines
    "max_cross_column_distance_lines": 2,        # Don't link entities across columns beyond 2 line gaps
    "sidebar_timeline_exclusion": True,          # Exclude timeline-like blocks unless tri-signal override
    "timeline_density_threshold": 0.45,          # >0.45 date/connector tokens per line = timeline
    "timeline_window_size": 4,                   # Analyze over 4-line windows
    
    # B) Experience Gates (tri-signal linkage)
    "tri_signal_window": 3,                      # At least 2 of {date, org, role} within 3-line span
    "tri_signal_min_signals": 2,                 # Minimum 2 signals required
    "tri_signal_require_date": True,             # At least 1 must be date
    "exp_gate_min": 0.55,                        # Below 0.55 mark as uncertain
    "min_desc_tokens": 6,                        # Unless internship with explicit employer+dates
    "pattern_diversity_floor": 0.30,             # Hard gate for pattern diversity
    "max_merge_expansions_multiplier": 2,       # Max merges = 2 × date_hit_count when diversity < threshold
    "education_proximity_guard_lines": 5,       # Check education tokens within ±5 lines
    "employment_keywords_score_min": 0.6,       # Required score unless employment keywords ≥ 0.6
    
    # C) Organization Rebinding (org_sieve)
    "nearest_valid_org_max_distance": 2,        # Search within 2 lines for valid org
    "employment_keyword_score_threshold": 0.5,   # If matched school + employment score < 0.5 = demote
    
    # D) Education Extractor & Dedup
    "edu_keep_rate_threshold": 0.10,            # If keep_rate < 0.10, enable second pass
    "edu_strong_signals_org_conf_min": 0.75,    # org_conf ≥ 0.75 for fallback_accept
    "edu_items_per_100_lines_max": 20,          # Cap total education items per 100 lines
    
    # E) Overfitting Enforcement
    "pattern_diversity_medium_alert": 0.30,     # MEDIUM alert threshold
    "pattern_diversity_hard_block": 0.20,       # HARD BLOCK threshold
    "pattern_diversity_enforce": False,          # Runtime flag to enable enforcement
    
    # F) New scoring and validation
    "min_date_precision": "month",              # Minimum date precision required
    "employment_score_window": 3,               # Window for employment keyword scoring
    "org_conf_min_fallback": 0.75,             # Minimum org confidence for fallback acceptance
}

# Lexiques pour la détection des institutions académiques et contexte
SCHOOL_TOKENS = [
    "école", "ecole", "lycée", "lycee", "université", "universite", 
    "faculté", "iut", "bts", "epsaa", "insa", "ensta", "ens", 
    "polytech", "isfac", "isep", "isima", "utc", "utbm", "utcl", 
    "grande école", "grande ecole", "supelec", "ensam", "epitech", 
    "supinfo", "efrei", "esme", "esiee", "epita", "iseg", "sorbonne"
]

# Tokens pour départements/laboratoires
DEPART_TOKENS = [
    "laboratoire", "laboratory", "lab", "département", "service", 
    "chaire", "umr", "ufr", "équipe", "equipe", "centre", "institut"
]

# Tokens de cours/matières académiques 
COURSE_TOKENS = [
    "cours", "matière", "matiere", "ects", "ue", "syllabus", 
    "professeur", "classe", "td", "tp", "examen", "partiels", 
    "bachelor", "licence", "master", "evaluation", "note", 
    "module", "semestre", "trimestre", "dissertation"
]

# Mots délivrables pour stages académiques
DELIVERABLE_TOKENS = [
    "rapport", "prototype", "déploiement", "deploiement", "poc", 
    "stage", "mémoire", "memoire", "soutenance", "présentation", 
    "presentation", "publication", "article", "implémentation", 
    "implementation", "développement", "developpement"
]

# Alias pour compatibilité
SCHOOL_BLACKLIST = SCHOOL_TOKENS

# Mots-clés d'emploi (permettent l'expérience)
EMPLOYMENT_KEYWORDS = [
    "stage", "stagiaire", "alternance", "apprentissage", "apprenti",
    "cdd", "cdi", "freelance", "indépendant", "mission", "intérim",
    "consultant", "temps plein", "temps partiel", "contrat", "emploi",
    "poste", "salarié", "travail", "job",
    "développeur", "developpeur", "équipe", "equipe"
]

# Certifications canoniques
CERT_CANON = [
    "pix", "toeic", "toefl", "ielts", "cambridge", "voltaire", "mooc", 
    "coursera", "openclassrooms", "aws certified", "azure", "gcp", 
    "scrum", "pmi", "prince2", "itil", "cisco", "microsoft", "google", 
    "oracle", "comptia", "ceh", "cissp", "pmp", "agile", "safe"
]

# Corrections typographiques des certifications
CERT_TYPO = {
    "tofl": "toefl", 
    "toelf": "toefl",
    "tofel": "toefl",
    "toeiff": "toefl",
    "cambrige": "cambridge", 
    "pix.": "pix",
    "toeic.": "toeic",
    "ielts.": "ielts",
    "comptia.": "comptia"
}

# Verbes d'action en français (normalisés) pour expériences légitimes
ACTION_VERBS_FR = [
    "développé", "developpe", "conçu", "concu", "implémenté", "implemente", 
    "géré", "gere", "piloté", "pilote", "assuré", "assure", "réalisé", "realise",
    "analysé", "analyse", "optimisé", "optimise", "maintenu", "industrialisé", 
    "industrialise", "documenté", "documente", "créé", "cree", "animé", "anime",
    "coordonné", "coordonne", "supervisé", "supervise", "encadré", "encadre",
    "formé", "forme", "participé", "participe", "collaboré", "collabore",
    "amélioré", "ameliore", "rédigé", "redige", "présenté", "presente", 
    "négocié", "negocie", "déployé", "deploye", "testé", "teste"
]
