"""
Module de normalisation et validation des certifications.

Fournit des fonctions pour canonicaliser les noms, normaliser les scores/niveaux,
valider la plausibilité des dates et dédupliquer les certifications.
"""

import re
import json
from typing import Dict, List, Any, Optional, Tuple, Set
from pathlib import Path
from datetime import datetime, date
from dataclasses import dataclass
from ..logging.safe_logger import get_safe_logger
from ..config import DEFAULT_PII_CONFIG
from ..utils.pii import validate_no_pii_leakage

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


@dataclass
class NormalizedCertification:
    """Structure d'une certification normalisée."""
    canonical_name: str
    original_text: str
    issuer: str = ""
    level: str = ""
    score: str = ""
    date: str = ""
    language: str = ""
    confidence_score: float = 0.0
    aliases: List[str] = None
    source: str = "cv"
    
    def __post_init__(self):
        if self.aliases is None:
            self.aliases = []


class CertificationNormalizer:
    """Normalisateur principal des certifications avec règles enhanced."""
    
    def __init__(self, rules_file: Optional[str] = None):
        """
        Initialise le normalisateur avec les règles de certification.
        
        Args:
            rules_file: Chemin vers le fichier de règles (optionnel)
        """
        self.rules = self._load_rules(rules_file)
        self.logger = get_safe_logger(f"{__name__}.CertificationNormalizer", cfg=DEFAULT_PII_CONFIG)
        
        # Construire les mappings rapides
        self._build_quick_lookup_maps()
    
    def _load_rules(self, rules_file: Optional[str] = None) -> Dict[str, Any]:
        """Charge les règles de certification."""
        if rules_file is None:
            rules_file = Path(__file__).parent.parent / "rules" / "certifications_enhanced.json"
        
        try:
            with open(rules_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"CERT_NORM: failed to load rules from {rules_file} | {e}")
            return {"language_certifications": {}, "technical_certifications": {}}
    
    def _build_quick_lookup_maps(self):
        """Construit les maps de lookup rapide pour la normalisation."""
        self.name_to_canonical = {}
        self.alias_to_canonical = {}
        self.issuer_patterns = {}
        self.score_ranges = {}
        
        # Parcourir toutes les certifications dans les règles
        for lang_family, lang_certs in self.rules.get("language_certifications", {}).items():
            for cert_key, cert_info in lang_certs.items():
                canonical = cert_info["canonical_name"]
                
                # Mapping nom canonique
                self.name_to_canonical[cert_key.lower()] = canonical
                self.name_to_canonical[canonical.lower()] = canonical
                
                # Mapping aliases
                for alias in cert_info.get("aliases", []):
                    self.alias_to_canonical[alias.lower()] = canonical
                
                # Mapping normalization spécifique
                for variant, normalized in cert_info.get("normalization", {}).items():
                    self.alias_to_canonical[variant.lower()] = canonical
                
                # Mapping issuer patterns
                issuer_info = cert_info.get("issuer", {})
                if issuer_info:
                    self.issuer_patterns[canonical] = issuer_info
                
                # Score ranges
                score_range = cert_info.get("score_range")
                if score_range:
                    self.score_ranges[canonical] = score_range
        
        # Même chose pour les certifications techniques
        for tech_family, tech_certs in self.rules.get("technical_certifications", {}).items():
            for cert_key, cert_info in tech_certs.items():
                canonical = cert_info["canonical_name"]
                
                self.name_to_canonical[cert_key.lower()] = canonical
                self.name_to_canonical[canonical.lower()] = canonical
                
                for alias in cert_info.get("aliases", []):
                    self.alias_to_canonical[alias.lower()] = canonical
                
                issuer_info = cert_info.get("issuer", {})
                if issuer_info:
                    self.issuer_patterns[canonical] = issuer_info
    
    def canonicalize_name(self, raw_text: str) -> Optional[str]:
        """
        Canonicalise le nom d'une certification.
        
        Args:
            raw_text: Texte brut potentiel
            
        Returns:
            Nom canonique ou None si non trouvé
        """
        if not raw_text:
            return None
        
        safe_text = validate_no_pii_leakage(raw_text, DEFAULT_PII_CONFIG.HASH_SALT)
        normalized = raw_text.lower().strip()
        
        # Recherche directe
        if normalized in self.name_to_canonical:
            canonical = self.name_to_canonical[normalized]
            self.logger.debug(f"CERT_CANON: direct_match | '{safe_text}' -> '{canonical}'")
            return canonical
        
        # Recherche par alias
        if normalized in self.alias_to_canonical:
            canonical = self.alias_to_canonical[normalized]
            self.logger.debug(f"CERT_CANON: alias_match | '{safe_text}' -> '{canonical}'")
            return canonical
        
        # Recherche par patterns partiels
        for alias, canonical in self.alias_to_canonical.items():
            if alias in normalized or normalized in alias:
                if len(alias) > 3 and len(normalized) > 3:  # Éviter les matches trop courts
                    self.logger.debug(f"CERT_CANON: partial_match | '{safe_text}' -> '{canonical}' via '{alias}'")
                    return canonical
        
        # Recherche par patterns regex pour cas complexes
        canonical = self._pattern_based_canonicalization(raw_text)
        if canonical:
            self.logger.debug(f"CERT_CANON: pattern_match | '{safe_text}' -> '{canonical}'")
            return canonical
        
        return None
    
    def _pattern_based_canonicalization(self, text: str) -> Optional[str]:
        """Canonicalisation basée sur les patterns regex."""
        text_lower = text.lower()
        
        # Patterns spécialisés pour certifications courantes
        patterns = [
            (r'\b(?:tofl|toefl)\b', 'TOEFL'),
            (r'\b(?:ielts)\b', 'IELTS'),
            (r'\bcambridge\s+(?:english|b2|c1|c2|first|advanced|proficiency)\b', 'Cambridge English'),
            (r'\b(?:delf|dalf)\b', 'DELF/DALF'),
            (r'\btoeic\b', 'TOEIC'),
            (r'\b(?:hsk)\b', 'HSK'),
            (r'\b(?:jlpt)\b', 'JLPT'),
            (r'\bgoethe\b', 'Goethe-Zertifikat'),
            (r'\b(?:aws|amazon\s+web\s+services)\b', 'AWS'),
            (r'\bazure\b', 'Microsoft Azure'),
            (r'\b(?:google\s+cloud|gcp)\b', 'Google Cloud'),
            (r'\bpmp\b', 'PMP')
        ]
        
        for pattern, canonical in patterns:
            if re.search(pattern, text_lower):
                return canonical
        
        return None
    
    def normalize_level(self, raw_level: str, cert_name: str) -> str:
        """
        Normalise le niveau d'une certification.
        
        Args:
            raw_level: Niveau brut
            cert_name: Nom canonique de la certification
            
        Returns:
            Niveau normalisé
        """
        if not raw_level:
            return ""
        
        level_lower = raw_level.lower().strip()
        
        # Normalisation par type de certification
        if "cambridge" in cert_name.lower() or "delf" in cert_name.lower() or "goethe" in cert_name.lower():
            # Certifications avec niveaux CECRL
            cecrl_patterns = [
                (r'\b([abc][12])\b', lambda m: m.group(1).upper()),
                (r'\bbeginner\b', 'A1'),
                (r'\belementary\b', 'A2'),
                (r'\bintermediate\b', 'B1'),
                (r'\bupper.?intermediate\b', 'B2'),
                (r'\badvanced\b', 'C1'),
                (r'\bproficiency\b', 'C2'),
                (r'\bfirst\b', 'B2'),
                (r'\bkey\b', 'A2'),
                (r'\bpreliminary\b', 'B1')
            ]
            
            for pattern, replacement in cecrl_patterns:
                match = re.search(pattern, level_lower)
                if match:
                    if callable(replacement):
                        return replacement(match)
                    else:
                        return replacement
        
        elif "jlpt" in cert_name.lower():
            # JLPT avec niveaux N1-N5
            jlpt_patterns = [
                (r'\b(?:level\s*)?n?([12345])\b', lambda m: f"N{m.group(1)}"),
                (r'\bn([12345])\b', lambda m: f"N{m.group(1)}")
            ]
            
            for pattern, replacement in jlpt_patterns:
                match = re.search(pattern, level_lower)
                if match:
                    return replacement(match)
        
        elif "hsk" in cert_name.lower():
            # HSK avec niveaux 1-6
            hsk_patterns = [
                (r'\b(?:hsk\s*)?([123456])\b', lambda m: f"HSK{m.group(1)}"),
                (r'\blevel\s*([123456])\b', lambda m: f"HSK{m.group(1)}")
            ]
            
            for pattern, replacement in hsk_patterns:
                match = re.search(pattern, level_lower)
                if match:
                    return replacement(match)
        
        # Si aucune normalisation spécialisée, retourner la version nettoyée
        return raw_level.upper().strip()
    
    def normalize_score(self, raw_score: str, cert_name: str) -> str:
        """
        Normalise et valide le score d'une certification.
        
        Args:
            raw_score: Score brut
            cert_name: Nom canonique de la certification
            
        Returns:
            Score normalisé et validé
        """
        if not raw_score:
            return ""
        
        # Extraction du score numérique
        score_match = re.search(r'(\d+(?:\.\d+)?)', raw_score)
        if not score_match:
            return ""
        
        try:
            score_value = float(score_match.group(1))
        except ValueError:
            return ""
        
        # Validation selon les plages connues
        score_range = self.score_ranges.get(cert_name.upper())
        if score_range:
            # IELTS (0-9 avec pas de 0.5)
            if "ielts" in cert_name.lower():
                if 0.0 <= score_value <= 9.0:
                    # Arrondir au 0.5 le plus proche
                    rounded = round(score_value * 2) / 2
                    return f"{rounded:.1f}".rstrip('0').rstrip('.')
            
            # TOEFL iBT (0-120)
            elif "toefl" in cert_name.lower():
                if isinstance(score_range, dict) and "ibt" in score_range:
                    ibt_range = score_range["ibt"]
                    if ibt_range["min"] <= score_value <= ibt_range["max"]:
                        return str(int(score_value))
            
            # TOEIC (10-990)
            elif "toeic" in cert_name.lower():
                if isinstance(score_range, dict) and "listening_reading" in score_range:
                    lr_range = score_range["listening_reading"]
                    if lr_range["min"] <= score_value <= lr_range["max"]:
                        return str(int(score_value))
        
        # Score générique si pas de validation spécifique
        if score_value == int(score_value):
            return str(int(score_value))
        else:
            return f"{score_value:.1f}".rstrip('0').rstrip('.')
    
    def validate_date_plausibility(self, date_str: str, profile_context: Optional[Dict] = None) -> bool:
        """
        Valide la plausibilité d'une date de certification.
        
        Args:
            date_str: Date à valider
            profile_context: Contexte du profil (optionnel)
            
        Returns:
            True si la date est plausible
        """
        if not date_str:
            return False
        
        # Extraction de l'année
        year_match = re.search(r'\b(\d{4})\b', date_str)
        if not year_match:
            return False
        
        try:
            cert_year = int(year_match.group(1))
        except ValueError:
            return False
        
        current_year = datetime.now().year
        
        # Validations de base
        if cert_year < 1990 or cert_year > current_year + 1:
            return False
        
        # Validations contextuelles si profil disponible
        if profile_context:
            # Vérifier cohérence avec âge approximatif
            birth_year = profile_context.get("birth_year")
            if birth_year and cert_year - birth_year < 10:
                self.logger.warning(f"CERT_DATE: implausible age | cert_year={cert_year} birth_year={birth_year}")
                return False
            
            # Vérifier cohérence avec expériences
            exp_years = profile_context.get("experience_years", [])
            if exp_years and cert_year > max(exp_years) + 5:
                self.logger.warning(f"CERT_DATE: future cert vs experience | cert_year={cert_year}")
                return False
        
        return True
    
    def merge_duplicates(self, certifications: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Fusionne les certifications en double.
        
        Args:
            certifications: Liste des certifications à dédupliquer
            
        Returns:
            Liste déduplicatée
        """
        if not certifications:
            return []
        
        # Grouper par nom canonique + niveau
        groups = {}
        for cert in certifications:
            canonical = self.canonicalize_name(cert.get("name", ""))
            if not canonical:
                continue
            
            level = cert.get("level", "")
            key = (canonical, level)
            
            if key not in groups:
                groups[key] = []
            groups[key].append(cert)
        
        # Fusionner chaque groupe
        merged = []
        for (canonical, level), cert_group in groups.items():
            if len(cert_group) == 1:
                merged.append(cert_group[0])
            else:
                merged_cert = self._merge_certification_group(cert_group)
                merged.append(merged_cert)
                
                self.logger.info(f"CERT_MERGE: merged {len(cert_group)} duplicates | "
                               f"canonical='{canonical}' level='{level}'")
        
        return merged
    
    def _merge_certification_group(self, cert_group: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Fusionne un groupe de certifications similaires."""
        # Prendre la certification avec le meilleur score de confiance
        best_cert = max(cert_group, key=lambda c: c.get("confidence_score", 0.0))
        merged = best_cert.copy()
        
        # Fusionner les champs manquants des autres certifications
        for cert in cert_group:
            if cert is best_cert:
                continue
            
            # Prendre les champs non vides des autres certifications
            for field in ["issuer", "score", "date", "language"]:
                if not merged.get(field) and cert.get(field):
                    merged[field] = cert[field]
            
            # Fusionner les alias
            if "aliases" not in merged:
                merged["aliases"] = []
            
            original_texts = [cert.get("original_text", "") for cert in cert_group if cert.get("original_text")]
            merged["aliases"].extend(original_texts)
        
        # Nettoyer les doublons dans les alias
        if merged.get("aliases"):
            merged["aliases"] = list(set(merged["aliases"]))
        
        return merged
    
    def extract_certification_from_text(self, text: str, context: Optional[Dict] = None) -> Optional[NormalizedCertification]:
        """
        Extrait et normalise une certification à partir d'un texte.
        
        Args:
            text: Texte à analyser
            context: Contexte additionnel (ligne, voisinage, etc.)
            
        Returns:
            Certification normalisée ou None
        """
        # Canonicalisation du nom
        canonical_name = self.canonicalize_name(text)
        if not canonical_name:
            return None
        
        # Extraction des détails
        score = self._extract_score(text, canonical_name)
        level = self._extract_level(text, canonical_name)
        date_str = self._extract_date(text, context)
        issuer = self._extract_issuer(text, canonical_name, context)
        language = self._infer_language(canonical_name)
        
        # Normalisation
        normalized_score = self.normalize_score(score, canonical_name)
        normalized_level = self.normalize_level(level, canonical_name)
        
        # Calcul de confiance
        confidence = self._calculate_confidence(canonical_name, issuer, normalized_level, 
                                              normalized_score, date_str, context)
        
        return NormalizedCertification(
            canonical_name=canonical_name,
            original_text=text,
            issuer=issuer,
            level=normalized_level,
            score=normalized_score,
            date=date_str,
            language=language,
            confidence_score=confidence,
            aliases=[text] if text != canonical_name else []
        )
    
    def _extract_score(self, text: str, cert_name: str) -> str:
        """Extrait le score du texte."""
        score_patterns = [
            r'score\s*[:=]?\s*(\d+(?:\.\d+)?)',
            r'(\d+(?:\.\d+)?)\s*/\s*(?:120|990|9)',
            r'band\s*[:=]?\s*(\d+(?:\.\d+)?)',
            r'result\s*[:=]?\s*(\d+(?:\.\d+)?)',
            r'(\d+(?:\.\d+)?)\s*(?:points?|pts)'
        ]
        
        for pattern in score_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)
        
        return ""
    
    def _extract_level(self, text: str, cert_name: str) -> str:
        """Extrait le niveau du texte."""
        level_patterns = [
            r'\b([ABC][12])\b',
            r'\b(N[12345])\b',
            r'\b(?:HSK\s*)?([123456])\b',
            r'\b(beginner|elementary|intermediate|upper.?intermediate|advanced|proficiency)\b',
            r'\b(first|preliminary|key)\b'
        ]
        
        for pattern in level_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)
        
        return ""
    
    def _extract_date(self, text: str, context: Optional[Dict] = None) -> str:
        """Extrait la date du texte ou contexte."""
        date_patterns = [
            r'\b(\d{1,2}/\d{1,2}/\d{4})\b',
            r'\b([A-Za-z]+\s+\d{4})\b',
            r'\b(\d{4})\b',
            r'(?:obtained|passed|achieved|earned)\s+(?:in\s+)?([A-Za-z]+\s+\d{4})',
            r'(?:obtenu|passé)\s+(?:en\s+)?([A-Za-z]+\s+\d{4})'
        ]
        
        # Recherche dans le texte principal
        for pattern in date_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)
        
        # Recherche dans le contexte si disponible
        if context and "context_lines" in context:
            context_text = " ".join(context["context_lines"])
            for pattern in date_patterns:
                match = re.search(pattern, context_text, re.IGNORECASE)
                if match:
                    return match.group(1)
        
        return ""
    
    def _extract_issuer(self, text: str, cert_name: str, context: Optional[Dict] = None) -> str:
        """Extrait l'émetteur du texte ou l'infère."""
        # Patterns d'émetteurs dans le texte
        issuer_patterns = [
            r'(?:by|from|issued by|certified by)\s+([A-Za-z\s]+)',
            r'(?:par|délivré par)\s+([A-Za-z\s]+)'
        ]
        
        for pattern in issuer_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        # Inférence basée sur le nom de certification
        issuer_info = self.issuer_patterns.get(cert_name)
        if issuer_info:
            return issuer_info.get("canonical", "")
        
        return ""
    
    def _infer_language(self, cert_name: str) -> str:
        """Infère la langue de la certification."""
        language_map = {
            "TOEFL": "English",
            "IELTS": "English", 
            "Cambridge English": "English",
            "TOEIC": "English",
            "DELF/DALF": "French",
            "TCF": "French",
            "Goethe-Zertifikat": "German",
            "JLPT": "Japanese",
            "HSK": "Chinese"
        }
        
        return language_map.get(cert_name, "")
    
    def _calculate_confidence(self, canonical: str, issuer: str, level: str, 
                            score: str, date: str, context: Optional[Dict] = None) -> float:
        """Calcule le score de confiance selon les règles enhanced."""
        weights = self.rules.get("confidence_weights", {})
        
        confidence = 0.0
        
        # Base : correspondance nom canonique
        confidence += weights.get("exact_name_match", 0.4)
        
        # Bonus pour émetteur présent
        if issuer:
            confidence += weights.get("issuer_present", 0.2)
        
        # Bonus pour niveau/score présent
        if level or score:
            confidence += weights.get("level_score_present", 0.15)
        
        # Bonus pour date présente
        if date:
            confidence += weights.get("date_present", 0.1)
        
        # Bonus contexte positif
        if context and context.get("positive_context"):
            confidence += weights.get("context_positive", 0.1)
        
        # Pénalité contexte négatif
        if context and context.get("negative_context"):
            confidence += weights.get("negative_context_penalty", -0.5)
        
        return max(0.0, min(1.0, confidence))


# Fonctions utilitaires pour compatibilité
def canonicalize_name(raw_text: str) -> Optional[str]:
    """Canonicalise le nom d'une certification."""
    normalizer = CertificationNormalizer()
    return normalizer.canonicalize_name(raw_text)


def normalize_level(raw_level: str, cert_name: str) -> str:
    """Normalise le niveau d'une certification."""
    normalizer = CertificationNormalizer()
    return normalizer.normalize_level(raw_level, cert_name)


def normalize_score(raw_score: str, cert_name: str) -> str:
    """Normalise le score d'une certification."""
    normalizer = CertificationNormalizer()
    return normalizer.normalize_score(raw_score, cert_name)


def merge_duplicates(certifications: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Fusionne les certifications en double."""
    normalizer = CertificationNormalizer()
    return normalizer.merge_duplicates(certifications)


def extract_certification_from_text(text: str, context: Optional[Dict] = None) -> Optional[NormalizedCertification]:
    """Extrait une certification normalisée du texte."""
    normalizer = CertificationNormalizer()
    return normalizer.extract_certification_from_text(text, context)