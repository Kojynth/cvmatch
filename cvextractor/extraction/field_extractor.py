"""
Extracteur de champs principal
"""

import re
import logging
from typing import List, Dict, Any, Optional

from ..core.types import (
    ExtractionResult,
    ExtractedField,
    SourceProvenance,
    PersonalInfo,
    ContactInfo,
    Experience,
    Education,
    Skill,
    Language,
    Project,
    Certification,
    CVSection,
    ExtractionMethod,
    BoundingBox,
)
from ..core.config import ExtractionConfig

logger = logging.getLogger(__name__)


class FieldExtractor:
    """Extracteur principal de champs CV"""

    def __init__(self, config: ExtractionConfig):
        self.config = config

    def extract(
        self, sections: List[CVSection], document: Dict[str, Any]
    ) -> ExtractionResult:
        """
        Extrait tous les champs d'un CV segmenté

        Args:
            sections: Sections détectées
            document: Document original

        Returns:
            Résultat d'extraction complet
        """
        logger.debug("⚙️ Début extraction des champs")

        result = ExtractionResult()
        result.source_file = document.get("metadata", {}).get("filename", "")
        result.detected_language = document.get("detected_language", "unknown")

        # Extraire par type de section
        for section in sections:
            logger.debug(f"🔍 Traitement section: {section.section_type}")

            if section.section_type == "personal_info":
                result.personal_info = self._extract_personal_info(section, document)
            elif section.section_type == "contact_info":
                result.contact_info = self._extract_contact_info(section, document)
            elif section.section_type == "experience":
                result.experiences.extend(self._extract_experiences(section, document))
            elif section.section_type == "education":
                result.education.extend(self._extract_education(section, document))
            elif section.section_type == "skills":
                result.skills.extend(self._extract_skills(section, document))
            elif section.section_type == "languages":
                result.languages.extend(self._extract_languages(section, document))
            elif section.section_type == "projects":
                result.projects.extend(self._extract_projects(section, document))
            elif section.section_type == "certifications":
                result.certifications.extend(
                    self._extract_certifications(section, document)
                )
            elif section.section_type == "interests":
                # Stocker les intérêts dans other_sections
                interests_section = CVSection(
                    section_type="interests",
                    title=section.title,
                    content=self._extract_interests(section, document),
                    confidence=section.confidence,
                )
                result.other_sections.append(interests_section)
            else:
                result.other_sections.append(section)

        # Extraction globale pour les champs manquants
        self._extract_global_fields(result, document)

        logger.debug(f"✅ Extraction terminée")
        return result

    def _extract_personal_info(
        self, section: CVSection, document: Dict[str, Any]
    ) -> PersonalInfo:
        """Extrait les informations personnelles"""

        text = self._get_section_text(section)
        personal_info = PersonalInfo()

        # Nom complet (première ligne non vide souvent)
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        if lines:
            first_line = lines[0]
            if len(first_line.split()) <= 4 and len(first_line) > 3:
                personal_info.full_name = ExtractedField(
                    value=first_line,
                    provenance=SourceProvenance(
                        page=0,
                        method=ExtractionMethod.HEURISTIC,
                        confidence=0.8,
                        source_text=first_line,
                    ),
                )

        # Titre/poste recherché
        title_patterns = [
            r"(?:recherche|objectif|poste)\s*:?\s*(.+)",
            r"(?:titre|function|role)\s*:?\s*(.+)",
        ]
        for pattern in title_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                personal_info.title = ExtractedField(
                    value=match.group(1).strip(),
                    provenance=SourceProvenance(
                        page=0,
                        method=ExtractionMethod.REGEX,
                        confidence=0.7,
                        source_text=match.group(0),
                    ),
                )
                break

        return personal_info

    def _extract_contact_info(
        self, section: CVSection, document: Dict[str, Any]
    ) -> ContactInfo:
        """Extrait les informations de contact"""

        text = self._get_section_text(section)
        contact_info = ContactInfo()

        # Email
        email_match = re.search(self.config.email_pattern, text)
        if email_match:
            contact_info.email = ExtractedField(
                value=email_match.group(),
                provenance=SourceProvenance(
                    page=0,
                    method=ExtractionMethod.REGEX,
                    confidence=0.95,
                    source_text=email_match.group(),
                ),
            )

        # Téléphone
        for pattern in self.config.phone_patterns:
            phone_match = re.search(pattern, text)
            if phone_match:
                contact_info.phone = ExtractedField(
                    value=phone_match.group().strip(),
                    provenance=SourceProvenance(
                        page=0,
                        method=ExtractionMethod.REGEX,
                        confidence=0.8,
                        source_text=phone_match.group(),
                    ),
                )
                break

        # LinkedIn
        linkedin_match = re.search(r"linkedin\.com/in/([\w\-]+)", text, re.IGNORECASE)
        if linkedin_match:
            full_url = f"https://linkedin.com/in/{linkedin_match.group(1)}"
            contact_info.linkedin = ExtractedField(
                value=full_url,
                provenance=SourceProvenance(
                    page=0,
                    method=ExtractionMethod.REGEX,
                    confidence=0.9,
                    source_text=linkedin_match.group(0),
                ),
            )

        return contact_info

    def _extract_experiences(
        self, section: CVSection, document: Dict[str, Any]
    ) -> List[Experience]:
        """Extrait les expériences professionnelles"""

        experiences = []
        language = document.get("detected_language", "en")
        date_patterns = self.config.get_date_patterns(language)

        for item in section.content:
            text = item.get("text", "")
            if not text or len(text) < 20:
                continue

            experience = Experience()

            # Analyser la structure (titre - entreprise - dates - description)
            lines = [line.strip() for line in text.split("\n") if line.strip()]

            if lines:
                # Première ligne souvent: "Titre chez Entreprise" ou "Titre - Entreprise"
                first_line = lines[0]

                # Pattern: "Titre chez/at/bei Entreprise"
                position_patterns = [
                    r"(.+?)\s+(?:chez|at|bei|en)\s+(.+)",
                    r"(.+?)\s+[-–—]\s+(.+)",
                    r"(.+?)\s+[,]\s+(.+)",
                ]

                for pattern in position_patterns:
                    match = re.match(pattern, first_line, re.IGNORECASE)
                    if match:
                        experience.title = ExtractedField(
                            value=match.group(1).strip(),
                            provenance=SourceProvenance(
                                page=0,
                                method=ExtractionMethod.REGEX,
                                confidence=0.8,
                                source_text=first_line,
                            ),
                        )
                        experience.company = ExtractedField(
                            value=match.group(2).strip(),
                            provenance=SourceProvenance(
                                page=0,
                                method=ExtractionMethod.REGEX,
                                confidence=0.8,
                                source_text=first_line,
                            ),
                        )
                        break

                # Si pas de pattern trouvé, supposer que c'est le titre
                if not experience.title:
                    experience.title = ExtractedField(
                        value=first_line,
                        provenance=SourceProvenance(
                            page=0,
                            method=ExtractionMethod.HEURISTIC,
                            confidence=0.6,
                            source_text=first_line,
                        ),
                    )

            # Extraire les dates
            dates = item.get("dates", [])
            if dates:
                date_str = dates[0]
                start_date, end_date = self._parse_date_range(date_str)

                if start_date:
                    experience.start_date = ExtractedField(
                        value=start_date,
                        provenance=SourceProvenance(
                            page=0,
                            method=ExtractionMethod.REGEX,
                            confidence=0.7,
                            source_text=date_str,
                        ),
                    )

                if end_date:
                    experience.end_date = ExtractedField(
                        value=end_date,
                        provenance=SourceProvenance(
                            page=0,
                            method=ExtractionMethod.REGEX,
                            confidence=0.7,
                            source_text=date_str,
                        ),
                    )

            # Description (lignes suivantes)
            if len(lines) > 1:
                description = "\n".join(lines[1:])
                experience.description = ExtractedField(
                    value=description,
                    provenance=SourceProvenance(
                        page=0,
                        method=ExtractionMethod.HEURISTIC,
                        confidence=0.5,
                        source_text=description[:100],
                    ),
                )

            experiences.append(experience)

        return experiences

    def _extract_education(
        self, section: CVSection, document: Dict[str, Any]
    ) -> List[Education]:
        """Extrait les formations"""

        education_list = []

        for item in section.content:
            text = item.get("text", "")
            if not text or len(text) < 10:
                continue

            education = Education()

            lines = [line.strip() for line in text.split("\n") if line.strip()]
            if lines:
                first_line = lines[0]

                # Pattern: "Diplôme - Établissement"
                edu_patterns = [
                    r"(.+?)\s+[-–—]\s+(.+)",
                    r"(.+?)\s+[,]\s+(.+)",
                    r"(.+?)\s+(?:à|at|an)\s+(.+)",
                ]

                for pattern in edu_patterns:
                    match = re.match(pattern, first_line, re.IGNORECASE)
                    if match:
                        education.degree = ExtractedField(
                            value=match.group(1).strip(),
                            provenance=SourceProvenance(
                                page=0,
                                method=ExtractionMethod.REGEX,
                                confidence=0.8,
                                source_text=first_line,
                            ),
                        )
                        education.institution = ExtractedField(
                            value=match.group(2).strip(),
                            provenance=SourceProvenance(
                                page=0,
                                method=ExtractionMethod.REGEX,
                                confidence=0.8,
                                source_text=first_line,
                            ),
                        )
                        break

                if not education.degree:
                    education.degree = ExtractedField(
                        value=first_line,
                        provenance=SourceProvenance(
                            page=0,
                            method=ExtractionMethod.HEURISTIC,
                            confidence=0.6,
                            source_text=first_line,
                        ),
                    )

            # Dates
            dates = item.get("dates", [])
            if dates:
                date_str = dates[0]
                start_date, end_date = self._parse_date_range(date_str)

                if end_date:  # Pour l'éducation, la date de fin est plus importante
                    education.end_date = ExtractedField(
                        value=end_date,
                        provenance=SourceProvenance(
                            page=0,
                            method=ExtractionMethod.REGEX,
                            confidence=0.7,
                            source_text=date_str,
                        ),
                    )

            education_list.append(education)

        return education_list

    def _extract_skills(
        self, section: CVSection, document: Dict[str, Any]
    ) -> List[Skill]:
        """Extrait les compétences"""

        skills = []

        for item in section.content:
            name = item.get("name", item.get("text", ""))
            if name and len(name.strip()) > 1:
                skill = Skill(
                    name=ExtractedField(
                        value=name.strip(),
                        provenance=SourceProvenance(
                            page=0,
                            method=ExtractionMethod.HEURISTIC,
                            confidence=0.7,
                            source_text=name,
                        ),
                    )
                )
                skills.append(skill)

        return skills

    def _extract_languages(
        self, section: CVSection, document: Dict[str, Any]
    ) -> List[Language]:
        """Extrait les langues"""

        languages = []

        for item in section.content:
            name = item.get("name", item.get("text", ""))
            if name and len(name.strip()) > 1:
                language = Language(
                    name=ExtractedField(
                        value=name.strip(),
                        provenance=SourceProvenance(
                            page=0,
                            method=ExtractionMethod.HEURISTIC,
                            confidence=0.7,
                            source_text=name,
                        ),
                    )
                )
                languages.append(language)

        return languages

    def _extract_projects(
        self, section: CVSection, document: Dict[str, Any]
    ) -> List[Project]:
        """Extrait les projets"""

        projects = []

        for item in section.content:
            text = item.get("text", "")
            if text and len(text.strip()) > 5:

                # Première ligne comme nom du projet
                lines = [line.strip() for line in text.split("\n") if line.strip()]
                project_name = lines[0] if lines else text[:50]

                project = Project(
                    name=ExtractedField(
                        value=project_name,
                        provenance=SourceProvenance(
                            page=0,
                            method=ExtractionMethod.HEURISTIC,
                            confidence=0.6,
                            source_text=project_name,
                        ),
                    )
                )

                # Description (lignes suivantes)
                if len(lines) > 1:
                    description = "\n".join(lines[1:])
                    project.description = ExtractedField(
                        value=description,
                        provenance=SourceProvenance(
                            page=0,
                            method=ExtractionMethod.HEURISTIC,
                            confidence=0.5,
                            source_text=description[:100],
                        ),
                    )

                projects.append(project)

        return projects

    def _extract_certifications(
        self, section: CVSection, document: Dict[str, Any]
    ) -> List[Certification]:
        """Extrait les certifications"""

        certifications = []

        for item in section.content:
            name = item.get("name", item.get("text", ""))
            if name and len(name.strip()) > 3:
                certification = Certification(
                    name=ExtractedField(
                        value=name.strip(),
                        provenance=SourceProvenance(
                            page=0,
                            method=ExtractionMethod.HEURISTIC,
                            confidence=0.6,
                            source_text=name,
                        ),
                    )
                )
                certifications.append(certification)

        return certifications

    def _extract_interests(
        self, section: CVSection, document: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Extrait les centres d'intérêt"""

        interests = []

        for item in section.content:
            name = item.get("name", item.get("text", ""))
            if name and len(name.strip()) > 1:
                interests.append(
                    {
                        "name": name.strip(),
                        "category": item.get("category", "loisirs"),
                        "confidence": 0.6,
                    }
                )

        return interests

    def _extract_global_fields(
        self, result: ExtractionResult, document: Dict[str, Any]
    ):
        """Extraction globale pour les champs manquants"""

        full_text = document.get("text", "")

        # Si pas d'email trouvé dans les sections, chercher globalement
        if not result.contact_info.email:
            email_match = re.search(self.config.email_pattern, full_text)
            if email_match:
                result.contact_info.email = ExtractedField(
                    value=email_match.group(),
                    provenance=SourceProvenance(
                        page=0,
                        method=ExtractionMethod.REGEX,
                        confidence=0.9,
                        source_text=email_match.group(),
                    ),
                )

        # Même chose pour le téléphone
        if not result.contact_info.phone:
            for pattern in self.config.phone_patterns:
                phone_match = re.search(pattern, full_text)
                if phone_match:
                    result.contact_info.phone = ExtractedField(
                        value=phone_match.group().strip(),
                        provenance=SourceProvenance(
                            page=0,
                            method=ExtractionMethod.REGEX,
                            confidence=0.8,
                            source_text=phone_match.group(),
                        ),
                    )
                    break

    def _get_section_text(self, section: CVSection) -> str:
        """Récupère tout le texte d'une section"""
        texts = []
        for item in section.content:
            if "text" in item:
                texts.append(item["text"])
        return "\n".join(texts)

    def _parse_date_range(self, date_str: str) -> tuple[Optional[str], Optional[str]]:
        """Parse une chaîne de dates en début/fin"""

        # Pattern: "2020-2022", "2020 - 2022", "depuis 2020", etc.
        range_patterns = [
            r"(\d{4})\s*[-–—]\s*(\d{4})",
            r"(\d{4})\s*[-–—]\s*(?:présent|present|current|aujourd\'hui)",
            r"(?:depuis|since|ab)\s+(\d{4})",
            r"(\d{4})",
        ]

        for pattern in range_patterns:
            match = re.search(pattern, date_str, re.IGNORECASE)
            if match:
                groups = match.groups()
                if len(groups) == 2:
                    return groups[0], groups[1]
                elif len(groups) == 1:
                    # Date unique, probablement de fin
                    return None, groups[0]

        return None, None
