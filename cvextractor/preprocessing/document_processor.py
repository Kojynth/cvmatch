"""
Processeur principal de documents
"""

import re
import unicodedata
import logging
from typing import Dict, Any, List

from .ocr_processor import OCRProcessor
from .language_detector import LanguageDetector
from ..core.config import ExtractionConfig

logger = logging.getLogger(__name__)


class DocumentPreprocessor:
    """Pré-processeur de documents avec OCR et détection de langue"""

    def __init__(self, config: ExtractionConfig):
        self.config = config
        self.ocr_processor = OCRProcessor(config)
        self.language_detector = LanguageDetector()

    def process(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """
        Pré-traite un document chargé

        Args:
            document: Document chargé par un loader

        Returns:
            Document pré-traité avec texte normalisé
        """
        logger.debug("🔧 Début pré-traitement document")

        processed_doc = document.copy()

        # 1. OCR si nécessaire
        if document.get("needs_ocr") and self.config.enable_ocr:
            logger.debug("👁️ Application OCR...")
            processed_doc = self.ocr_processor.process(processed_doc)

        # 2. Normalisation du texte
        logger.debug("📝 Normalisation du texte...")
        processed_doc["text"] = self._normalize_text(processed_doc["text"])

        # 3. Détection de langue
        logger.debug("🌍 Détection de langue...")
        detected_lang = self.language_detector.detect(processed_doc["text"])
        processed_doc["detected_language"] = detected_lang

        # 4. Nettoyage avancé basé sur la langue
        processed_doc["text"] = self._language_specific_cleanup(
            processed_doc["text"], detected_lang
        )

        # 5. Détection et suppression headers/footers
        processed_doc = self._remove_headers_footers(processed_doc)

        # 6. Métriques de qualité
        processed_doc["text_quality"] = self._assess_text_quality(processed_doc["text"])

        logger.debug(f"✅ Pré-traitement terminé - Langue: {detected_lang}")
        return processed_doc

    def _normalize_text(self, text: str) -> str:
        """Normalise le texte Unicode"""
        if not text:
            return ""

        # Normalisation Unicode
        text = unicodedata.normalize("NFKC", text)

        # Supprimer les caractères de contrôle sauf retours à la ligne et tabulations
        text = "".join(
            char
            for char in text
            if unicodedata.category(char)[0] != "C" or char in "\n\t\r"
        )

        # Normaliser les espaces
        text = re.sub(r"[ \t]+", " ", text)  # Espaces multiples -> simple
        text = re.sub(r"\n[ \t]+", "\n", text)  # Espaces en début de ligne
        text = re.sub(r"[ \t]+\n", "\n", text)  # Espaces en fin de ligne

        # Normaliser les retours à la ligne multiples
        text = re.sub(r"\n{3,}", "\n\n", text)

        return text.strip()

    def _language_specific_cleanup(self, text: str, language: str) -> str:
        """Nettoyage spécifique à la langue"""

        # Dé-hyphénation pour les langues européennes
        if language in ["fr", "en", "de", "es", "it"]:
            # Réparer les mots coupés en fin de ligne
            text = re.sub(
                r"([a-z])-\s*\n\s*([a-z])", r"\1\2", text, flags=re.IGNORECASE
            )

        # Corrections spécifiques français
        if language == "fr":
            # Espaces avant ponctuations
            text = re.sub(r"\s+([;:!?])", r" \1", text)
            text = re.sub(r"([;:!?])\s+", r"\1 ", text)

        # Corrections spécifiques anglais
        elif language == "en":
            # Contractions courantes
            contractions = {
                r"can't": "cannot",
                r"won't": "will not",
                r"n't": " not",
                r"'re": " are",
                r"'ve": " have",
                r"'ll": " will",
                r"'d": " would",
            }
            for pattern, replacement in contractions.items():
                text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

        return text

    def _remove_headers_footers(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """Détecte et supprime headers/footers répétitifs"""

        if document.get("page_count", 1) <= 1:
            return document

        pages = document.get("pages", [])
        if len(pages) <= 1:
            return document

        # Analyser les patterns répétitifs
        potential_headers = []
        potential_footers = []

        for page in pages:
            page_text = page.get("text", "")
            lines = page_text.split("\n")

            if len(lines) >= 2:
                # Première ligne comme header potentiel
                first_line = lines[0].strip()
                if len(first_line) > 5 and len(first_line) < 100:
                    potential_headers.append(first_line)

                # Dernière ligne comme footer potentiel
                last_line = lines[-1].strip()
                if len(last_line) > 5 and len(last_line) < 100:
                    potential_footers.append(last_line)

        # Identifier les headers/footers récurrents
        recurring_headers = self._find_recurring_patterns(potential_headers)
        recurring_footers = self._find_recurring_patterns(potential_footers)

        # Supprimer des pages
        cleaned_text_parts = []
        for page in pages:
            page_text = page.get("text", "")

            # Supprimer headers récurrents
            for header in recurring_headers:
                if page_text.startswith(header):
                    page_text = page_text[len(header) :].lstrip("\n")

            # Supprimer footers récurrents
            for footer in recurring_footers:
                if page_text.rstrip().endswith(footer):
                    page_text = page_text.rstrip()[: -len(footer)].rstrip("\n")

            cleaned_text_parts.append(page_text)

        # Mettre à jour le document
        document["text"] = "\n".join(cleaned_text_parts)
        document["headers_removed"] = len(recurring_headers)
        document["footers_removed"] = len(recurring_footers)

        return document

    def _find_recurring_patterns(
        self, patterns: List[str], min_occurrences: int = 2
    ) -> List[str]:
        """Trouve les patterns qui se répètent"""
        from collections import Counter

        if len(patterns) < min_occurrences:
            return []

        # Compter les occurrences exactes
        counter = Counter(patterns)
        recurring = [
            pattern for pattern, count in counter.items() if count >= min_occurrences
        ]

        return recurring

    def _assess_text_quality(self, text: str) -> Dict[str, Any]:
        """Évalue la qualité du texte extrait"""

        if not text:
            return {"score": 0.0, "issues": ["Texte vide"]}

        quality = {"score": 1.0, "issues": []}

        # Analyser la densité de caractères valides
        total_chars = len(text)
        valid_chars = len(re.findall(r"[a-zA-ZÀ-ÿ0-9\s\.,;:!?\-()]", text))
        char_density = valid_chars / total_chars if total_chars > 0 else 0

        if char_density < 0.8:
            quality["score"] *= 0.7
            quality["issues"].append(f"Densité caractères faible: {char_density:.2f}")

        # Analyser les mots valides
        words = re.findall(r"\b[a-zA-ZÀ-ÿ]+\b", text)
        if words:
            # Mots trop courts ou trop longs (possibles erreurs OCR)
            weird_words = [w for w in words if len(w) == 1 or len(w) > 25]
            weird_ratio = len(weird_words) / len(words)

            if weird_ratio > 0.1:
                quality["score"] *= 0.8
                quality["issues"].append(f"Mots suspects: {weird_ratio:.2f}")

        # Analyser la structure
        lines = text.split("\n")
        empty_line_ratio = sum(1 for line in lines if not line.strip()) / len(lines)

        if empty_line_ratio > 0.5:
            quality["score"] *= 0.9
            quality["issues"].append("Beaucoup de lignes vides")

        quality["char_density"] = char_density
        quality["word_count"] = len(words) if "words" in locals() else 0
        quality["line_count"] = len(lines)

        return quality
