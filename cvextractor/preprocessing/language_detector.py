"""
Détecteur de langue pour documents
"""

import logging
import re
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)


class LanguageDetector:
    """Détecteur de langue basé sur des patterns et mots-clés"""

    def __init__(self):
        self.language_patterns = self._load_language_patterns()
        self.language_keywords = self._load_language_keywords()

    def detect(self, text: str) -> str:
        """
        Détecte la langue principale d'un texte

        Args:
            text: Texte à analyser

        Returns:
            Code langue (ISO 639-1) ou 'unknown'
        """
        if not text or len(text.strip()) < 20:
            return "unknown"

        # Nettoyer le texte pour l'analyse
        clean_text = self._clean_text_for_analysis(text)

        # Scores par langue
        language_scores = {}

        # 1. Analyse par mots-clés
        keyword_scores = self._analyze_keywords(clean_text)
        for lang, score in keyword_scores.items():
            language_scores[lang] = language_scores.get(lang, 0) + score * 0.6

        # 2. Analyse par patterns de caractères
        pattern_scores = self._analyze_patterns(clean_text)
        for lang, score in pattern_scores.items():
            language_scores[lang] = language_scores.get(lang, 0) + score * 0.4

        # 3. Trouver la langue dominante
        if not language_scores:
            return "unknown"

        detected_lang = max(language_scores, key=language_scores.get)
        confidence = language_scores[detected_lang]

        # Seuil de confiance minimum
        if confidence < 0.3:
            return "unknown"

        logger.debug(
            f"🌐 Langue détectée: {detected_lang} (confiance: {confidence:.2f})"
        )
        return detected_lang

    def _clean_text_for_analysis(self, text: str) -> str:
        """Nettoie le texte pour l'analyse linguistique"""
        # Supprimer URLs, emails, numéros
        text = re.sub(r"https?://[^\s]+", "", text)
        text = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "", text)
        text = re.sub(r"\b\d+\b", "", text)
        text = re.sub(r"[^\w\s]", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.lower().strip()

    def _analyze_keywords(self, text: str) -> Dict[str, float]:
        """Analyse basée sur des mots-clés spécifiques aux langues"""
        scores = {}
        words = text.split()

        for language, keywords in self.language_keywords.items():
            matches = sum(1 for word in words if word in keywords)
            if words:
                scores[language] = matches / len(words)

        return scores

    def _analyze_patterns(self, text: str) -> Dict[str, float]:
        """Analyse basée sur des patterns de caractères"""
        scores = {}

        for language, patterns in self.language_patterns.items():
            language_score = 0

            for pattern, weight in patterns.items():
                matches = len(re.findall(pattern, text))
                # Normaliser par la longueur du texte
                normalized_matches = matches / (len(text) / 1000) if text else 0
                language_score += normalized_matches * weight

            scores[language] = language_score

        return scores

    def _load_language_patterns(self) -> Dict[str, Dict[str, float]]:
        """Charge les patterns spécifiques aux langues"""
        return {
            "fr": {
                r"\bqu[e\']?\b": 0.3,  # que, qu'
                r"\b[dl]e[s]?\b": 0.2,  # le, la, les, de, des
                r"\bune?\b": 0.2,  # un, une
                r"tion\b": 0.1,  # terminaisons -tion
                r"eur\b": 0.1,  # terminaisons -eur
                r"[àâäéèêëïîôöùûü]": 0.2,  # accents français
                r"ç": 0.3,  # cédille
            },
            "en": {
                r"\bthe\b": 0.4,
                r"\band\b": 0.2,
                r"\b(?:is|are|was|were)\b": 0.2,
                r"\b(?:this|that|these|those)\b": 0.2,
                r"ing\b": 0.2,  # terminaisons -ing
                r"ed\b": 0.1,  # terminaisons -ed
                r"\b(?:will|would|should|could)\b": 0.1,
            },
            "de": {
                r"\b(?:der|die|das)\b": 0.4,
                r"\b(?:und|oder)\b": 0.2,
                r"\b(?:ist|sind|war|waren)\b": 0.2,
                r"\b(?:ich|du|er|sie|es|wir|ihr)\b": 0.2,
                r"ung\b": 0.2,  # terminaisons -ung
                r"heit\b": 0.1,  # terminaisons -heit
                r"[äöüß]": 0.3,  # caractères allemands
            },
            "es": {
                r"\b(?:el|la|los|las)\b": 0.4,
                r"\by\b": 0.2,
                r"\b(?:es|son|está|están)\b": 0.2,
                r"\b(?:que|pero|con|por)\b": 0.2,
                r"ción\b": 0.2,  # terminaisons -ción
                r"idad\b": 0.1,  # terminaisons -idad
                r"[ñáéíóúü]": 0.2,  # accents espagnols
            },
            "it": {
                r"\b(?:il|la|lo|gli|le)\b": 0.4,
                r"\be\b": 0.2,
                r"\b(?:è|sono|era|erano)\b": 0.2,
                r"\b(?:che|ma|con|per)\b": 0.2,
                r"zione\b": 0.2,  # terminaisons -zione
                r"ità\b": 0.1,  # terminaisons -ità
                r"[àèéìíîòóù]": 0.2,  # accents italiens
            },
            "pt": {
                r"\b(?:o|a|os|as)\b": 0.4,
                r"\be\b": 0.2,
                r"\b(?:é|são|era|eram)\b": 0.2,
                r"\b(?:que|mas|com|por)\b": 0.2,
                r"ção\b": 0.2,  # terminaisons -ção
                r"dade\b": 0.1,  # terminaisons -dade
                r"[ãàâáçéêíóôõú]": 0.2,  # accents portugais
            },
            "nl": {
                r"\b(?:de|het|een)\b": 0.4,
                r"\ben\b": 0.2,
                r"\b(?:is|zijn|was|waren)\b": 0.2,
                r"\b(?:dit|dat|deze|die)\b": 0.2,
                r"ing\b": 0.1,
                r"lijk\b": 0.1,
                r"ij\b": 0.1,
            },
        }

    def _load_language_keywords(self) -> Dict[str, set]:
        """Charge les mots-clés spécifiques aux langues"""
        return {
            "fr": {
                "formation",
                "expérience",
                "experience",
                "compétences",
                "competences",
                "diplôme",
                "diplome",
                "entreprise",
                "poste",
                "stage",
                "depuis",
                "actuellement",
                "responsable",
                "projet",
                "développement",
                "developpement",
                "gestion",
                "équipe",
                "equipe",
                "français",
                "francais",
                "anglais",
                "niveau",
                "maîtrise",
                "maitrise",
                "connaissance",
                "technique",
            },
            "en": {
                "experience",
                "education",
                "skills",
                "degree",
                "company",
                "position",
                "internship",
                "current",
                "currently",
                "manager",
                "project",
                "development",
                "management",
                "team",
                "english",
                "language",
                "level",
                "proficient",
                "knowledge",
                "technical",
                "with",
                "from",
                "they",
                "have",
                "more",
                "like",
                "well",
                "first",
                "also",
                "after",
                "back",
                "other",
                "many",
                "than",
            },
            "de": {
                "erfahrung",
                "ausbildung",
                "fähigkeiten",
                "faehigkeiten",
                "abschluss",
                "unternehmen",
                "position",
                "praktikum",
                "aktuell",
                "derzeit",
                "leiter",
                "projekt",
                "entwicklung",
                "führung",
                "fuehrung",
                "team",
                "deutsch",
                "sprache",
                "niveau",
                "kenntnisse",
                "technisch",
                "bereich",
                "nach",
                "bei",
                "auf",
                "für",
                "fuer",
                "mit",
                "an",
                "zu",
                "von",
                "auch",
                "nur",
                "noch",
                "wie",
                "über",
                "ueber",
                "aus",
                "wenn",
            },
            "es": {
                "experiencia",
                "educación",
                "educacion",
                "habilidades",
                "título",
                "titulo",
                "empresa",
                "puesto",
                "prácticas",
                "practicas",
                "actual",
                "actualmente",
                "responsable",
                "proyecto",
                "desarrollo",
                "gestión",
                "gestion",
                "equipo",
                "español",
                "espanol",
                "idioma",
                "nivel",
                "dominio",
                "conocimiento",
                "técnico",
                "tecnico",
                "con",
                "para",
                "por",
                "como",
                "más",
                "mas",
                "todo",
                "bien",
                "muy",
                "ser",
                "estar",
                "tener",
                "hacer",
                "poder",
                "decir",
            },
            "it": {
                "esperienza",
                "educazione",
                "competenze",
                "laurea",
                "azienda",
                "posizione",
                "stage",
                "attuale",
                "attualmente",
                "responsabile",
                "progetto",
                "sviluppo",
                "gestione",
                "team",
                "italiano",
                "lingua",
                "livello",
                "padronanza",
                "conoscenza",
                "tecnico",
                "con",
                "per",
                "come",
                "più",
                "piu",
                "tutto",
                "bene",
                "molto",
                "essere",
                "avere",
                "fare",
                "dire",
                "andare",
                "potere",
                "dovere",
            },
            "pt": {
                "experiência",
                "experiencia",
                "educação",
                "educacao",
                "habilidades",
                "formação",
                "formacao",
                "empresa",
                "cargo",
                "estágio",
                "estagio",
                "atual",
                "atualmente",
                "responsável",
                "responsavel",
                "projeto",
                "desenvolvimento",
                "gestão",
                "gestao",
                "equipe",
                "português",
                "portugues",
                "idioma",
                "nível",
                "nivel",
                "domínio",
                "dominio",
                "conhecimento",
                "técnico",
                "tecnico",
                "com",
                "para",
                "por",
                "como",
                "mais",
                "todo",
                "bem",
                "muito",
                "ser",
                "estar",
                "ter",
                "fazer",
                "poder",
                "dizer",
            },
            "nl": {
                "de",
                "het",
                "een",
                "en",
                "is",
                "zijn",
                "was",
                "waren",
                "dit",
                "dat",
                "deze",
                "die",
                "ing",
                "lijk",
                "ij",
            },
        }

    def get_supported_languages(self) -> List[str]:
        """Retourne la liste des langues supportées"""
        return list(self.language_keywords.keys())

    def detect_multiple(
        self, text: str, threshold: float = 0.1
    ) -> List[Tuple[str, float]]:
        """Détecte plusieurs langues dans un texte avec scores"""
        if not text or len(text.strip()) < 20:
            return [("unknown", 0.0)]
        clean_text = self._clean_text_for_analysis(text)
        language_scores: Dict[str, float] = {}
        keyword_scores = self._analyze_keywords(clean_text)
        pattern_scores = self._analyze_patterns(clean_text)
        for lang in set(keyword_scores.keys()) | set(pattern_scores.keys()):
            score = (
                keyword_scores.get(lang, 0) * 0.6 + pattern_scores.get(lang, 0) * 0.4
            )
            if score >= threshold:
                language_scores[lang] = score
        result = sorted(language_scores.items(), key=lambda x: x[1], reverse=True)
        return result if result else [("unknown", 0.0)]
