"""
Export Manager
==============

Gestionnaire pour l'export des CV en différents formats.
"""

import os
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional
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
            "skills": "Skills" if is_en else "Competences",
            "education": "Education" if is_en else "Formation",
            "projects": "Projects" if is_en else "Projets",
            "languages": "Languages" if is_en else "Langues",
            "certifications": "Certifications",
            "interests": "Interests" if is_en else "Centres d'interet",
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
                formatted_data["experience"] = self.format_experience(experience_data)
            elif experience_data is None:
                formatted_data["experience"] = []
        except Exception as e:
            logger.warning(f"Erreur formatage experience: {e}")
            formatted_data["experience"] = []
        
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
            content: "⚠️";
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
            # Si c'est une liste simple, la convertir en structure categorisee
            if skills and len(skills) > 0 and isinstance(skills[0], str):
                return [
                    {
                        "category": default_category,
                        "skills_list": [
                            {"name": skill, "level": None}
                            for skill in skills
                            if isinstance(skill, str) and skill.strip()
                        ],
                    }
                ]

            normalized = []
            for block in skills:
                if isinstance(block, dict):
                    if isinstance(block.get("skills_list"), list):
                        normalized.append(block)
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
                        name = str(name).strip()
                        if name:
                            skills_list.append({"name": name, "level": level})

                    if skills_list:
                        normalized.append(
                            {
                                "category": block.get("category") or default_category,
                                "skills_list": skills_list,
                            }
                        )
                elif isinstance(block, str):
                    name = block.strip()
                    if not name:
                        continue
                    if not normalized:
                        normalized.append(
                            {"category": default_category, "skills_list": []}
                        )
                    normalized[0]["skills_list"].append(
                        {"name": name, "level": None}
                    )

            return normalized or skills
        except Exception as e:
            logger.error(f"Erreur format_skills: {e}")
            return []
    
    def format_experience(self, experience: list) -> list:
        """Formate l'expérience pour les templates."""
        if not experience or not isinstance(experience, list):
            return []
        
        try:
            for exp in experience:
                if isinstance(exp, dict):
                    # S'assurer que la description est une liste pour les templates
                    if isinstance(exp.get("description"), str):
                        exp["description"] = [exp["description"]]
                    elif exp.get("description") is None:
                        exp["description"] = []
            
            return experience
        except Exception as e:
            logger.error(f"Erreur format_experience: {e}")
            return []
    
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
                "alternative": "Utiliser un convertisseur en ligne HTML → PDF"
            }
        }
    
    def create_sample_cv_data(self) -> Dict[str, Any]:
        """Crée des données d'exemple pour tester les templates."""
        return {
            "name": "Jean Dupont",
            "email": "jean.dupont@email.com",
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
                    "institution": "École Polytechnique",
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
