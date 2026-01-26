"""
CV Generator
============

Contrôleur principal pour la génération de CV.
"""

import json
from typing import Dict, Any, Optional
from pathlib import Path
from loguru import logger

from ..models.user_profile import UserProfile
from ..models.job_application import JobApplication
from ..utils.parsers import DocumentParser
from .export_manager import ExportManager


class CVGenerator:
    """Générateur de CV intelligent."""
    
    def __init__(self):
        self.parser = DocumentParser()
        self.export_manager = ExportManager()
    
    def parse_cv_from_markdown(self, markdown_content: str) -> Dict[str, Any]:
        """Parse un CV depuis du markdown généré par l'IA."""
        cv_data = {
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
            "interests": []
        }
        
        lines = markdown_content.split('\n')
        current_section = None
        current_item = {}
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Titre principal (nom)
            if line.startswith('# ') and not cv_data["name"]:
                cv_data["name"] = line[2:].strip()
                continue
            
            # Titre de poste
            if line.startswith('## ') and not cv_data["job_title"]:
                title = line[3:].strip()
                if any(word in title.lower() for word in ['profil', 'contact', 'expérience', 'formation']):
                    current_section = title.lower()
                else:
                    cv_data["job_title"] = title
                continue
            
            # Sections
            if line.startswith('## '):
                section_title = line[3:].strip().lower()
                current_section = self.normalize_section_name(section_title)
                current_item = {}
                continue
            
            # Traitement par section
            if current_section == "contact" or current_section == "informations":
                self.parse_contact_line(line, cv_data)
            elif current_section == "profil":
                if cv_data["profile_summary"]:
                    cv_data["profile_summary"] += " " + line
                else:
                    cv_data["profile_summary"] = line
            elif current_section == "expérience" or current_section == "experience":
                self.parse_experience_line(line, cv_data, current_item)
            elif current_section == "formation" or current_section == "education":
                self.parse_education_line(line, cv_data, current_item)
            elif current_section == "compétences" or current_section == "skills":
                self.parse_skills_line(line, cv_data)
            elif current_section == "langues" or current_section == "languages":
                self.parse_languages_line(line, cv_data)
            elif current_section == "projets" or current_section == "projects":
                self.parse_projects_line(line, cv_data, current_item)
        
        return cv_data
    
    def normalize_section_name(self, section: str) -> str:
        """Normalise les noms de sections."""
        section = section.lower().strip()
        
        mappings = {
            "informations de contact": "contact",
            "contact": "contact",
            "profil professionnel": "profil",
            "profil": "profil",
            "expérience professionnelle": "expérience",
            "expérience": "expérience",
            "experience": "expérience",
            "formation": "formation",
            "education": "formation",
            "compétences techniques": "compétences",
            "compétences": "compétences",
            "skills": "compétences",
            "langues": "langues",
            "languages": "langues",
            "projets": "projets",
            "projects": "projets",
            "centres d'intérêt": "intérêts",
            "intérêts": "intérêts"
        }
        
        return mappings.get(section, section)
    
    def parse_contact_line(self, line: str, cv_data: Dict[str, Any]):
        """Parse une ligne de contact."""
        if "email" in line.lower() or "@" in line:
            import re
            email_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', line)
            if email_match:
                cv_data["email"] = email_match.group()
        
        elif "téléphone" in line.lower() or "phone" in line.lower():
            import re
            phone_match = re.search(r'[\+]?[0-9\s\-\.\(\)]{10,}', line)
            if phone_match:
                cv_data["phone"] = phone_match.group().strip()
        
        elif "linkedin" in line.lower():
            import re
            linkedin_match = re.search(r'https?://[^\s]+', line)
            if linkedin_match:
                cv_data["linkedin_url"] = linkedin_match.group()
        
        elif any(city in line.lower() for city in ["paris", "lyon", "marseille", "toulouse", "lille", "bordeaux"]):
            cv_data["location"] = line.replace("-", "").replace(":", "").strip()
    
    def parse_experience_line(self, line: str, cv_data: Dict[str, Any], current_item: Dict[str, Any]):
        """Parse une ligne d'expérience."""
        if line.startswith('### '):
            # Nouveau poste
            if current_item and "title" in current_item:
                cv_data["experience"].append(current_item.copy())
            current_item.clear()
            current_item["title"] = line[4:].strip()
            current_item["description"] = []
        
        elif line.startswith('**') and line.endswith('**'):
            # Entreprise ou période
            content = line[2:-2].strip()
            if "|" in content:
                parts = content.split("|")
                current_item["company"] = parts[0].strip()
                if len(parts) > 1:
                    current_item["start_date"], current_item["end_date"] = self.parse_date_range(parts[1].strip())
            else:
                current_item["company"] = content
        
        elif line.startswith('- '):
            # Accomplissement
            if "description" not in current_item:
                current_item["description"] = []
            current_item["description"].append(line[2:].strip())
    
    def parse_education_line(self, line: str, cv_data: Dict[str, Any], current_item: Dict[str, Any]):
        """Parse une ligne de formation."""
        if line.startswith('**') and line.endswith('**'):
            # Nouveau diplôme
            if current_item and "degree" in current_item:
                cv_data["education"].append(current_item.copy())
            current_item.clear()
            
            content = line[2:-2].strip()
            if "|" in content:
                parts = content.split("|")
                current_item["degree"] = parts[0].strip()
                if len(parts) > 1:
                    current_item["institution"] = parts[1].strip()
                if len(parts) > 2:
                    current_item["year"] = parts[2].strip()
            else:
                current_item["degree"] = content
    
    def parse_skills_line(self, line: str, cv_data: Dict[str, Any]):
        """Parse une ligne de compétences."""
        if line.startswith('- '):
            skill = line[2:].strip()
            if not cv_data["skills"]:
                cv_data["skills"] = [{"category": "Compétences", "items": []}]
            cv_data["skills"][0]["items"].append({"name": skill, "level": None})
    
    def parse_languages_line(self, line: str, cv_data: Dict[str, Any]):
        """Parse une ligne de langues."""
        if line.startswith('- '):
            lang_info = line[2:].strip()
            if ":" in lang_info:
                name, level = lang_info.split(":", 1)
                cv_data["languages"].append({
                    "name": name.strip(),
                    "level": level.strip()
                })
            else:
                cv_data["languages"].append({
                    "name": lang_info,
                    "level": "Non spécifié"
                })
    
    def parse_projects_line(self, line: str, cv_data: Dict[str, Any], current_item: Dict[str, Any]):
        """Parse une ligne de projets."""
        if line.startswith('### '):
            # Nouveau projet
            if current_item and "name" in current_item:
                cv_data["projects"].append(current_item.copy())
            current_item.clear()
            current_item["name"] = line[4:].strip()
        
        elif line and not line.startswith('#'):
            current_item["description"] = line
    
    def parse_date_range(self, date_str: str) -> tuple:
        """Parse une période (ex: "2020 - 2022" ou "2020 - Présent")."""
        if " - " in date_str:
            start, end = date_str.split(" - ", 1)
            end = None if end.strip().lower() in ["présent", "present", "actuel"] else end.strip()
            return start.strip(), end
        return date_str.strip(), None
    
    def enhance_cv_data(self, cv_data: Dict[str, Any], profile: UserProfile) -> Dict[str, Any]:
        """Enrichit les données CV avec les informations du profil."""
        # Compléter les informations manquantes
        if profile.name:
            cv_data["name"] = profile.name
        
        if profile.email:
            cv_data["email"] = profile.email
        
        if profile.phone:
            cv_data["phone"] = profile.phone
        
        if profile.linkedin_url:
            cv_data["linkedin_url"] = profile.linkedin_url
        
        return cv_data
    
    def generate_cv_variations(self, base_cv_data: Dict[str, Any], job_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Génère des variations du CV adaptées à l'offre."""
        variations = {
            "original": base_cv_data.copy(),
            "optimized": base_cv_data.copy()
        }
        
        # Optimisation basée sur l'analyse de l'offre
        optimized = variations["optimized"]
        
        # Adapter le titre du poste
        if job_analysis.get("job_title"):
            optimized["job_title"] = job_analysis["job_title"]
        
        # Réorganiser les compétences selon les besoins
        if job_analysis.get("skills_required"):
            optimized["skills"] = self.reorder_skills_by_relevance(
                optimized.get("skills", []), 
                job_analysis["skills_required"]
            )
        
        # Mettre en avant l'expérience pertinente
        if job_analysis.get("sector"):
            optimized["experience"] = self.prioritize_relevant_experience(
                optimized.get("experience", []),
                job_analysis["sector"]
            )
        
        return variations
    
    def reorder_skills_by_relevance(self, skills: list, required_skills: list) -> list:
        """Réorganise les compétences par pertinence."""
        if not skills or not required_skills:
            return skills
        
        # Créer un score de pertinence pour chaque compétence
        for skill_category in skills:
            if "items" in skill_category:
                skill_category["items"] = sorted(
                    skill_category["items"],
                    key=lambda x: self.calculate_skill_relevance(x["name"], required_skills),
                    reverse=True
                )
        
        return skills
    
    def calculate_skill_relevance(self, skill_name: str, required_skills: list) -> int:
        """Calcule la pertinence d'une compétence."""
        skill_lower = skill_name.lower()
        score = 0
        
        for required in required_skills:
            required_lower = required.lower()
            if skill_lower == required_lower:
                score += 10
            elif required_lower in skill_lower or skill_lower in required_lower:
                score += 5
        
        return score
    
    def prioritize_relevant_experience(self, experience: list, sector: str) -> list:
        """Priorise l'expérience pertinente."""
        if not experience or not sector:
            return experience
        
        # Simple scoring basé sur les mots-clés du secteur
        sector_keywords = {
            "tech": ["développement", "programmation", "software", "tech", "digital"],
            "marketing": ["marketing", "communication", "digital", "campagne"],
            "finance": ["finance", "comptabilité", "audit", "banque"]
        }
        
        keywords = sector_keywords.get(sector, [])
        
        def experience_relevance(exp):
            score = 0
            text = f"{exp.get('title', '')} {exp.get('company', '')} {' '.join(exp.get('description', []))}"
            text = text.lower()
            
            for keyword in keywords:
                if keyword in text:
                    score += 1
            
            return score
        
        return sorted(experience, key=experience_relevance, reverse=True)
    
    def export_cv(
        self, 
        cv_data: Dict[str, Any], 
        template: str = "modern", 
        output_format: str = "pdf",
        output_path: Optional[str] = None
    ) -> str:
        """Exporte le CV."""
        return self.export_manager.export_cv(cv_data, template, output_format, output_path)
    
    def get_available_templates(self) -> list:
        """Retourne les templates disponibles."""
        return self.export_manager.get_available_templates()
    
    def create_sample_cv(self) -> Dict[str, Any]:
        """Crée un CV d'exemple."""
        return self.export_manager.create_sample_cv_data()
