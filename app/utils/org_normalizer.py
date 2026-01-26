"""
ORG Normalizer - Normalisation avancée des noms d'organisations.

Normalise les guillemets, accents, casing et applique une blocklist scolaire étendue
pour améliorer la précision d'ORG_SIEVE.
"""

import re
import unicodedata
from typing import Set, List, Tuple, Optional
from dataclasses import dataclass

from ..logging.safe_logger import get_safe_logger
from ..config import DEFAULT_PII_CONFIG

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


@dataclass
class NormalizationResult:
    """Résultat de la normalisation d'une organisation."""
    original: str
    normalized: str
    changes_applied: List[str]
    is_school: bool
    school_indicators: List[str]
    confidence: float = 1.0


class OrganizationNormalizer:
    """Normaliseur avancé pour noms d'organisations."""
    
    def __init__(self):
        self.logger = get_safe_logger(f"{__name__}.OrganizationNormalizer", cfg=DEFAULT_PII_CONFIG)
        
        # Blocklist étendue d'entités scolaires
        self.school_blocklist = {
            # Établissements primaires/secondaires
            "ecole", "école", "school", "elementary", "primaire", "primary",
            "college", "collège", "middle school", "secondary school",
            "lycee", "lycée", "high school", "gymnasium", "lyceum",
            
            # Universités et enseignement supérieur
            "universite", "université", "university", "uni", "univ",
            "faculte", "faculté", "faculty", "fac",
            "institut", "institute", "institution", "inst",
            "academie", "académie", "academy", "academic",
            "campus", "campus universitaire", "university campus",
            
            # Écoles spécialisées
            "iut", "but", "dut", "iup", "iep", "ena", "hec", "essec", "escp",
            "epsaa", "ensad", "beaux-arts", "conservatoire",
            "école d'ingénieur", "école d'ingénieurs", "engineering school",
            "école de commerce", "business school", "management school",
            "école supérieure", "grande école", "sup", "sup de",
            
            # Types d'établissements
            "centre de formation", "training center", "formation center",
            "centre d'apprentissage", "apprenticeship center",
            "organisme de formation", "training organization",
            "établissement scolaire", "educational institution",
            "institution scolaire", "school institution",
            "établissement d'enseignement", "teaching institution",
            
            # Mentions spécifiques françaises courantes
            "le rebours", "saint joseph", "sainte marie", "notre dame",
            "saint louis", "sainte therese", "jeanne d'arc",
            "la salle", "saint michel", "saint vincent",
            
            # Acronymes et abréviations
            "cfa", "cfppa", "greta", "afpa", "cnam", "cned",
            "irts", "ifsi", "ifas", "iae", "iae paris", "iae lyon",
            "polytech", "insa", "ensi", "eni", "ensa", "ensam"
        }
        
        # Patterns de guillemets à normaliser
        self.quote_patterns = {
            # Guillemets français
            '"': '"', '"': '"', '«': '"', '»': '"',
            # Guillemets anglais
            ''': "'", ''': "'", '`': "'",
            # Autres variations
            '‹': "'", '›': "'", '„': '"', '"': '"'
        }
        
        # Patterns regex pour détecter les établissements scolaires (ASCII safe)
        self.school_regex_patterns = [
            r'\b(?:ecole|school)\s+(?:superieure|d[\'\'].*|le|la|saint|sainte)\b',
            r'\b(?:lycee)\s+(?:le|la|saint|sainte|general|technique|professionnel)\b',
            r'\b(?:college)\s+(?:le|la|saint|sainte|prive|public)\b',
            r'\b(?:universite)\s+(?:de|d[\'\']|paris|lyon|marseille|lille|bordeaux)\b',
            r'\b(?:institut|institute)\s+(?:superieur|de|d[\'\']|national|europeen)\b',
            r'\b(?:centre|center)\s+(?:de\s+)?formation\b',
            r'\b(?:grande\s+)?ecole\s+(?:de|d[\'\']|superieure)\b',
            r'\b(?:faculte)\s+(?:de|d[\'\']|des)\b'
        ]
        
        # Compile les patterns regex pour la performance
        self.compiled_school_patterns = [
            re.compile(pattern, re.IGNORECASE) for pattern in self.school_regex_patterns
        ]
    
    def normalize_quotes(self, text: str) -> Tuple[str, List[str]]:
        """Normalise tous les types de guillemets."""
        if not text:
            return text, []
        
        changes = []
        normalized = text
        
        for old_quote, new_quote in self.quote_patterns.items():
            if old_quote in normalized:
                normalized = normalized.replace(old_quote, new_quote)
                changes.append(f"quote_{ord(old_quote)}_to_{ord(new_quote)}")
        
        return normalized, changes
    
    def normalize_accents(self, text: str) -> Tuple[str, List[str]]:
        """Normalise les accents et caractères spéciaux."""
        if not text:
            return text, []
        
        # Décomposer les caractères accentués
        nfd_text = unicodedata.normalize('NFD', text)
        
        # Supprimer les diacritiques (accents)
        ascii_text = ''.join(
            char for char in nfd_text 
            if unicodedata.category(char) != 'Mn'
        )
        
        changes = []
        if ascii_text != text:
            changes.append("accents_removed")
        
        return ascii_text, changes
    
    def normalize_casing(self, text: str) -> Tuple[str, List[str]]:
        """Normalise la casse selon des règles intelligentes."""
        if not text:
            return text, []
        
        original = text
        
        # Si tout en majuscules, convertir en titre
        if text.isupper():
            text = text.title()
            return text, ["all_caps_to_title"]
        
        # Si tout en minuscules, appliquer une capitalisation intelligente
        if text.islower():
            # Diviser en mots
            words = text.split()
            normalized_words = []
            
            # Articles et prépositions à ne pas capitaliser (sauf premier mot)
            minor_words = {'de', 'du', 'des', 'le', 'la', 'les', 'un', 'une', 
                          'et', 'ou', 'pour', 'avec', 'sans', 'sur', 'sous',
                          'of', 'the', 'a', 'an', 'and', 'or', 'for', 'with',
                          'without', 'on', 'under', 'in', 'at', 'to'}
            
            for i, word in enumerate(words):
                if i == 0 or word not in minor_words:
                    # Capitaliser le premier mot et les mots importants
                    normalized_words.append(word.capitalize())
                else:
                    # Garder les articles/prépositions en minuscule
                    normalized_words.append(word)
            
            normalized = ' '.join(normalized_words)
            
            if normalized != original:
                return normalized, ["smart_capitalization"]
        
        return text, []
    
    def is_school_organization(self, text: str) -> Tuple[bool, List[str]]:
        """Détermine si le texte représente un établissement scolaire."""
        if not text:
            return False, []
        
        # Normaliser le texte pour la comparaison
        text_lower = text.lower()
        normalized_text, _ = self.normalize_accents(text_lower)
        
        indicators = []
        
        # Vérifier la blocklist exacte
        for school_term in self.school_blocklist:
            if school_term in normalized_text:
                indicators.append(f"blocklist:{school_term}")
        
        # Vérifier les patterns regex
        for pattern in self.compiled_school_patterns:
            matches = pattern.findall(text_lower)
            for match in matches:
                indicators.append(f"pattern:{match}")
        
        # Détecter des patterns spécifiques français (ASCII safe)
        french_school_indicators = [
            r'\b\w+\s+superieur\w*\s+d[\s\w]+',  # "ecole superieure d ingenieurs"
            r'\bepsaa\b',  # EPSAA
            r'\b(?:saint|sainte|st|ste)\s+\w+',  # Établissements religieux
            r'\b\w+\s+le\s+\w+\b'  # "lycee le rebours"
        ]
        
        for pattern in french_school_indicators:
            if re.search(pattern, text_lower, re.IGNORECASE):
                indicators.append(f"french_pattern:{pattern[:20]}")
        
        is_school = len(indicators) > 0
        
        if is_school:
            self.logger.debug(f"ORG_NORMALIZER: school_detected | text='{text[:30]}...' "
                            f"indicators={indicators[:3]}...")  # Limiter les logs
        
        return is_school, indicators
    
    def normalize_organization(self, org_name: str) -> NormalizationResult:
        """Normalise complètement un nom d'organisation."""
        if not org_name:
            return NormalizationResult(
                original="",
                normalized="",
                changes_applied=[],
                is_school=False,
                school_indicators=[],
                confidence=0.0
            )
        
        original = org_name
        current = org_name
        all_changes = []
        
        # Étape 1: Normaliser les guillemets
        current, quote_changes = self.normalize_quotes(current)
        all_changes.extend(quote_changes)
        
        # Étape 2: Normaliser les accents
        current, accent_changes = self.normalize_accents(current)
        all_changes.extend(accent_changes)
        
        # Étape 3: Normaliser la casse
        current, case_changes = self.normalize_casing(current)
        all_changes.extend(case_changes)
        
        # Étape 4: Nettoyage final
        current = re.sub(r'\s+', ' ', current.strip())  # Espaces multiples
        if current != current.strip():
            all_changes.append("whitespace_cleaned")
        
        # Étape 5: Vérifier si c'est un établissement scolaire
        is_school, school_indicators = self.is_school_organization(current)
        
        # Calculer la confiance
        confidence = 1.0
        if is_school:
            confidence -= 0.3  # Réduire la confiance pour les écoles
        if len(all_changes) > 3:
            confidence -= 0.1  # Réduire si beaucoup de changements
        
        confidence = max(confidence, 0.1)  # Minimum 0.1
        
        self.logger.debug(f"ORG_NORMALIZER: normalized | original='{original[:30]}...' "
                         f"normalized='{current[:30]}...' changes={len(all_changes)} "
                         f"is_school={is_school} confidence={confidence:.2f}")
        
        return NormalizationResult(
            original=original,
            normalized=current,
            changes_applied=all_changes,
            is_school=is_school,
            school_indicators=school_indicators,
            confidence=confidence
        )
    
    def should_block_as_school(self, org_name: str, confidence_threshold: float = 0.7) -> bool:
        """Détermine si une organisation doit être bloquée comme établissement scolaire."""
        result = self.normalize_organization(org_name)
        
        if not result.is_school:
            return False
        
        # Vérifier les indicateurs d'entreprise privée qui peuvent sauvegarder
        private_indicators = ['sas', 'sarl', 'sa', 'inc', 'corp', 'consulting', 'solutions', 
                             'company', 'ltd', 'llc', 'gmbh', 'division', 'r&d']
        
        normalized_lower = result.normalized.lower()
        has_private_indicator = any(indicator in normalized_lower for indicator in private_indicators)
        
        if has_private_indicator:
            # Réduire la probabilité de blocage pour les entreprises privées
            adjusted_threshold = confidence_threshold + 0.15  # Plus strict pour ces cas
            should_block = result.confidence >= adjusted_threshold
            
            if not should_block:
                self.logger.debug(f"ORG_NORMALIZER: private_org_saved | org='{org_name[:30]}...' "
                                f"confidence={result.confidence:.2f} adjusted_threshold={adjusted_threshold:.2f}")
                return False
        
        # Bloquer si c'est une école ET que la confiance est suffisante
        should_block = result.is_school and result.confidence >= confidence_threshold
        
        if should_block:
            self.logger.info(f"ORG_NORMALIZER: school_blocked | org='{org_name[:30]}...' "
                           f"confidence={result.confidence:.2f} indicators={len(result.school_indicators)}")
        
        return should_block
    
    def get_normalized_for_matching(self, org_name: str) -> str:
        """Obtient la version normalisée pour comparaison/matching."""
        result = self.normalize_organization(org_name)
        return result.normalized.lower()


# Instance globale
_org_normalizer = None


def get_org_normalizer() -> OrganizationNormalizer:
    """Obtient l'instance globale du normaliseur d'organisations."""
    global _org_normalizer
    if _org_normalizer is None:
        _org_normalizer = OrganizationNormalizer()
    return _org_normalizer


def normalize_org_name(org_name: str) -> str:
    """Fonction de convenance pour normaliser un nom d'organisation."""
    normalizer = get_org_normalizer()
    result = normalizer.normalize_organization(org_name)
    return result.normalized


def is_school_organization(org_name: str) -> bool:
    """Détermine si une organisation est un établissement scolaire."""
    normalizer = get_org_normalizer()
    result = normalizer.normalize_organization(org_name)
    return result.is_school


if __name__ == "__main__":
    # Tests du normaliseur d'organisations
    normalizer = OrganizationNormalizer()
    
    test_cases = [
        # Guillemets problématiques
        "École supérieure d'ingénieurs « Le Rebours »",
        '"EPSAA" - École Pratique',
        "'Université de Paris' - Campus",
        
        # Accents et casse
        "ÉCOLE SUPÉRIEURE D'INFORMATIQUE",
        "université paris dauphine",
        "Lycée Général Saint-Joseph",
        
        # Établissements scolaires avec patterns complexes
        "École supérieure d'informatique de Lyon",
        "Institut National des Sciences Appliquées",
        "Centre de Formation d'Apprentis",
        "IUT de Cachan - Université Paris-Sud",
        
        # Non-écoles (entreprises)
        "Société Générale - Direction IT",
        "TOTAL S.A.",
        "Capgemini Consulting",
        "Microsoft France",
        
        # Cas ambigus
        "Formation et Conseil SAS",  # Entreprise avec "formation"
        "Institut de Recherche Privé",  # Institut privé
        "École de Commerce Parisienne"  # École de commerce
    ]
    
    print("Test du normaliseur d'organisations")
    print("=" * 50)
    
    for org_name in test_cases:
        result = normalizer.normalize_organization(org_name)
        
        print(f"Original: '{org_name}'")
        print(f"Normalisé: '{result.normalized}'")
        print(f"Changements: {result.changes_applied}")
        print(f"École: {result.is_school}")
        if result.is_school and result.school_indicators:
            print(f"Indicateurs: {result.school_indicators[:3]}...")
        print(f"Confiance: {result.confidence:.2f}")
        print("-" * 30)