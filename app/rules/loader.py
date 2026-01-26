"""
Chargeur de règles JSON pour l'extraction CV.

Ce module charge les règles d'extraction depuis des fichiers JSON
avec cache et valeurs par défaut sécurisées.
"""

import json
from pathlib import Path
from typing import Dict, Any
from loguru import logger

# Cache global des règles chargées
_rules_cache: Dict[str, Dict[str, Any]] = {}

# Chemin du dossier des règles
RULES_DIR = Path(__file__).parent


def load_rules(name: str) -> Dict[str, Any]:
    """
    Charge les règles depuis un fichier JSON avec cache.
    
    Args:
        name: Nom du fichier de règles (sans extension .json)
        
    Returns:
        Dict contenant les règles ou valeurs par défaut si fichier absent
    """
    if name in _rules_cache:
        return _rules_cache[name]
    
    file_path = RULES_DIR / f"{name}.json"
    
    try:
        if file_path.exists():
            with open(file_path, 'r', encoding='utf-8') as f:
                rules = json.load(f)
            logger.debug(f"📋 Règles chargées depuis {file_path}")
        else:
            rules = _get_default_rules(name)
            logger.warning(f"⚠️ Fichier {file_path} absent, utilisation des défauts pour {name}")
        
        _rules_cache[name] = rules
        return rules
        
    except Exception as e:
        logger.error(f"❌ Erreur chargement règles {name}: {e}")
        rules = _get_default_rules(name)
        _rules_cache[name] = rules
        return rules


def _get_default_rules(name: str) -> Dict[str, Any]:
    """
    Retourne les règles par défaut pour un type donné.
    
    Args:
        name: Nom du type de règles
        
    Returns:
        Dict contenant les valeurs par défaut sécurisées
    """
    defaults = {
        "experience": {
            "non_pro_terms": [
                "natation", "fitness", "musculation", "course", "marathon", "trail",
                "randonnée", "voyage", "voyages", "photographie", "cinéma", "lecture",
                "piano", "guitare", "football", "basket", "tennis", "esport",
                "bénévolat", "club", "chorale", "théâtre", "année sabbatique", "sabbatique",
                "loisir", "loisirs", "hobby", "hobbies", "extra-professionnel", "extraprofessionnel"
            ],
            "employment_tokens": [
                "stage", "alternance", "cdi", "cdd", "freelance", "apprentissage",
                "internship", "contrat", "mission", "poste", "emploi", "travail",
                "salarié", "employee", "contractor", "consultant"
            ],
            "job_title_hints": [
                "développeur", "ingénieur", "consultant", "assistant", "manager",
                "stagiaire", "alternant", "chef", "responsable", "directeur",
                "analyste", "technicien", "administrateur", "coordinateur",
                "developer", "engineer", "analyst", "manager", "director",
                "intern", "trainee", "supervisor", "lead", "senior", "junior"
            ],
            "company_patterns": {
                "allow_acronyms": True,
                "allow_apostrophe_names": True,
                "legal_suffixes": ["SAS", "SASU", "SARL", "SA", "EURL", "Inc", "LLC", "Ltd", "GmbH", "AG", "Corp"],
                "two_capitalized_words": True
            },
            "address_ban_regex": "tel|téléphone|phone|rue|avenue|av\\.|bd|boulevard|cedex|\\d{5}|\\d{2}\\s*\\d{3}|street|road|address",
            "date_formats": [
                "yyyy–yyyy", "yyyy-yyyy", "yyyy - yyyy",
                "mm/yyyy–mm/yyyy", "mm/yyyy-mm/yyyy", "mm/yyyy - mm/yyyy",
                "dd/mm/yy–dd/mm/yyyy", "dd/mm/yyyy-dd/mm/yyyy",
                "mois yyyy – mois yyyy"
            ]
        },
        
        "volunteering": {
            "association_tokens": [
                "association", "asso", "club", "ong", "ngo", "croix-rouge", "secours",
                "humanitaire", "bénévole", "volontaire", "volunteer", "charity",
                "fondation", "foundation", "scouts", "rotary", "lions"
            ]
        },
        
        "education": {
            "degree_tokens": [
                "bachelor", "licence", "but", "bts", "dut", "master", "msc", "maîtrise",
                "doctorat", "phd", "mba", "cap", "bac", "baccalauréat", "diplôme",
                "certificat", "degree", "diploma", "formation"
            ],
            "school_tokens": [
                "université", "école", "lycée", "iut", "insa", "ens", "institut",
                "university", "school", "college", "institute", "academy",
                "faculté", "campus", "établissement"
            ],
            "ban_address_patterns": "tel|téléphone|phone|rue|avenue|av\\.|bd|boulevard|cedex|\\d{5}|\\d{2}\\s*\\d{3}|street|road|address",
            "ban_duration_words": ["semaine", "semaines", "week", "weeks", "jour", "jours", "day", "days"]
        },
        
        "projects": {
            "require_title_or_url": True,
            "bullet_markers": ["–", "-", "•", "*", "·"]
        },
        
        "certifications": {
            "whitelist": [
                "pix", "toeic", "toefl", "ielts", "cambridge", "azure", "aws", "gcp",
                "ccna", "pmp", "prince2", "itil", "scrum", "agile", "cisco",
                "microsoft", "google", "amazon", "oracle", "sap"
            ],
            "skill_blacklist": [
                "pack office", "microsoft office", "excel", "word", "powerpoint",
                "zoom", "teams", "skype", "outlook", "windows", "mac", "linux"
            ]
        },
        
        "languages": {
            "cefr_regex": "\\b(A1|A2|B1|B2|C1|C2)\\b",
            "lang_names": [
                "français", "anglais", "english", "japonais", "japanese",
                "espagnol", "spanish", "italien", "italian", "allemand", "german",
                "portugais", "portuguese", "chinois", "chinese", "mandarin",
                "arabe", "arabic", "russe", "russian"
            ],
            "level_words": {
                "courant": "C1?",
                "fluent": "C1?",
                "bilingue": "C2?",
                "native": "C2?",
                "natif": "C2?",
                "intermédiaire": "B1?",
                "intermediate": "B1?",
                "débutant": "A2?",
                "beginner": "A2?",
                "avancé": "B2?",
                "advanced": "B2?"
            }
        },
        
        "publications": {
            "strong_signals_regex": "doi:\\s*10\\.\\d{4,9}/\\S+|arxiv\\.org|hal\\.archives|researchgate\\.net|pubmed|springer|ieee|acm",
            "context_words": [
                "journal", "conférence", "conference", "article", "poster",
                "présentation", "publication", "paper", "proceedings", "symposium"
            ]
        },
        
        "soft_skills": [
            "pédagogue", "curieux", "rigoureux", "autonome", "proactif", "créatif",
            "esprit d'équipe", "leadership", "communication", "adaptable", "organisé",
            "persévérant", "analytique", "innovant", "collaboratif", "empathique",
            "motivé", "dynamique", "polyvalent", "réactif", "méthodique",
            "diplomatic", "patient", "flexible", "determined", "reliable"
        ]
    }
    
    return defaults.get(name, {})


def clear_cache():
    """Vide le cache des règles (utile pour les tests)."""
    global _rules_cache
    _rules_cache.clear()
    logger.debug("🧹 Cache des règles vidé")
