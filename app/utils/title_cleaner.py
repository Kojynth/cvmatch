"""
Title Cleaner - Nettoyage des titres "romans" et post-processing.

Supprime les suffixes de dates, coupe les titres trop longs, 
enlève les parenthèses/exclamations orphelines, et reclasse
si nécessaire selon les tokens significatifs restants.
"""

import re
from typing import Optional, Tuple, List
from dataclasses import dataclass

from ..logging.safe_logger import get_safe_logger
from ..config import DEFAULT_PII_CONFIG
from .feature_flags import get_extraction_fixes_flags
from .intelligent_routing import get_intelligent_router, ContentType

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


@dataclass
class CleaningResult:
    """Résultat du nettoyage d'un titre."""
    original: str
    cleaned: str
    was_truncated: bool
    removed_dates: bool
    removed_punctuation: bool
    significant_tokens: int
    suggested_reclassification: Optional[str] = None
    reason: str = ""


class TitleCleaner:
    """Nettoyeur de titres avec post-processing intelligent."""
    
    def __init__(self):
        self.logger = get_safe_logger(f"{__name__}.TitleCleaner", cfg=DEFAULT_PII_CONFIG)
        self.flags = get_extraction_fixes_flags()
        self.router = get_intelligent_router()
        
        # Patterns pour supprimer les suffixes de dates
        self.date_suffix_patterns = [
            # Dates avec tirets: — 09/2022 – 10/2022
            r'\s*[—–-]\s*\d{1,2}/\d{4}\s*[—–-]\s*\d{1,2}/\d{4}\s*$',
            r'\s*[—–-]\s*\d{4}\s*[—–-]\s*\d{4}\s*$',
            # Dates simples: - 2023, (2022-2023)
            r'\s*[—–-]\s*\d{4}\s*$',
            r'\s*[—–-]\s*\d{1,2}/\d{4}\s*$',
            # Parenthèses avec dates: (09/2022 – 10/2022)
            r'\s*\(\d{1,2}/\d{4}\s*[—–-]\s*\d{1,2}/\d{4}\)\s*$',
            r'\s*\(\d{4}\s*[—–-]\s*\d{4}\)\s*$',
            r'\s*\(\d{4}\)\s*$',
            # Patterns avec "depuis", "à ce jour"
            r'\s*[—–-]\s*depuis\s+\d{4}\s*$',
            r'\s*[—–-]\s*à\s+ce\s+jour\s*$',
            r'\s*[—–-]\s*présent\s*$',
        ]
        
        # Patterns pour nettoyer la ponctuation orpheline
        self.orphan_punctuation_patterns = [
            # Parenthèses/crochets non appariés
            r'\s*\(\s*$',  # Parenthèse ouvrante en fin
            r'^\s*\)\s*',  # Parenthèse fermante en début
            r'\s*\[\s*$',  # Crochet ouvrant en fin
            r'^\s*\]\s*',  # Crochet fermant en début
            # Ponctuation excessive
            r'\s*[,;:]+\s*$',  # Virgules/points-virgules en fin
            r'^\s*[,;:]+\s*',  # Virgules/points-virgules en début
            r'\s*[!?]{2,}\s*$',  # Points d'exclamation multiples
            # Tirets orphelins
            r'^\s*[—–-]\s*',  # Tiret en début
            r'\s*[—–-]\s*$',  # Tiret en fin (après nettoyage dates)
        ]
        
        # Mots non-significatifs (stop words)
        self.stop_words = {
            # Français
            'le', 'la', 'les', 'un', 'une', 'des', 'du', 'de', 'et', 'ou', 'à', 'en',
            'dans', 'sur', 'avec', 'pour', 'par', 'sans', 'sous', 'chez', 'entre',
            'durant', 'pendant', 'depuis', 'jusqu', 'vers', 'selon', 'contre',
            # Anglais  
            'the', 'a', 'an', 'and', 'or', 'in', 'on', 'at', 'to', 'for', 'of',
            'with', 'by', 'from', 'about', 'into', 'through', 'during', 'before',
            'after', 'above', 'below', 'between', 'among', 'under', 'over',
            # Communs
            'stage', 'internship', 'projet', 'project'
        }
    
    def remove_date_suffixes(self, title: str) -> Tuple[str, bool]:
        """Supprime les suffixes de dates du titre."""
        if not title:
            return title, False
        
        cleaned = title
        removed_any = False
        
        for pattern in self.date_suffix_patterns:
            before_length = len(cleaned)
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
            if len(cleaned) < before_length:
                removed_any = True
        
        return cleaned.strip(), removed_any
    
    def remove_orphan_punctuation(self, title: str) -> Tuple[str, bool]:
        """Enlève la ponctuation orpheline."""
        if not title:
            return title, False
        
        cleaned = title
        removed_any = False
        
        for pattern in self.orphan_punctuation_patterns:
            before_length = len(cleaned)
            cleaned = re.sub(pattern, '', cleaned)
            if len(cleaned) < before_length:
                removed_any = True
        
        return cleaned.strip(), removed_any
    
    def truncate_if_needed(self, title: str, max_length: Optional[int] = None) -> Tuple[str, bool]:
        """Tronque le titre si trop long."""
        if not title:
            return title, False
        
        if max_length is None:
            max_length = self.flags.max_title_length if self.flags.max_title_length > 0 else 120
        
        if len(title) <= max_length:
            return title, False
        
        # Tronquer au dernier espace avant la limite pour éviter de couper un mot
        truncated = title[:max_length]
        last_space = truncated.rfind(' ')
        
        if last_space > max_length * 0.8:  # Si l'espace est assez proche de la fin
            truncated = truncated[:last_space]
        
        return truncated.strip(), True
    
    def count_significant_tokens(self, title: str) -> int:
        """Compte les tokens significatifs (non stop-words)."""
        if not title:
            return 0
        
        # Tokenizer simple
        tokens = re.findall(r'\b\w{2,}\b', title.lower())
        
        # Filtrer les stop words
        significant = [token for token in tokens if token not in self.stop_words]
        
        return len(significant)
    
    def suggest_reclassification(self, cleaned_title: str, significant_tokens: int) -> Tuple[Optional[str], str]:
        """Suggère une reclassification si le titre nettoyé est trop court."""
        if significant_tokens >= 3:
            return None, "sufficient_tokens"
        
        # Moins de 3 tokens significatifs - analyser pour reclassification
        if not cleaned_title:
            return "interest", "empty_after_cleaning"
        
        # Utiliser le router intelligent pour déterminer le type
        decision = self.router.route_content(cleaned_title)
        
        if decision.target_type == ContentType.PROJECT:
            return "project", f"project_signals_detected: {decision.reason}"
        elif decision.target_type == ContentType.INTEREST:
            return "interest", f"interest_signals_detected: {decision.reason}"
        elif significant_tokens <= 1:
            return "interest", "single_significant_token"
        
        return None, "keep_as_is"
    
    def clean_title(self, title: str, max_length: Optional[int] = None) -> CleaningResult:
        """
        Nettoie complètement un titre avec toutes les étapes.
        
        Args:
            title: Titre original à nettoyer
            max_length: Longueur maximale (défaut depuis feature flags)
        
        Returns:
            Résultat complet du nettoyage avec suggestions
        """
        if not title:
            return CleaningResult(
                original="",
                cleaned="",
                was_truncated=False,
                removed_dates=False,
                removed_punctuation=False,
                significant_tokens=0,
                reason="empty_input"
            )
        
        original = title
        current = title
        
        # Étape 1: Supprimer les suffixes de dates
        current, removed_dates = self.remove_date_suffixes(current)
        
        # Étape 2: Supprimer la ponctuation orpheline 
        current, removed_punctuation = self.remove_orphan_punctuation(current)
        
        # Étape 3: Tronquer si nécessaire
        current, was_truncated = self.truncate_if_needed(current, max_length)
        
        # Étape 4: Analyser les tokens significatifs
        significant_tokens = self.count_significant_tokens(current)
        
        # Étape 5: Suggérer reclassification si nécessaire
        suggested_reclass, reason = self.suggest_reclassification(current, significant_tokens)
        
        result = CleaningResult(
            original=original,
            cleaned=current,
            was_truncated=was_truncated,
            removed_dates=removed_dates,
            removed_punctuation=removed_punctuation,
            significant_tokens=significant_tokens,
            suggested_reclassification=suggested_reclass,
            reason=reason
        )
        
        # Log si nettoyage significatif
        if any([removed_dates, removed_punctuation, was_truncated, suggested_reclass]):
            self.logger.debug(
                f"TITLE_CLEAN: '{original}' -> '{current}' | "
                f"dates:{removed_dates} punct:{removed_punctuation} trunc:{was_truncated} "
                f"tokens:{significant_tokens} reclass:{suggested_reclass}"
            )
        
        return result
    
    def clean_titles_batch(self, titles: List[str]) -> List[CleaningResult]:
        """Nettoie une liste de titres en batch."""
        return [self.clean_title(title) for title in titles]


# Instance globale
_title_cleaner = None


def get_title_cleaner() -> TitleCleaner:
    """Obtient l'instance globale du nettoyeur de titres."""
    global _title_cleaner
    if _title_cleaner is None:
        _title_cleaner = TitleCleaner()
    return _title_cleaner


def clean_title_simple(title: str, max_length: int = 120) -> str:
    """Fonction de convenance pour nettoyer un titre simplement."""
    cleaner = get_title_cleaner()
    result = cleaner.clean_title(title, max_length)
    return result.cleaned


def should_reclassify_after_cleaning(title: str) -> Tuple[bool, Optional[str]]:
    """Détermine si un titre doit être reclassifié après nettoyage."""
    cleaner = get_title_cleaner()
    result = cleaner.clean_title(title)
    
    if result.suggested_reclassification:
        return True, result.suggested_reclassification
    
    return False, None


if __name__ == "__main__":
    # Tests du nettoyeur de titres
    cleaner = TitleCleaner()
    
    test_titles = [
        # Titres avec dates
        "Développeur Web — 09/2022 – 10/2022",
        "Chef de projet (2020-2023)",
        "Stage chez Google - depuis 2023",
        
        # Titres trop longs
        "Responsable développement applications web et mobile avec expertise React, Node.js et gestion d'équipe dans environnement Agile et DevOps",
        
        # Ponctuation orpheline
        "Développeur (",
        ") Consultant IT",
        "Manager, ",
        
        # Titres courts après nettoyage
        "Stage - 2023",
        "Projet ()",
        "Formation chez école",
        
        # Titres normaux
        "Développeur Python",
        "Chef de projet IT"
    ]
    
    print("Test du nettoyeur de titres")
    print("=" * 60)
    
    for title in test_titles:
        result = cleaner.clean_title(title)
        
        print(f"Original: '{result.original}'")
        print(f"Nettoyé:  '{result.cleaned}'")
        print(f"Modifications: dates={result.removed_dates}, punct={result.removed_punctuation}, trunc={result.was_truncated}")
        print(f"Tokens significatifs: {result.significant_tokens}")
        
        if result.suggested_reclassification:
            print(f"🔄 Reclassification suggérée: {result.suggested_reclassification} ({result.reason})")
        
        print("-" * 40)