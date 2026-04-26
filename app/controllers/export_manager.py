"""
Export Manager
==============

Gestionnaire pour l'export des CV en différents formats.
"""

import os
import re
import tempfile
import unicodedata
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from jinja2 import Environment, FileSystemLoader
from loguru import logger

# WeasyPrint sera importé seulement quand nécessaire pour éviter les messages d'erreur multiples
WEASYPRINT_AVAILABLE = None  # Sera déterminé lors du premier usage

PDF_ONE_PAGE_FIT_CSS = """
@page {
  size: A4;
  margin: 8mm;
}
@media print {
  html,
  body {
    margin: 0 !important;
    padding: 0 !important;
    background: #ffffff !important;
  }
  body {
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }
  .cv-container {
    width: 194mm !important;
    max-width: 194mm !important;
    margin: 0 auto !important;
    border: none !important;
    border-radius: 0 !important;
    box-shadow: none !important;
    overflow: visible !important;
    background: #ffffff !important;
  }
  .cv-header,
  .cv-body {
    padding-left: 14px !important;
    padding-right: 14px !important;
  }
  .cv-header {
    padding-top: 12px !important;
    padding-bottom: 8px !important;
    margin-bottom: 10px !important;
  }
  .cv-body {
    padding-top: 8px !important;
    padding-bottom: 10px !important;
  }
  .cv-header .name {
    font-size: 24px !important;
    line-height: 1.05 !important;
  }
  .cv-header .title {
    font-size: 11px !important;
    line-height: 1.2 !important;
    margin-top: 4px !important;
  }
  .contact-info {
    margin-top: 6px !important;
    gap: 5px 10px !important;
  }
  .contact-label,
  .contact-value,
  .contact-item {
    font-size: 9px !important;
    line-height: 1.15 !important;
  }
  .cv-section {
    margin-top: 7px !important;
  }
  .section-title {
    margin-top: 0 !important;
    margin-bottom: 4px !important;
    font-size: 9.5px !important;
    line-height: 1.1 !important;
  }
  .section-content,
  .dynamic-content {
    font-size: 10.3px !important;
    line-height: 1.18 !important;
  }
  .entry h3 {
    margin-top: 6px !important;
    margin-bottom: 2px !important;
    font-size: 12px !important;
    line-height: 1.18 !important;
  }
  .meta {
    margin: 2px 0 3px !important;
    font-size: 9.5px !important;
    line-height: 1.15 !important;
  }
  .summary-content,
  .skill-chip-list {
    gap: 4px !important;
  }
  .skill-chip {
    padding: 1px 6px !important;
    font-size: 9.5px !important;
    line-height: 1.1 !important;
  }
  .experience-highlights,
  .certification-list,
  ul {
    margin-top: 3px !important;
    margin-bottom: 3px !important;
    padding-left: 13px !important;
  }
  .experience-highlights {
    padding-left: 0 !important;
  }
  .experience-highlight {
    margin: 0 0 1px !important;
    padding-left: 13px !important;
  }
  li {
    margin-bottom: 1px !important;
  }
  .cv-section,
  .entry,
  .experience-entry,
  .education-entry,
  .project-entry {
    break-inside: avoid;
    page-break-inside: avoid;
  }
  a {
    color: inherit !important;
    text-decoration: none !important;
  }
}
"""


def _check_weasyprint():
    """Vérifie la disponibilité de WeasyPrint seulement quand nécessaire."""
    global WEASYPRINT_AVAILABLE
    if WEASYPRINT_AVAILABLE is None:
        try:
            from weasyprint import HTML, CSS

            WEASYPRINT_AVAILABLE = True
            # Ne pas logger ici pour éviter les messages multiples
        except (ImportError, OSError):
            WEASYPRINT_AVAILABLE = False
    return WEASYPRINT_AVAILABLE


class ExportManager:
    """Gestionnaire d'export pour les CV."""

    DEFAULT_PRIMARY_EXPERIENCE_COUNT = 4
    PRIMARY_EXPERIENCE_COUNT = DEFAULT_PRIMARY_EXPERIENCE_COUNT
    MIN_PRIMARY_EXPERIENCE_COUNT = 2
    MAX_PRIMARY_EXPERIENCE_COUNT = 6
    PRIMARY_EXPERIENCE_INFO_BUDGET = 12
    PRIMARY_EXPERIENCE_RELEVANCE_THRESHOLD = 1.0

    def __init__(self):
        # Chemin vers les templates
        self.templates_dir = Path(__file__).parent.parent.parent / "templates"
        self.cv_templates_dir = self.templates_dir / "cv_templates"
        self.css_dir = self.templates_dir / "css"

        # Configuration Jinja2
        self.jinja_env = Environment(
            loader=FileSystemLoader(
                [str(self.cv_templates_dir), str(self.templates_dir)]
            ),
            autoescape=True,
        )

        # Ajouter des filtres personnalisés
        self.jinja_env.filters["rjust"] = self._filter_rjust
        self.jinja_env.filters["ljust"] = self._filter_ljust

        # Formats supportés
        self.supported_formats = ["html"]
        if _check_weasyprint():
            self.supported_formats.append("pdf")

    def _filter_rjust(self, value, width, fillchar=" "):
        """Filtre Jinja2 pour rjust (alignement à droite)."""
        return str(value).rjust(int(width), str(fillchar))

    def _filter_ljust(self, value, width, fillchar=" "):
        """Filtre Jinja2 pour ljust (alignement à gauche)."""
        return str(value).ljust(int(width), str(fillchar))

    def export_cv(
        self,
        cv_data: Dict[str, Any],
        template: str = "modern",
        output_format: str = "html",  # Changé par défaut
        output_path: Optional[str] = None,
    ) -> str:
        """Exporte un CV dans le format spécifié."""

        if output_format not in self.supported_formats:
            available_formats = ", ".join(self.supported_formats)
            raise ValueError(
                f"Format {output_format} non supporté. Formats disponibles: {available_formats}"
            )

        # Génération HTML
        html_content = self.generate_html(cv_data, template)

        if output_format == "html":
            return self.save_html(html_content, output_path)
        elif output_format == "pdf":
            if not _check_weasyprint():
                # Fallback vers HTML si PDF non disponible
                logger.warning(
                    "Export PDF demandé mais WeasyPrint non disponible - Export en HTML"
                )
                return self.save_html(
                    html_content,
                    output_path.replace(".pdf", ".html") if output_path else None,
                )
            return self.generate_pdf(html_content, template, output_path)

    def generate_html(
        self, cv_data: Dict[str, Any], template: str, is_fallback: bool = False
    ) -> str:
        """Génère le HTML du CV."""
        try:
            # Charger le template
            template_file = f"{template}.html"
            jinja_template = self.jinja_env.get_template(template_file)

            # Préparer les données
            formatted_data = self.prepare_template_data(cv_data)

            # Générer le HTML
            html_content = jinja_template.render(**formatted_data)

            # Ajouter le message d'avertissement fallback si nécessaire
            if is_fallback:
                html_content = self._inject_fallback_warning(html_content)

            logger.info(f"HTML généré avec template {template}")
            return html_content

        except Exception as e:
            logger.error(f"Erreur génération HTML : {e}")
            raise

    def prepare_template_data(self, cv_data: Dict[str, Any]) -> Dict[str, Any]:
        """Prépare les données pour le template."""
        # Données par défaut
        formatted_data = {
            "name": "",
            "email": "",
            "phone": "",
            "linkedin_url": "",
            "location": "",
            "links": [],
            "contact_methods": [],
            "job_title": "",
            "profile_summary": "",
            "profile_summary_lines": [],
            "experience": [],
            "education": [],
            "skills": [],
            "soft_skills": [],
            "featured_skills": [],
            "featured_soft_skills": [],
            "languages": [],
            "projects": [],
            "featured_project": None,
            "certifications": [],
            "featured_certifications": [],
            "interests": [],
            "labels": {},
            "language": "fr",
            "photo_base64": "",
            "target_role_line": "",
        }

        # Fusion avec les données fournies
        if isinstance(cv_data, dict):
            formatted_data.update(cv_data)

        language = formatted_data.get("language") or "fr"
        language_code = str(language).strip().lower()
        is_en = language_code.startswith("en")
        default_labels = {
            "contact": "Contact" if is_en else "Contact",
            "profile": "Profile" if is_en else "Profil",
            "experience": "Experience" if is_en else "Expérience",
            "additional_relevant": (
                "Additional relevant details"
                if is_en
                else "Éléments complémentaires pertinents"
            ),
            "skills": "Skills" if is_en else "Compétences",
            "soft_skills": "Soft skills" if is_en else "Savoir-être",
            "education": "Education" if is_en else "Formation",
            "projects": "Projects" if is_en else "Projets",
            "languages": "Languages" if is_en else "Langues",
            "certifications": "Certifications",
            "interests": "Interests" if is_en else "Centres d'intérêt",
        }
        labels = formatted_data.get("labels")
        if not isinstance(labels, dict):
            labels = {}
        for key, value in default_labels.items():
            if not labels.get(key):
                labels[key] = value
        formatted_data["labels"] = labels
        formatted_data["language"] = "en" if is_en else "fr"

        # Formatage spécial pour certains champs
        try:
            skills_data = formatted_data.get("skills")
            skills_label = (formatted_data.get("labels") or {}).get(
                "skills"
            ) or "Skills"
            if skills_data is not None and isinstance(skills_data, list):
                formatted_data["skills"] = self.format_skills(
                    skills_data, default_category=skills_label
                )
            elif skills_data is None:
                formatted_data["skills"] = []
        except Exception as e:
            logger.warning(f"Erreur formatage skills: {e}")
            formatted_data["skills"] = []

        try:
            experience_data = formatted_data.get("experience")
            if experience_data is not None and isinstance(experience_data, list):
                experience_data = self._sort_entries_by_recency(experience_data)
                normalized_experience = self.format_experience(
                    experience_data,
                    language_code=formatted_data["language"],
                )
                job_title_hint = (
                    formatted_data.get("job_title")
                    or formatted_data.get("target_job_title")
                    or ""
                )
                offer_terms = self._collect_offer_terms_for_render(formatted_data)
                primary_experience, additional_relevant_items = (
                    self._split_experience_for_render(
                        normalized_experience,
                        job_title=job_title_hint,
                        offer_terms=offer_terms,
                        primary_count=None,
                    )
                )
                formatted_data["experience_all"] = normalized_experience
                formatted_data["experience"] = primary_experience
                formatted_data["experience_primary"] = primary_experience
                formatted_data["additional_relevant_items"] = additional_relevant_items
                formatted_data["experience_top_n"] = len(primary_experience)
                formatted_data["additional_relevant_summary"] = (
                    self._build_additional_relevant_summary(
                        additional_relevant_items,
                        formatted_data,
                    )
                )
            elif experience_data is None:
                formatted_data["experience"] = []
                formatted_data["experience_all"] = []
                formatted_data["experience_primary"] = []
                formatted_data["additional_relevant_items"] = []
                formatted_data["experience_top_n"] = 0
                formatted_data["additional_relevant_summary"] = ""
        except Exception as e:
            logger.warning(f"Erreur formatage experience: {e}")
            formatted_data["experience"] = []
            formatted_data["experience_all"] = []
            formatted_data["experience_primary"] = []
            formatted_data["additional_relevant_items"] = []
            formatted_data["experience_top_n"] = 0
            formatted_data["additional_relevant_summary"] = ""

        contact_methods = formatted_data.get("contact_methods")
        if not isinstance(contact_methods, list) or not contact_methods:
            formatted_data["contact_methods"] = (
                self._build_contact_methods_from_formatted_data(formatted_data)
            )

        if formatted_data.get("experience"):
            formatted_data["featured_soft_skills"] = []
        else:
            formatted_data["featured_soft_skills"] = self._select_featured_soft_skills(
                self._collect_soft_skill_candidates(
                    formatted_data.get("soft_skills"),
                    formatted_data.get("skills"),
                ),
                max_items=3,
            )
        formatted_data["featured_project"] = self._build_featured_project(
            formatted_data.get("projects"),
        )
        formatted_data["featured_certifications"] = self._build_featured_certifications(
            formatted_data.get("certifications"),
            max_items=2,
        )
        formatted_data["languages"] = self._compact_language_entries(
            formatted_data.get("languages"),
            max_items=2,
        )

        space_pressure = sum(
            1
            for item in (
                formatted_data.get("featured_project"),
                formatted_data.get("featured_certifications"),
                formatted_data.get("education"),
                formatted_data.get("languages"),
            )
            if item
        )
        max_skill_items = 10
        max_roles = 4 if space_pressure <= 1 else 3
        offer_terms = self._collect_offer_terms_for_render(formatted_data)
        job_title_hint = (
            formatted_data.get("job_title")
            or formatted_data.get("target_job_title")
            or ""
        )
        formatted_data["experience"] = self._compact_experience_entries(
            formatted_data.get("experience_primary")
            or formatted_data.get("experience"),
            job_title=str(job_title_hint).strip(),
            offer_terms=offer_terms,
            language_code=str(formatted_data.get("language") or "fr"),
            max_roles=max_roles,
            max_bullets=3,
        )
        formatted_data["experience_top_n"] = len(formatted_data["experience"])
        selected_featured_skills = self._select_featured_skills(
            formatted_data.get("skills"),
            max_items=max_skill_items,
            offer_terms=offer_terms,
            job_title=str(job_title_hint).strip(),
            experience_entries=formatted_data.get("experience"),
            experience_all=formatted_data.get("experience_all"),
            projects=formatted_data.get("projects"),
            language_code=str(formatted_data.get("language") or "fr"),
        )
        formatted_data["featured_skills"] = self._group_featured_skills_for_display(
            selected_featured_skills,
            formatted_data,
            offer_terms=offer_terms,
            job_title=str(job_title_hint).strip(),
            language_code=language_code,
            max_items=max_skill_items,
        )
        formatted_data["profile_summary_lines"] = self._build_render_summary_lines(
            formatted_data
        )

        try:
            education_data = formatted_data.get("education")
            if education_data is not None and isinstance(education_data, list):
                formatted_data["education"] = self._sort_entries_by_recency(
                    education_data
                )
            elif education_data is None:
                formatted_data["education"] = []
        except Exception as e:
            logger.warning(f"Erreur tri education: {e}")
            formatted_data["education"] = formatted_data.get("education") or []

        formatted_data["education"] = self._compact_education_entries(
            formatted_data.get("education"),
            max_items=2,
        )

        return formatted_data

    def _inject_fallback_warning(self, html_content: str) -> str:
        """Injecte un message d'avertissement fallback dans le HTML."""
        # CSS pour le message d'avertissement
        warning_css = """
        <style>
        .fallback-warning {
            position: fixed;
            top: 10px;
            right: 10px;
            background: linear-gradient(135deg, #ff6b6b, #ffa726);
            color: white;
            padding: 12px 16px;
            border-radius: 8px;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            font-size: 13px;
            font-weight: 600;
            box-shadow: 0 4px 20px rgba(255, 107, 107, 0.4);
            z-index: 9999;
            max-width: 280px;
            border: 2px solid rgba(255, 255, 255, 0.2);
            backdrop-filter: blur(10px);
        }
        .fallback-warning::before {
            content: "!";
            margin-right: 8px;
            font-size: 16px;
        }
        .fallback-warning-details {
            font-size: 11px;
            margin-top: 6px;
            opacity: 0.9;
            line-height: 1.3;
        }
        @media print {
            .fallback-warning { display: none; }
        }
        </style>
        """

        # HTML du message d'avertissement
        warning_html = """
        <div class="fallback-warning">
            <div>CV généré en mode FALLBACK</div>
            <div class="fallback-warning-details">
                IA indisponible - Données réelles utilisées<br>
                Vérifiez la configuration GPU/CUDA
            </div>
        </div>
        """

        # Injecter le CSS dans le <head>
        if "<head>" in html_content:
            html_content = html_content.replace("<head>", f"<head>{warning_css}")
        else:
            # Si pas de <head>, ajouter au début
            html_content = f"{warning_css}\n{html_content}"

        # Injecter le message juste après <body>
        if "<body>" in html_content:
            html_content = html_content.replace("<body>", f"<body>{warning_html}")
        else:
            # Si pas de <body>, ajouter au début du contenu
            html_content = f"{warning_html}\n{html_content}"

        return html_content

    def format_skills(self, skills: list, default_category: str = "Skills") -> list:
        """Formate les competences pour les templates."""
        if not skills or not isinstance(skills, list):
            return []

        try:
            try:
                from ..utils.cv_skill_recovery import _clean_skill_candidate
            except Exception:

                def _clean_skill_candidate(value, profile_json=None):
                    return str(value or "").strip()

            try:
                from ..utils.cv_postprocessing import clean_skill_item_residues
            except Exception:
                clean_skill_item_residues = None

            def _normalize_text_key(value: Any) -> str:
                text = str(value or "").strip().casefold()
                text = unicodedata.normalize("NFKD", text)
                text = "".join(ch for ch in text if not unicodedata.combining(ch))
                text = re.sub(r"[^\w]+", " ", text, flags=re.UNICODE)
                return re.sub(r"\s+", " ", text).strip()

            _LOW_VALUE_SOFT_SKILL_KEYS = {
                "adaptabilite",
                "adaptability",
                "autonomie",
                "autonomy",
                "communication",
                "curieux",
                "curieuse",
                "curiosity",
                "efficacite",
                "efficiency",
                "esprit d equipe",
                "motivation",
                "motive",
                "motived",
                "pedagogue",
                "rigoureux",
                "rigoureuse",
                "rigueur",
                "savoir vendre ses idees",
                "team player",
                "teamwork",
                "travailler en equipe",
            }

            def _normalize_category_label(label: Any) -> str:
                text = str(label or "").strip()
                lowered = text.casefold()
                replacements = {
                    "competences": "Compétences",
                    "competences techniques": "Compétences techniques",
                    "qualites": "Qualités",
                    "soft skills": "Soft Skills",
                }
                return replacements.get(
                    lowered, text or str(default_category or "Skills")
                )

            def _is_soft_category_label(label: Any) -> bool:
                lowered = _normalize_text_key(label)
                return lowered in {
                    "qualites",
                    "qualites personnelles",
                    "soft skills",
                    "soft skill",
                }

            def _is_low_value_soft_skill(name: Any, *, category_label: Any) -> bool:
                if not _is_soft_category_label(category_label):
                    return False
                normalized = _normalize_text_key(name)
                if not normalized:
                    return True
                return False

            # Si c'est une liste simple, la convertir en structure categorisee
            if skills and len(skills) > 0 and isinstance(skills[0], str):
                cleaned_simple_skills = []
                seen_simple = set()
                for skill in skills:
                    if not isinstance(skill, str) or not skill.strip():
                        continue
                    cleaned = _clean_skill_candidate(skill, None)
                    key = _normalize_text_key(cleaned)
                    if cleaned and key and key not in seen_simple:
                        seen_simple.add(key)
                        cleaned_simple_skills.append(cleaned)
                return (
                    [
                        {
                            "category": _normalize_category_label(default_category),
                            "skills_list": [
                                {"name": skill, "level": None}
                                for skill in cleaned_simple_skills
                            ],
                        }
                    ]
                    if cleaned_simple_skills
                    else []
                )

            normalized = []
            seen_global_items = set()
            for block in skills:
                if isinstance(block, dict):
                    category_label = _normalize_category_label(
                        block.get("category") or default_category
                    )
                    if isinstance(block.get("skills_list"), list):
                        filtered_skills_list = []
                        for item in block.get("skills_list") or []:
                            if isinstance(item, dict):
                                name = item.get("name") or item.get("skill") or ""
                                level = item.get("level")
                            else:
                                name = str(item)
                                level = None
                            cleaned_name = _clean_skill_candidate(name, None)
                            item_key = _normalize_text_key(cleaned_name)
                            if (
                                cleaned_name
                                and item_key
                                and item_key not in seen_global_items
                                and not _is_low_value_soft_skill(
                                    cleaned_name, category_label=category_label
                                )
                            ):
                                seen_global_items.add(item_key)
                                filtered_skills_list.append(
                                    {"name": cleaned_name, "level": level}
                                )
                        if filtered_skills_list:
                            normalized.append(
                                {
                                    "category": category_label,
                                    "skills_list": filtered_skills_list,
                                }
                            )
                        continue

                    items = block.get("items") or block.get("skills") or []
                    skills_list = []
                    for item in items:
                        if isinstance(item, dict):
                            name = item.get("name") or item.get("skill") or ""
                            level = item.get("level")
                        else:
                            name = str(item)
                            level = None
                        name = _clean_skill_candidate(name, None)
                        item_key = _normalize_text_key(name)
                        if (
                            name
                            and item_key
                            and item_key not in seen_global_items
                            and not _is_low_value_soft_skill(
                                name, category_label=category_label
                            )
                        ):
                            seen_global_items.add(item_key)
                            skills_list.append({"name": name, "level": level})

                    if skills_list:
                        normalized.append(
                            {
                                "category": category_label,
                                "skills_list": skills_list,
                            }
                        )
                elif isinstance(block, str):
                    name = _clean_skill_candidate(block, None)
                    item_key = _normalize_text_key(name)
                    if not name or not item_key or item_key in seen_global_items:
                        continue
                    seen_global_items.add(item_key)
                    if not normalized:
                        normalized.append(
                            {
                                "category": _normalize_category_label(default_category),
                                "skills_list": [],
                            }
                        )
                    normalized[0]["skills_list"].append({"name": name, "level": None})

            merged: list = []
            category_index: dict = {}
            for block in normalized:
                category = _normalize_category_label(
                    block.get("category") or default_category
                )
                block_items = [
                    item
                    for item in (block.get("skills_list") or [])
                    if isinstance(item, dict) and str(item.get("name") or "").strip()
                ]
                if not block_items:
                    continue
                category_key = _normalize_text_key(category) or category.casefold()
                if category_key not in category_index:
                    category_index[category_key] = len(merged)
                    merged.append({"category": category, "skills_list": block_items})
                    continue
                idx = category_index[category_key]
                existing_keys = {
                    _normalize_text_key(item.get("name"))
                    for item in merged[idx].get("skills_list") or []
                    if isinstance(item, dict)
                }
                for item in block_items:
                    item_key = _normalize_text_key(item.get("name"))
                    if item_key and item_key not in existing_keys:
                        merged[idx]["skills_list"].append(item)
                        existing_keys.add(item_key)

            if callable(clean_skill_item_residues):
                all_skill_names = [
                    str(item.get("name") or "").strip()
                    for block in merged
                    if isinstance(block, dict)
                    for item in (block.get("skills_list") or [])
                    if isinstance(item, dict) and str(item.get("name") or "").strip()
                ]
                for block in merged:
                    if not isinstance(block, dict):
                        continue
                    by_name = {
                        _normalize_text_key(item.get("name")): item
                        for item in (block.get("skills_list") or [])
                        if isinstance(item, dict)
                    }
                    cleaned_names = clean_skill_item_residues(
                        [
                            item.get("name")
                            for item in (block.get("skills_list") or [])
                            if isinstance(item, dict)
                        ],
                        other_items=all_skill_names,
                        category_label=block.get("category") or "",
                    )
                    rebuilt_items = []
                    seen_rebuilt = set()
                    for name in cleaned_names:
                        name_key = _normalize_text_key(name)
                        if not name_key or name_key in seen_rebuilt:
                            continue
                        original = by_name.get(name_key, {"level": None})
                        rebuilt_items.append(
                            {
                                "name": name,
                                "level": original.get("level"),
                            }
                        )
                        seen_rebuilt.add(name_key)
                    block["skills_list"] = rebuilt_items
                merged = [
                    block
                    for block in merged
                    if isinstance(block, dict) and block.get("skills_list")
                ]

            if len(merged) > 1:
                merged = [
                    block
                    for block in merged
                    if not (
                        _is_soft_category_label(block.get("category"))
                        and len(block.get("skills_list") or []) < 2
                    )
                ] or merged

            return merged or skills
        except Exception as e:
            logger.error(f"Erreur format_skills: {e}")
            return []

    def format_experience(self, experience: list, language_code: str = "fr") -> list:
        """Formate l'experience pour les templates."""
        if not experience or not isinstance(experience, list):
            return []

        try:
            try:
                from ..utils.cv_postprocessing import _polish_experience_fragment
            except Exception:

                def _polish_experience_fragment(
                    text, *, company="", language_code="fr", prefer_articleless=False
                ):
                    return str(text or "").strip()

            def word_count(text: Any) -> int:
                return len(re.findall(r"\b\S+\b", str(text or "").strip()))

            def normalize_location(text: Any) -> str:
                value = str(text or "").strip()
                if not value:
                    return ""
                return re.sub(r"\s+-\s+", ", ", value)

            def is_generic_summary(text: Any) -> bool:
                normalized = re.sub(r"\s+", " ", str(text or "").strip().lower())
                return normalized in {
                    "delivered key contributions in this role.",
                    "contributions principales realisees sur ce poste.",
                } or normalized.startswith("delivered key contributions as ")

            def looks_like_inline_pseudo_bullets(text: Any) -> bool:
                return bool(
                    re.search(
                        r"(?:[:;]\s*[-•])|(?:\s-\s+\w.{15,}\s*;\s*-\s+\w)",
                        str(text or ""),
                        re.IGNORECASE,
                    )
                )

            def split_inline_pseudo_bullets(text: Any) -> List[str]:
                raw = str(text or "").strip()
                if not raw or not looks_like_inline_pseudo_bullets(raw):
                    return []
                normalized = (
                    raw.replace("•", "-")
                    .replace("▪", "-")
                    .replace("➜", "-")
                    .replace("✓", "-")
                    .replace("–", "-")
                    .replace("—", "-")
                )
                if ":" in normalized:
                    prefix, remainder = normalized.split(":", 1)
                    if re.search(r"\s*-\s*\w", remainder):
                        normalized = remainder
                normalized = re.sub(r"\s*;\s*", "\n", normalized)
                normalized = re.sub(r"(?:(?<=:)|^|\n)\s*-\s+", "\n", normalized)
                output: List[str] = []
                for part in normalized.splitlines():
                    cleaned = re.sub(r"^[\s:;\-]+", "", part).strip(" ;:-")
                    if cleaned and re.search(r"\w", cleaned, re.UNICODE):
                        output.append(cleaned)
                return output[:12]

            def polish_line(
                text: Any,
                *,
                company: str,
                prefer_articleless: bool = False,
            ) -> str:
                return str(
                    _polish_experience_fragment(
                        text,
                        company=company,
                        language_code=language_code,
                        prefer_articleless=prefer_articleless,
                    )
                    or ""
                ).strip()

            def strip_role_context_prefix(text: Any) -> str:
                value = str(text or "").strip()
                if not value:
                    return ""

                action_heads = {
                    "ajoute",
                    "analyse",
                    "analyser",
                    "automatise",
                    "concevoir",
                    "contribue",
                    "controle",
                    "cree",
                    "execute",
                    "explore",
                    "identifie",
                    "mene",
                    "prepare",
                    "presente",
                    "qualifie",
                    "realise",
                    "redige",
                    "refondu",
                    "relance",
                    "repris",
                    "structure",
                    "teste",
                }
                role_markers = {
                    "alternance",
                    "apprenti",
                    "business",
                    "developer",
                    "ingenieur",
                    "manager",
                    "qa",
                    "sales",
                    "stagiaire",
                    "support",
                }
                tokens = re.findall(r"\S+", value, flags=re.UNICODE)
                if len(tokens) < 4:
                    return value
                for idx in range(2, min(len(tokens), 10)):
                    head = self._normalize_text_key(tokens[idx]).split(" ", 1)[0]
                    if head not in action_heads:
                        continue
                    prefix = " ".join(tokens[:idx])
                    prefix_tokens = set(self._normalize_text_key(prefix).split())
                    if not (prefix_tokens & role_markers):
                        continue
                    tail = " ".join(tokens[idx:]).strip(" ,;:-")
                    if tail:
                        return tail[:1].upper() + tail[1:]
                return value

            def collect_description_lines(text: Any, *, company: str) -> List[str]:
                raw = str(text or "").strip()
                if not raw:
                    return []
                parsed = split_inline_pseudo_bullets(raw)
                candidates = (
                    parsed if parsed else re.split(r"[\r\n]+|(?<=[\.\!\?])\s+", raw)
                )
                cleaned_lines: List[str] = []
                for candidate in candidates:
                    cleaned = polish_line(
                        candidate,
                        company=company,
                        prefer_articleless=True,
                    )
                    if not cleaned:
                        continue
                    cleaned = strip_role_context_prefix(cleaned)
                    cleaned_lines.append(cleaned)
                    if len(cleaned_lines) >= 12:
                        break
                return cleaned_lines

            normalized: List[Dict[str, Any]] = []
            for exp in experience:
                if not isinstance(exp, dict):
                    continue

                entry = dict(exp)
                entry["location"] = normalize_location(entry.get("location") or "")
                entry["company"] = self._normalize_render_text(entry.get("company"))
                company_name = str(entry.get("company") or "").strip()
                description_lines: List[str] = []
                compact_lines: List[str] = []
                description_raw = entry.get("description")
                if isinstance(description_raw, str) and description_raw.strip():
                    description_lines.extend(
                        collect_description_lines(
                            description_raw,
                            company=company_name,
                        )
                    )
                elif isinstance(description_raw, list):
                    for value in description_raw:
                        if isinstance(value, str) and value.strip():
                            description_lines.extend(
                                collect_description_lines(
                                    value,
                                    company=company_name,
                                )
                            )

                summary = entry.get("summary")
                highlights = entry.get("highlights")
                cleaned_highlights: List[str] = []
                if isinstance(highlights, list):
                    for value in highlights:
                        if isinstance(value, str) and value.strip():
                            cleaned = polish_line(
                                value,
                                company=company_name,
                                prefer_articleless=True,
                            )
                            cleaned = strip_role_context_prefix(cleaned)
                            if cleaned:
                                cleaned_highlights.append(cleaned)

                has_highlights = bool(cleaned_highlights)
                if isinstance(summary, str) and summary.strip():
                    summary_text = summary.strip()
                    parsed_summary = split_inline_pseudo_bullets(summary_text)
                    if is_generic_summary(summary_text):
                        parsed_summary = []
                    if parsed_summary and not has_highlights:
                        compact_lines.extend(
                            collect_description_lines(
                                summary_text,
                                company=company_name,
                            )
                        )
                    elif (
                        not is_generic_summary(summary_text)
                        and not looks_like_inline_pseudo_bullets(summary_text)
                        and word_count(summary_text) <= 32
                    ):
                        cleaned_summary = polish_line(
                            summary_text,
                            company=company_name,
                        )
                        if cleaned_summary:
                            cleaned_summary = strip_role_context_prefix(cleaned_summary)
                            compact_lines.append(cleaned_summary)
                    elif not has_highlights:
                        cleaned_summary = polish_line(
                            summary_text,
                            company=company_name,
                        )
                        if cleaned_summary:
                            cleaned_summary = strip_role_context_prefix(cleaned_summary)
                            description_lines.insert(0, cleaned_summary)

                if has_highlights:
                    compact_lines.extend(cleaned_highlights[:12])
                else:
                    compact_lines.extend(description_lines[:12])

                entry["description"] = self._dedupe_render_lines_fuzzy(compact_lines)[
                    :12
                ]
                normalized.append(entry)

            return normalized
        except Exception as e:
            logger.error(f"Erreur format_experience: {e}")
            return []

    def _collect_offer_terms_for_render(
        self, formatted_data: Dict[str, Any]
    ) -> List[str]:
        terms: List[str] = []
        if not isinstance(formatted_data, dict):
            return terms

        for key in ("ats_keywords", "keywords", "skills", "tools", "responsibilities"):
            value = formatted_data.get(key)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, str) and item.strip():
                        terms.append(item.strip())
            elif isinstance(value, str):
                terms.extend(part.strip() for part in value.split(",") if part.strip())

        return terms

    def _experience_recency_rank(self, exp: Dict[str, Any]) -> int:
        if not isinstance(exp, dict):
            return 0

        def parse_date_rank(raw: Any) -> int:
            raw_text = str(raw or "").strip()
            text = raw_text.lower()
            if not raw_text:
                return 0
            if any(
                token in text
                for token in ("present", "current", "actuel", "en cours", "aujourd")
            ):
                return 999912

            def rank_from_yyyy_mm(value: Any) -> int:
                probe = str(value or "").strip()
                match = re.match(r"^(?P<y>\d{4})-(?P<m>0[1-9]|1[0-2])$", probe)
                if not match:
                    return 0
                return int(match.group("y")) * 100 + int(match.group("m"))

            month_map = {
                "jan": 1,
                "janv": 1,
                "january": 1,
                "janvier": 1,
                "feb": 2,
                "fev": 2,
                "fevr": 2,
                "february": 2,
                "fevrier": 2,
                "mar": 3,
                "march": 3,
                "mars": 3,
                "apr": 4,
                "avr": 4,
                "april": 4,
                "avril": 4,
                "may": 5,
                "mai": 5,
                "jun": 6,
                "june": 6,
                "juin": 6,
                "jul": 7,
                "july": 7,
                "juil": 7,
                "juillet": 7,
                "aug": 8,
                "aou": 8,
                "aout": 8,
                "august": 8,
                "sep": 9,
                "sept": 9,
                "september": 9,
                "septembre": 9,
                "oct": 10,
                "october": 10,
                "octobre": 10,
                "nov": 11,
                "november": 11,
                "novembre": 11,
                "dec": 12,
                "december": 12,
                "decembre": 12,
            }

            alpha = re.sub(r"[^a-z]+", " ", text)
            month = 0
            for token in alpha.split():
                if token in month_map:
                    month = month_map[token]
                    break

            # Single source of truth for numeric date formats.
            try:
                from ..rules.date_normalize import (
                    normalize_date_span,
                    _normalize_single_date,
                )

                ambiguous_day_first = re.search(
                    r"\b(?P<d>0?[1-9]|1[0-2])\s*[/\-]\s*(?P<m>0?[1-9]|1[0-2])\s*[/\-]\s*(?P<y>19\d{2}|20\d{2})\b",
                    raw_text,
                )
                if ambiguous_day_first:
                    logger.warning(
                        "RECENCY_AMBIGUOUS_DAY_FIRST: '{}' interpreted as DD/MM/YYYY (FR).",
                        raw_text,
                    )

                start_norm, end_norm, is_current = normalize_date_span(raw_text)
                if is_current:
                    return 999912

                for candidate in (end_norm, start_norm):
                    rank = rank_from_yyyy_mm(candidate)
                    if rank:
                        return rank

                iso_yyyy_mm_dd = re.search(
                    r"\b(?P<y>19\d{2}|20\d{2})\s*[/\-]\s*(?P<m>0?[1-9]|1[0-2])\s*[/\-]\s*(?P<d>0?[1-9]|[12]\d|3[01])\b",
                    raw_text,
                )
                if iso_yyyy_mm_dd:
                    return int(iso_yyyy_mm_dd.group("y")) * 100 + int(
                        iso_yyyy_mm_dd.group("m")
                    )

                iso_yyyy_mm = re.search(
                    r"\b(?P<y>19\d{2}|20\d{2})\s*[/\-]\s*(?P<m>0?[1-9]|1[0-2])\b",
                    raw_text,
                )
                if iso_yyyy_mm:
                    return int(iso_yyyy_mm.group("y")) * 100 + int(
                        iso_yyyy_mm.group("m")
                    )

                single_norm = _normalize_single_date(raw_text)
                rank = rank_from_yyyy_mm(single_norm)
                if rank:
                    return rank
            except Exception as exc:
                logger.debug(f"Recency date_normalize fallback used: {exc}")

            year_match = re.search(r"(19\d{2}|20\d{2})", text)
            if year_match:
                year = int(year_match.group(1))
                return year * 100 + (month or 12)

            return 0

        end_rank = parse_date_rank(exp.get("end_date"))
        if end_rank:
            return end_rank
        return parse_date_rank(exp.get("start_date"))

    def _experience_information_units(self, exp: Dict[str, Any]) -> int:
        if not isinstance(exp, dict):
            return 1

        units = 1
        summary = exp.get("summary")
        if isinstance(summary, str) and summary.strip():
            units += 1

        description = exp.get("description")
        if isinstance(description, list):
            description_items = [
                item.strip()
                for item in description
                if isinstance(item, str) and item.strip()
            ]
            units += min(4, len(description_items))
            if any(len(item) >= 120 for item in description_items):
                units += 1
        elif isinstance(description, str) and description.strip():
            units += 1

        technologies = exp.get("technologies")
        if isinstance(technologies, list) and any(
            isinstance(item, str) and item.strip() for item in technologies
        ):
            units += 1

        return max(1, min(units, 8))

    def _rank_experiences_for_render(
        self,
        experiences: List[Dict[str, Any]],
        *,
        job_title: str,
        offer_terms: List[str],
    ) -> Tuple[List[Dict[str, Any]], List[Tuple[float, int, int, int, Dict[str, Any]]]]:
        if not experiences:
            return [], []

        try:
            from ..utils.keyword_alignment import (
                normalize_keyword_for_match,
                normalized_term_in_probe as normalized_term_present,
            )
        except Exception:
            scored_fallback: List[Tuple[float, int, int, int, Dict[str, Any]]] = []
            for idx, exp in enumerate(experiences):
                if not isinstance(exp, dict):
                    continue
                recency_rank = self._experience_recency_rank(exp)
                info_units = self._experience_information_units(exp)
                scored_fallback.append((0.0, recency_rank, -idx, info_units, exp))
            scored_fallback.sort(key=lambda row: (row[1], row[2]), reverse=True)
            return [row[4] for row in scored_fallback], scored_fallback

        job_norm = normalize_keyword_for_match(job_title)
        normalized_terms: List[str] = []
        seen = set()
        for term in offer_terms or []:
            norm = normalize_keyword_for_match(term)
            if not norm or norm in seen:
                continue
            seen.add(norm)
            normalized_terms.append(norm)

        scored: List[Tuple[float, int, int, int, Dict[str, Any]]] = []
        max_relevance = 0.0
        try:
            from ..domain.generation.tool_signals import collect_named_tool_hints
        except Exception:
            collect_named_tool_hints = None
        for idx, exp in enumerate(experiences):
            if not isinstance(exp, dict):
                continue
            parts: List[str] = []
            for key in ("title", "company", "summary", "location"):
                value = exp.get(key)
                if isinstance(value, str) and value.strip():
                    parts.append(value.strip())
            for line in exp.get("description") or []:
                if isinstance(line, str) and line.strip():
                    parts.append(line.strip())
            for tech in exp.get("technologies") or []:
                if isinstance(tech, str) and tech.strip():
                    parts.append(tech.strip())
            blob_norm = normalize_keyword_for_match(" ".join(parts))
            title_norm = normalize_keyword_for_match(exp.get("title") or "")

            relevance = 0.0
            if job_norm and normalized_term_present(blob_norm, job_norm):
                relevance += 4.0
                if title_norm and normalized_term_present(title_norm, job_norm):
                    relevance += 1.8
            for term in normalized_terms:
                if normalized_term_present(blob_norm, term):
                    relevance += 2.2 if " " in term else 1.1

            impact_hits = sum(
                1
                for token in (
                    "resultat",
                    "impact",
                    "gain",
                    "amelior",
                    "improve",
                    "reduce",
                    "acceler",
                    "fiabil",
                    "automatis",
                    "benchmark",
                    "qualif",
                    "validation",
                    "release",
                    "gate",
                )
                if token in blob_norm
            )
            if impact_hits:
                relevance += min(2.2, impact_hits * 0.45)
            if re.search(
                r"\b\d+(?:[.,]\d+)?\s*(?:%|k|m|ans?|mois|jours?|hours?|users?|clients?|applications?)?\b",
                " ".join(parts),
                re.IGNORECASE,
            ):
                relevance += 0.9

            action_hits = sum(
                1
                for token in (
                    "concevoir",
                    "executer",
                    "suivre",
                    "rediger",
                    "analyser",
                    "piloter",
                    "tester",
                    "valider",
                    "implement",
                    "develop",
                    "design",
                    "lead",
                    "build",
                    "improve",
                    "deliver",
                )
                if token in blob_norm
            )
            if action_hits:
                relevance += min(1.8, action_hits * 0.35)

            if collect_named_tool_hints:
                named_tools = collect_named_tool_hints(
                    {
                        "experience": [exp],
                    },
                    max_items=8,
                )
                if named_tools:
                    relevance += min(1.5, len(named_tools) * 0.35)

            max_relevance = max(max_relevance, relevance)
            recency_rank = self._experience_recency_rank(exp)
            info_units = self._experience_information_units(exp)
            scored.append((relevance, recency_rank, -idx, info_units, exp))

        if not scored:
            return experiences, []

        if max_relevance <= 0.0:
            scored.sort(key=lambda row: (row[1], row[2]), reverse=True)
        else:
            scored.sort(key=lambda row: (row[0], row[1], row[2]), reverse=True)
        return [row[4] for row in scored], scored

    def _resolve_primary_experience_count(
        self,
        scored_rows: List[Tuple[float, int, int, int, Dict[str, Any]]],
    ) -> int:
        total = len(scored_rows)
        if total == 0:
            return 0
        if total <= 3:
            return total
        if total <= self.MIN_PRIMARY_EXPERIENCE_COUNT:
            return total

        min_count = min(self.MIN_PRIMARY_EXPERIENCE_COUNT, total)
        max_count = min(self.MAX_PRIMARY_EXPERIENCE_COUNT, total)

        budget_count = 0
        budget_used = 0
        for _relevance, _recency, _position, info_units, _exp in scored_rows:
            if budget_count >= max_count:
                break
            units = max(1, int(info_units or 1))
            if budget_count < min_count:
                budget_count += 1
                budget_used += units
                continue
            if budget_used + units > self.PRIMARY_EXPERIENCE_INFO_BUDGET:
                break
            budget_count += 1
            budget_used += units

        if budget_count < min_count:
            budget_count = min_count

        relevant_hits = sum(
            1
            for relevance, _recency, _position, _info_units, _exp in scored_rows
            if relevance >= self.PRIMARY_EXPERIENCE_RELEVANCE_THRESHOLD
        )

        if relevant_hits == 0:
            target_count = min(max_count, self.DEFAULT_PRIMARY_EXPERIENCE_COUNT)
        else:
            target_count = max(min_count, min(max_count, relevant_hits))

        return max(min_count, min(budget_count, target_count))

    def _split_experience_for_render(
        self,
        experiences: List[Dict[str, Any]],
        *,
        job_title: str,
        offer_terms: List[str],
        primary_count: Optional[int] = None,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        ranked, scored_rows = self._rank_experiences_for_render(
            experiences,
            job_title=job_title,
            offer_terms=offer_terms,
        )

        if primary_count is None:
            count = self._resolve_primary_experience_count(scored_rows)
        else:
            count = max(1, int(primary_count))

        selected_keys = {
            self._experience_identity_key(exp)
            for exp in ranked[:count]
            if isinstance(exp, dict)
        }
        primary_items: List[Dict[str, Any]] = []
        additional_relevant_items: List[Dict[str, Any]] = []
        for exp in experiences:
            if not isinstance(exp, dict):
                continue
            if self._experience_identity_key(exp) in selected_keys:
                primary_items.append(exp)
            else:
                additional_relevant_items.append(exp)
        return primary_items, additional_relevant_items

    def _build_additional_relevant_summary(
        self,
        additional_items: List[Dict[str, Any]],
        formatted_data: Dict[str, Any],
    ) -> str:
        if not isinstance(additional_items, list) or not additional_items:
            return ""

        is_en = (
            str((formatted_data or {}).get("language") or "").lower().startswith("en")
        )
        target_language = "en" if is_en else "fr"

        try:
            from ..utils.language_policy import text_matches_target_language
        except Exception:

            def text_matches_target_language(value, _target_language):
                return True

        try:
            from ..utils.cv_postprocessing import _polish_experience_fragment
        except Exception:

            def _polish_experience_fragment(
                text, *, company="", language_code="fr", prefer_articleless=False
            ):
                return str(text or "").strip()

        import unicodedata as _unicodedata

        def _normalize_tokens(text: Any) -> frozenset:
            raw = str(text or "").strip().lower()
            if not raw:
                return frozenset()
            stripped = "".join(
                ch
                for ch in _unicodedata.normalize("NFD", raw)
                if _unicodedata.category(ch) != "Mn"
            )
            return frozenset(re.findall(r"\w{3,}", stripped, flags=re.UNICODE))

        primary_items = list((formatted_data or {}).get("experience_primary") or [])
        primary_signatures: List[frozenset] = []
        for primary in primary_items:
            if not isinstance(primary, dict):
                continue
            tokens: set = set()
            summary_text = primary.get("summary")
            if isinstance(summary_text, str):
                tokens |= _normalize_tokens(summary_text)
            highlights = primary.get("highlights")
            if isinstance(highlights, list):
                for bullet in highlights:
                    if isinstance(bullet, str):
                        tokens |= _normalize_tokens(bullet)
            if tokens:
                primary_signatures.append(frozenset(tokens))

        def _overlaps_primary(candidate: str) -> bool:
            tokens = _normalize_tokens(candidate)
            if len(tokens) < 3:
                return False
            for signature in primary_signatures:
                if not signature:
                    continue
                intersection = len(tokens & signature)
                if intersection >= max(3, int(len(tokens) * 0.7)):
                    return True
            return False

        def _date_text(exp: Dict[str, Any]) -> str:
            start = str(exp.get("start_date") or "").strip()
            end = str(exp.get("end_date") or "").strip()
            duration = str(exp.get("duration") or "").strip()
            if start and end:
                date_text = f"{start}-{end}"
            else:
                date_text = start or end
            if date_text and duration:
                return f"{date_text} ({duration})"
            return date_text or duration

        def _exp_snippet(exp: Dict[str, Any]) -> str:
            title = str(exp.get("title") or "").strip()
            company = str(exp.get("company") or "").strip()
            date_part = _date_text(exp)

            details_text: List[str] = []
            detail_candidates: List[str] = []
            description = exp.get("description")
            if isinstance(description, list):
                detail_candidates.extend(
                    item
                    for item in description
                    if isinstance(item, str) and item.strip()
                )
            elif isinstance(description, str) and description.strip():
                detail_candidates.append(description)
            summary = exp.get("summary")
            if isinstance(summary, str) and summary.strip():
                detail_candidates.append(summary)
            highlights = exp.get("highlights")
            if isinstance(highlights, list):
                detail_candidates.extend(
                    item
                    for item in highlights
                    if isinstance(item, str) and item.strip()
                )
            technologies = exp.get("technologies")
            if isinstance(technologies, list):
                tech_values = [
                    str(item).strip()
                    for item in technologies
                    if isinstance(item, str) and item.strip()
                ]
                if tech_values:
                    detail_candidates.append(", ".join(tech_values[:4]))

            for candidate in detail_candidates:
                if not text_matches_target_language(candidate, target_language):
                    continue
                cleaned = str(
                    _polish_experience_fragment(
                        candidate,
                        company=company,
                        language_code=target_language,
                        prefer_articleless=True,
                    )
                    or ""
                ).strip()
                if len(re.findall(r"\b\S+\b", cleaned, flags=re.UNICODE)) < 3:
                    continue
                clean_detail = cleaned.rstrip(".")
                if _overlaps_primary(clean_detail):
                    continue
                if clean_detail not in details_text:
                    details_text.append(clean_detail)
                if len(details_text) >= 3:
                    break

            head = title or company or ("Role" if is_en else "Role")
            details: List[str] = []
            if company and company != head:
                details.append(company)
            if date_part:
                details.append(date_part)
            if details:
                head = f"{head} ({', '.join(details)})"
            if details_text:
                return f"{head} - {'; '.join(details_text)}"
            return head

        preview = [
            _exp_snippet(exp) for exp in additional_items[:4] if isinstance(exp, dict)
        ]
        preview = [item for item in preview if item]
        if not preview:
            return ""

        sentence = "; ".join(preview)
        remaining = len(additional_items) - len(preview)
        if remaining > 0:
            sentence += f"; +{remaining} {'more' if is_en else 'autres'}"

        return sentence

    def _sort_entries_by_recency(
        self,
        entries: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        if not isinstance(entries, list):
            return []
        sortable = [entry for entry in entries if isinstance(entry, dict)]
        return sorted(
            sortable,
            key=lambda entry: self._experience_recency_rank(entry),
            reverse=True,
        )

    def _collect_skill_names_for_compact_summary(self, skills: Any) -> List[str]:
        if not isinstance(skills, list):
            return []
        names: List[str] = []
        seen = set()
        for block in skills:
            items = []
            if isinstance(block, dict):
                items = (
                    block.get("skills_list")
                    or block.get("items")
                    or block.get("skills")
                    or []
                )
            elif isinstance(block, str):
                items = [block]
            if not isinstance(items, list):
                continue
            for item in items:
                if isinstance(item, dict):
                    name = str(item.get("name") or item.get("skill") or "").strip()
                else:
                    name = str(item or "").strip()
                if not name:
                    continue
                key = name.lower()
                if key in seen:
                    continue
                seen.add(key)
                names.append(name)
        return names

    def _collect_hard_skill_names_for_compact_summary(self, skills: Any) -> List[str]:
        if not isinstance(skills, list):
            return []
        names: List[str] = []
        seen = set()
        for block in skills:
            items = []
            if isinstance(block, dict):
                if self._is_soft_skill_category(block.get("category")):
                    continue
                items = (
                    block.get("skills_list")
                    or block.get("items")
                    or block.get("skills")
                    or []
                )
            elif isinstance(block, str):
                items = [block]
            if not isinstance(items, list):
                continue
            for item in items:
                if isinstance(item, dict):
                    name = str(item.get("name") or item.get("skill") or "").strip()
                else:
                    name = str(item or "").strip()
                key = self._normalize_text_key(name)
                if not name or not key or key in seen:
                    continue
                seen.add(key)
                names.append(name)
        return names

    def _experience_identity_key(self, exp: Dict[str, Any]) -> str:
        if not isinstance(exp, dict):
            return ""
        return self._normalize_text_key(
            "::".join(
                [
                    str(exp.get("title") or "").strip(),
                    str(exp.get("company") or "").strip(),
                    str(exp.get("start_date") or "").strip(),
                    str(exp.get("end_date") or "").strip(),
                ]
            )
        )

    def _collect_education_labels_for_compact_summary(
        self, education: Any
    ) -> List[str]:
        if not isinstance(education, list):
            return []
        labels: List[str] = []
        seen = set()
        for entry in education:
            if not isinstance(entry, dict):
                continue
            degree = str(entry.get("degree") or "").strip()
            school = str(entry.get("institution") or "").strip()
            if degree and school:
                text = f"{degree} - {school}"
            else:
                text = degree or school
            if not text:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            labels.append(text)
        return labels

    def _normalize_text_key(self, value: Any) -> str:
        text = str(value or "").strip().casefold()
        if not text:
            return ""
        text = unicodedata.normalize("NFKD", text)
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        text = re.sub(r"[^\w]+", " ", text, flags=re.UNICODE)
        return re.sub(r"\s+", " ", text).strip()

    def _human_join(self, items: List[str], *, is_en: bool) -> str:
        cleaned = [str(item or "").strip() for item in items if str(item or "").strip()]
        if not cleaned:
            return ""
        if len(cleaned) == 1:
            return cleaned[0]
        if len(cleaned) == 2:
            glue = " and " if is_en else " et "
            return glue.join(cleaned)
        glue = "and" if is_en else "et"
        return ", ".join(cleaned[:-1]) + f", {glue} {cleaned[-1]}"

    def _restore_display_acronyms(self, value: Any) -> str:
        text = re.sub(r"\s+", " ", str(value or "").strip()).strip()
        if not text:
            return ""
        replacements = {
            "ai": "AI",
            "api": "API",
            "bi": "BI",
            "ci": "CI",
            "cd": "CD",
            "crm": "CRM",
            "erp": "ERP",
            "it": "IT",
            "llm": "LLM",
            "ml": "ML",
            "qa": "QA",
            "rgpd": "RGPD",
            "sql": "SQL",
            "ui": "UI",
            "ux": "UX",
        }
        pattern = r"\b(" + "|".join(re.escape(item) for item in replacements) + r")\b"
        return re.sub(
            pattern,
            lambda match: replacements.get(
                str(match.group(1) or "").casefold(), str(match.group(1) or "")
            ),
            text,
            flags=re.IGNORECASE,
        )

    def _sentence_case_label(self, value: Any) -> str:
        text = self._restore_display_acronyms(self._normalize_render_text(value))
        if not text:
            return ""

        parts = re.split(r"(\s+)", text)
        seen_word = False
        fixed: List[str] = []
        for part in parts:
            if not part or part.isspace():
                fixed.append(part)
                continue
            match = re.match(
                r"^([^A-Za-zÀ-ÖØ-öø-ÿ0-9]*)(.+?)([^A-Za-zÀ-ÖØ-öø-ÿ0-9]*)$", part
            )
            if not match:
                fixed.append(part)
                continue
            prefix, core, suffix = match.groups()
            if self._is_display_token_protected(core):
                word = core
            elif not seen_word:
                lowered = core.lower()
                word = lowered[:1].upper() + lowered[1:] if lowered else lowered
            else:
                word = core.lower()
            fixed.append(f"{prefix}{word}{suffix}")
            seen_word = True
        return "".join(fixed).strip()

    def _is_display_token_protected(self, value: Any) -> bool:
        token = str(value or "").strip()
        if not token:
            return False
        if self._normalize_text_key(token) in {
            "ai",
            "api",
            "bi",
            "ci",
            "cd",
            "crm",
            "erp",
            "it",
            "llm",
            "ml",
            "qa",
            "rgpd",
            "sql",
            "ui",
            "ux",
        }:
            return True
        if re.search(r"[./+#]", token):
            return True
        letters = [char for char in token if char.isalpha()]
        return bool(letters) and sum(1 for char in letters if char.isupper()) >= 2

    def _split_sentences(self, value: Any) -> List[str]:
        raw = str(value or "").strip()
        if not raw:
            return []
        raw = re.sub(r"\s+", " ", raw).strip()
        return [
            sentence.strip()
            for sentence in re.split(r"(?<=[.!?])\s+", raw)
            if sentence.strip()
        ]

    def _normalize_render_text(self, value: Any) -> str:
        text = re.sub(r"\s+", " ", str(value or "").strip()).strip()
        if not text:
            return ""
        return self._normalize_cv_display_text(text)

    def _normalize_cv_display_text(self, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        replacements = (
            (r"\bLaPoste\b", "La Poste"),
            (r"\bLa Poste Santé et Autonomie\b", "La Poste Santé & Autonomie"),
            (r"\(Careside Filiale\)", "- Careside"),
            (r"\bCareside Filiale\b", "Careside"),
            (r"\bdes Datas\b", "de la Data"),
            (r"\bdatas\b", "data"),
            (r"\bd'automatisations\b", "d'automatisation"),
            (r"\boutils d'automatisations\b", "outils d'automatisation"),
            (r"\bavec experience\b", "avec expérience"),
            (r"\bd['’]experience\b", "d'expérience"),
        )
        for pattern, replacement in replacements:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        text = re.sub(r"\s+([,.])", r"\1", text)
        text = re.sub(r"\s*-\s*Careside\b", " - Careside", text)
        return re.sub(r"\s+", " ", text).strip()

    def _word_count(self, value: Any) -> int:
        return len(re.findall(r"\b\S+\b", str(value or "").strip(), flags=re.UNICODE))

    def _dedupe_render_lines_fuzzy(self, lines: Any) -> List[str]:
        deduped: List[str] = []
        seen_norms: List[str] = []
        for raw in lines or []:
            text = self._normalize_render_text(raw)
            norm = self._normalize_text_key(text)
            if not text or not norm:
                continue
            duplicate = False
            for idx, seen in enumerate(seen_norms):
                if norm == seen:
                    duplicate = True
                    break
                if len(norm) >= 24 and norm in seen:
                    duplicate = True
                    break
                if len(seen) >= 24 and seen in norm:
                    deduped[idx] = text
                    seen_norms[idx] = norm
                    duplicate = True
                    break
            if duplicate:
                continue
            deduped.append(text)
            seen_norms.append(norm)
        return deduped

    def _is_positioning_sentence(self, value: Any, *, is_en: bool) -> bool:
        text = self._normalize_render_text(value)
        if not text:
            return False
        patterns = (
            (
                re.compile(
                    r"^Atouts\s+pertinents(?:\s+pour\s+[^.:]{1,80})?\s*[:\-]\s*.+\.$",
                    re.IGNORECASE,
                ),
                re.compile(
                    r"^Profil\s+pertinent(?:\s+pour\s+[^.]{1,80}?)?\s+gr(?:a|â)ce\s+[aà]\s+.+\.$",
                    re.IGNORECASE,
                ),
                re.compile(
                    r"^Pour\s+[^.]{1,100},\s+ce\s+profil\s+(?:met\s+en\s+avant\s+un\s+positionnement\s+pertinent\s+autour\s+de|cible\s+le\s+poste\s+de\s+.+?\s+avec\s+un\s+positionnement\s+autour\s+de)\s+.+\.$",
                    re.IGNORECASE,
                ),
                re.compile(
                    r"^Ce\s+profil\s+met\s+en\s+avant\s+un\s+positionnement\s+pertinent\s+autour\s+de\s+.+\.$",
                    re.IGNORECASE,
                ),
            )
            if not is_en
            else (
                re.compile(
                    r"^Relevant\s+strengths(?:\s+for\s+[^.:]{1,80})?\s+include\s+.+\.$",
                    re.IGNORECASE,
                ),
                re.compile(
                    r"^Profile\s+aligned(?:\s+with\s+[^.]{1,80}?)?\s+through\s+.+\.$",
                    re.IGNORECASE,
                ),
                re.compile(
                    r"^For\s+[^.]{1,100},\s+this\s+profile\s+(?:highlights\s+relevant\s+positioning\s+around|targets\s+the\s+.+?\s+role\s+with\s+positioning\s+around)\s+.+\.$",
                    re.IGNORECASE,
                ),
                re.compile(
                    r"^This\s+profile\s+highlights\s+relevant\s+positioning\s+around\s+.+\.$",
                    re.IGNORECASE,
                ),
            )
        )
        return any(pattern.match(text) for pattern in patterns)

    def _parse_positioning_sentence(
        self,
        value: Any,
        *,
        is_en: bool,
    ) -> Tuple[str, List[str]]:
        text = self._normalize_render_text(value)
        if not text:
            return "", []
        patterns = (
            (
                re.compile(
                    r"^Atouts\s+pertinents(?:\s+pour\s+(?P<company>.+?))?\s*[:\-]\s*(?P<terms>.+?)\.\s*$",
                    re.IGNORECASE,
                ),
                re.compile(
                    r"^Profil\s+pertinent(?:\s+pour\s+(?P<company>.+?))?\s+gr(?:a|â)ce\s+[aà]\s+(?P<terms>.+?)\.\s*$",
                    re.IGNORECASE,
                ),
                re.compile(
                    r"^Pour\s+(?P<company>.+?),\s+ce\s+profil\s+(?:met\s+en\s+avant\s+un\s+positionnement\s+pertinent\s+autour\s+de|cible\s+le\s+poste\s+de\s+.+?\s+avec\s+un\s+positionnement\s+autour\s+de)\s+(?P<terms>.+?)\.\s*$",
                    re.IGNORECASE,
                ),
                re.compile(
                    r"^Ce\s+profil\s+met\s+en\s+avant\s+un\s+positionnement\s+pertinent\s+autour\s+de\s+(?P<terms>.+?)\.\s*$",
                    re.IGNORECASE,
                ),
            )
            if not is_en
            else (
                re.compile(
                    r"^Relevant\s+strengths(?:\s+for\s+(?P<company>.+?))?\s+include\s+(?P<terms>.+?)\.\s*$",
                    re.IGNORECASE,
                ),
                re.compile(
                    r"^Profile\s+aligned(?:\s+with\s+(?P<company>.+?))?\s+through\s+(?P<terms>.+?)\.\s*$",
                    re.IGNORECASE,
                ),
                re.compile(
                    r"^For\s+(?P<company>.+?),\s+this\s+profile\s+(?:highlights\s+relevant\s+positioning\s+around|targets\s+the\s+.+?\s+role\s+with\s+positioning\s+around)\s+(?P<terms>.+?)\.\s*$",
                    re.IGNORECASE,
                ),
                re.compile(
                    r"^This\s+profile\s+highlights\s+relevant\s+positioning\s+around\s+(?P<terms>.+?)\.\s*$",
                    re.IGNORECASE,
                ),
            )
        )
        for pattern in patterns:
            match = pattern.match(text)
            if not match:
                continue
            company = self._restore_display_acronyms(
                match.groupdict().get("company") or ""
            )
            raw_terms = str(match.groupdict().get("terms") or "").strip()
            items: List[str] = []
            seen: set[str] = set()
            for chunk in re.split(r"\s*;\s*", raw_terms):
                cleaned_chunk = self._normalize_render_text(chunk)
                if not cleaned_chunk:
                    continue
                lowered_chunk = self._normalize_text_key(cleaned_chunk)
                if not is_en and lowered_chunk.startswith("une proximite claire avec "):
                    cleaned_chunk = cleaned_chunk[len("une proximité claire avec ") :]
                elif is_en and lowered_chunk.startswith("clear proximity to "):
                    cleaned_chunk = cleaned_chunk[len("clear proximity to ") :]
                for item in re.split(r"\s*,\s*", cleaned_chunk):
                    cleaned_item = self._restore_display_acronyms(
                        self._normalize_render_text(item)
                    )
                    key = self._normalize_text_key(cleaned_item)
                    if not cleaned_item or not key or key in seen:
                        continue
                    seen.add(key)
                    items.append(cleaned_item)
            return company, items
        return "", []

    def _score_positioning_terms(
        self,
        terms: List[str],
        *,
        offer_terms: List[str],
        profile_terms: List[str],
        rendered_signatures: List[frozenset[str]],
    ) -> float:
        score = 0.0
        seen: set[str] = set()
        low_signal_singletons = {"ai", "api", "bi", "it", "ml", "qa", "sql", "ui", "ux"}
        for raw in terms or []:
            text = self._restore_display_acronyms(self._normalize_render_text(raw))
            key = self._normalize_text_key(text)
            if not text or not key or key in seen:
                continue
            seen.add(key)
            offer_match = any(
                self._match_probe_overlaps_term(text, item)
                for item in (offer_terms or [])
            )
            profile_match = any(
                self._match_probe_overlaps_term(text, item)
                for item in (profile_terms or [])
            )
            if offer_match and profile_match:
                score += 3.0
            elif offer_match:
                score += 1.9
            elif profile_match:
                score += 1.0
            if len(key.split()) >= 2:
                score += 0.4
            if re.search(r"[A-Z0-9+/#.-]", text):
                score += 0.3
            if self._sentence_overlaps_rendered_content(text, rendered_signatures):
                score -= 1.2
            if (
                len(key.split()) == 1
                and key in low_signal_singletons
                and not (offer_match and profile_match)
            ):
                score -= 0.8
        return score

    def _select_whole_sentences(
        self,
        sentences: Any,
        *,
        max_items: int,
        char_budget: int = 0,
        preferred_tail: str = "",
    ) -> List[str]:
        cleaned: List[str] = []
        seen: set[str] = set()
        for item in sentences or []:
            text = self._restore_display_acronyms(self._normalize_render_text(item))
            key = self._normalize_text_key(text)
            if not text or not key or key in seen:
                continue
            seen.add(key)
            cleaned.append(text)

        if not cleaned and not preferred_tail:
            return []

        selected: List[str] = []
        used = 0
        tail = self._normalize_render_text(preferred_tail)
        tail_key = self._normalize_text_key(tail)
        if tail_key:
            cleaned = [
                item for item in cleaned if self._normalize_text_key(item) != tail_key
            ]

        reserve_slots = 1 if tail else 0
        reserve_chars = (len(tail) + 1) if tail and char_budget > 0 else 0
        max_regular_items = max(0, int(max_items or 0) - reserve_slots)
        regular_budget = (
            max(0, int(char_budget or 0) - reserve_chars) if char_budget > 0 else 0
        )

        for sentence in cleaned:
            if len(selected) >= max_regular_items:
                break
            projected = used + len(sentence) + (1 if selected else 0)
            if regular_budget > 0 and selected and projected > regular_budget:
                continue
            if (
                regular_budget > 0
                and not selected
                and len(sentence) > regular_budget
                and max_regular_items > 0
            ):
                continue
            selected.append(sentence)
            used = projected

        if tail:
            if not selected and max_items == 1:
                return [tail]
            while selected and char_budget > 0 and (used + len(tail) + 1) > char_budget:
                removed = selected.pop()
                used -= len(removed) + (1 if selected else 0)
            if len(selected) < max(1, int(max_items or 1)):
                if (
                    char_budget <= 0
                    or not selected
                    or (used + len(tail) + 1) <= char_budget
                ):
                    selected.append(tail)
                elif not selected:
                    return [tail]

        if not selected and cleaned:
            return cleaned[: max(1, int(max_items or 1))]
        return selected[: max(1, int(max_items or 1))]

    def _score_experience_render_line(
        self,
        line: Any,
        *,
        company: str,
        job_title: str,
        offer_terms: List[str],
        language_code: str,
    ) -> float:
        text = self._normalize_render_text(line)
        if self._word_count(text) < 3:
            return -100.0

        try:
            from ..utils.cv_postprocessing import (
                _looks_like_company_description,
                _starts_with_action_phrase,
            )
        except Exception:

            def _looks_like_company_description(value, _company=""):
                lowered = str(value or "").lower()
                return ":" in lowered and any(
                    token in lowered
                    for token in (
                        "filiale",
                        "specialisee",
                        "specialized",
                        "group",
                        "groupe",
                        "company",
                    )
                )

            def _starts_with_action_phrase(value, *, language_code="fr"):
                lowered = str(value or "").strip().lower()
                verbs = (
                    (
                        "concevoir",
                        "executer",
                        "suivre",
                        "rediger",
                        "analyser",
                        "piloter",
                        "tester",
                        "valider",
                    )
                    if not str(language_code or "fr").lower().startswith("en")
                    else (
                        "designed",
                        "built",
                        "implemented",
                        "tested",
                        "led",
                        "improved",
                        "validated",
                    )
                )
                return lowered.startswith(verbs)

        if _looks_like_company_description(text, company):
            return -100.0

        try:
            from ..utils.keyword_alignment import (
                normalize_keyword_for_match,
                normalized_term_in_probe as normalized_term_present,
            )
        except Exception:

            def normalize_keyword_for_match(value):
                return self._normalize_text_key(value)

            def normalized_term_present(probe, term):
                return str(term or "") in str(probe or "")

        normalized_text = normalize_keyword_for_match(text)
        if not normalized_text:
            return -100.0
        if normalized_text.startswith(
            (
                "filiale ",
                "specialisee ",
                "specialized ",
                "groupe ",
                "group ",
                "plateforme ",
                "platform ",
                "autonomie specialisee ",
            )
        ) or "digitalisation du parcours patient" in normalized_text:
            return -100.0
        if re.search(r"\btaches?\s+de\s+lea\b", normalized_text):
            return -100.0

        company_desc_match = re.match(
            r"^\s*(?P<head>[^:]{1,60})\s*:\s*(?P<tail>.+)$",
            text,
        ) or re.match(
            r"^\s*(?P<head>.+?)\s+[-–—]\s+(?P<tail>.+)$",
            text,
        )
        if company_desc_match:
            tail_norm = normalize_keyword_for_match(
                company_desc_match.group("tail") or ""
            )
            company_descriptor_starts = (
                "filiale",
                "specialisee",
                "specialisee",
                "specialized",
                "specialised",
                "groupe",
                "group",
                "plateforme",
                "platform",
                "company",
                "societe",
            )
            if any(
                tail_norm.startswith(prefix) for prefix in company_descriptor_starts
            ):
                return -100.0

        score = 0.0
        if _starts_with_action_phrase(text, language_code=language_code):
            score += 2.5
        if re.search(
            r"\b\d+(?:[.,]\d+)?\s*(?:%|k|m|ans?|mois|jours?|hours?|users?|clients?)?\b",
            text,
            re.IGNORECASE,
        ):
            score += 1.2
        if any(
            token in normalized_text
            for token in (
                "resultat",
                "impact",
                "gain",
                "reduce",
                "improve",
                "fiabil",
                "automatis",
                "benchmark",
            )
        ):
            score += 0.8
        if "cas limite" in normalized_text or "edge case" in normalized_text:
            score += 2.0
        if any(
            token in normalized_text
            for token in (
                "postman",
                "jira",
                "xray",
                "gherkin",
                "mongodb",
                "postgresql",
                "sql server",
                "non regression",
                "exploratoire",
                "exploratoires",
                "anomal",
                "api",
                "release",
                "cas limite",
                "edge case",
                "agents ia",
                "poc",
                "donnees de test",
            )
        ):
            score += 1.6

        job_norm = normalize_keyword_for_match(job_title)
        if job_norm and normalized_term_present(normalized_text, job_norm):
            score += 1.6

        seen_terms: set[str] = set()
        for item in offer_terms or []:
            norm = normalize_keyword_for_match(item)
            if not norm or norm in seen_terms:
                continue
            seen_terms.add(norm)
            if normalized_term_present(normalized_text, norm):
                score += 1.4 if " " in norm else 0.8

        word_count = self._word_count(text)
        score += min(0.6, float(word_count) / 20.0)
        if word_count > 40:
            score -= 4.0
        if word_count > 55:
            score -= 3.0
        if word_count > 32 and ";" in text:
            score -= 1.5
        return score

    def _experience_line_bucket(self, value: Any) -> str:
        norm = self._normalize_text_key(value)
        if not norm:
            return "other"
        if norm.startswith("environnement"):
            return "tooling_delivery"
        if any(
            token in norm
            for token in (
                "ia",
                "ai",
                "poc",
                "agent",
                "agents",
                "automatisation",
                "automation",
                "playwright",
                "cypress",
                "selenium",
                "agilitest",
                "benchmark",
                "industrialisation",
                "donnees de test",
            )
        ):
            return "automation_ai"
        if any(
            token in norm
            for token in (
                "api",
                "postman",
                "mongodb",
                "postgresql",
                "sql server",
                "base de donnees",
                "donnees",
                "data",
            )
        ):
            return "api_data"
        if any(
            token in norm
            for token in (
                "jira",
                "xray",
                "gherkin",
                "anomal",
                "livrable",
                "documentation",
                "recette",
                "release",
                "transmission",
            )
        ):
            return "tooling_delivery"
        if any(
            token in norm
            for token in (
                "plan de test",
                "plans de test",
                "fonctionnel",
                "exploratoire",
                "exploratoires",
                "non regression",
                "specification",
                "ambiguite",
                "incoherence",
                "risque",
                "applications critiques",
            )
        ):
            return "qa_strategy"
        if any(
            token in norm
            for token in (
                "migration",
                "front end",
                "back end",
                "backend",
                "parametrage",
                "rgpd",
                "purge",
                "conformite",
                "qualifier",
                "qualifie",
            )
        ):
            return "technical_quality"
        return "other"

    def _merge_experience_bucket_lines(
        self,
        lines: List[str],
        *,
        max_parts: int = 3,
    ) -> str:
        cleaned: List[str] = []
        seen: set[str] = set()
        for line in lines or []:
            text = self._normalize_render_text(line).strip(" .;")
            key = self._normalize_text_key(text)
            if not text or not key or key in seen:
                continue
            seen.add(key)
            cleaned.append(text)
            if len(cleaned) >= max(1, int(max_parts or 1)):
                break
        if not cleaned:
            return ""
        # The renderer is a layout/safety layer, not a prose generator. Rich
        # fused bullets must be authored by the LLM from source evidence; do
        # not mechanically concatenate fragments with semicolons here.
        return cleaned[0]

    def _merge_experience_lines_by_signal(
        self,
        rows: List[Tuple[float, int, str]],
        *,
        max_items: int,
    ) -> List[str]:
        if not rows:
            return []

        selected_count = max(1, int(max_items or 1))
        grouped: Dict[str, List[Tuple[float, int, str]]] = {}
        for score, idx, text in sorted(rows, key=lambda row: row[1]):
            bucket = self._experience_line_bucket(text)
            grouped.setdefault(bucket, []).append((score, idx, text))

        bucket_priority = [
            "qa_strategy",
            "api_data",
            "tooling_delivery",
            "automation_ai",
            "technical_quality",
            "other",
        ]
        bucket_rank = {name: idx for idx, name in enumerate(bucket_priority)}
        ordered_buckets = sorted(
            grouped,
            key=lambda bucket: (
                bucket_rank.get(bucket, len(bucket_rank)),
                min(idx for _score, idx, _text in grouped[bucket]),
            ),
        )

        merged: List[Tuple[int, str]] = []
        for bucket in ordered_buckets:
            bucket_rows = sorted(grouped[bucket], key=lambda row: (-row[0], row[1]))
            top_rows = sorted(bucket_rows[:3], key=lambda row: row[1])
            text = self._merge_experience_bucket_lines(
                [row[2] for row in top_rows],
                max_parts=3,
            )
            if not text:
                continue
            merged.append((min(row[1] for row in top_rows), text))

        output = self._dedupe_render_lines_fuzzy(
            [text for _idx, text in sorted(merged[:selected_count], key=lambda row: row[0])]
        )
        if len(output) < selected_count:
            existing = {self._normalize_text_key(item) for item in output}
            for _score, _idx, text in sorted(rows, key=lambda row: (-row[0], row[1])):
                key = self._normalize_text_key(text)
                if not key or key in existing:
                    continue
                existing.add(key)
                output.append(text)
                if len(output) >= selected_count:
                    break
        return self._drop_contained_experience_lines(output)[:selected_count]

    def _drop_contained_experience_lines(self, lines: List[str]) -> List[str]:
        kept: List[str] = []
        kept_tokens: List[set[str]] = []
        for line in lines or []:
            text = self._normalize_render_text(line)
            tokens = {
                token
                for token in self._normalize_text_key(text).split()
                if len(token) >= 4
            }
            if tokens and any(
                len(tokens & previous) >= max(4, int(len(tokens) * 0.75))
                for previous in kept_tokens
            ):
                continue
            kept.append(text)
            kept_tokens.append(tokens)
        return kept

    def _ensure_named_tool_evidence_lines(
        self,
        selected: List[str],
        source_lines: List[str],
        *,
        max_items: int,
    ) -> List[str]:
        output = [
            self._normalize_render_text(item)
            for item in selected
            if self._normalize_render_text(item)
        ]
        selected_probe = self._normalize_text_key(" ".join(output))
        priority_markers = (
            ("playwright", "cypress", "selenium", "agilitest"),
            ("postman", "mongodb", "postgresql", "sql server"),
            ("jira", "xray", "gherkin"),
        )
        for markers in priority_markers:
            if any(marker in selected_probe for marker in markers):
                continue
            candidate = next(
                (
                    self._normalize_render_text(line)
                    for line in source_lines or []
                    if any(marker in self._normalize_text_key(line) for marker in markers)
                ),
                "",
            )
            if not candidate:
                continue
            if len(output) < max(1, int(max_items or 1)):
                output.append(candidate)
                selected_probe = self._normalize_text_key(" ".join(output))
        return self._drop_contained_experience_lines(output)[: max(1, int(max_items or 1))]

    def _select_experience_render_lines(
        self,
        lines: Any,
        *,
        company: str,
        job_title: str,
        offer_terms: List[str],
        language_code: str,
        max_items: int,
    ) -> List[str]:
        if not isinstance(lines, list):
            return []

        scored: List[Tuple[float, int, str]] = []
        for idx, raw in enumerate(lines):
            text = self._normalize_render_text(raw)
            if not text:
                continue
            score = self._score_experience_render_line(
                text,
                company=company,
                job_title=job_title,
                offer_terms=offer_terms,
                language_code=language_code,
            )
            if score <= -50.0:
                continue
            scored.append((score, idx, text))

        if not scored:
            fallback = [
                self._normalize_render_text(item)
                for item in lines
                if self._normalize_render_text(item)
            ]
            return self._dedupe_render_lines_fuzzy(fallback)[
                : max(1, int(max_items or 1))
            ]

        target_count = max(1, int(max_items or 1))
        short_scored = [row for row in scored if self._word_count(row[2]) <= 40]
        if len(short_scored) >= target_count:
            scored = short_scored

        candidate_limit = max(target_count * 3, target_count)
        rich_rows = sorted(scored, key=lambda row: (-row[0], row[1]))[:candidate_limit]
        return self._merge_experience_lines_by_signal(
            rich_rows,
            max_items=target_count,
        )

    def _trim_render_text(self, value: Any, max_chars: int) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        if len(text) <= max_chars:
            return text
        trimmed = text[: max_chars - 1].rstrip(" ,;:")
        return f"{trimmed}..."

    def _build_contact_methods_from_formatted_data(
        self,
        formatted_data: Dict[str, Any],
    ) -> List[Dict[str, str]]:
        methods: List[Dict[str, str]] = []
        seen: set[str] = set()
        is_en = (
            str((formatted_data or {}).get("language") or "").lower().startswith("en")
        )
        safe_schemes = {"http", "https", "mailto", "tel"}

        def _explicit_scheme(value: str) -> str:
            match = re.match(
                r"^([a-z][a-z0-9+.\-]*):", str(value or "").strip(), re.IGNORECASE
            )
            if not match:
                return ""
            return str(match.group(1) or "").lower()

        def _normalize_href(value: Any) -> str:
            text = str(value or "").strip()
            if not text:
                return ""
            scheme = _explicit_scheme(text)
            if scheme:
                if scheme not in safe_schemes:
                    return ""
                return text
            return f"https://{text.lstrip('/')}"

        def _display_link_value(url: str, href: str) -> str:
            scheme = _explicit_scheme(href)
            if scheme in {"mailto", "tel"}:
                return href.split(":", 1)[1].strip()
            return url

        def _append(kind: str, label: str, value: Any, href: str = "") -> None:
            text = str(value or "").strip()
            if not text:
                return
            resolved_href = str(href or "").strip()
            scheme = _explicit_scheme(resolved_href)
            if scheme:
                if scheme not in safe_schemes:
                    return
            if kind != "location" and not resolved_href:
                return
            dedupe_key = (resolved_href or text).lower()
            if dedupe_key in seen:
                return
            seen.add(dedupe_key)
            methods.append(
                {
                    "kind": kind,
                    "label": label,
                    "value": text,
                    "display_value": text,
                    "href": resolved_href,
                }
            )

        email = str((formatted_data or {}).get("email") or "").strip()
        if email:
            _append("email", "Email", email, f"mailto:{email}")

        phone = str((formatted_data or {}).get("phone") or "").strip()
        if phone:
            tel = re.sub(r"[^\d+]+", "", phone)
            _append("phone", "Phone" if is_en else "Telephone", phone, f"tel:{tel}")

        linkedin = str((formatted_data or {}).get("linkedin_url") or "").strip()
        if linkedin:
            href = _normalize_href(linkedin)
            _append("linkedin", "LinkedIn", linkedin, href)

        for link in (formatted_data or {}).get("links") or []:
            if not isinstance(link, dict):
                continue
            label = str(link.get("label") or "").strip()
            url = str(link.get("url") or "").strip()
            if not url:
                continue
            href = _normalize_href(url)
            if not href:
                continue
            if not label or re.match(r"^(?:lien|link)\s*\d*$", label, re.IGNORECASE):
                scheme = _explicit_scheme(href)
                if scheme == "mailto":
                    label = "Email"
                elif scheme == "tel":
                    label = "Phone" if is_en else "Telephone"
                else:
                    parsed = re.sub(r"^https?://", "", href, flags=re.IGNORECASE)
                    label = (
                        parsed.split("/")[0]
                        .replace("www.", "")
                        .split(".")[0]
                        .capitalize()
                    )
            display_value = _display_link_value(url, href)
            _append(label.lower(), label, display_value, href)

        location = str((formatted_data or {}).get("location") or "").strip()
        if location:
            _append("location", "Location" if is_en else "Localisation", location, "")

        return methods

    def _is_soft_skill_category(self, label: Any) -> bool:
        normalized = self._normalize_text_key(label)
        return normalized in {
            "soft skill",
            "soft skills",
            "qualites",
            "qualites personnelles",
            "qualities",
            "strengths",
        }

    def _score_featured_skill_candidate(
        self,
        value: Any,
        *,
        source: str = "skill",
    ) -> float:
        text = self._normalize_render_text(value)
        if not text:
            return -100.0

        norm = self._normalize_text_key(text)
        tokens = [token for token in norm.split() if token]
        if not tokens:
            return -100.0

        action_starters = {
            "analyse",
            "analyser",
            "build",
            "building",
            "collaborate",
            "collaborating",
            "concevoir",
            "contribute",
            "contributing",
            "deliver",
            "delivering",
            "develop",
            "developing",
            "driving",
            "ensure",
            "ensuring",
            "execute",
            "executing",
            "improve",
            "improving",
            "implement",
            "implementing",
            "integrate",
            "integrating",
            "lead",
            "leading",
            "manage",
            "managing",
            "piloter",
            "support",
            "supporting",
            "suivre",
            "test",
            "testing",
            "use",
            "using",
            "validate",
            "validating",
        }
        short_allowed = {
            "ai",
            "ml",
            "qa",
            "ui",
            "ux",
            "bi",
            "ci",
            "cd",
            "db",
            "sql",
            "api",
            "erp",
            "crm",
        }
        hard_generic_singletons = {
            "api",
            "apis",
            "automation",
            "automatisation",
            "bi",
            "cloud",
            "crm",
            "erp",
            "framework",
            "frameworks",
            "outil",
            "outils",
            "platform",
            "platforms",
            "plateforme",
            "plateformes",
            "qa",
            "reporting",
            "software",
            "stack",
            "suite",
            "suites",
            "system",
            "systems",
            "testing",
            "tests",
            "tool",
            "tools",
        }

        score = 0.0
        if len(tokens) == 1:
            score += 1.5
        elif len(tokens) <= 3:
            score += 1.0
        elif len(tokens) <= 5:
            score += 0.2
        else:
            score -= 2.5

        if len(text) > 42:
            score -= 1.2
        if text.endswith((".", "!", "?")):
            score -= 2.0
        if (
            re.search(r"[+#./0-9]", text)
            or re.search(r"[A-Z]", text[1:])
            or re.fullmatch(r"[A-Z0-9]{2,8}", text)
        ):
            score += 1.2
        if any(token in short_allowed for token in tokens):
            score += 1.0
        if len(tokens) == 1 and tokens[0] in hard_generic_singletons:
            score -= 4.5
        if source == "named_tool":
            score += 2.2
        elif source == "experience_tool":
            score += 1.6
        if tokens[0] in action_starters:
            score -= 4.0
        if any(token in {"with", "through", "using"} for token in tokens[:2]):
            score -= 1.0
        if len(tokens) >= 2 and any(
            token
            in {
                "api",
                "apis",
                "testing",
                "sql",
                "python",
                "jira",
                "xray",
                "mongodb",
                "postgresql",
                "postman",
                "playwright",
                "cypress",
                "selenium",
            }
            for token in tokens
        ):
            score += 0.8

        return score

    def _collect_named_featured_skill_candidates(
        self,
        formatted_data: Dict[str, Any],
    ) -> List[str]:
        try:
            from ..domain.generation.tool_signals import collect_named_tool_hints
        except Exception:
            return []

        payload = {
            "skills": (formatted_data or {}).get("skills"),
            "experience": (formatted_data or {}).get("experience_all")
            or (formatted_data or {}).get("experience"),
            "projects": (formatted_data or {}).get("projects"),
        }
        return collect_named_tool_hints(payload, max_items=18)

    def _normalize_match_probe(self, value: Any) -> str:
        try:
            from ..utils.keyword_alignment import normalize_keyword_for_match
        except Exception:
            return self._normalize_text_key(value)
        return normalize_keyword_for_match(value)

    def _looks_like_compact_tool_label(self, value: Any) -> bool:
        text = self._normalize_render_text(value)
        if not text:
            return False
        words = text.split()
        if len(words) > 3:
            return False
        normalized = self._normalize_text_key(text)
        if not normalized:
            return False
        if normalized in {
            "automation",
            "automatisation",
            "benchmark",
            "comparison",
            "comparaison",
            "evaluation",
            "exploration",
            "outils",
            "tools",
            "logiciels",
            "software",
            "platform",
            "plateforme",
            "differents modeles",
        }:
            return False
        if words[0].casefold() in {
            "analyser",
            "concevoir",
            "creer",
            "deliver",
            "develop",
            "ensure",
            "executer",
            "execute",
            "implement",
            "improve",
            "integrate",
            "realiser",
            "suivre",
            "tester",
            "using",
            "validate",
        }:
            return False
        common_lowercase_tools = {
            "agilitest",
            "cypress",
            "docker",
            "jira",
            "kubernetes",
            "looker",
            "mongodb",
            "mysql",
            "playwright",
            "postman",
            "postgresql",
            "powerbi",
            "pytest",
            "python",
            "selenium",
            "serviceNow".casefold(),
            "sql",
            "tableau",
            "xray",
        }
        if normalized in common_lowercase_tools:
            return True
        if re.search(r"[+#./0-9]", text):
            return True
        if any(ch.isupper() for ch in text[1:]):
            return True
        return bool(
            re.fullmatch(
                r"[A-Z][A-Za-z0-9#+./-]{1,30}(?:\s+[A-Z][A-Za-z0-9#+./-]{1,30}){0,2}",
                text,
            )
        )

    def _match_probe_contains_term(self, probe: Any, term: Any) -> bool:
        try:
            from ..utils.keyword_alignment import (
                normalize_keyword_for_match,
                normalized_term_in_probe as normalized_term_present,
            )
        except Exception:
            norm_probe = self._normalize_text_key(probe)
            norm_term = self._normalize_text_key(term)
            return bool(norm_probe and norm_term and norm_term in norm_probe)
        return normalized_term_present(
            normalize_keyword_for_match(probe),
            normalize_keyword_for_match(term),
        )

    def _match_probe_overlaps_term(self, left: Any, right: Any) -> bool:
        return self._match_probe_contains_term(
            left, right
        ) or self._match_probe_contains_term(right, left)

    def _collect_skill_proof_tools(
        self,
        skill_name: Any,
        *,
        experience_entries: Any,
        projects: Any,
        max_items: int = 8,
    ) -> List[str]:
        try:
            from ..domain.generation.tool_signals import collect_named_tool_hints
        except Exception:
            return []

        skill_norm = self._normalize_text_key(skill_name)
        if not skill_norm:
            return []

        context_keywords = {token for token in skill_norm.split() if len(token) >= 4}
        comparative_markers = {
            "benchmark",
            "benchmarker",
            "compar",
            "evaluation",
            "evaluer",
            "explor",
            "automat",
            "automatis",
            "outil",
            "outils",
            "tool",
            "tools",
            "logiciel",
            "software",
            "platform",
            "plateforme",
        }
        requires_contextual_tools = any(
            marker in skill_norm for marker in comparative_markers
        )
        specific_context_keywords = {
            token[:8]
            for token in context_keywords
            if token not in comparative_markers
            and token not in {"outil", "outils", "tool", "tools"}
        }

        contextual_lines: List[str] = []
        for block in list(experience_entries or []) + list(projects or []):
            if not isinstance(block, dict):
                continue
            candidates: List[str] = []
            for key in ("summary", "description"):
                value = block.get(key)
                if isinstance(value, str) and value.strip():
                    candidates.append(value.strip())
                elif isinstance(value, list):
                    candidates.extend(
                        str(item).strip()
                        for item in value
                        if isinstance(item, str) and item.strip()
                    )
            for key in ("highlights",):
                value = block.get(key)
                if isinstance(value, list):
                    candidates.extend(
                        str(item).strip()
                        for item in value
                        if isinstance(item, str) and item.strip()
                    )
            for key in ("_render_source_description",):
                value = block.get(key)
                if isinstance(value, list):
                    candidates.extend(
                        str(item).strip()
                        for item in value
                        if isinstance(item, str) and item.strip()
                    )
            technologies = block.get("technologies")
            if isinstance(technologies, list):
                candidates.extend(
                    str(item).strip()
                    for item in technologies
                    if isinstance(item, str) and item.strip()
                )
            elif isinstance(technologies, str) and technologies.strip():
                candidates.append(technologies.strip())

            for candidate in candidates:
                candidate_norm = self._normalize_text_key(candidate)
                if not candidate_norm:
                    continue
                if any(marker in candidate_norm for marker in comparative_markers):
                    if specific_context_keywords and any(
                        token in candidate_norm for token in specific_context_keywords
                    ):
                        contextual_lines.append(candidate)
                    elif not specific_context_keywords:
                        contextual_lines.append(candidate)
                    continue
                if specific_context_keywords and any(
                    token in candidate_norm for token in specific_context_keywords
                ):
                    contextual_lines.append(candidate)

        payload: Dict[str, Any]
        if contextual_lines:
            payload = {"description": contextual_lines}
        elif requires_contextual_tools:
            return []
        else:
            payload = {
                "experience": experience_entries,
                "projects": projects,
            }

        candidates = collect_named_tool_hints(payload, max_items=max_items * 3)
        filtered: List[str] = []
        seen_filtered: set[str] = set()
        for candidate in candidates:
            parts = [
                self._normalize_render_text(part).strip(" .,:;")
                for part in re.split(
                    r"\s*(?:/|,|;|\|)\s*", str(candidate or "").strip()
                )
                if self._normalize_render_text(part).strip(" .,:;")
            ]
            for part in parts or [
                self._normalize_render_text(candidate).strip(" .,:;")
            ]:
                key = self._normalize_text_key(part)
                if not key or key in seen_filtered:
                    continue
                if not self._looks_like_compact_tool_label(part):
                    continue
                seen_filtered.add(key)
                filtered.append(part)
                if len(filtered) >= max(1, int(max_items or 1)):
                    return filtered
        if filtered:
            return filtered[: max(1, int(max_items or 1))]

        if contextual_lines:
            for line in contextual_lines:
                probe = re.split(
                    r"\b(?:notamment|including|such as|like|avec|using|used|comme)\b",
                    str(line or ""),
                    maxsplit=1,
                    flags=re.IGNORECASE,
                )
                tail = probe[-1] if probe else str(line or "")
                for part in re.split(
                    r"\s*(?:,|;|/|\bet\b|\band\b|\bou\b|\bor\b)\s*", tail
                ):
                    cleaned = self._normalize_render_text(part).strip(" .,:;")
                    key = self._normalize_text_key(cleaned)
                    if not cleaned or not key or key in seen_filtered:
                        continue
                    if not self._looks_like_compact_tool_label(cleaned):
                        continue
                    seen_filtered.add(key)
                    filtered.append(cleaned)
                    if len(filtered) >= max(1, int(max_items or 1)):
                        return filtered
        return filtered[: max(1, int(max_items or 1))]

    def _rewrite_featured_skill_label(
        self,
        skill_name: Any,
        *,
        experience_entries: Any,
        projects: Any,
        language_code: str = "fr",
    ) -> str:
        text = self._normalize_render_text(skill_name)
        if not text:
            return ""

        is_en = str(language_code or "").lower().startswith("en")
        normalized = self._normalize_text_key(text)
        context_probe = self._normalize_match_probe(
            " ".join(
                [
                    str(block.get("title") or "").strip()
                    for block in (experience_entries or [])
                    if isinstance(block, dict) and str(block.get("title") or "").strip()
                ]
                + [
                    str(item).strip()
                    for block in list(experience_entries or []) + list(projects or [])
                    if isinstance(block, dict)
                    for key in ("summary", "description", "_render_source_description")
                    for value in (
                        [block.get(key)]
                        if isinstance(block.get(key), str)
                        else list(block.get(key) or [])
                    )
                    for item in [value]
                    if isinstance(item, str) and str(item).strip()
                ]
            )
        )
        proof_tools = self._collect_skill_proof_tools(
            text,
            experience_entries=experience_entries,
            projects=projects,
            max_items=8,
        )
        compact_tools = [
            tool for tool in proof_tools if self._normalize_render_text(tool)
        ]

        if (
            "tests d acceptance" in normalized
            or "tests d acceptation" in normalized
            or "acceptance" in normalized
        ):
            if "explor" in normalized:
                return (
                    "Acceptance and exploratory testing"
                    if is_en
                    else "Tests d'acceptation et exploratoires"
                )
            return "Acceptance testing" if is_en else "Tests d'acceptation"
        if "plan de test" in normalized or "plans de test" in normalized:
            return "Test plans" if is_en else "Plans de test"
        if "anomal" in normalized:
            return "Defect tracking" if is_en else "Suivi d'anomalies"
        if "regress" in normalized:
            if compact_tools:
                return self._restore_display_acronyms(
                    f"Regression testing {' / '.join(compact_tools)}"
                    if is_en
                    else f"Tests de non-régression {' / '.join(compact_tools)}"
                )
            return "Regression testing" if is_en else "Tests de non-régression"
        if normalized in {"api", "apis"}:
            if any(
                self._match_probe_contains_term(context_probe, marker)
                for marker in ("api testing", "test api", "postman", "tests", "qa")
            ):
                return "API testing" if is_en else "Tests API"
            return "API"
        if normalized == "qa":
            return "QA"
        if (
            "bilan de recette" in normalized
            or "bilans de recettes" in normalized
            or "recette" in normalized
        ):
            return "Acceptance reports" if is_en else "Bilans de recette"
        if (
            "dev back" in normalized
            or "back end" in normalized
            or "backend" in normalized
        ):
            return "Back-end"
        if any(
            token in normalized
            for token in ("tableau", "powerbi", "power bi", "looker")
        ):
            return "Tableau / Power BI / Looker"

        if any(
            marker in normalized
            for marker in (
                "benchmark",
                "benchmarker",
                "compar",
                "evaluation",
                "evaluer",
            )
        ):
            if compact_tools:
                return self._restore_display_acronyms(
                    f"Benchmark {' / '.join(compact_tools)}"
                )
            return (
                "Automation tool benchmark"
                if is_en
                else "Benchmark d'outils d'automatisation"
            )
        if any(marker in normalized for marker in ("explor", "research", "veille")):
            if compact_tools:
                prefix = "Exploration" if not is_en else "Exploration"
                return self._restore_display_acronyms(
                    f"{prefix} {' / '.join(compact_tools)}"
                )
            return "Tool exploration" if is_en else "Exploration d'outils"
        return self._restore_display_acronyms(text)

    def _score_featured_skill_relevance(
        self,
        original_name: Any,
        display_name: Any,
        *,
        offer_terms: List[str],
        job_title: str,
        experience_entries: Any,
        projects: Any,
        source: str = "skill",
    ) -> float:
        original_text = self._normalize_render_text(original_name)
        display_text = self._normalize_render_text(display_name) or original_text
        score = self._score_featured_skill_candidate(display_text, source=source)

        probes: List[str] = []
        for entry in experience_entries or []:
            if not isinstance(entry, dict):
                continue
            probes.append(
                " ".join(
                    [
                        str(entry.get("title") or "").strip(),
                        str(entry.get("company") or "").strip(),
                        " ".join(
                            str(line).strip()
                            for line in (entry.get("description") or [])
                            if isinstance(line, str) and str(line).strip()
                        ),
                        " ".join(
                            str(line).strip()
                            for line in (entry.get("_render_source_description") or [])
                            if isinstance(line, str) and str(line).strip()
                        ),
                    ]
                )
            )
        all_experience_probe = self._normalize_match_probe(" ".join(probes))
        anchor_probe = ""
        recent_probe = ""
        ranked_entries = [
            entry for entry in (experience_entries or []) if isinstance(entry, dict)
        ]
        if ranked_entries:
            anchor_entry = sorted(
                ranked_entries,
                key=lambda item: float(item.get("render_alignment_score") or 0.0),
                reverse=True,
            )[0]
            anchor_probe = self._normalize_match_probe(
                " ".join(
                    [
                        str(anchor_entry.get("title") or "").strip(),
                        " ".join(
                            str(line).strip()
                            for line in (
                                anchor_entry.get("_render_source_description")
                                or anchor_entry.get("description")
                                or []
                            )
                            if isinstance(line, str) and str(line).strip()
                        ),
                    ]
                )
            )
            recent_entry = sorted(
                ranked_entries,
                key=self._experience_recency_rank,
                reverse=True,
            )[0]
            recent_probe = self._normalize_match_probe(
                " ".join(
                    [
                        str(recent_entry.get("title") or "").strip(),
                        " ".join(
                            str(line).strip()
                            for line in (
                                recent_entry.get("_render_source_description")
                                or recent_entry.get("description")
                                or []
                            )
                            if isinstance(line, str) and str(line).strip()
                        ),
                    ]
                )
            )
        project_parts: List[str] = []
        for project in projects or []:
            if not isinstance(project, dict):
                continue
            project_parts.extend(
                [
                    str(project.get("name") or "").strip(),
                    str(project.get("description") or "").strip(),
                    str(project.get("technologies") or "").strip(),
                ]
            )
        project_probe = self._normalize_match_probe(" ".join(project_parts))

        evidence_terms: List[str] = []
        for item in (original_text, display_text):
            if item:
                evidence_terms.append(item)
        for tool in self._collect_skill_proof_tools(
            original_text,
            experience_entries=experience_entries,
            projects=projects,
            max_items=8,
        ):
            text = self._normalize_render_text(tool)
            if text:
                evidence_terms.append(text)

        evidence_terms = [
            item
            for idx, item in enumerate(evidence_terms)
            if item
            and self._normalize_text_key(item)
            not in {self._normalize_text_key(other) for other in evidence_terms[:idx]}
        ]

        offer_hits = 0.0
        offer_match_count = 0
        for term in offer_terms or []:
            term_text = self._normalize_render_text(term)
            if not term_text:
                continue
            if any(
                self._match_probe_overlaps_term(candidate, term_text)
                for candidate in evidence_terms
            ):
                offer_match_count += 1
                offer_hits += (
                    2.1 if " " in self._normalize_match_probe(term_text) else 1.1
                )
        score += min(5.5, offer_hits)

        job_title_hit = bool(
            job_title
            and any(
                self._match_probe_overlaps_term(candidate, job_title)
                for candidate in evidence_terms
            )
        )
        if job_title_hit:
            score += 1.8

        direct_alignment_signal = offer_match_count > 0 or job_title_hit
        if anchor_probe and any(
            self._match_probe_contains_term(anchor_probe, candidate)
            for candidate in evidence_terms
        ):
            score += 2.2 if direct_alignment_signal else 0.6
        if recent_probe and any(
            self._match_probe_contains_term(recent_probe, candidate)
            for candidate in evidence_terms
        ):
            score += 1.6 if direct_alignment_signal else 0.4
        if all_experience_probe and any(
            self._match_probe_contains_term(all_experience_probe, candidate)
            for candidate in evidence_terms
        ):
            score += 1.0 if direct_alignment_signal else 0.2
        if project_probe and any(
            self._match_probe_contains_term(project_probe, candidate)
            for candidate in evidence_terms
        ):
            score += 0.8

        generic_labels = {
            "pack office",
            "microsoft office",
            "zoom et teams",
            "zoom and teams",
            "dev back",
        }
        normalized_display = self._normalize_text_key(display_text)
        if normalized_display in generic_labels and offer_hits <= 0.0:
            score -= 2.4
        if "/" in display_text:
            score += 1.0
        if ":" in display_text and any(
            marker in normalized_display
            for marker in ("benchmark", "exploration", "evaluation")
        ):
            score -= 0.5
        if (
            any(
                marker in normalized_display
                for marker in ("benchmark", "exploration", "evaluation")
            )
            and len(evidence_terms) >= 3
        ):
            score += 1.2
        if str(source or "") == "soft_skill":
            score += 0.4

        rendered_probe = self._normalize_match_probe(
            " ".join(
                str(line).strip()
                for entry in (experience_entries or [])
                if isinstance(entry, dict)
                for line in (entry.get("description") or [])
                if isinstance(line, str) and str(line).strip()
            )
        )
        if rendered_probe and self._match_probe_contains_term(
            rendered_probe, display_text
        ):
            score -= 0.8

        offer_probe = self._normalize_match_probe(
            " ".join([job_title, *(offer_terms or [])])
        )
        has_explicit_offer_terms = any(
            self._normalize_render_text(item) for item in (offer_terms or [])
        )
        skill_probe = self._normalize_match_probe(
            " ".join(evidence_terms + [display_text, original_text])
        )
        soft_alignment_groups = (
            (
                ("autonomie", "autonomous", "self starter", "self-starter"),
                ("autonomous", "self starter", "self-starter", "autonomie"),
            ),
            (
                ("rigueur", "rigoureux", "rigoureuse"),
                ("accuracy", "robustness", "reliability", "quality", "rigueur"),
            ),
            (
                ("travailler en equipe", "travail en equipe", "teamwork"),
                (
                    "collaborative",
                    "cross functional",
                    "team spirited",
                    "teamwork",
                    "stakeholders",
                ),
            ),
            (
                ("curieux", "curiosite", "curiosity"),
                (
                    "learning",
                    "innovation",
                    "continuous improvement",
                    "creative",
                    "curiosity",
                ),
            ),
            (
                ("efficacite", "efficiency"),
                ("efficient", "efficiency", "productivity", "scalable", "save time"),
            ),
            (
                ("problem solving", "resolution de problemes"),
                ("problem solver", "debugging", "resolve", "issue"),
            ),
        )
        for skill_aliases, offer_aliases in soft_alignment_groups:
            if any(
                self._match_probe_contains_term(skill_probe, item)
                for item in skill_aliases
            ) and any(
                self._match_probe_contains_term(offer_probe, item)
                for item in offer_aliases
            ):
                score += 2.0
                break
        qa_offer_markers = (
            "qa",
            "test",
            "testing",
            "quality",
            "automation",
            "api",
            "playwright",
            "postman",
            "regression",
            "exploratory",
            "debug",
        )
        qa_skill_markers = (
            "qa",
            "test",
            "tests",
            "testing",
            "acceptation",
            "acceptance",
            "explor",
            "regression",
            "anomal",
            "recette",
            "plan de test",
            "plans de test",
            "automation",
            "automatisation",
            "api",
            "playwright",
            "postman",
            "cypress",
            "selenium",
            "xray",
            "jira",
            "quality",
            "benchmark",
        )
        bi_skill_markers = (
            "tableau",
            "power bi",
            "powerbi",
            "looker",
            "reporting",
            "dashboard",
            "business intelligence",
            "bi",
        )
        bi_offer_markers = (
            "tableau",
            "power bi",
            "powerbi",
            "looker",
            "reporting",
            "dashboard",
            "analytics",
            "business intelligence",
            "bi",
            "data visualization",
        )
        db_skill_markers = (
            "sql",
            "database",
            "postgresql",
            "mongodb",
            "mysql",
            "sql server",
        )
        db_offer_markers = (
            "sql",
            "database",
            "databases",
            "postgresql",
            "mongodb",
            "mysql",
            "backend",
            "back end",
            "data",
            "warehouse",
            "etl",
        )
        programming_skill_markers = (
            "python",
            "typescript",
            "javascript",
            "backend",
            "back end",
            "pytest",
        )
        programming_offer_markers = (
            "python",
            "typescript",
            "javascript",
            "backend",
            "back end",
            "developer",
            "engineering",
            "software engineer",
            "scripting",
        )
        ai_skill_markers = (
            "ai",
            "ia",
            "ml",
            "llm",
            "llmops",
            "mlops",
            "machine learning",
            "intelligence artificielle",
            "ia avancee",
            "ia avance",
            "prompt engineering",
            "rag",
            "model",
            "modele",
        )
        ai_offer_markers = (
            "ai",
            "ia",
            "ml",
            "llm",
            "machine learning",
            "intelligence artificielle",
            "model",
            "models",
            "modele",
            "modeles",
            "model integrations",
            "inference",
            "rag",
            "prompt",
        )
        qa_offer_active = any(
            self._match_probe_contains_term(offer_probe, marker)
            for marker in qa_offer_markers
        )
        bi_offer_active = any(
            self._match_probe_contains_term(offer_probe, marker)
            for marker in bi_offer_markers
        )
        db_offer_active = any(
            self._match_probe_contains_term(offer_probe, marker)
            for marker in db_offer_markers
        )
        programming_offer_active = any(
            self._match_probe_contains_term(offer_probe, marker)
            for marker in programming_offer_markers
        )
        ai_offer_active = any(
            self._match_probe_contains_term(offer_probe, marker)
            for marker in ai_offer_markers
        )
        qa_skill_match = any(
            self._match_probe_contains_term(skill_probe, marker)
            for marker in qa_skill_markers
        )
        bi_skill_match = any(
            self._match_probe_contains_term(skill_probe, marker)
            for marker in bi_skill_markers
        )
        db_skill_match = any(
            self._match_probe_contains_term(skill_probe, marker)
            for marker in db_skill_markers
        )
        programming_skill_match = any(
            self._match_probe_contains_term(skill_probe, marker)
            for marker in programming_skill_markers
        )
        ai_skill_match = any(
            self._match_probe_contains_term(skill_probe, marker)
            for marker in ai_skill_markers
        )

        if ai_offer_active and ai_skill_match:
            score += 3.2
            if any(
                self._match_probe_contains_term(skill_probe, marker)
                for marker in ("llmops", "mlops", "prompt engineering", "rag")
            ):
                score += 1.2

        if qa_offer_active:
            if qa_skill_match:
                score += 3.0
            if any(
                self._match_probe_contains_term(skill_probe, marker)
                for marker in ("playwright", "postman", "cypress", "selenium", "api")
            ):
                score += 1.3
            if any(
                self._match_probe_contains_term(skill_probe, marker)
                for marker in (
                    "plans de test",
                    "plan de test",
                    "anomal",
                    "regression",
                    "explor",
                    "acceptance",
                    "acceptation",
                )
            ):
                score += 2.4
            if normalized_display in {
                "tests api",
                "tests d acceptation",
                "tests d acceptation et exploratoires",
                "plans de test",
            }:
                score += 2.4
            if normalized_display in {"suivi d anomalies"}:
                score += 1.2
            if normalized_display.startswith("tests de non regression"):
                score += 2.0
            if has_explicit_offer_terms and bi_skill_match and not bi_offer_active:
                score -= 8.0
            if has_explicit_offer_terms and db_skill_match and not db_offer_active:
                score -= 8.2
            if (
                has_explicit_offer_terms
                and any(
                    self._match_probe_contains_term(skill_probe, marker)
                    for marker in ("back end", "backend")
                )
                and not programming_offer_active
            ):
                score -= 2.4

        if bi_skill_match and bi_offer_active:
            score += 1.6
        if db_skill_match and db_offer_active:
            score += 1.4
        if programming_skill_match and programming_offer_active:
            score += 1.0

        if (
            has_explicit_offer_terms
            and db_skill_match
            and len(normalized_display.split()) == 1
            and not db_offer_active
        ):
            score -= 5.0
        if (
            len(normalized_display.split()) == 1
            and offer_match_count <= 0
            and not qa_skill_match
            and not programming_skill_match
        ):
            score -= 1.4

        return score

    def _collect_soft_skill_candidates(
        self, soft_skills: Any, skill_blocks: Any
    ) -> List[str]:
        candidates: List[str] = []
        seen: set[str] = set()

        def _append(value: Any) -> None:
            text = self._sentence_case_label(value)
            key = self._normalize_text_key(text)
            if not text or not key or key in seen:
                return
            seen.add(key)
            candidates.append(text)

        if isinstance(soft_skills, list):
            for item in soft_skills:
                if isinstance(item, dict):
                    _append(item.get("name") or item.get("label") or item.get("skill"))
                    nested = item.get("items") or item.get("skills")
                    if isinstance(nested, list):
                        for sub in nested:
                            if isinstance(sub, dict):
                                _append(
                                    sub.get("name")
                                    or sub.get("skill")
                                    or sub.get("label")
                                )
                            else:
                                _append(sub)
                else:
                    _append(item)

        if isinstance(skill_blocks, list):
            for block in skill_blocks:
                if not isinstance(block, dict) or not self._is_soft_skill_category(
                    block.get("category")
                ):
                    continue
                items = (
                    block.get("skills_list")
                    or block.get("items")
                    or block.get("skills")
                    or []
                )
                if not isinstance(items, list):
                    continue
                for item in items:
                    if isinstance(item, dict):
                        _append(
                            item.get("name") or item.get("skill") or item.get("label")
                        )
                    else:
                        _append(item)

        return candidates

    def _group_featured_skills_for_display(
        self,
        selected_skills: Any,
        formatted_data: Dict[str, Any],
        *,
        offer_terms: List[str],
        job_title: str,
        language_code: str,
        max_items: int = 10,
    ) -> List[str]:
        # Rendering must stay domain-neutral. Profession-specific grouping
        # belongs to the LLM-generated CV JSON, where JOB_TITLE and offer
        # evidence are available, not to this fallback renderer.
        category_rows: List[str] = []
        category_seen: set[str] = set()
        skill_blocks = (formatted_data or {}).get("skills")
        if isinstance(skill_blocks, list):
            non_soft_blocks = [
                block
                for block in skill_blocks
                if isinstance(block, dict)
                and not self._is_soft_skill_category(block.get("category"))
            ]
            names_per_row = 8 if len(non_soft_blocks) <= 2 else 6
            for block in non_soft_blocks:
                category = self._normalize_render_text(
                    block.get("category") or ""
                ).strip(" :")
                items = (
                    block.get("skills_list")
                    or block.get("items")
                    or block.get("skills")
                    or []
                )
                if not isinstance(items, list):
                    continue
                names: List[str] = []
                seen_names: set[str] = set()
                for item in items:
                    if isinstance(item, dict):
                        raw_name = item.get("name") or item.get("skill") or ""
                    else:
                        raw_name = item
                    name = self._normalize_render_text(raw_name).strip(" ,;:-")
                    key = self._normalize_text_key(name)
                    if not name or not key or key in seen_names:
                        continue
                    seen_names.add(key)
                    names.append(name)
                    if len(names) >= names_per_row:
                        break
                if not names:
                    continue
                if category:
                    row = f"{category} : {' / '.join(names)}"
                else:
                    row = " / ".join(names)
                row_key = self._normalize_text_key(row)
                if not row_key or row_key in category_seen:
                    continue
                category_seen.add(row_key)
                category_rows.append(row)
                if len(category_rows) >= max(1, int(max_items or 1)):
                    break
        if category_rows:
            return category_rows

        output: List[str] = []
        seen: set[str] = set()
        limit = max(1, int(max_items or 1))
        for item in selected_skills or []:
            text = self._normalize_render_text(item)
            if not text:
                continue
            key = self._normalize_text_key(text)
            if not key or key in seen:
                continue
            seen.add(key)
            output.append(text)
            if len(output) >= limit:
                break
        return output

    def _select_featured_skills(
        self,
        skills: Any,
        *,
        max_items: int = 5,
        offer_terms: Optional[List[str]] = None,
        job_title: str = "",
        experience_entries: Any = None,
        experience_all: Any = None,
        projects: Any = None,
        language_code: str = "fr",
    ) -> List[str]:
        if not isinstance(skills, list):
            skills = []

        primary: List[Tuple[int, str, str]] = []
        fallback: List[Tuple[int, str, str]] = []
        seen: set[str] = set()

        def _append(
            target: List[Tuple[int, str, str]],
            value: Any,
            order: int,
            *,
            source: str,
        ) -> int:
            name = (
                self._sentence_case_label(value)
                if source == "soft_skill"
                else str(value or "").strip()
            )
            key = self._normalize_text_key(name)
            if not name or not key or key in seen:
                return order
            seen.add(key)
            target.append((order, name, source))
            return order + 1

        order = 0

        for block in skills:
            if isinstance(block, dict):
                items = (
                    block.get("skills_list")
                    or block.get("items")
                    or block.get("skills")
                    or []
                )
                is_soft = self._is_soft_skill_category(block.get("category"))
                bucket = fallback if is_soft else primary
                if not isinstance(items, list):
                    continue
                for item in items:
                    if isinstance(item, dict):
                        order = _append(
                            bucket,
                            item.get("name") or item.get("skill") or "",
                            order,
                            source="soft_skill" if is_soft else "skill",
                        )
                    else:
                        order = _append(
                            bucket,
                            item,
                            order,
                            source="soft_skill" if is_soft else "skill",
                        )
            elif isinstance(block, str):
                order = _append(primary, block, order, source="skill")

        candidates = primary if primary else fallback
        if not candidates:
            return []

        experience_probe_entries = [
            item
            for item in ((experience_entries or []) or (experience_all or []) or [])
            if isinstance(item, dict)
        ]
        ranked = sorted(
            (
                (
                    self._score_featured_skill_relevance(
                        name,
                        self._rewrite_featured_skill_label(
                            name,
                            experience_entries=experience_probe_entries
                            or (experience_all or []),
                            projects=projects,
                            language_code=language_code,
                        ),
                        offer_terms=list(offer_terms or []),
                        job_title=job_title,
                        experience_entries=experience_probe_entries
                        or (experience_all or []),
                        projects=projects,
                        source=source,
                    ),
                    order,
                    self._rewrite_featured_skill_label(
                        name,
                        experience_entries=experience_probe_entries
                        or (experience_all or []),
                        projects=projects,
                        language_code=language_code,
                    )
                    or name,
                    source,
                )
                for order, name, source in candidates
            ),
            key=lambda row: (-row[0], row[1]),
        )
        has_offer_signal = bool(list(offer_terms or []))
        selection_floor = (
            0.0
            if has_offer_signal
            else (-2.5 if len(ranked) <= max(1, int(max_items or 1)) else 0.0)
        )
        selected = [
            name for score, _order, name, _source in ranked if score >= selection_floor
        ]
        if len(ranked) <= max(1, int(max_items or 1)) and len(selected) < len(ranked):
            for score, _order, name, source in ranked:
                if name in selected:
                    continue
                if score < selection_floor:
                    continue
                if self._score_featured_skill_candidate(name, source=source) < 0.0:
                    continue
                selected.append(name)
        deduped: List[str] = []
        seen_selected: set[str] = set()
        for item in selected:
            key = self._normalize_text_key(item)
            if not key or key in seen_selected:
                continue
            seen_selected.add(key)
            deduped.append(item)
        return deduped[: max(1, int(max_items or 1))]

    def _select_featured_soft_skills(
        self, soft_skills: Any, *, max_items: int = 3
    ) -> List[str]:
        if not isinstance(soft_skills, list):
            return []
        selected: List[str] = []
        seen: set[str] = set()
        for item in soft_skills:
            if isinstance(item, dict):
                name = str(item.get("name") or item.get("label") or "").strip()
            else:
                name = str(item or "").strip()
            name = self._sentence_case_label(name)
            key = self._normalize_text_key(name)
            if not name or not key or key in seen:
                continue
            seen.add(key)
            selected.append(name)
            if len(selected) >= max(1, int(max_items or 1)):
                break
        return selected

    def _summary_text_signature(self, value: Any) -> frozenset[str]:
        short_allowed = {
            "ai",
            "ml",
            "qa",
            "ui",
            "ux",
            "bi",
            "ci",
            "cd",
            "db",
            "sql",
            "api",
            "erp",
            "crm",
        }
        tokens = [
            token
            for token in self._normalize_text_key(value).split()
            if len(token) >= 3 or token in short_allowed
        ]
        return frozenset(tokens)

    def _collect_rendered_summary_signatures(
        self,
        formatted_data: Dict[str, Any],
    ) -> List[frozenset[str]]:
        signatures: List[frozenset[str]] = []

        def _append(value: Any) -> None:
            signature = self._summary_text_signature(value)
            if len(signature) >= 2:
                signatures.append(signature)

        for exp in (formatted_data or {}).get("experience") or []:
            if not isinstance(exp, dict):
                continue
            _append(exp.get("title"))
            _append(exp.get("company"))
            for line in exp.get("description") or []:
                _append(line)

        project = (formatted_data or {}).get("featured_project")
        if isinstance(project, dict):
            _append(project.get("name"))
            for line in project.get("description_lines") or []:
                _append(line)

        for cert in (formatted_data or {}).get("featured_certifications") or []:
            if isinstance(cert, dict):
                _append(cert.get("name"))

        return signatures

    def _sentence_overlaps_rendered_content(
        self,
        value: Any,
        signatures: List[frozenset[str]],
    ) -> bool:
        probe = self._summary_text_signature(value)
        if len(probe) < 2:
            return False
        for signature in signatures:
            if not signature:
                continue
            intersection = len(probe & signature)
            if intersection >= max(2, int(len(probe) * 0.7)):
                return True
        return False

    def _group_summary_sentences(self, sentences: List[str]) -> List[str]:
        cleaned: List[str] = []
        seen: set[str] = set()
        for item in sentences or []:
            text = self._normalize_render_text(item)
            key = self._normalize_text_key(text)
            if not text or not key or key in seen:
                continue
            seen.add(key)
            cleaned.append(text)

        if len(cleaned) <= 2:
            return cleaned
        if len(cleaned) == 3:
            return [" ".join(cleaned[:2]), cleaned[2]]
        return [" ".join(cleaned[:2]), " ".join(cleaned[2:4])]

    def _collect_profile_summary_terms(
        self, formatted_data: Dict[str, Any]
    ) -> List[str]:
        terms: List[str] = []
        seen: set[str] = set()
        offer_terms = self._collect_offer_terms_for_render(formatted_data)
        featured_terms = list((formatted_data or {}).get("featured_skills") or [])

        def _append(value: Any) -> None:
            text = self._restore_display_acronyms(self._normalize_render_text(value))
            key = self._normalize_text_key(text)
            if not text or not key or key in seen:
                return
            tokens = key.split()
            if tokens and tokens[0] in {
                "concevoir",
                "executer",
                "maintenir",
                "rediger",
                "suivre",
                "faciliter",
                "proposer",
            }:
                return
            if len(tokens) > 6 and ":" not in text:
                return
            seen.add(key)
            terms.append(text)

        for item in featured_terms:
            text = self._normalize_render_text(item)
            if ":" in text:
                _label, values = text.split(":", 1)
                for part in re.split(r"\s*[·,/]\s*", values):
                    _append(part)
            else:
                _append(text)
        raw_skill_budget = 2 if featured_terms else 6
        raw_skill_reference = (
            featured_terms
            or self._collect_hard_skill_names_for_compact_summary(
                (formatted_data or {}).get("skills")
            )
        )
        for item in self._collect_hard_skill_names_for_compact_summary(
            (formatted_data or {}).get("skills")
        ):
            if raw_skill_budget <= 0:
                break
            if (
                self._score_positioning_terms(
                    [item],
                    offer_terms=offer_terms,
                    profile_terms=raw_skill_reference,
                    rendered_signatures=[],
                )
                < 1.6
            ):
                continue
            _append(item)
            raw_skill_budget -= 1

        for cert in (formatted_data or {}).get("featured_certifications") or []:
            if isinstance(cert, dict):
                _append(cert.get("name"))

        return terms

    def _pick_distinct_summary_candidate(
        self,
        candidates: List[str],
        *,
        rendered_signatures: List[frozenset[str]],
        used_keys: set[str],
    ) -> str:
        while candidates:
            text = self._normalize_render_text(candidates.pop(0))
            key = self._normalize_text_key(text)
            if not text or not key or key in used_keys:
                continue
            if self._sentence_overlaps_rendered_content(text, rendered_signatures):
                continue
            used_keys.add(key)
            return text
        return ""

    def _build_evidence_based_profile_sentence(
        self,
        formatted_data: Dict[str, Any],
        *,
        rendered_signatures: List[frozenset[str]],
    ) -> str:
        is_en = (
            str((formatted_data or {}).get("language") or "").lower().startswith("en")
        )
        if is_en:
            return ""

        role = str((formatted_data or {}).get("job_title") or "").strip()
        entries = [
            item
            for item in (formatted_data or {}).get("experience") or []
            if isinstance(item, dict)
        ]
        anchor = next(
            (
                item
                for item in entries
                if item.get("render_role_priority") == "anchor"
            ),
            entries[0] if entries else None,
        )

        evidence_parts: List[str] = [role]
        for skill in self._collect_hard_skill_names_for_compact_summary(
            (formatted_data or {}).get("skills")
        ):
            evidence_parts.append(skill)
        for entry in (formatted_data or {}).get("experience_all") or entries:
            if not isinstance(entry, dict):
                continue
            evidence_parts.extend(
                [
                    str(entry.get("title") or ""),
                    str(entry.get("company") or ""),
                    " ".join(
                        str(line)
                        for line in (
                            entry.get("_render_source_description")
                            or entry.get("description")
                            or []
                        )
                        if isinstance(line, str)
                    ),
                ]
            )
        for project in (formatted_data or {}).get("projects") or []:
            if isinstance(project, dict):
                evidence_parts.extend(
                    [
                        str(project.get("name") or ""),
                        str(project.get("description") or ""),
                        str(project.get("technologies") or ""),
                    ]
                )
        offer_probe = self._normalize_match_probe(
            " ".join([role, *self._collect_offer_terms_for_render(formatted_data)])
        )
        evidence_probe = self._normalize_match_probe(" ".join(evidence_parts))

        qa_context = any(
            self._match_probe_contains_term(" ".join([offer_probe, evidence_probe]), marker)
            for marker in ("qa", "quality", "test", "testing", "recette")
        )
        if not qa_context:
            return ""

        def has(marker: str) -> bool:
            return self._match_probe_contains_term(evidence_probe, marker)

        def offer_has(marker: str) -> bool:
            return self._match_probe_contains_term(offer_probe, marker)

        role_label = "QA Engineer" if has("qa") or offer_has("qa") else (role or "Profil QA")
        if "altern" in self._normalize_text_key(anchor.get("title") if anchor else ""):
            role_label = f"{role_label} en alternance"

        duration_text = ""
        if isinstance(anchor, dict):
            duration = str(anchor.get("duration") or "").strip()
            match = re.search(r"(\d+)\s+ans?", duration)
            if match and int(match.group(1)) >= 1:
                duration_text = f" avec plus de {match.group(1)} ans d'expérience"

        scope_chunks: List[str] = []
        if has("plan de test") or has("plans de test"):
            scope_chunks.append("la conception de plans de test")
        testing_types: List[str] = []
        if has("fonctionnel") or offer_has("functional testing"):
            testing_types.append("fonctionnels")
        if has("exploratoire") or has("exploratoires") or offer_has("exploratory"):
            testing_types.append("exploratoires")
        if has("non regression") or has("xray") or offer_has("regression"):
            testing_types.append("de non-régression")
        if testing_types:
            if len(testing_types) == 1:
                testing_text = testing_types[0]
            else:
                testing_text = ", ".join(testing_types[:-1]) + f" et {testing_types[-1]}"
            scope_chunks.append(f"les tests {testing_text}")

        scope_text = " et ".join(scope_chunks)
        if has("applications critiques") or has("3 applications"):
            app_context = "sur des applications critiques"
            if has("sante") or has("patient"):
                app_context += " de santé numérique"
            scope_text = f"{scope_text} {app_context}" if scope_text else app_context

        second_parts: List[str] = []
        if has("api") or has("postman"):
            second_parts.append("tests API")
        if has("sql") or has("postgresql") or has("mongodb") or has("sql server"):
            second_parts.append("vérifications SQL et bases de données")
        if has("anomalie") or has("anomalies"):
            second_parts.append("qualification d'anomalies")
        if has("pratiques qa") or has("documentation") or has("livrable"):
            second_parts.append("structuration de pratiques QA")

        third_parts: List[str] = []
        if has("automatisation") or has("playwright") or has("cypress") or has("selenium"):
            third_parts.append("l'automatisation")
        if (has("ia") or has("ai") or has("poc") or has("agent")) and (
            offer_has("ai") or offer_has("ml") or offer_has("model")
        ):
            third_parts.append("l'évaluation de produits IA")
        if offer_has("edge") or offer_has("cas limite") or has("risque"):
            third_parts.append("l'analyse des cas limites")

        sentences: List[str] = []
        if scope_text:
            sentences.append(f"{role_label}{duration_text} dans {scope_text}.")
        if second_parts:
            sentences.append(f"Expérience en {', '.join(second_parts)}.")
        if third_parts:
            sentences.append(f"Intérêt marqué pour {', '.join(third_parts)}.")

        if not sentences:
            return ""
        return " ".join(sentences[:3])

    def _is_weak_profile_summary_candidate(self, value: Any) -> bool:
        text = self._normalize_text_key(value)
        if not text:
            return True
        weak_markers = (
            "bilan de recette",
            "bilans de recettes",
            "benchmark d outils",
            "outils d automatisations",
            "avec une experience en",
            "avec experience en",
        )
        strong_markers = (
            "test api",
            "tests api",
            "plan de test",
            "plans de test",
            "non regression",
            "postman",
            "xray",
            "jira",
            "anomal",
        )
        return any(marker in text for marker in weak_markers) and not any(
            marker in text for marker in strong_markers
        )

    def _build_summary_profile_sentence(
        self,
        formatted_data: Dict[str, Any],
        *,
        rendered_signatures: List[frozenset[str]],
        used_keys: set[str],
        summary_candidates: List[str],
    ) -> str:
        candidate = self._pick_distinct_summary_candidate(
            summary_candidates,
            rendered_signatures=rendered_signatures,
            used_keys=used_keys,
        )
        evidence_candidate = self._build_evidence_based_profile_sentence(
            formatted_data,
            rendered_signatures=rendered_signatures,
        )
        if evidence_candidate and (
            not candidate or self._is_weak_profile_summary_candidate(candidate)
        ):
            used_keys.add(self._normalize_text_key(evidence_candidate))
            return evidence_candidate
        if candidate:
            return candidate

        is_en = (
            str((formatted_data or {}).get("language") or "").lower().startswith("en")
        )
        role = (
            str((formatted_data or {}).get("job_title") or "").strip()
            or str(
                (((formatted_data or {}).get("experience") or [{}])[0]).get("title")
                or ""
            ).strip()
        )
        skills = [
            skill
            for skill in ((formatted_data or {}).get("featured_skills") or [])
            if not self._sentence_overlaps_rendered_content(skill, rendered_signatures)
        ]
        if not skills:
            skills = list((formatted_data or {}).get("featured_skills") or [])
        skills_text = self._human_join(skills[:4], is_en=is_en)
        if role and skills_text:
            sentence = (
                f"{role} with experience in {skills_text}."
                if is_en
                else f"{role} avec expérience en {skills_text}."
            )
        elif role:
            sentence = role if role.endswith((".", "!", "?")) else f"{role}."
        else:
            sentence = ""
        if sentence:
            used_keys.add(self._normalize_text_key(sentence))
        return sentence

    def _collect_matched_offer_terms_for_experience(
        self,
        exp: Dict[str, Any],
        *,
        offer_terms: List[str],
        excluded_terms: List[str],
    ) -> List[str]:
        if not isinstance(exp, dict):
            return []

        try:
            from ..utils.keyword_alignment import (
                normalize_keyword_for_match,
                normalized_term_in_probe as normalized_term_present,
            )
        except Exception:

            def normalize_keyword_for_match(value):
                return self._normalize_text_key(value)

            def normalized_term_present(probe, term):
                return str(term or "") in str(probe or "")

        parts: List[str] = []
        for key in ("title", "company", "summary", "location"):
            value = exp.get(key)
            if isinstance(value, str) and value.strip():
                parts.append(value.strip())
        for line in exp.get("_render_source_description") or []:
            if isinstance(line, str) and line.strip():
                parts.append(line.strip())
        for tech in exp.get("technologies") or []:
            if isinstance(tech, str) and tech.strip():
                parts.append(tech.strip())

        blob_norm = normalize_keyword_for_match(" ".join(parts))
        rendered_norm = normalize_keyword_for_match(
            " ".join(exp.get("description") or [])
        )
        if not blob_norm:
            return []

        excluded_norms = {
            normalize_keyword_for_match(item)
            for item in (excluded_terms or [])
            if normalize_keyword_for_match(item)
        }
        selected: List[str] = []
        seen: set[str] = set()
        for term in offer_terms or []:
            text = self._normalize_render_text(term)
            norm = normalize_keyword_for_match(text)
            if not text or not norm or norm in seen or norm in excluded_norms:
                continue
            if not normalized_term_present(blob_norm, norm):
                continue
            if rendered_norm and normalized_term_present(rendered_norm, norm):
                continue
            seen.add(norm)
            selected.append(text)
        return selected

    def _build_experience_focus_sentence(
        self,
        exp: Dict[str, Any],
        *,
        label: str,
        offer_terms: List[str],
        rendered_signatures: List[frozenset[str]],
        used_keys: set[str],
        language_code: str,
    ) -> str:
        if not isinstance(exp, dict):
            return ""

        is_en = str(language_code or "").lower().startswith("en")
        title = str(exp.get("title") or "").strip()
        company = str(exp.get("company") or "").strip()
        matched_terms = self._collect_matched_offer_terms_for_experience(
            exp,
            offer_terms=offer_terms,
            excluded_terms=list(used_keys),
        )
        matched_terms = [
            term
            for term in matched_terms
            if not self._sentence_overlaps_rendered_content(term, rendered_signatures)
        ]
        terms_text = self._human_join(matched_terms[:4], is_en=is_en)

        if label == "recent":
            prefix = (
                "Recent complementary experience"
                if is_en
                else "Expérience récente complémentaire"
            )
        else:
            prefix = "Most aligned experience" if is_en else "Expérience la plus alignée"

        head = title
        if company:
            head = (
                f"{title} at {company}"
                if is_en and title
                else f"{title} chez {company}" if title else company
            )

        if not head:
            return ""

        if terms_text:
            sentence = (
                f"{prefix}: {head}, centered on {terms_text}."
                if is_en
                else f"{prefix} : {head}, avec un positionnement sur {terms_text}."
            )
        else:
            sentence = f"{prefix}: {head}." if is_en else f"{prefix} : {head}."

        key = self._normalize_text_key(sentence)
        if not key or key in used_keys:
            return ""
        used_keys.add(key)
        return sentence

    def _build_targeted_summary_sentence(
        self,
        formatted_data: Dict[str, Any],
        *,
        rendered_signatures: List[frozenset[str]],
        used_keys: set[str],
    ) -> str:
        is_en = (
            str((formatted_data or {}).get("language") or "").lower().startswith("en")
        )
        company = self._restore_display_acronyms(
            (formatted_data or {}).get("company") or ""
        )
        job_title = str((formatted_data or {}).get("job_title") or "").strip()
        existing = self._normalize_render_text(
            (formatted_data or {}).get("profile_positioning_sentence") or ""
        )

        max_total_terms = 6
        max_common_terms = 4
        max_profile_extra_terms = 3
        max_offer_only_terms = 2

        try:
            from ..utils.cv_summary_adaptation import collect_targeted_offer_terms
        except Exception:
            collect_targeted_offer_terms = None

        offer_terms = self._collect_offer_terms_for_render(formatted_data)
        profile_terms = self._collect_profile_summary_terms(formatted_data)
        profile_norms = [
            self._normalize_text_key(item)
            for item in profile_terms
            if self._normalize_text_key(item)
        ]

        rendered_probe_parts: List[str] = []
        for exp in (formatted_data or {}).get("experience") or []:
            if not isinstance(exp, dict):
                continue
            rendered_probe_parts.extend(
                [
                    str(exp.get("title") or "").strip(),
                    str(exp.get("company") or "").strip(),
                    " ".join(
                        str(line)
                        for line in (exp.get("description") or [])
                        if isinstance(line, str)
                    ),
                ]
            )
        rendered_probe = self._normalize_text_key(" ".join(rendered_probe_parts))

        common_terms_input: List[str] = []
        offer_only_input: List[str] = []
        seen_offer: set[str] = set()
        for term in offer_terms:
            text = self._normalize_render_text(term)
            norm = self._normalize_text_key(text)
            if not text or not norm or norm in seen_offer:
                continue
            seen_offer.add(norm)
            if rendered_probe and norm in rendered_probe:
                continue
            if any(
                norm == item or norm in item or item in norm for item in profile_norms
            ):
                common_terms_input.append(text)
            else:
                offer_only_input.append(text)

        excluded_terms = list(used_keys)
        common_terms = (
            collect_targeted_offer_terms(
                common_terms_input,
                profile_json=formatted_data,
                max_terms=min(max_common_terms, max_total_terms),
                excluded_terms=excluded_terms,
                job_title=job_title,
            )
            if collect_targeted_offer_terms and common_terms_input
            else []
        )

        selected_norms = {self._normalize_text_key(item) for item in common_terms}
        profile_extra_terms: List[str] = []
        remaining_budget = max(0, max_total_terms - len(common_terms))
        for item in profile_terms:
            if (
                remaining_budget <= 0
                or len(profile_extra_terms) >= max_profile_extra_terms
            ):
                break
            text = self._normalize_render_text(item)
            norm = self._normalize_text_key(text)
            if not text or not norm or norm in selected_norms or norm in used_keys:
                continue
            if rendered_probe and norm in rendered_probe:
                continue
            if self._sentence_overlaps_rendered_content(text, rendered_signatures):
                continue
            selected_norms.add(norm)
            profile_extra_terms.append(text)
            remaining_budget -= 1

        offer_only_budget = min(
            max_offer_only_terms,
            max(0, max_total_terms - len(common_terms) - len(profile_extra_terms)),
        )

        offer_only_terms = (
            collect_targeted_offer_terms(
                offer_only_input,
                profile_json=formatted_data,
                max_terms=max(1, offer_only_budget),
                excluded_terms=excluded_terms + common_terms + profile_extra_terms,
                job_title=job_title,
            )
            if collect_targeted_offer_terms
            and offer_only_input
            and offer_only_budget > 0
            else []
        )
        common_terms = [
            self._restore_display_acronyms(item)
            for item in common_terms
            if self._normalize_render_text(item)
        ]
        profile_extra_terms = [
            self._restore_display_acronyms(item)
            for item in profile_extra_terms
            if self._normalize_render_text(item)
        ]
        offer_only_terms = [
            self._restore_display_acronyms(item)
            for item in offer_only_terms
            if self._normalize_render_text(item)
        ]

        def keep_positioning_term(value: Any) -> bool:
            norm = self._normalize_text_key(value)
            if not norm:
                return False
            tokens = norm.split()
            if tokens and tokens[0] in {
                "concevoir",
                "executer",
                "maintenir",
                "rediger",
                "suivre",
                "faciliter",
                "proposer",
            }:
                return False
            return len(tokens) <= 5 or any(
                marker in norm
                for marker in (
                    "playwright",
                    "cypress",
                    "selenium",
                    "agilitest",
                    "postgresql",
                    "mongodb",
                    "sql server",
                )
            )

        common_terms = [item for item in common_terms if keep_positioning_term(item)]
        profile_extra_terms = [
            item for item in profile_extra_terms if keep_positioning_term(item)
        ]
        offer_only_terms = [
            item for item in offer_only_terms if keep_positioning_term(item)
        ]

        def join_positioning_terms(values: List[str]) -> str:
            cleaned_values: List[str] = []
            seen_values: set[str] = set()
            for value in values or []:
                text = self._restore_display_acronyms(
                    self._normalize_render_text(value)
                )
                key = self._normalize_text_key(text)
                if not text or not key or key in seen_values:
                    continue
                seen_values.add(key)
                cleaned_values.append(text)
            if not cleaned_values:
                return ""
            if len(cleaned_values) == 1:
                return cleaned_values[0]
            return ", ".join(cleaned_values[:-1]) + (
                f" and {cleaned_values[-1]}" if is_en else f" et {cleaned_values[-1]}"
            )

        def natural_positioning_sentence(
            values: List[str],
            *,
            company_name: str = "",
            role_name: str = "",
        ) -> str:
            terms_text = join_positioning_terms(values)
            if not terms_text:
                return ""
            if is_en:
                if company_name and role_name:
                    return (
                        f"For {company_name}, this profile targets the {role_name} "
                        f"role with positioning around {terms_text}."
                    )
                if company_name:
                    return (
                        f"For {company_name}, this profile highlights relevant "
                        f"positioning around {terms_text}."
                    )
                return f"This profile highlights relevant positioning around {terms_text}."
            if company_name and role_name:
                return (
                    f"Pour {company_name}, ce profil cible le poste de {role_name} "
                    f"avec un positionnement autour de {terms_text}."
                )
            if company_name:
                return (
                    f"Pour {company_name}, ce profil met en avant un positionnement "
                    f"pertinent autour de {terms_text}."
                )
            return (
                f"Ce profil met en avant un positionnement pertinent autour de "
                f"{terms_text}."
            )

        candidate_terms = common_terms + profile_extra_terms + offer_only_terms
        candidate_sentence = natural_positioning_sentence(
            candidate_terms,
            company_name=company,
            role_name=job_title,
        )

        sentence = ""
        if existing:
            existing_company, existing_terms = self._parse_positioning_sentence(
                existing, is_en=is_en
            )
            if existing_terms:
                normalized_existing = natural_positioning_sentence(
                    existing_terms,
                    company_name=existing_company or company,
                    role_name=job_title,
                )
                existing_score = self._score_positioning_terms(
                    existing_terms,
                    offer_terms=offer_terms,
                    profile_terms=profile_terms,
                    rendered_signatures=rendered_signatures,
                )
                candidate_score = self._score_positioning_terms(
                    candidate_terms,
                    offer_terms=offer_terms,
                    profile_terms=profile_terms,
                    rendered_signatures=rendered_signatures,
                )
                overlap = len(
                    {
                        self._normalize_text_key(item)
                        for item in existing_terms
                        if self._normalize_text_key(item)
                    }
                    & {
                        self._normalize_text_key(item)
                        for item in candidate_terms
                        if self._normalize_text_key(item)
                    }
                )
                if (
                    not candidate_terms
                    or existing_score >= candidate_score
                    or (overlap >= 1 and existing_score >= (candidate_score - 0.6))
                ):
                    sentence = normalized_existing
        if not sentence and candidate_sentence:
            sentence = candidate_sentence
        elif not sentence and company and job_title:
            sentence = (
                f"For {company}, this profile targets the {job_title} role."
                if is_en
                else f"Pour {company}, ce profil cible le poste de {job_title}."
            )

        key = self._normalize_text_key(sentence)
        if sentence and key and key not in used_keys:
            used_keys.add(key)
            return sentence
        return ""

    def _build_summary_complement_sentence(
        self,
        formatted_data: Dict[str, Any],
        *,
        rendered_signatures: List[frozenset[str]],
        used_keys: set[str],
        summary_candidates: List[str],
    ) -> str:
        candidate = self._pick_distinct_summary_candidate(
            summary_candidates,
            rendered_signatures=rendered_signatures,
            used_keys=used_keys,
        )
        if candidate:
            return candidate

        is_en = (
            str((formatted_data or {}).get("language") or "").lower().startswith("en")
        )
        certifications = [
            str(cert.get("name") or "").strip()
            for cert in ((formatted_data or {}).get("featured_certifications") or [])
            if isinstance(cert, dict) and str(cert.get("name") or "").strip()
        ]
        certifications = [
            item
            for item in certifications
            if not self._sentence_overlaps_rendered_content(item, rendered_signatures)
        ]
        if certifications:
            joined = self._human_join(certifications[:3], is_en=is_en)
            sentence = (
                f"Additional credentials include {joined}."
                if is_en
                else f"Reperes complementaires : {joined}."
            )
            used_keys.add(self._normalize_text_key(sentence))
            return sentence

        project = (formatted_data or {}).get("featured_project")
        if isinstance(project, dict) and str(project.get("name") or "").strip():
            name = str(project.get("name") or "").strip()
            techs = [
                tech
                for tech in (project.get("technologies") or [])
                if not self._sentence_overlaps_rendered_content(
                    tech, rendered_signatures
                )
            ]
            if techs:
                tech_text = self._human_join(techs[:4], is_en=is_en)
                sentence = (
                    f"Highlighted project: {name}, with {tech_text}."
                    if is_en
                    else f"Projet mis en avant : {name}, avec {tech_text}."
                )
            else:
                sentence = (
                    f"Highlighted project: {name}."
                    if is_en
                    else f"Projet mis en avant : {name}."
                )
            used_keys.add(self._normalize_text_key(sentence))
            return sentence

        return ""

    def _build_summary_fallback_lines(
        self, formatted_data: Dict[str, Any]
    ) -> List[str]:
        is_en = (
            str((formatted_data or {}).get("language") or "").lower().startswith("en")
        )
        role = (
            str((formatted_data or {}).get("job_title") or "").strip()
            or str(
                ((formatted_data or {}).get("experience_all") or [{}])[0].get("title")
                or ""
            ).strip()
        )
        skills = list((formatted_data or {}).get("featured_skills") or [])[:3]

        lines: List[str] = []
        if role and skills:
            skills_text = self._human_join(skills, is_en=is_en)
            if skills_text:
                if is_en:
                    lines.append(f"{role} with experience in {skills_text}.")
                else:
                    lines.append(f"{role} avec expérience en {skills_text}.")
        elif role:
            lines.append(role if role.endswith((".", "!", "?")) else f"{role}.")

        for exp in (formatted_data or {}).get("experience_all") or []:
            if not isinstance(exp, dict):
                continue
            for candidate in exp.get("description") or []:
                text = self._normalize_render_text(candidate)
                if self._word_count(text) < 4:
                    continue
                if lines and self._normalize_text_key(text) == self._normalize_text_key(
                    lines[0]
                ):
                    continue
                if len(text) > 220:
                    continue
                if not text.endswith((".", "!", "?")):
                    text += "."
                lines.append(text)
                return lines[:2]

        return lines[:2]

    def _build_render_summary_lines(self, formatted_data: Dict[str, Any]) -> List[str]:
        language_code = str((formatted_data or {}).get("language") or "fr")
        is_en = language_code.lower().startswith("en")
        summary = str((formatted_data or {}).get("profile_summary") or "").strip()
        summary_sentences = [
            sentence
            for sentence in self._split_sentences(summary)
            if not self._is_positioning_sentence(sentence, is_en=is_en)
        ]
        rendered_signatures = self._collect_rendered_summary_signatures(formatted_data)
        used_keys: set[str] = set()
        lines: List[str] = []

        profile_sentence = self._build_summary_profile_sentence(
            formatted_data,
            rendered_signatures=rendered_signatures,
            used_keys=used_keys,
            summary_candidates=summary_sentences,
        )
        if profile_sentence:
            lines.append(profile_sentence)

        experience_entries = [
            item
            for item in ((formatted_data or {}).get("experience") or [])
            if isinstance(item, dict)
        ]
        offer_terms = self._collect_offer_terms_for_render(formatted_data)
        anchor_exp = (
            sorted(
                experience_entries,
                key=lambda item: float(item.get("render_alignment_score") or 0.0),
                reverse=True,
            )[0]
            if experience_entries
            else None
        )
        recent_exp = None
        if experience_entries:
            recent_exp = sorted(
                experience_entries,
                key=self._experience_recency_rank,
                reverse=True,
            )[0]

        profile_norm = self._normalize_text_key(profile_sentence)
        if not (
            profile_norm
            and (
                "applications critiques" in profile_norm
                or "experience en tests api" in profile_norm
            )
        ):
            anchor_sentence = self._build_experience_focus_sentence(
                anchor_exp,
                label="anchor",
                offer_terms=offer_terms,
                rendered_signatures=rendered_signatures,
                used_keys=used_keys,
                language_code=language_code,
            )
            if anchor_sentence:
                lines.append(anchor_sentence)

        targeted_sentence = self._build_targeted_summary_sentence(
            formatted_data,
            rendered_signatures=rendered_signatures,
            used_keys=used_keys,
        )
        if targeted_sentence:
            lines.append(targeted_sentence)

        if recent_exp is not None and recent_exp is not anchor_exp:
            recent_sentence = self._build_experience_focus_sentence(
                recent_exp,
                label="recent",
                offer_terms=offer_terms,
                rendered_signatures=rendered_signatures,
                used_keys=used_keys,
                language_code=language_code,
            )
            if recent_sentence:
                lines.append(recent_sentence)

        if len(lines) < 4:
            complement = self._build_summary_complement_sentence(
                formatted_data,
                rendered_signatures=rendered_signatures,
                used_keys=used_keys,
                summary_candidates=summary_sentences,
            )
            if complement:
                lines.append(complement)

        grouped = self._group_summary_sentences(lines[:4])
        if grouped:
            return grouped

        return self._build_summary_fallback_lines(formatted_data)

    def _split_technologies(self, value: Any, *, max_items: int = 4) -> List[str]:
        raw = str(value or "").strip()
        if not raw:
            return []
        items = [
            item.strip() for item in re.split(r"\s*(?:,|;|\|)\s*", raw) if item.strip()
        ]
        deduped: List[str] = []
        seen: set[str] = set()
        for item in items:
            key = self._normalize_text_key(item)
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(item)
            if len(deduped) >= max(1, int(max_items or 1)):
                break
        return deduped

    def _build_featured_project(self, projects: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(projects, list):
            return None
        candidates = [
            item
            for item in projects
            if isinstance(item, dict) and str(item.get("name") or "").strip()
        ]
        if not candidates:
            return None

        def _score(project: Dict[str, Any]) -> int:
            return sum(
                1
                for field in ("description", "technologies", "url", "duration")
                if str(project.get(field) or "").strip()
            )

        best = sorted(candidates, key=_score, reverse=True)[0]
        description_lines = self._select_whole_sentences(
            self._split_sentences(best.get("description") or ""),
            max_items=2,
            char_budget=280,
        )
        return {
            "name": str(best.get("name") or "").strip(),
            "duration": str(best.get("duration") or "").strip(),
            "url": str(best.get("url") or "").strip(),
            "technologies": self._split_technologies(
                best.get("technologies") or "", max_items=4
            ),
            "description_lines": description_lines,
        }

    def _build_featured_certifications(
        self,
        certifications: Any,
        *,
        max_items: int = 2,
    ) -> List[Dict[str, str]]:
        if not isinstance(certifications, list):
            return []
        featured: List[Dict[str, str]] = []
        for cert in certifications:
            if not isinstance(cert, dict):
                continue
            name = str(cert.get("name") or "").strip()
            if not name:
                continue
            featured.append(
                {
                    "name": name,
                    "organization": str(cert.get("organization") or "").strip(),
                    "date": str(cert.get("date") or "").strip(),
                    "url": str(cert.get("url") or "").strip(),
                }
            )
            if len(featured) >= max(1, int(max_items or 1)):
                break
        return featured

    def _compact_experience_entries(
        self,
        experiences: Any,
        *,
        job_title: str,
        offer_terms: List[str],
        language_code: str,
        max_roles: int,
        max_bullets: int,
    ) -> List[Dict[str, Any]]:
        if not isinstance(experiences, list):
            return []
        ranked_experiences, scored_rows = self._rank_experiences_for_render(
            [item for item in experiences if isinstance(item, dict)],
            job_title=job_title,
            offer_terms=offer_terms,
        )
        ranked_keys = [
            self._experience_identity_key(item) for item in ranked_experiences
        ]
        score_by_key = {
            self._experience_identity_key(item): float(score)
            for score, _recency, _position, _info_units, item in scored_rows
            if isinstance(item, dict)
        }
        info_units_by_key = {
            self._experience_identity_key(item): int(info_units or 1)
            for _score, _recency, _position, info_units, item in scored_rows
            if isinstance(item, dict)
        }
        max_roles_limit = max(1, int(max_roles or 1))
        most_recent_key = ""
        if ranked_experiences:
            most_recent_exp = sorted(
                ranked_experiences,
                key=self._experience_recency_rank,
                reverse=True,
            )[0]
            most_recent_key = self._experience_identity_key(most_recent_exp)
        anchor_key = ranked_keys[0] if ranked_keys else ""

        render_candidates = [item for item in experiences if isinstance(item, dict)]
        if len(render_candidates) > max_roles_limit:
            selected_candidates = list(render_candidates[:max_roles_limit])
            selected_keys = [
                self._experience_identity_key(item) for item in selected_candidates
            ]
            if anchor_key and anchor_key not in selected_keys:
                drop_index = len(selected_candidates) - 1
                for idx in range(len(selected_candidates) - 1, -1, -1):
                    candidate_key = selected_keys[idx]
                    if candidate_key != anchor_key:
                        drop_index = idx
                        if candidate_key != most_recent_key:
                            break
                selected_candidates.pop(drop_index)
                anchor_candidate = next(
                    (
                        item
                        for item in render_candidates
                        if self._experience_identity_key(item) == anchor_key
                    ),
                    None,
                )
                if anchor_candidate is not None:
                    selected_candidates.append(anchor_candidate)
                selected_key_set = {
                    self._experience_identity_key(item)
                    for item in selected_candidates
                    if isinstance(item, dict)
                }
                render_candidates = [
                    item
                    for item in render_candidates
                    if self._experience_identity_key(item) in selected_key_set
                ]
            else:
                render_candidates = selected_candidates

        compacted: List[Dict[str, Any]] = []
        for exp in render_candidates:
            if not isinstance(exp, dict):
                continue
            entry = dict(exp)
            exp_key = self._experience_identity_key(entry)
            source_description = [
                self._normalize_render_text(item)
                for item in (entry.get("description") or [])
                if self._normalize_render_text(item)
            ]
            entry["_render_source_description"] = source_description
            role_budget = max(1, int(max_bullets or 1))
            exp_score = float(score_by_key.get(exp_key) or 0.0)
            info_units = int(info_units_by_key.get(exp_key) or 1)
            if ranked_keys and exp_key == ranked_keys[0]:
                role_budget = 4 if (len(source_description) >= 7 or info_units >= 7) else max(role_budget, 3)
            elif most_recent_key and exp_key == most_recent_key:
                role_budget = 2
            elif len(compacted) >= 2:
                role_budget = 2
            else:
                role_budget = min(role_budget, 2)

            selected_description = self._select_experience_render_lines(
                entry.get("description") or [],
                company=str(entry.get("company") or "").strip(),
                job_title=job_title,
                offer_terms=offer_terms,
                language_code=language_code,
                max_items=role_budget,
            )
            entry["description"] = self._ensure_named_tool_evidence_lines(
                selected_description,
                source_description,
                max_items=role_budget,
            )
            entry["render_alignment_score"] = exp_score
            entry["render_role_priority"] = (
                "anchor"
                if ranked_keys and exp_key == ranked_keys[0]
                else (
                    "recent"
                    if most_recent_key and exp_key == most_recent_key
                    else "support"
                )
            )
            entry["render_detail_budget"] = role_budget
            compacted.append(entry)
        return compacted

    def _compact_education_entries(
        self,
        education: Any,
        *,
        max_items: int,
    ) -> List[Dict[str, Any]]:
        if not isinstance(education, list):
            return []
        compacted: List[Dict[str, Any]] = []
        for entry in education:
            if not isinstance(entry, dict):
                continue
            item = dict(entry)
            for key in ("degree", "school", "institution", "field_of_study"):
                if key in item:
                    item[key] = self._normalize_render_text(item.get(key))
            details = []
            for line in item.get("description") or []:
                text = self._normalize_render_text(line)
                if not text:
                    continue
                if len(text) > 160 and details:
                    continue
                details.append(text)
                if len(details) >= 1:
                    break
            item["description"] = details[:1]
            compacted.append(item)
            if len(compacted) >= max(1, int(max_items or 1)):
                break
        return compacted

    def _compact_language_entries(
        self,
        languages: Any,
        *,
        max_items: int,
    ) -> List[Dict[str, Any]]:
        if not isinstance(languages, list):
            return []
        compacted: List[Dict[str, Any]] = []
        for entry in languages:
            if not isinstance(entry, dict):
                continue
            compacted.append(
                {
                    "name": str(entry.get("name") or "").strip(),
                    "level": str(entry.get("level") or "").strip(),
                }
            )
            if len(compacted) >= max(1, int(max_items or 1)):
                break
        return compacted

    def save_html(self, html_content: str, output_path: Optional[str] = None) -> str:
        """Sauvegarde le HTML."""
        if output_path is None:
            output_path = tempfile.mktemp(suffix=".html")

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, "w", encoding="utf-8") as f:
            f.write(html_content)

        logger.info(f"HTML sauvegardé : {output_file}")
        return str(output_file)

    def generate_pdf(
        self,
        html_content: str,
        template: str,
        output_path: Optional[str] = None,
        use_css_file: bool = True,
    ) -> str:
        """Génère un PDF à partir du HTML."""
        if not _check_weasyprint():
            raise RuntimeError("WeasyPrint n'est pas disponible pour l'export PDF")

        try:
            # Import local pour éviter les erreurs multiples
            from weasyprint import HTML, CSS

            if output_path is None:
                output_path = tempfile.mktemp(suffix=".pdf")

            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)

            # Créer l'objet HTML avec le CSS
            html_doc = HTML(string=html_content, base_url=str(self.templates_dir))

            # Ajouter le CSS si disponible
            css_objects = []
            if use_css_file:
                css_file = self.css_dir / f"{template}.css"
                if css_file.exists():
                    css_objects.append(CSS(filename=str(css_file)))
            css_objects.append(CSS(string=PDF_ONE_PAGE_FIT_CSS))

            # Générer le PDF
            html_doc.write_pdf(str(output_file), stylesheets=css_objects)

            logger.info(f"PDF généré : {output_file}")
            return str(output_file)

        except Exception as e:
            logger.error(f"Erreur génération PDF : {e}")
            raise

    def get_available_templates(self) -> list:
        """Retourne la liste des templates disponibles."""
        templates = []

        for file in self.cv_templates_dir.glob("*.html"):
            template_name = file.stem
            css_file = self.css_dir / f"{template_name}.css"

            templates.append(
                {
                    "name": template_name,
                    "title": template_name.title(),
                    "html_file": str(file),
                    "css_file": str(css_file) if css_file.exists() else None,
                    "preview_available": (
                        self.templates_dir / "previews" / f"{template_name}.png"
                    ).exists(),
                }
            )

        return templates

    def validate_cv_data(self, cv_data: Dict[str, Any]) -> Dict[str, Any]:
        """Valide et nettoie les données CV."""
        errors = []
        warnings = []

        # Vérifications obligatoires
        if not cv_data.get("name"):
            errors.append("Le nom est obligatoire")

        if not cv_data.get("email"):
            warnings.append("Email non spécifié")

        # Validation format email
        if cv_data.get("email"):
            import re

            email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
            if not re.match(email_pattern, cv_data["email"]):
                warnings.append("Format email invalide")

        # Validation des listes
        list_fields = ["experience", "education", "skills", "projects"]
        for field in list_fields:
            if field in cv_data and not isinstance(cv_data[field], list):
                warnings.append(f"Le champ {field} devrait être une liste")

        return {"errors": errors, "warnings": warnings, "valid": len(errors) == 0}

    def check_pdf_support(self) -> Dict[str, Any]:
        """Vérifie le support PDF et donne des conseils."""
        return {
            "pdf_available": _check_weasyprint(),
            "fallback_format": "html",
            "install_instructions": {
                "windows": [
                    "Installer GTK3 Runtime: https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer",
                    "Ou utiliser: pip install --find-links https://github.com/Kozea/WeasyPrint/releases weasyprint",
                    "Ou temporairement: exporter en HTML puis convertir en ligne",
                ],
                "alternative": "Utiliser un convertisseur en ligne HTML -> PDF",
            },
        }

    def create_sample_cv_data(self) -> Dict[str, Any]:
        """Crée des données d'exemple pour tester les templates."""
        return {
            "name": "Jean Dupont",
            "email": "contact_placeholder",
            "phone": "+33 6 12 34 56 78",
            "linkedin_url": "https://linkedin.com/in/jean-dupont",
            "location": "Paris, France",
            "job_title": "Développeur Full-Stack",
            "profile_summary": "Développeur passionné avec 5 ans d'expérience en développement web. Spécialisé en React, Node.js et Python. Toujours à la recherche de nouveaux défis techniques.",
            "experience": [
                {
                    "title": "Développeur Senior Full-Stack",
                    "company": "TechCorp",
                    "location": "Paris",
                    "start_date": "2022",
                    "end_date": None,
                    "description": [
                        "Développement d'applications web avec React et Node.js",
                        "Architecture et conception de bases de données",
                        "Encadrement d'une équipe de 3 développeurs juniors",
                        "Mise en place de CI/CD avec GitLab",
                    ],
                    "technologies": ["React", "Node.js", "PostgreSQL", "Docker"],
                },
                {
                    "title": "Développeur Full-Stack",
                    "company": "StartupXYZ",
                    "location": "Lyon",
                    "start_date": "2020",
                    "end_date": "2022",
                    "description": [
                        "Développement de l'MVP de l'application principale",
                        "Intégration d'APIs externes",
                        "Optimisation des performances front-end",
                    ],
                    "technologies": ["Vue.js", "Express", "MongoDB"],
                },
            ],
            "education": [
                {
                    "degree": "Master en Informatique",
                    "institution": "Ecole Polytechnique",
                    "location": "Palaiseau",
                    "year": "2020",
                    "grade": "Mention Bien",
                },
                {
                    "degree": "Licence Informatique",
                    "institution": "Université Paris-Saclay",
                    "location": "Saclay",
                    "year": "2018",
                },
            ],
            "skills": [
                {
                    "category": "Langages",
                    "skills_list": [
                        {"name": "JavaScript", "level": 90},
                        {"name": "Python", "level": 85},
                        {"name": "TypeScript", "level": 80},
                        {"name": "Java", "level": 70},
                    ],
                },
                {
                    "category": "Frameworks",
                    "skills_list": [
                        {"name": "React", "level": 90},
                        {"name": "Node.js", "level": 85},
                        {"name": "Vue.js", "level": 75},
                        {"name": "Django", "level": 70},
                    ],
                },
                {
                    "category": "Outils",
                    "skills_list": [
                        {"name": "Git", "level": 95},
                        {"name": "Docker", "level": 80},
                        {"name": "AWS", "level": 75},
                    ],
                },
            ],
            "languages": [
                {"name": "Français", "level": "Natif"},
                {"name": "Anglais", "level": "Professionnel"},
                {"name": "Espagnol", "level": "Intermédiaire"},
            ],
            "projects": [
                {
                    "name": "E-commerce Platform",
                    "description": "Plateforme e-commerce complète avec paiement en ligne et gestion des stocks",
                    "url": "https://github.com/jean/ecommerce",
                    "technologies": ["React", "Node.js", "Stripe", "MongoDB"],
                },
                {
                    "name": "Task Manager App",
                    "description": "Application de gestion de tâches collaborative avec notifications en temps réel",
                    "technologies": ["Vue.js", "Express", "Socket.io", "PostgreSQL"],
                },
            ],
            "certifications": [
                {
                    "name": "AWS Certified Developer",
                    "issuer": "Amazon Web Services",
                    "date": "2023",
                    "credential_id": "AWS-CDA-123456",
                },
                {
                    "name": "Scrum Master Certified",
                    "issuer": "Scrum Alliance",
                    "date": "2022",
                },
            ],
            "interests": [
                "Open Source",
                "Intelligence Artificielle",
                "Blockchain",
                "Escalade",
                "Photographie",
                "Voyages",
            ],
        }
