"""
Certification Normalizer - Normalisation des certifications avec correction des typos.

Corrige les typos courantes (TOFL→TOEFL), normalise les variantes,
et force le routage des certifications vers la section appropriée.
"""

import re
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass

from ..logging.safe_logger import get_safe_logger
from ..config import DEFAULT_PII_CONFIG

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


@dataclass
class CertificationMatch:
    """Résultat d'une correspondance de certification."""
    original: str
    normalized: str
    certification_type: str
    language: Optional[str] = None
    level: Optional[str] = None
    confidence: float = 1.0
    

class CertificationNormalizer:
    """Normaliseur de certifications avec correction de typos et classification."""
    
    def __init__(self):
        self.logger = get_safe_logger(f"{__name__}.CertificationNormalizer", cfg=DEFAULT_PII_CONFIG)
        
        # Mapping des typos vers les formes correctes
        self.typo_corrections = {
            # TOEFL variants
            "tofl": "toefl",
            "toelf": "toefl", 
            "teofl": "toefl",
            "tofle": "toefl",
            "toful": "toefl",
            
            # TOEIC variants
            "toeik": "toeic",
            "toiec": "toeic",
            "toeick": "toeic",
            
            # IELTS variants
            "ilets": "ielts",
            "ielst": "ielts",
            "ietls": "ielts",
            
            # Cambridge variants
            "cambrige": "cambridge",
            "cambrdige": "cambridge",
            
            # Autres certifications langues
            "delph": "delf",
            "dalph": "dalf",
            "goethe": "goethe-institut",
        }
        
        # Certifications de langue par langue
        self.language_certifications = {
            "english": {
                "toefl": {"full_name": "Test of English as a Foreign Language", "type": "language"},
                "toeic": {"full_name": "Test of English for International Communication", "type": "language"},
                "ielts": {"full_name": "International English Language Testing System", "type": "language"},
                "cambridge": {"full_name": "Cambridge English Qualifications", "type": "language"},
                "cae": {"full_name": "Cambridge Advanced English", "type": "language"},
                "cpe": {"full_name": "Cambridge Proficiency in English", "type": "language"},
                "fce": {"full_name": "Cambridge First Certificate in English", "type": "language"},
                "pet": {"full_name": "Cambridge Preliminary English Test", "type": "language"},
                "ket": {"full_name": "Cambridge Key English Test", "type": "language"},
                "bulats": {"full_name": "Business Language Testing Service", "type": "language"},
            },
            "french": {
                "delf": {"full_name": "Diplôme d'Études en Langue Française", "type": "language"},
                "dalf": {"full_name": "Diplôme Approfondi de Langue Française", "type": "language"},
                "tcf": {"full_name": "Test de Connaissance du Français", "type": "language"},
                "tef": {"full_name": "Test d'Évaluation de Français", "type": "language"},
            },
            "spanish": {
                "dele": {"full_name": "Diploma de Español como Lengua Extranjera", "type": "language"},
                "siele": {"full_name": "Servicio Internacional de Evaluación de la Lengua Española", "type": "language"},
                "ccse": {"full_name": "Conocimientos Constitucionales y Socioculturales de España", "type": "language"},
            },
            "german": {
                "testdaf": {"full_name": "Test Deutsch als Fremdsprache", "type": "language"},
                "goethe-institut": {"full_name": "Goethe-Institut Certificates", "type": "language"},
                "telc": {"full_name": "The European Language Certificates", "type": "language"},
                "dsh": {"full_name": "Deutsche Sprachprüfung für den Hochschulzugang", "type": "language"},
            },
            "chinese": {
                "hsk": {"full_name": "Hanyu Shuiping Kaoshi", "type": "language"},
                "bcpt": {"full_name": "Business Chinese Proficiency Test", "type": "language"},
            },
            "japanese": {
                "jlpt": {"full_name": "Japanese Language Proficiency Test", "type": "language"},
                "j-test": {"full_name": "Practical Japanese Test", "type": "language"},
            },
            "italian": {
                "cils": {"full_name": "Certificazione di Italiano come Lingua Straniera", "type": "language"},
                "celi": {"full_name": "Certificato di Conoscenza della Lingua Italiana", "type": "language"},
            }
        }
        
        # Niveaux CECR et équivalents
        self.level_patterns = {
            # CECR standard
            r'\b(a1|a2|b1|b2|c1|c2)\b': "cecr",
            # Niveaux descriptifs
            r'\b(beginner|debutant|elementaire|elementary)\b': "a1",
            r'\b(pre-intermediate|pre\s*intermediate)\b': "a2", 
            r'\b(intermediate|intermediaire)\b': "b1",
            r'\b(upper[-\s]*intermediate|intermediaire\s+avance)\b': "b2",
            r'\b(advanced|avance)\b': "c1",
            r'\b(proficient|proficiency|maitrise|bilingue)\b': "c2",
            # Scores TOEFL
            r'\b(toefl.*)?(\d{2,3})\s*(?:points?|pts?)?\b': "toefl_score",
            # Scores TOEIC
            r'\b(toeic.*)?(\d{3,4})\s*(?:points?|pts?)?\b': "toeic_score",
            # Scores IELTS (0-9)
            r'\b(ielts.*)?([0-9](?:\.[0-9])?)\s*(?:/9)?\b': "ielts_score"
        }
        
        # Certifications techniques (non-langues)
        self.tech_certifications = {
            "microsoft": ["mcsa", "mcse", "mcp", "azure", "office365"],
            "cisco": ["ccna", "ccnp", "ccie", "ccent"],
            "amazon": ["aws", "saa", "dva", "soa", "ans", "dop", "scs", "mls"],
            "google": ["gcp", "ace", "pca", "pde"],
            "oracle": ["oca", "ocp", "ocm"],
            "comptia": ["a+", "network+", "security+", "linux+"],
            "pmi": ["pmp", "capm", "pmi-acp"],
            "itil": ["itil", "prince2"],
            "scrum": ["csm", "psm", "cspo", "pso"],
        }
        
        # Compile regex patterns pour performance
        self._compile_patterns()
    
    def _compile_patterns(self):
        """Compile les patterns regex pour la performance."""
        self.compiled_level_patterns = [
            (re.compile(pattern, re.IGNORECASE), level_type)
            for pattern, level_type in self.level_patterns.items()
        ]
    
    def normalize_typos(self, text: str) -> str:
        """Corrige les typos dans le texte."""
        if not text:
            return text
        
        normalized = text.lower()
        
        # Appliquer les corrections de typos
        for typo, correct in self.typo_corrections.items():
            # Remplacer seulement les mots complets
            pattern = rf'\b{re.escape(typo)}\b'
            normalized = re.sub(pattern, correct, normalized, flags=re.IGNORECASE)
        
        return normalized
    
    def extract_level(self, text: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Extrait le niveau de certification du texte.
        
        Returns:
            (level, score) où level est normalisé et score est brut
        """
        if not text:
            return None, None
        
        text_lower = text.lower()
        
        for pattern, level_type in self.compiled_level_patterns:
            match = pattern.search(text_lower)
            if match:
                if level_type in ["cecr", "a1", "a2", "b1", "b2", "c1", "c2"]:
                    return level_type if level_type != "cecr" else match.group(1).upper(), None
                elif level_type == "toefl_score":
                    score = match.group(2) if len(match.groups()) > 1 else match.group(1)
                    return "toefl_score", score
                elif level_type == "toeic_score":
                    score = match.group(2) if len(match.groups()) > 1 else match.group(1)  
                    return "toeic_score", score
                elif level_type == "ielts_score":
                    score = match.group(2) if len(match.groups()) > 1 else match.group(1)
                    return "ielts_score", score
        
        return None, None
    
    def identify_certification(self, text: str) -> Optional[CertificationMatch]:
        """
        Identifie et normalise une certification dans le texte.
        
        Returns:
            CertificationMatch si trouvé, None sinon
        """
        if not text:
            return None
        
        # Étape 1: Normaliser les typos
        normalized_text = self.normalize_typos(text)
        
        # Étape 2: Chercher dans les certifications de langue
        for language, certs in self.language_certifications.items():
            for cert_key, cert_info in certs.items():
                pattern = rf'\b{re.escape(cert_key)}\b'
                if re.search(pattern, normalized_text, re.IGNORECASE):
                    # Extraire le niveau si présent
                    level, score = self.extract_level(text)
                    
                    return CertificationMatch(
                        original=text,
                        normalized=cert_key.upper(),
                        certification_type="language",
                        language=language,
                        level=level or score,
                        confidence=0.9
                    )
        
        # Étape 3: Chercher dans les certifications techniques
        text_lower = normalized_text.lower()
        for provider, certs in self.tech_certifications.items():
            for cert in certs:
                pattern = rf'\b{re.escape(cert)}\b'
                if re.search(pattern, text_lower, re.IGNORECASE):
                    return CertificationMatch(
                        original=text,
                        normalized=cert.upper(),
                        certification_type="technical",
                        language=None,
                        level=None,
                        confidence=0.85
                    )
        
        return None
    
    def is_certification_line(self, text: str) -> bool:
        """Détermine si une ligne contient une certification."""
        match = self.identify_certification(text)
        return match is not None
    
    def extract_all_certifications(self, text_lines: List[str]) -> List[CertificationMatch]:
        """Extrait toutes les certifications d'une liste de lignes."""
        certifications = []
        
        for line in text_lines:
            match = self.identify_certification(line)
            if match:
                certifications.append(match)
        
        return certifications
    
    def should_force_certification_routing(self, text: str) -> bool:
        """
        Détermine si le texte doit être forcé vers les certifications.
        
        Utilisé pour empêcher les certifications d'aller en expériences.
        """
        return self.is_certification_line(text)
    
    def get_certification_suggestions(self, text: str) -> List[str]:
        """Suggère des corrections pour du texte potentiellement mal orthographié."""
        suggestions = []
        text_lower = text.lower()
        
        # Chercher des mots similaires aux certifications connues
        all_cert_names = set()
        
        # Ajouter toutes les certifications connues
        for lang_certs in self.language_certifications.values():
            all_cert_names.update(lang_certs.keys())
        
        for tech_certs in self.tech_certifications.values():
            all_cert_names.update(tech_certs)
        
        # Simple distance d'édition approximative
        for cert_name in all_cert_names:
            if cert_name in text_lower:
                suggestions.append(cert_name.upper())
        
        return suggestions


# Instance globale
_certification_normalizer = None


def get_certification_normalizer() -> CertificationNormalizer:
    """Obtient l'instance globale du normaliseur de certifications."""
    global _certification_normalizer
    if _certification_normalizer is None:
        _certification_normalizer = CertificationNormalizer()
    return _certification_normalizer


def normalize_certification_text(text: str) -> str:
    """Fonction de convenance pour normaliser une certification."""
    normalizer = get_certification_normalizer()
    match = normalizer.identify_certification(text)
    
    if match:
        result = match.normalized
        if match.level:
            result += f" {match.level}"
        return result
    
    return text


def is_language_certification(text: str) -> bool:
    """Détermine si le texte contient une certification de langue."""
    normalizer = get_certification_normalizer()
    match = normalizer.identify_certification(text)
    return match is not None and match.certification_type == "language"


if __name__ == "__main__":
    # Tests du normaliseur de certifications
    normalizer = CertificationNormalizer()
    
    test_cases = [
        # Typos TOEFL
        "TOFL B2 - Janvier 2023",
        "TOELF niveau intermediaire", 
        "TEOFL 95 points",
        
        # TOEIC variants
        "TOEIK 850",
        "TOIEC niveau avance",
        
        # IELTS
        "ILETS 7.5",
        "IELTS Academic 6.5",
        
        # Certifications avec niveaux
        "DELF B2 obtenu en 2022",
        "Cambridge FCE niveau C1",
        "DELE niveau intermediaire",
        
        # Certifications techniques
        "AWS Solution Architect Associate",
        "CCNA certification",
        "PMP certified",
        
        # Non-certifications
        "Experience chez Google",
        "Formation informatique"
    ]
    
    print("Test du normaliseur de certifications")
    print("=" * 60)
    
    for text in test_cases:
        match = normalizer.identify_certification(text)
        
        print(f"Texte: '{text}'")
        if match:
            print(f"  -> Certification: {match.normalized}")
            print(f"     Type: {match.certification_type}")
            if match.language:
                print(f"     Langue: {match.language}")
            if match.level:
                print(f"     Niveau: {match.level}")
            print(f"     Confiance: {match.confidence:.2f}")
        else:
            print(f"  -> Pas de certification détectée")
        print()