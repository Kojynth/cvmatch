"""
Normalisateur et validateur de données extraites
"""

import re
import logging
from datetime import datetime
from typing import Any, Optional

from ..core.types import ExtractionResult, ExtractedField
from ..core.config import ExtractionConfig

logger = logging.getLogger(__name__)


class DataNormalizer:
    """Normalise et valide les données extraites"""

    def __init__(self, config: ExtractionConfig):
        self.config = config

    def normalize(self, result: ExtractionResult) -> ExtractionResult:
        """
        Normalise tous les champs d'un résultat d'extraction

        Args:
            result: Résultat brut d'extraction

        Returns:
            Résultat normalisé et validé
        """
        logger.debug("✨ Début normalisation des données")

        # Normaliser les informations personnelles
        if result.personal_info:
            if result.personal_info.full_name:
                result.personal_info.full_name.normalized_value = self._normalize_name(
                    result.personal_info.full_name.value
                )

            if result.personal_info.title:
                result.personal_info.title.normalized_value = self._normalize_title(
                    result.personal_info.title.value
                )

        # Normaliser les informations de contact
        if result.contact_info:
            if result.contact_info.email:
                result.contact_info.email.normalized_value = self._normalize_email(
                    result.contact_info.email.value, result.contact_info.email
                )

            if result.contact_info.phone:
                result.contact_info.phone.normalized_value = self._normalize_phone(
                    result.contact_info.phone.value, result.contact_info.phone
                )

            if result.contact_info.linkedin:
                result.contact_info.linkedin.normalized_value = self._normalize_url(
                    result.contact_info.linkedin.value
                )

        # Normaliser les expériences
        for experience in result.experiences:
            if experience.start_date:
                experience.start_date.normalized_value = self._normalize_date(
                    experience.start_date.value, experience.start_date
                )

            if experience.end_date:
                experience.end_date.normalized_value = self._normalize_date(
                    experience.end_date.value, experience.end_date
                )

            # Calculer la durée si possible
            if experience.start_date and experience.end_date:
                duration = self._calculate_duration(
                    experience.start_date.normalized_value
                    or experience.start_date.value,
                    experience.end_date.normalized_value or experience.end_date.value,
                )
                if duration:
                    experience.duration_months = ExtractedField(
                        value=duration,
                        provenance=experience.start_date.provenance,
                        normalized_value=duration,
                    )

        # Normaliser l'éducation
        for education in result.education:
            if education.start_date:
                education.start_date.normalized_value = self._normalize_date(
                    education.start_date.value, education.start_date
                )

            if education.end_date:
                education.end_date.normalized_value = self._normalize_date(
                    education.end_date.value, education.end_date
                )

        # Normaliser les compétences
        for skill in result.skills:
            if skill.name:
                skill.name.normalized_value = self._normalize_skill(skill.name.value)

        # Normaliser les langues
        for language in result.languages:
            if language.name:
                language.name.normalized_value = self._normalize_language(
                    language.name.value
                )

        logger.debug("✅ Normalisation terminée")
        return result

    def _normalize_name(self, name: str) -> str:
        """Normalise un nom de personne"""
        if not name:
            return ""

        # Supprimer les caractères spéciaux excessifs
        name = re.sub(r"[^\w\s\-\']", " ", name)

        # Normaliser les espaces
        name = re.sub(r"\s+", " ", name).strip()

        # Capitalisation appropriée
        words = name.split()
        normalized_words = []

        for word in words:
            if len(word) > 1:
                # Gérer les noms avec apostrophes (O'Connor, D'Artagnan)
                if "'" in word:
                    parts = word.split("'")
                    normalized_parts = [part.capitalize() for part in parts]
                    normalized_words.append("'".join(normalized_parts))
                # Gérer les noms avec tirets (Jean-Pierre)
                elif "-" in word:
                    parts = word.split("-")
                    normalized_parts = [part.capitalize() for part in parts]
                    normalized_words.append("-".join(normalized_parts))
                else:
                    normalized_words.append(word.capitalize())
            else:
                normalized_words.append(word.upper())

        return " ".join(normalized_words)

    def _normalize_title(self, title: str) -> str:
        """Normalise un titre de poste"""
        if not title:
            return ""

        # Nettoyer
        title = re.sub(r"[^\w\s\-/]", " ", title)
        title = re.sub(r"\s+", " ", title).strip()

        # Capitalisation des mots importants
        words = title.split()
        normalized_words = []

        # Articles et prépositions à ne pas capitaliser (sauf en début)
        articles = {
            "de",
            "du",
            "des",
            "le",
            "la",
            "les",
            "un",
            "une",
            "et",
            "ou",
            "of",
            "the",
            "a",
            "an",
            "and",
            "or",
            "in",
            "at",
            "for",
        }

        for i, word in enumerate(words):
            if i == 0 or word.lower() not in articles:
                normalized_words.append(word.capitalize())
            else:
                normalized_words.append(word.lower())

        return " ".join(normalized_words)

    def _normalize_email(self, email: str, field: ExtractedField) -> str:
        """Normalise et valide une adresse email"""
        if not email:
            return ""

        # Nettoyer
        email = email.strip().lower()

        # Validation basique
        if self.config.validate_emails:
            if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
                field.validation_status = "invalid"
                field.warnings.append("Format email invalide")
                return email

        field.validation_status = "valid"
        return email

    def _normalize_phone(self, phone: str, field: ExtractedField) -> str:
        """Normalise un numéro de téléphone"""
        if not phone:
            return ""

        # Nettoyer - garder seulement chiffres et +
        clean_phone = re.sub(r"[^\d+]", "", phone)

        if self.config.normalize_phones:
            # Tentative de normalisation E.164 basique
            if clean_phone.startswith("0"):
                # Numéro français local -> international
                clean_phone = "+33" + clean_phone[1:]
            elif not clean_phone.startswith("+"):
                # Ajouter indicatif par défaut si pas de +
                if len(clean_phone) == 10:  # Probablement français
                    clean_phone = (
                        "+33" + clean_phone[1:]
                        if clean_phone.startswith("0")
                        else "+33" + clean_phone
                    )

        # Validation longueur basique
        if len(clean_phone) < 8 or len(clean_phone) > 15:
            field.validation_status = "suspicious"
            field.warnings.append("Longueur de numéro inhabituelle")
        else:
            field.validation_status = "valid"

        return clean_phone

    def _normalize_url(self, url: str) -> str:
        """Normalise une URL"""
        if not url:
            return ""

        url = url.strip()

        # Ajouter protocole si manquant
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        # Normaliser LinkedIn spécifiquement
        if "linkedin.com" in url:
            # Extraire juste la partie profil
            match = re.search(r"linkedin\.com/in/([\w\-]+)", url)
            if match:
                url = f"https://linkedin.com/in/{match.group(1)}"

        return url

    def _normalize_date(self, date: str, field: ExtractedField) -> str:
        """Normalise une date au format ISO"""
        if not date:
            return ""

        if not self.config.normalize_dates:
            return date

        # Patterns de dates courants
        date_patterns = [
            (r"(\d{4})", r"\1"),  # 2020 -> 2020
            (r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})", r"\3-\2-\1"),  # DD/MM/YYYY
            (r"(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})", r"\1-\2-\3"),  # YYYY/MM/DD
        ]

        for pattern, replacement in date_patterns:
            match = re.match(pattern, date.strip())
            if match:
                try:
                    normalized = re.sub(pattern, replacement, date.strip())
                    # Valider que c'est une date plausible
                    if self._validate_date(normalized):
                        field.validation_status = "valid"
                        return normalized
                except:
                    pass

        # Si aucun pattern ne marche, garder l'original
        field.validation_status = "raw"
        field.warnings.append("Format de date non reconnu")
        return date

    def _validate_date(self, date_str: str) -> bool:
        """Valide qu'une date est plausible"""
        try:
            # Vérifier que l'année est raisonnable
            year_match = re.search(r"(\d{4})", date_str)
            if year_match:
                year = int(year_match.group(1))
                current_year = datetime.now().year
                # Années entre 1950 et année courante + 1
                return 1950 <= year <= current_year + 1
        except:
            pass
        return False

    def _calculate_duration(self, start_date: str, end_date: str) -> Optional[int]:
        """Calcule la durée en mois entre deux dates"""
        try:
            # Extraire les années
            start_year = int(re.search(r"(\d{4})", start_date).group(1))

            # Gérer "présent", "current", etc.
            if any(
                keyword in end_date.lower()
                for keyword in ["présent", "present", "current", "aujourd'hui"]
            ):
                end_year = datetime.now().year
            else:
                end_year = int(re.search(r"(\d{4})", end_date).group(1))

            # Calcul approximatif en mois (12 mois par an)
            duration = (end_year - start_year) * 12

            # Ajustements basiques pour les mois si disponibles
            start_month_match = re.search(r"-(\d{2})-", start_date)
            end_month_match = re.search(r"-(\d{2})-", end_date)

            if start_month_match and end_month_match:
                start_month = int(start_month_match.group(1))
                end_month = int(end_month_match.group(1))
                duration += end_month - start_month

            return max(duration, 1)  # Au minimum 1 mois

        except Exception as e:
            logger.debug(f"Impossible de calculer la durée: {e}")
            return None

    def _normalize_skill(self, skill: str) -> str:
        """Normalise le nom d'une compétence"""
        if not skill:
            return ""

        # Nettoyer
        skill = skill.strip()
        skill = re.sub(r"[^\w\s\+\#\.]", " ", skill)  # Garder +, #, . pour les techno
        skill = re.sub(r"\s+", " ", skill).strip()

        # Capitalisation appropriée pour les technologies
        # JavaScript, C++, etc.
        tech_mappings = {
            "javascript": "JavaScript",
            "typescript": "TypeScript",
            "nodejs": "Node.js",
            "reactjs": "React.js",
            "vuejs": "Vue.js",
            "angularjs": "Angular.js",
            "c++": "C++",
            "c#": "C#",
            ".net": ".NET",
            "mysql": "MySQL",
            "postgresql": "PostgreSQL",
            "mongodb": "MongoDB",
        }

        skill_lower = skill.lower()
        for key, value in tech_mappings.items():
            if skill_lower == key:
                return value

        # Capitalisation par défaut
        return skill.title()

    def _normalize_language(self, language: str) -> str:
        """Normalise le nom d'une langue"""
        if not language:
            return ""

        # Nettoyer
        language = language.strip()

        # Mappings des langues
        language_mappings = {
            "fr": "Français",
            "french": "Français",
            "francais": "Français",
            "en": "Anglais",
            "english": "Anglais",
            "anglais": "Anglais",
            "de": "Allemand",
            "german": "Allemand",
            "deutsch": "Allemand",
            "allemand": "Allemand",
            "es": "Espagnol",
            "spanish": "Espagnol",
            "espanol": "Espagnol",
            "espagnol": "Espagnol",
            "it": "Italien",
            "italian": "Italien",
            "italiano": "Italien",
            "italien": "Italien",
            "pt": "Portugais",
            "portuguese": "Portugais",
            "portugues": "Portugais",
            "portugais": "Portugais",
        }

        language_lower = language.lower()
        for key, value in language_mappings.items():
            if key in language_lower:
                return value

        # Capitalisation par défaut
        return language.capitalize()
