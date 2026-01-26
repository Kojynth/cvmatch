"""
Interest Deduplicator - Déduplication intelligente des centres d'intérêts.

Évite la création de centres d'intérêts fantômes et dupliqués,
avec normalisation canonique et règles anti-fantômes.
"""

import re
from typing import List, Set, Dict, Tuple, Optional
from dataclasses import dataclass

from ..logging.safe_logger import get_safe_logger
from ..config import DEFAULT_PII_CONFIG
from .intelligent_routing import get_intelligent_router

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


@dataclass
class Interest:
    """Représentation d'un centre d'intérêt."""
    original: str
    canonical: str
    category: Optional[str] = None
    confidence: float = 1.0


class InterestDeduplicator:
    """Déduplicateur intelligent pour centres d'intérêts."""
    
    def __init__(self):
        self.logger = get_safe_logger(f"{__name__}.InterestDeduplicator", cfg=DEFAULT_PII_CONFIG)
        self.router = get_intelligent_router()
        
        # Aliases pour normalisation canonique
        self.interest_aliases = {
            # Sports
            "sport": ["sports", "activité sportive", "activités sportives"],
            "football": ["foot", "soccer", "ballon"],
            "basketball": ["basket", "basket-ball"],
            "tennis": ["tennis de table", "ping-pong"],
            "natation": ["nage", "swimming", "piscine"],
            "course": ["running", "jogging", "course à pied"],
            "fitness": ["musculation", "gym", "gymnastique", "salle de sport"],
            "cyclisme": ["vélo", "cycling", "bike"],
            "randonnée": ["hiking", "marche", "trekking"],
            
            # Musique
            "musique": ["music", "musical"],
            "guitare": ["guitar"],
            "piano": ["piano classique"],
            "chant": ["singing", "vocal"],
            
            # Arts
            "lecture": ["reading", "lire", "livres", "books"],
            "cinéma": ["cinema", "film", "films", "movies"],
            "photographie": ["photo", "photography"],
            "dessin": ["drawing", "art"],
            "peinture": ["painting"],
            
            # Technologie
            "informatique": ["computer", "ordinateur", "IT"],
            "programmation": ["programming", "coding", "code"],
            "jeux vidéo": ["gaming", "video games", "games"],
            "technologie": ["tech", "technology", "nouvelles technologies"],
            
            # Voyage
            "voyage": ["voyages", "travel", "traveling"],
            "découverte": ["exploration", "découvertes"],
            
            # Cuisine
            "cuisine": ["cooking", "culinary", "gastronomie"],
            "pâtisserie": ["baking", "patisserie"],
            
            # Autres
            "bénévolat": ["volontariat", "volunteering", "volunteer work"],
            "association": ["associations", "associatif"]
        }
        
        # Créer un mapping inverse pour la recherche
        self.alias_to_canonical = {}
        for canonical, aliases in self.interest_aliases.items():
            self.alias_to_canonical[canonical] = canonical
            for alias in aliases:
                self.alias_to_canonical[alias.lower()] = canonical
        
        # Catégories pour classification
        self.categories = {
            "sports": ["sport", "football", "basketball", "tennis", "natation", "course", "fitness", "cyclisme", "randonnée"],
            "arts": ["musique", "guitare", "piano", "chant", "lecture", "cinéma", "photographie", "dessin", "peinture"],
            "technologie": ["informatique", "programmation", "jeux vidéo", "technologie"],
            "voyage": ["voyage", "découverte"],
            "cuisine": ["cuisine", "pâtisserie"],
            "social": ["bénévolat", "association"]
        }
    
    def normalize_interest(self, text: str) -> str:
        """Normalise un centre d'intérêt vers sa forme canonique."""
        if not text:
            return ""
        
        # Nettoyer le texte
        normalized = text.lower().strip()
        
        # Supprimer la ponctuation en fin
        normalized = re.sub(r'[,;:.!?]+$', '', normalized)
        
        # Supprimer les articles
        normalized = re.sub(r'^(le|la|les|un|une|des|du|de|the|a|an)\s+', '', normalized)
        
        # Chercher dans les aliases
        if normalized in self.alias_to_canonical:
            return self.alias_to_canonical[normalized]
        
        # Chercher des correspondances partielles
        for alias, canonical in self.alias_to_canonical.items():
            if alias in normalized or normalized in alias:
                return canonical
        
        return normalized
    
    def get_category(self, canonical_interest: str) -> Optional[str]:
        """Détermine la catégorie d'un centre d'intérêt."""
        for category, interests in self.categories.items():
            if canonical_interest in interests:
                return category
        return None
    
    def is_valid_interest(self, text: str, has_dates: bool = False, 
                         has_company: bool = False, has_role: bool = False) -> bool:
        """
        Détermine si un texte peut être un centre d'intérêt valide.
        
        Règles anti-fantômes:
        - Pas de dates, entreprise, ou rôle professionnel
        - Pas de verbes d'action professionnels
        """
        if not text:
            return False
        
        # Utiliser le router intelligent pour vérification
        if not self.router.can_reclass_to_interest(text, has_dates, has_company, has_role):
            return False
        
        # Vérifications supplémentaires
        text_lower = text.lower()
        
        # Rejeter les textes trop courts ou trop génériques
        if len(text.strip()) < 3:
            return False
        
        # Rejeter les textes qui ressemblent à des expériences
        experience_indicators = [
            r'\b\d{4}\b',  # Années
            r'\b\d{1,2}[/\-]\d{4}\b',  # Dates MM/YYYY
            r'\b(stage|intern|job|work|emploi)\b',
            r'\b(entreprise|company|société|firm)\b',
            r'\b(poste|position|role|fonction)\b'
        ]
        
        for pattern in experience_indicators:
            if re.search(pattern, text_lower):
                return False
        
        return True
    
    def deduplicate_interests(self, interests: List[str], 
                            metadata: Optional[List[Dict]] = None) -> List[Interest]:
        """
        Déduplique une liste de centres d'intérêts.
        
        Args:
            interests: Liste des centres d'intérêts bruts
            metadata: Métadonnées optionnelles pour chaque intérêt
        
        Returns:
            Liste d'intérêts dédupliqués et normalisés
        """
        if not interests:
            return []
        
        seen_canonical = set()
        deduplicated = []
        
        for i, interest_text in enumerate(interests):
            # Récupérer les métadonnées pour cet intérêt
            meta = metadata[i] if metadata and i < len(metadata) else {}
            has_dates = meta.get('has_dates', False)
            has_company = meta.get('has_company', False)
            has_role = meta.get('has_role', False)
            
            # Vérifier si c'est un intérêt valide
            if not self.is_valid_interest(interest_text, has_dates, has_company, has_role):
                self.logger.debug(f"INTEREST_INVALID: rejected '{interest_text}' - not a valid interest")
                continue
            
            # Normaliser
            canonical = self.normalize_interest(interest_text)
            
            # Éviter les doublons
            if canonical in seen_canonical:
                self.logger.debug(f"INTEREST_DUPLICATE: skipped '{interest_text}' -> '{canonical}' (already seen)")
                continue
            
            seen_canonical.add(canonical)
            
            # Créer l'objet Interest
            interest = Interest(
                original=interest_text,
                canonical=canonical,
                category=self.get_category(canonical),
                confidence=0.8
            )
            
            deduplicated.append(interest)
        
        self.logger.info(f"INTEREST_DEDUP: {len(interests)} -> {len(deduplicated)} interests (removed {len(interests) - len(deduplicated)} duplicates/invalid)")
        
        return deduplicated
    
    def limit_interests_count(self, interests: List[Interest], max_count: int = 5) -> List[Interest]:
        """Limite le nombre d'intérêts pour éviter les listes trop longues."""
        if len(interests) <= max_count:
            return interests
        
        # Trier par confiance et diversité de catégories
        sorted_interests = sorted(interests, key=lambda x: x.confidence, reverse=True)
        
        # Sélectionner en privilégiant la diversité
        selected = []
        used_categories = set()
        
        # Premier passage: un par catégorie
        for interest in sorted_interests:
            if len(selected) >= max_count:
                break
            
            if interest.category and interest.category not in used_categories:
                selected.append(interest)
                used_categories.add(interest.category)
        
        # Deuxième passage: compléter sans contrainte de catégorie
        for interest in sorted_interests:
            if len(selected) >= max_count:
                break
            
            if interest not in selected:
                selected.append(interest)
        
        self.logger.debug(f"INTEREST_LIMIT: limited from {len(interests)} to {len(selected)} interests")
        
        return selected[:max_count]
    
    def should_block_duplicate_creation(self, existing_interests: List[str], 
                                      candidate_text: str) -> bool:
        """
        Détermine si on doit bloquer la création d'un intérêt dupliqué.
        
        Utilisé pour éviter que le système ne crée un 2e/3e bloc identique.
        """
        if not candidate_text or not existing_interests:
            return False
        
        candidate_canonical = self.normalize_interest(candidate_text)
        
        for existing in existing_interests:
            existing_canonical = self.normalize_interest(existing)
            
            # Correspondance exacte
            if candidate_canonical == existing_canonical:
                return True
            
            # Correspondance avec seuil de similarité
            if self._text_similarity(candidate_canonical, existing_canonical) > 0.8:
                return True
        
        return False
    
    def _text_similarity(self, text1: str, text2: str) -> float:
        """Calcule la similarité entre deux textes (simple)."""
        if not text1 or not text2:
            return 0.0
        
        # Simple similarité basée sur les mots communs
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union) if union else 0.0


# Instance globale
_interest_deduplicator = None


def get_interest_deduplicator() -> InterestDeduplicator:
    """Obtient l'instance globale du déduplicateur d'intérêts."""
    global _interest_deduplicator
    if _interest_deduplicator is None:
        _interest_deduplicator = InterestDeduplicator()
    return _interest_deduplicator


def deduplicate_interests_simple(interests: List[str]) -> List[str]:
    """Fonction de convenance pour dédupliquer des intérêts."""
    deduplicator = get_interest_deduplicator()
    deduplicated = deduplicator.deduplicate_interests(interests)
    return [interest.canonical for interest in deduplicated]


def is_valid_interest_text(text: str) -> bool:
    """Détermine si un texte peut être un intérêt valide."""
    deduplicator = get_interest_deduplicator()
    return deduplicator.is_valid_interest(text)


if __name__ == "__main__":
    # Tests du déduplicateur
    deduplicator = InterestDeduplicator()
    
    test_interests = [
        # Doublons
        "sport", "sports", "activité sportive",
        "foot", "football", "soccer",
        "lecture", "lire", "livres",
        
        # Invalides (avec dates/entreprises)
        "Stage chez Google 2023",
        "Développement logiciel",
        "Expérience professionnelle",
        
        # Valides
        "photographie", "voyage", "cuisine", "guitare",
        
        # Trop courts
        "IT", "a", "",
        
        # Normaux
        "bénévolat", "associations", "volontariat"
    ]
    
    print("Test déduplicateur d'intérêts")
    print("=" * 40)
    
    results = deduplicator.deduplicate_interests(test_interests)
    
    print(f"Entrée: {len(test_interests)} intérêts")
    print(f"Sortie: {len(results)} intérêts")
    print()
    
    for interest in results:
        category_info = f" ({interest.category})" if interest.category else ""
        print(f"'{interest.original}' -> '{interest.canonical}'{category_info}")
        
    print()
    print("Intérêts rejetés:")
    processed_originals = {r.original for r in results}
    for original in test_interests:
        if original not in processed_originals and original.strip():
            print(f"  '{original}' - rejeté")