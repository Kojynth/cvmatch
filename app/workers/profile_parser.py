"""
Profile Parser Worker
====================

Worker pour parser les CV et documents en arrière-plan.
"""

from pathlib import Path
from typing import Dict, Any
from PySide6.QtCore import QThread, Signal
from loguru import logger

from ..utils.parsers import DocumentParser


class ProfileParserWorker(QThread):
    """Worker pour parser les documents de profil."""
    
    progress_updated = Signal(str)
    parsing_finished = Signal(dict)
    error_occurred = Signal(str)
    
    def __init__(self, file_path: str, document_type: str = "cv"):
        super().__init__()
        self.file_path = file_path
        self.document_type = document_type
        self.parser = DocumentParser()
    
    def run(self):
        """Lance le parsing."""
        try:
            self.progress_updated.emit(f"📄 Lecture du fichier {Path(self.file_path).name}...")
            
            # Parser le document
            content = self.parser.parse_document(self.file_path)
            
            self.progress_updated.emit("🔍 Analyse du contenu...")
            
            # Analyser le contenu selon le type
            if self.document_type == "cv":
                analysis = self.analyze_cv_content(content)
            elif self.document_type == "offer":
                analysis = self.analyze_offer_content(content)
            else:
                analysis = {"content": content}
            
            result = {
                "file_path": self.file_path,
                "content": content,
                "analysis": analysis,
                "document_type": self.document_type
            }
            
            self.progress_updated.emit("✅ Analyse terminée !")
            self.parsing_finished.emit(result)
            
        except Exception as e:
            logger.error(f"Erreur parsing {self.file_path} : {e}")
            self.error_occurred.emit(str(e))
    
    def analyze_cv_content(self, content: str) -> Dict[str, Any]:
        """Analyse le contenu d'un CV."""
        lines = content.split('\n')
        
        # Extraction basique d'informations
        analysis = {
            "length": len(content),
            "lines_count": len(lines),
            "sections_detected": [],
            "contact_info": {},
            "skills": [],
            "languages": []
        }
        
        # Détection de sections communes
        section_keywords = {
            "experience": ["expérience", "experience", "emploi", "professionnel"],
            "education": ["formation", "education", "études", "diplôme"],
            "skills": ["compétences", "skills", "qualifications"],
            "languages": ["langues", "languages", "idiomas"],
            "projects": ["projets", "projects", "réalisations"]
        }
        
        content_lower = content.lower()
        for section, keywords in section_keywords.items():
            if any(keyword in content_lower for keyword in keywords):
                analysis["sections_detected"].append(section)
        
        # Extraction d'email (basique)
        import re
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        emails = re.findall(email_pattern, content)
        if emails:
            analysis["contact_info"]["email"] = emails[0]
        
        # Détection de technologies (mots-clés tech communs)
        tech_keywords = [
            "python", "javascript", "java", "react", "vue", "angular", "node",
            "sql", "mysql", "postgresql", "mongodb", "docker", "kubernetes",
            "git", "github", "gitlab", "aws", "azure", "gcp", "linux", "windows"
        ]
        
        for tech in tech_keywords:
            if tech in content_lower:
                analysis["skills"].append(tech)
        
        # Détection de langues
        language_indicators = {
            "français": ["français", "french", "francés"],
            "anglais": ["anglais", "english", "inglés"],
            "espagnol": ["espagnol", "spanish", "español"],
            "allemand": ["allemand", "german", "alemán"]
        }
        
        for lang, indicators in language_indicators.items():
            if any(indicator in content_lower for indicator in indicators):
                analysis["languages"].append(lang)
        
        return analysis
    
    def analyze_offer_content(self, content: str) -> Dict[str, Any]:
        """Analyse le contenu d'une offre d'emploi."""
        content_lower = content.lower()
        
        analysis = {
            "length": len(content),
            "language": "fr" if any(word in content_lower for word in ["le", "la", "de", "du", "des"]) else "en",
            "sector": "general",
            "level": "unspecified",
            "skills_required": [],
            "company_type": "unknown"
        }
        
        # Détection de secteur
        sector_keywords = {
            "tech": ["développeur", "developer", "programmeur", "software", "informatique", "it", "tech"],
            "marketing": ["marketing", "communication", "digital", "réseaux sociaux"],
            "finance": ["finance", "comptable", "audit", "banque", "assurance"],
            "sales": ["vente", "commercial", "sales", "business development"],
            "hr": ["ressources humaines", "rh", "hr", "recrutement"],
            "design": ["design", "graphique", "ux", "ui", "créatif"]
        }
        
        for sector, keywords in sector_keywords.items():
            if any(keyword in content_lower for keyword in keywords):
                analysis["sector"] = sector
                break
        
        # Détection de niveau
        level_keywords = {
            "junior": ["junior", "débutant", "stage", "alternance", "graduate"],
            "senior": ["senior", "expérimenté", "expert", "lead", "principal"],
            "manager": ["manager", "chef", "directeur", "responsable", "head"]
        }
        
        for level, keywords in level_keywords.items():
            if any(keyword in content_lower for keyword in keywords):
                analysis["level"] = level
                break
        
        # Extraction de compétences requises (mots-clés techniques)
        tech_skills = [
            "python", "javascript", "java", "react", "vue", "angular", "node",
            "sql", "mysql", "postgresql", "mongodb", "docker", "kubernetes",
            "git", "github", "aws", "azure", "scrum", "agile"
        ]
        
        for skill in tech_skills:
            if skill in content_lower:
                analysis["skills_required"].append(skill)
        
        # Type d'entreprise
        company_indicators = {
            "startup": ["startup", "scale-up", "jeune pousse"],
            "corporation": ["groupe", "corporation", "multinationale", "cac 40"],
            "agency": ["agence", "agency", "studio"],
            "consulting": ["conseil", "consulting", "cabinet"]
        }
        
        for company_type, indicators in company_indicators.items():
            if any(indicator in content_lower for indicator in indicators):
                analysis["company_type"] = company_type
                break
        
        return analysis
