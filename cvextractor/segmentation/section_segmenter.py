"""
Segmenteur de sections CV basé sur des heuristiques et ML léger
"""

import re
import logging
from typing import List, Dict, Any, Tuple
from collections import defaultdict

from ..core.types import CVSection, BoundingBox
from ..core.config import ExtractionConfig

logger = logging.getLogger(__name__)


class SectionSegmenter:
    """Segmente un CV en sections sémantiques"""

    def __init__(self, config: ExtractionConfig):
        self.config = config
        self.section_patterns = self._build_section_patterns()

    def segment(self, document: Dict[str, Any]) -> List[CVSection]:
        """
        Segmente un document en sections sémantiques

        Args:
            document: Document pré-traité

        Returns:
            Liste des sections détectées
        """
        logger.debug("📋 Début segmentation des sections")

        text = document.get("text", "")
        language = document.get("detected_language", "en")

        if not text.strip():
            logger.warning("⚠️ Texte vide - aucune segmentation possible")
            return []

        # 1. Détecter les titres de sections
        section_candidates = self._detect_section_headers(text, language)

        # 2. Valider et scorer les candidats
        validated_sections = self._validate_sections(section_candidates, text)

        # 3. Créer les sections avec contenu
        sections = self._create_sections(validated_sections, text)

        logger.debug(f"✅ Segmentation terminée: {len(sections)} sections détectées")
        return sections

    def _build_section_patterns(self) -> Dict[str, List[str]]:
        """Construit les patterns de détection des sections"""
        patterns = {}

        for section_type, aliases in self.config.section_aliases.items():
            patterns[section_type] = []

            for alias in aliases:
                # Pattern exact
                patterns[section_type].append(rf"^\s*{re.escape(alias)}\s*$")
                # Avec ponctuation
                patterns[section_type].append(rf"^\s*{re.escape(alias)}\s*[:;]\s*$")
                # Avec numérotation
                patterns[section_type].append(
                    rf"^\s*\d+[\.\)]\s*{re.escape(alias)}\s*$"
                )
                # En majuscules
                patterns[section_type].append(rf"^\s*{re.escape(alias.upper())}\s*$")

        return patterns

    def _detect_section_headers(
        self, text: str, language: str
    ) -> List[Tuple[str, int, str, float]]:
        """
        Détecte les titres de sections dans le texte

        Returns:
            List[(section_type, line_number, header_text, confidence)]
        """
        lines = text.split("\n")
        candidates = []

        for line_num, line in enumerate(lines):
            line_stripped = line.strip()
            if not line_stripped or len(line_stripped) > 100:
                continue

            # Tester chaque pattern de section
            for section_type, patterns in self.section_patterns.items():
                for pattern in patterns:
                    if re.match(pattern, line_stripped, re.IGNORECASE):
                        confidence = self._calculate_header_confidence(
                            line_stripped, line_num, lines, section_type
                        )

                        if confidence >= self.config.section_confidence_threshold:
                            candidates.append(
                                (section_type, line_num, line_stripped, confidence)
                            )
                        break

        # Trier par confiance décroissante
        candidates.sort(key=lambda x: x[3], reverse=True)
        return candidates

    def _calculate_header_confidence(
        self, header: str, line_num: int, lines: List[str], section_type: str
    ) -> float:
        """Calcule la confiance d'un titre de section"""

        confidence = 0.5  # Base

        # 1. Formatage typique des titres
        if header.isupper():
            confidence += 0.2
        if any(char in header for char in ":;"):
            confidence += 0.1
        if re.match(r"^\s*\d+[\.\)]\s*", header):
            confidence += 0.1

        # 2. Position dans le document
        total_lines = len(lines)
        relative_position = line_num / total_lines if total_lines > 0 else 0

        # Certaines sections apparaissent généralement dans certaines zones
        position_bonus = {
            "personal_info": 0.3 if relative_position < 0.3 else 0,
            "experience": 0.2 if 0.2 < relative_position < 0.8 else 0,
            "education": 0.2 if 0.3 < relative_position < 0.9 else 0,
            "skills": 0.1 if relative_position > 0.5 else 0,
            "interests": 0.2 if relative_position > 0.7 else 0,
        }
        confidence += position_bonus.get(section_type, 0)

        # 3. Contexte (lignes suivantes non vides)
        following_lines = 0
        for i in range(line_num + 1, min(line_num + 5, len(lines))):
            if lines[i].strip():
                following_lines += 1
            else:
                break

        if following_lines >= 2:
            confidence += 0.1

        # 4. Longueur appropriée pour un titre
        if 3 <= len(header) <= 50:
            confidence += 0.1

        return min(confidence, 1.0)

    def _validate_sections(
        self, candidates: List[Tuple[str, int, str, float]], text: str
    ) -> List[Tuple[str, int, str, float]]:
        """Valide et dédoublonne les candidats de sections"""

        validated = []
        used_lines = set()
        section_counts = defaultdict(int)

        for section_type, line_num, header, confidence in candidates:
            # Éviter les doublons de ligne
            if line_num in used_lines:
                continue

            # Limiter les sections multiples du même type
            if section_counts[section_type] >= 2:
                # Permettre seulement si confiance très haute
                if confidence < 0.9:
                    continue

            # Vérifier qu'il y a du contenu après
            if self._has_meaningful_content_after(line_num, text):
                validated.append((section_type, line_num, header, confidence))
                used_lines.add(line_num)
                section_counts[section_type] += 1

        return validated

    def _has_meaningful_content_after(self, header_line: int, text: str) -> bool:
        """Vérifie qu'il y a du contenu significatif après un titre"""

        lines = text.split("\n")
        content_lines = 0

        for i in range(header_line + 1, min(header_line + 10, len(lines))):
            line = lines[i].strip()
            if line and len(line) > 10:  # Ligne substantielle
                content_lines += 1
            elif line and any(char.isalpha() for char in line):
                content_lines += 0.5

        return content_lines >= 1.5

    def _create_sections(
        self, validated_sections: List[Tuple[str, int, str, float]], text: str
    ) -> List[CVSection]:
        """Crée les objets CVSection avec leur contenu"""

        lines = text.split("\n")
        sections = []

        # Trier par numéro de ligne
        validated_sections.sort(key=lambda x: x[1])

        for i, (section_type, line_num, header, confidence) in enumerate(
            validated_sections
        ):
            # Déterminer la fin de la section
            next_line = len(lines)
            if i + 1 < len(validated_sections):
                next_line = validated_sections[i + 1][1]

            # Extraire le contenu de la section
            section_lines = lines[line_num + 1 : next_line]
            section_content = "\n".join(section_lines).strip()

            if section_content:
                # Créer la section
                section = CVSection(
                    section_type=section_type,
                    title=header,
                    content=self._parse_section_content(section_content, section_type),
                    confidence=confidence,
                )
                sections.append(section)

        # Ajouter une section générique pour le contenu non classifié
        if sections:
            self._add_unclassified_content(sections, text)

        return sections

    def _parse_section_content(
        self, content: str, section_type: str
    ) -> List[Dict[str, Any]]:
        """Parse le contenu d'une section selon son type"""

        if section_type in ["experience", "education"]:
            return self._parse_structured_content(content)
        elif section_type in ["skills", "languages"]:
            return self._parse_list_content(content)
        elif section_type == "interests":
            return self._parse_interests_content(content)
        else:
            return [{"text": content}]

    def _parse_structured_content(self, content: str) -> List[Dict[str, Any]]:
        """Parse du contenu structuré (expériences, formation)"""

        items = []
        paragraphs = re.split(r"\n\s*\n", content)

        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if paragraph and len(paragraph) > 20:
                # Détecter les dates
                dates = re.findall(r"\b\d{4}(?:\s*[-–—]\s*\d{4})?\b", paragraph)

                items.append(
                    {
                        "text": paragraph,
                        "dates": dates,
                        "estimated_items": len(paragraph.split("\n")),
                    }
                )

        return items if items else [{"text": content}]

    def _parse_list_content(self, content: str) -> List[Dict[str, Any]]:
        """Parse du contenu en liste (compétences, langues)"""

        items = []

        # Diviser par lignes et séparateurs
        for line in content.split("\n"):
            line = line.strip()
            if not line:
                continue

            # Diviser par virgules, points, puces
            parts = re.split(r"[,;•\-\+]\s*", line)

            for part in parts:
                part = part.strip()
                if part and len(part) > 1:
                    items.append({"name": part, "text": part})

        return items if items else [{"text": content}]

    def _parse_interests_content(self, content: str) -> List[Dict[str, Any]]:
        """Parse spécialisé pour les centres d'intérêt"""

        interests = []

        # Nettoyer et diviser le contenu
        clean_content = re.sub(
            r"[^\w\sàâäéèêëïîôöùûüçñáéíóúü,;•\-]", " ", content, flags=re.IGNORECASE
        )

        # Diviser par séparateurs multiples
        parts = re.split(r"[,;•\-\n]\s*", clean_content)

        for part in parts:
            part = part.strip()
            if part and 2 < len(part) < 50:
                # Filtrer les patterns non pertinents
                if not re.search(r"\d{4}", part) and not any(
                    word in part.lower()
                    for word in [
                        "niveau",
                        "compétitif",
                        "entreprise",
                        "stage",
                        "formation",
                    ]
                ):
                    interests.append(
                        {"name": part, "category": "loisirs", "text": part}
                    )

        return interests[:10] if interests else [{"text": content}]

    def _add_unclassified_content(self, sections: List[CVSection], text: str):
        """Ajoute le contenu non classifié dans une section générique"""

        lines = text.split("\n")
        classified_lines = set()

        # Marquer les lignes déjà classifiées
        for section in sections:
            # Trouver les lignes de cette section dans le texte original
            section_text = "\n".join([item.get("text", "") for item in section.content])
            for line_num, line in enumerate(lines):
                if line.strip() in section_text:
                    classified_lines.add(line_num)

        # Collecter le contenu non classifié
        unclassified_lines = []
        for line_num, line in enumerate(lines):
            if line_num not in classified_lines and line.strip():
                unclassified_lines.append(line)

        if unclassified_lines:
            unclassified_content = "\n".join(unclassified_lines)
            other_section = CVSection(
                section_type="other",
                title="Autres informations",
                content=[{"text": unclassified_content}],
                confidence=0.3,
            )
            sections.append(other_section)
