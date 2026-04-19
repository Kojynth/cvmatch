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
            loader=FileSystemLoader([
                str(self.cv_templates_dir),
                str(self.templates_dir)
            ]),
            autoescape=True
        )
        
        # Ajouter des filtres personnalisés
        self.jinja_env.filters['rjust'] = self._filter_rjust
        self.jinja_env.filters['ljust'] = self._filter_ljust
        
        # Formats supportés
        self.supported_formats = ['html']
        if _check_weasyprint():
            self.supported_formats.append('pdf')
    
    def _filter_rjust(self, value, width, fillchar=' '):
        """Filtre Jinja2 pour rjust (alignement à droite)."""
        return str(value).rjust(int(width), str(fillchar))
    
    def _filter_ljust(self, value, width, fillchar=' '):
        """Filtre Jinja2 pour ljust (alignement à gauche)."""
        return str(value).ljust(int(width), str(fillchar))
    
    def export_cv(
        self, 
        cv_data: Dict[str, Any], 
        template: str = "modern", 
        output_format: str = "html",  # Changé par défaut
        output_path: Optional[str] = None
    ) -> str:
        """Exporte un CV dans le format spécifié."""
        
        if output_format not in self.supported_formats:
            available_formats = ", ".join(self.supported_formats)
            raise ValueError(f"Format {output_format} non supporté. Formats disponibles: {available_formats}")
        
        # Génération HTML
        html_content = self.generate_html(cv_data, template)
        
        if output_format == "html":
            return self.save_html(html_content, output_path)
        elif output_format == "pdf":
            if not _check_weasyprint():
                # Fallback vers HTML si PDF non disponible
                logger.warning("Export PDF demandé mais WeasyPrint non disponible - Export en HTML")
                return self.save_html(html_content, output_path.replace('.pdf', '.html') if output_path else None)
            return self.generate_pdf(html_content, template, output_path)
    
    def generate_html(self, cv_data: Dict[str, Any], template: str, is_fallback: bool = False) -> str:
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
            "job_title": "",
            "profile_summary": "",
            "experience": [],
            "education": [],
            "skills": [],
            "languages": [],
            "projects": [],
            "certifications": [],
            "interests": [],
            "labels": {},
            "language": "fr",
            "photo_base64": "",
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
            "experience": "Experience" if is_en else "Experience",
            "additional_relevant": "Additional relevant details" if is_en else "Éléments complémentaires pertinents",
            "skills": "Skills" if is_en else "Compétences",
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
            skills_label = (formatted_data.get("labels") or {}).get("skills") or "Skills"
            if skills_data is not None and isinstance(skills_data, list):
                formatted_data["skills"] = self.format_skills(skills_data, default_category=skills_label)
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
                primary_experience, additional_relevant_items = self._split_experience_for_render(
                    normalized_experience,
                    job_title=job_title_hint,
                    offer_terms=offer_terms,
                    primary_count=None,
                )
                formatted_data["experience_all"] = normalized_experience
                formatted_data["experience"] = primary_experience
                formatted_data["experience_primary"] = primary_experience
                formatted_data["additional_relevant_items"] = additional_relevant_items
                formatted_data["experience_top_n"] = len(primary_experience)
                formatted_data["additional_relevant_summary"] = self._build_additional_relevant_summary(
                    additional_relevant_items,
                    formatted_data,
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

        try:
            education_data = formatted_data.get("education")
            if education_data is not None and isinstance(education_data, list):
                formatted_data["education"] = self._sort_entries_by_recency(education_data)
            elif education_data is None:
                formatted_data["education"] = []
        except Exception as e:
            logger.warning(f"Erreur tri education: {e}")
            formatted_data["education"] = formatted_data.get("education") or []
        
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
                return replacements.get(lowered, text or str(default_category or "Skills"))

            def _is_soft_category_label(label: Any) -> bool:
                lowered = _normalize_text_key(label)
                return lowered in {"qualites", "qualites personnelles", "soft skills", "soft skill"}

            def _is_low_value_soft_skill(name: Any, *, category_label: Any) -> bool:
                if not _is_soft_category_label(category_label):
                    return False
                normalized = _normalize_text_key(name)
                if not normalized:
                    return True
                return normalized in _LOW_VALUE_SOFT_SKILL_KEYS

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
                return [
                    {
                        "category": _normalize_category_label(default_category),
                        "skills_list": [
                            {"name": skill, "level": None}
                            for skill in cleaned_simple_skills
                        ],
                    }
                ] if cleaned_simple_skills else []

            normalized = []
            seen_global_items = set()
            for block in skills:
                if isinstance(block, dict):
                    category_label = _normalize_category_label(block.get("category") or default_category)
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
                                and not _is_low_value_soft_skill(cleaned_name, category_label=category_label)
                            ):
                                seen_global_items.add(item_key)
                                filtered_skills_list.append({"name": cleaned_name, "level": level})
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
                            and not _is_low_value_soft_skill(name, category_label=category_label)
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
                            {"category": _normalize_category_label(default_category), "skills_list": []}
                        )
                    normalized[0]["skills_list"].append(
                        {"name": name, "level": None}
                    )

            merged: list = []
            category_index: dict = {}
            for block in normalized:
                category = _normalize_category_label(block.get("category") or default_category)
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
                return output[:4]

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

            def collect_description_lines(text: Any, *, company: str) -> List[str]:
                raw = str(text or "").strip()
                if not raw:
                    return []
                parsed = split_inline_pseudo_bullets(raw)
                candidates = (
                    parsed
                    if parsed
                    else re.split(r"[\r\n]+|(?<=[\.\!\?])\s+", raw)
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
                    cleaned_lines.append(cleaned)
                    if len(cleaned_lines) >= 4:
                        break
                return cleaned_lines

            normalized: List[Dict[str, Any]] = []
            for exp in experience:
                if not isinstance(exp, dict):
                    continue

                entry = dict(exp)
                entry["location"] = normalize_location(entry.get("location") or "")
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
                        and
                        not looks_like_inline_pseudo_bullets(summary_text)
                        and word_count(summary_text) <= 32
                    ):
                        cleaned_summary = polish_line(
                            summary_text,
                            company=company_name,
                        )
                        if cleaned_summary:
                            compact_lines.append(cleaned_summary)
                    elif not has_highlights:
                        cleaned_summary = polish_line(
                            summary_text,
                            company=company_name,
                        )
                        if cleaned_summary:
                            description_lines.insert(0, cleaned_summary)

                if has_highlights:
                    compact_lines.extend(cleaned_highlights[:4])
                else:
                    compact_lines.extend(description_lines[:4])

                dedup_seen = set()
                dedup_desc: List[str] = []
                for line in compact_lines:
                    key = line.lower()
                    if key in dedup_seen:
                        continue
                    dedup_seen.add(key)
                    dedup_desc.append(line)
                    if len(dedup_desc) >= 4:
                        break

                entry["description"] = dedup_desc
                normalized.append(entry)

            return normalized
        except Exception as e:
            logger.error(f"Erreur format_experience: {e}")
            return []

    def _collect_offer_terms_for_render(self, formatted_data: Dict[str, Any]) -> List[str]:
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
            if any(token in text for token in ("present", "current", "actuel", "en cours", "aujourd")):
                return 999912

            def rank_from_yyyy_mm(value: Any) -> int:
                probe = str(value or "").strip()
                match = re.match(r"^(?P<y>\d{4})-(?P<m>0[1-9]|1[0-2])$", probe)
                if not match:
                    return 0
                return int(match.group("y")) * 100 + int(match.group("m"))

            month_map = {
                "jan": 1, "janv": 1, "january": 1, "janvier": 1,
                "feb": 2, "fev": 2, "fevr": 2, "february": 2, "fevrier": 2,
                "mar": 3, "march": 3, "mars": 3,
                "apr": 4, "avr": 4, "april": 4, "avril": 4,
                "may": 5, "mai": 5,
                "jun": 6, "june": 6, "juin": 6,
                "jul": 7, "july": 7, "juil": 7, "juillet": 7,
                "aug": 8, "aou": 8, "aout": 8, "august": 8,
                "sep": 9, "sept": 9, "september": 9, "septembre": 9,
                "oct": 10, "october": 10, "octobre": 10,
                "nov": 11, "november": 11, "novembre": 11,
                "dec": 12, "december": 12, "decembre": 12,
            }

            alpha = re.sub(r"[^a-z]+", " ", text)
            month = 0
            for token in alpha.split():
                if token in month_map:
                    month = month_map[token]
                    break

            # Single source of truth for numeric date formats.
            try:
                from ..rules.date_normalize import normalize_date_span, _normalize_single_date

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
                    return int(iso_yyyy_mm_dd.group("y")) * 100 + int(iso_yyyy_mm_dd.group("m"))

                iso_yyyy_mm = re.search(
                    r"\b(?P<y>19\d{2}|20\d{2})\s*[/\-]\s*(?P<m>0?[1-9]|1[0-2])\b",
                    raw_text,
                )
                if iso_yyyy_mm:
                    return int(iso_yyyy_mm.group("y")) * 100 + int(iso_yyyy_mm.group("m"))

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
            blob_norm = normalize_keyword_for_match(" ".join(parts))

            relevance = 0.0
            if job_norm and normalized_term_present(blob_norm, job_norm):
                relevance += 2.0
            for term in normalized_terms:
                if normalized_term_present(blob_norm, term):
                    relevance += 1.8 if " " in term else 1.0

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

        primary_items = ranked[:count]
        additional_relevant_items = ranked[count:]
        return primary_items, additional_relevant_items

    def _build_additional_relevant_summary(
        self,
        additional_items: List[Dict[str, Any]],
        formatted_data: Dict[str, Any],
    ) -> str:
        if not isinstance(additional_items, list) or not additional_items:
            return ""

        is_en = str((formatted_data or {}).get("language") or "").lower().startswith("en")
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
                    item for item in description if isinstance(item, str) and item.strip()
                )
            elif isinstance(description, str) and description.strip():
                detail_candidates.append(description)
            summary = exp.get("summary")
            if isinstance(summary, str) and summary.strip():
                detail_candidates.append(summary)
            highlights = exp.get("highlights")
            if isinstance(highlights, list):
                detail_candidates.extend(
                    item for item in highlights if isinstance(item, str) and item.strip()
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

        preview = [_exp_snippet(exp) for exp in additional_items[:4] if isinstance(exp, dict)]
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
                items = block.get("skills_list") or block.get("items") or block.get("skills") or []
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

    def _collect_education_labels_for_compact_summary(self, education: Any) -> List[str]:
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

    def save_html(self, html_content: str, output_path: Optional[str] = None) -> str:
        """Sauvegarde le HTML."""
        if output_path is None:
            output_path = tempfile.mktemp(suffix=".html")
        
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
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
            
            templates.append({
                "name": template_name,
                "title": template_name.title(),
                "html_file": str(file),
                "css_file": str(css_file) if css_file.exists() else None,
                "preview_available": (self.templates_dir / "previews" / f"{template_name}.png").exists()
            })
        
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
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not re.match(email_pattern, cv_data["email"]):
                warnings.append("Format email invalide")
        
        # Validation des listes
        list_fields = ["experience", "education", "skills", "projects"]
        for field in list_fields:
            if field in cv_data and not isinstance(cv_data[field], list):
                warnings.append(f"Le champ {field} devrait être une liste")
        
        return {
            "errors": errors,
            "warnings": warnings,
            "valid": len(errors) == 0
        }
    
    def check_pdf_support(self) -> Dict[str, Any]:
        """Vérifie le support PDF et donne des conseils."""
        return {
            "pdf_available": _check_weasyprint(),
            "fallback_format": "html",
            "install_instructions": {
                "windows": [
                    "Installer GTK3 Runtime: https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer",
                    "Ou utiliser: pip install --find-links https://github.com/Kozea/WeasyPrint/releases weasyprint",
                    "Ou temporairement: exporter en HTML puis convertir en ligne"
                ],
                "alternative": "Utiliser un convertisseur en ligne HTML -> PDF"
            }
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
                        "Mise en place de CI/CD avec GitLab"
                    ],
                    "technologies": ["React", "Node.js", "PostgreSQL", "Docker"]
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
                        "Optimisation des performances front-end"
                    ],
                    "technologies": ["Vue.js", "Express", "MongoDB"]
                }
            ],
            
            "education": [
                {
                    "degree": "Master en Informatique",
                    "institution": "Ecole Polytechnique",
                    "location": "Palaiseau",
                    "year": "2020",
                    "grade": "Mention Bien"
                },
                {
                    "degree": "Licence Informatique",
                    "institution": "Université Paris-Saclay",
                    "location": "Saclay",
                    "year": "2018"
                }
            ],
            
            "skills": [
                {
                    "category": "Langages",
                    "skills_list": [
                        {"name": "JavaScript", "level": 90},
                        {"name": "Python", "level": 85},
                        {"name": "TypeScript", "level": 80},
                        {"name": "Java", "level": 70}
                    ]
                },
                {
                    "category": "Frameworks",
                    "skills_list": [
                        {"name": "React", "level": 90},
                        {"name": "Node.js", "level": 85},
                        {"name": "Vue.js", "level": 75},
                        {"name": "Django", "level": 70}
                    ]
                },
                {
                    "category": "Outils",
                    "skills_list": [
                        {"name": "Git", "level": 95},
                        {"name": "Docker", "level": 80},
                        {"name": "AWS", "level": 75}
                    ]
                }
            ],
            
            "languages": [
                {"name": "Français", "level": "Natif"},
                {"name": "Anglais", "level": "Professionnel"},
                {"name": "Espagnol", "level": "Intermédiaire"}
            ],
            
            "projects": [
                {
                    "name": "E-commerce Platform",
                    "description": "Plateforme e-commerce complète avec paiement en ligne et gestion des stocks",
                    "url": "https://github.com/jean/ecommerce",
                    "technologies": ["React", "Node.js", "Stripe", "MongoDB"]
                },
                {
                    "name": "Task Manager App",
                    "description": "Application de gestion de tâches collaborative avec notifications en temps réel",
                    "technologies": ["Vue.js", "Express", "Socket.io", "PostgreSQL"]
                }
            ],
            
            "certifications": [
                {
                    "name": "AWS Certified Developer",
                    "issuer": "Amazon Web Services",
                    "date": "2023",
                    "credential_id": "AWS-CDA-123456"
                },
                {
                    "name": "Scrum Master Certified",
                    "issuer": "Scrum Alliance",
                    "date": "2022"
                }
            ],
            
            "interests": [
                "Open Source", "Intelligence Artificielle", "Blockchain", 
                "Escalade", "Photographie", "Voyages"
            ]
        }
