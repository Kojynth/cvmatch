"""
Schémas Pydantic pour ExperienceItem et EducationItem (Task 9).
Définit la structure et validation des données extraites du CV.
"""

from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, List, Dict, Any, Union
from datetime import date, datetime
from enum import Enum


class ConfidenceLevel(str, Enum):
    """Niveaux de confiance pour l'extraction."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class DateFormat(str, Enum):
    """Formats de dates supportés."""
    YYYY = "YYYY"
    MM_YYYY = "MM/YYYY"
    DD_MM_YYYY = "DD/MM/YYYY"
    FRENCH_MONTH_YYYY = "MONTH YYYY"


class ExperienceType(str, Enum):
    """Types d'expériences professionnelles."""
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    INTERNSHIP = "internship"
    FREELANCE = "freelance"
    CONTRACT = "contract"
    VOLUNTEER = "volunteer"
    PROJECT = "project"


class EducationLevel(str, Enum):
    """Niveaux d'éducation standardisés."""
    BAC = "bac"
    BAC_PLUS_2 = "bac+2"
    BAC_PLUS_3 = "bac+3"
    BAC_PLUS_5 = "bac+5"
    DOCTORATE = "doctorate"
    OTHER = "other"


class ExperienceItem(BaseModel):
    """
    Modèle Pydantic pour un élément d'expérience professionnelle.
    
    Assure la validation et la structuration des données extraites.
    """
    
    # Champs obligatoires
    title: str = Field(..., min_length=1, max_length=200, description="Titre du poste")
    
    # Champs optionnels avec valeurs par défaut
    company: Optional[str] = Field(None, max_length=200, description="Nom de l'entreprise")
    location: Optional[str] = Field(None, max_length=100, description="Lieu (ville, pays)")
    
    # Dates avec validation
    start_date: Optional[str] = Field(None, description="Date de début (format flexible)")
    end_date: Optional[str] = Field(None, description="Date de fin ou 'present'")
    
    # Métadonnées
    experience_type: Optional[ExperienceType] = Field(None, description="Type d'expérience")
    confidence: ConfidenceLevel = Field(ConfidenceLevel.MEDIUM, description="Confiance extraction")
    
    # Contenu détaillé
    description: Optional[str] = Field(None, description="Description des responsabilités")
    achievements: Optional[List[str]] = Field(default_factory=list, description="Réalisations clés")
    skills_used: Optional[List[str]] = Field(default_factory=list, description="Compétences utilisées")
    
    # Informations techniques d'extraction
    source_lines: Optional[List[int]] = Field(default_factory=list, description="Lignes sources dans le CV")
    extraction_method: Optional[str] = Field(None, description="Méthode d'extraction utilisée")
    span_start: Optional[int] = Field(None, description="Début de span dans le texte")
    
    @property
    def is_ongoing(self) -> bool:
        """
        Détermine si l'expérience est en cours.
        
        Returns:
            True si end_date est None ou contient des indicateurs d'ongoing
        """
        if self.end_date is None:
            return True
        
        if not isinstance(self.end_date, str):
            return False
            
        end_date_lower = self.end_date.lower().strip()
        
        # Patterns d'ongoing reconnus
        ongoing_patterns = [
            'présent', 'present', 'en cours', 'current', 'currently',
            'à ce jour', 'ce jour', 'maintenant', 'now', 'today',
            'ongoing', 'actuel', 'actuellement'
        ]
        
        return any(pattern in end_date_lower for pattern in ongoing_patterns)
    
    def set_ongoing(self, is_ongoing: bool) -> None:
        """
        Définit l'état ongoing en ajustant end_date.
        
        Args:
            is_ongoing: True pour marquer comme en cours, False sinon
        """
        if is_ongoing:
            self.end_date = None
        elif self.end_date is None:
            # Si on passe de ongoing à non-ongoing, fournir une date par défaut
            from datetime import datetime
            current_date = datetime.now()
            self.end_date = f"{current_date.month:02d}/{current_date.year}"
    span_end: Optional[int] = Field(None, description="Fin de span dans le texte")
    
    # Flags et métadonnées avancées
    flags: Optional[List[str]] = Field(default_factory=list, description="Flags d'extraction")
    raw_text: Optional[str] = Field(None, description="Texte brut extrait")
    
    @field_validator('title')
    @classmethod
    def validate_title(cls, v):
        """Valide et nettoie le titre."""
        if not v or not v.strip():
            raise ValueError("Le titre ne peut pas être vide")
        
        # Nettoyer les caractères indésirables
        cleaned = v.strip().replace('\n', ' ').replace('\t', ' ')
        # Limiter les espaces multiples
        cleaned = ' '.join(cleaned.split())
        
        if len(cleaned) < 2:
            raise ValueError("Le titre doit contenir au moins 2 caractères")
        
        return cleaned
    
    @field_validator('company')
    @classmethod
    def validate_company(cls, v):
        """Valide et nettoie le nom d'entreprise."""
        if v is None:
            return v
        
        cleaned = v.strip()
        if cleaned in ["", "Entreprise à définir", "N/A"]:
            return None
        
        return cleaned
    
    @field_validator('start_date', 'end_date')
    @classmethod
    def validate_dates(cls, v):
        """Valide les formats de dates."""
        if v is None:
            return v
        
        # Nettoyer la date
        cleaned = str(v).strip()
        
        # Cas spéciaux
        if cleaned.lower() in ['present', 'présent', 'actuel', 'current', 'ongoing', 'now']:
            return 'present'
        
        if cleaned == "":
            return None
        
        # Valider les formats supportés
        import re
        
        # Format YYYY
        if re.match(r'^\d{4}$', cleaned):
            year = int(cleaned)
            if 1990 <= year <= 2030:
                return cleaned
            raise ValueError(f"Année hors plage valide (1990-2030): {year}")
        
        # Format MM/YYYY
        if re.match(r'^\d{1,2}/\d{4}$', cleaned):
            month, year = cleaned.split('/')
            month, year = int(month), int(year)
            if not (1 <= month <= 12):
                raise ValueError(f"Mois invalide: {month}")
            if not (1990 <= year <= 2030):
                raise ValueError(f"Année hors plage valide: {year}")
            return f"{month:02d}/{year}"
        
        # Format DD/MM/YYYY
        if re.match(r'^\d{1,2}/\d{1,2}/\d{4}$', cleaned):
            day, month, year = cleaned.split('/')
            day, month, year = int(day), int(month), int(year)
            if not (1 <= day <= 31):
                raise ValueError(f"Jour invalide: {day}")
            if not (1 <= month <= 12):
                raise ValueError(f"Mois invalide: {month}")
            if not (1990 <= year <= 2030):
                raise ValueError(f"Année hors plage valide: {year}")
            return f"{day:02d}/{month:02d}/{year}"
        
        # Si aucun format reconnu, retourner tel quel (pour flexibilité)
        return cleaned
    
    @model_validator(mode='after')
    def validate_date_consistency(self):
        """Valide la cohérence entre dates de début et fin."""
        start_date = self.start_date
        end_date = self.end_date
        
        if not start_date or not end_date or end_date == 'present':
            return self
        
        # Extraction des années pour comparaison simple
        import re
        
        start_year_match = re.search(r'\b(\d{4})\b', start_date)
        end_year_match = re.search(r'\b(\d{4})\b', end_date)
        
        if start_year_match and end_year_match:
            start_year = int(start_year_match.group(1))
            end_year = int(end_year_match.group(1))
            
            if start_year > end_year:
                raise ValueError(f"Date début ({start_date}) postérieure à date fin ({end_date})")
        
        return self
    
    @field_validator('achievements', 'skills_used')
    @classmethod
    def validate_lists(cls, v):
        """Valide et nettoie les listes."""
        if v is None:
            return []
        
        # Filtrer les éléments vides ou trop courts
        cleaned = [item.strip() for item in v if item and len(item.strip()) >= 2]
        return cleaned
    
    def to_legacy_dict(self) -> Dict[str, Any]:
        """Convertit vers le format dictionnaire legacy pour compatibilité."""
        return {
            'title': self.title,
            'company': self.company,
            'location': self.location,
            'start_date': self.start_date,
            'end_date': self.end_date,
            'description': self.description,
            'confidence': self.confidence.value,
            'span_start': self.span_start,
            'span_end': self.span_end,
            'flags': self.flags
        }
    
    @classmethod
    def from_legacy_dict(cls, data: Dict[str, Any]) -> 'ExperienceItem':
        """Crée une instance depuis un dictionnaire legacy."""
        # Mapper les anciens champs vers les nouveaux
        mapped_data = {
            'title': data.get('title', 'Poste à définir'),
            'company': data.get('company'),
            'location': data.get('location'),
            'start_date': data.get('start_date'),
            'end_date': data.get('end_date'),
            'description': data.get('description'),
            'confidence': data.get('confidence', 'medium'),
            'span_start': data.get('span_start'),
            'span_end': data.get('span_end'),
            'flags': data.get('flags', [])
        }
        
        # Filtrer les valeurs None pour utiliser les defaults
        filtered_data = {k: v for k, v in mapped_data.items() if v is not None}
        
        return cls(**filtered_data)


class EducationItem(BaseModel):
    """
    Modèle Pydantic pour un élément d'éducation/formation.
    
    Structure et valide les données d'éducation extraites.
    """
    
    # Champs principaux
    degree: str = Field(..., min_length=1, max_length=200, description="Diplôme ou formation")
    institution: str = Field(..., min_length=1, max_length=200, description="Établissement")
    
    # Détails optionnels
    field_of_study: Optional[str] = Field(None, max_length=200, description="Domaine d'études")
    location: Optional[str] = Field(None, max_length=100, description="Lieu de l'établissement")
    
    # Dates et durée
    start_year: Optional[int] = Field(None, ge=1990, le=2030, description="Année de début")
    end_year: Optional[int] = Field(None, ge=1990, le=2030, description="Année de fin")
    year: Optional[str] = Field(None, description="Année(s) au format texte (ex: '2020-2022')")
    
    # Classification
    education_level: Optional[EducationLevel] = Field(None, description="Niveau d'éducation")
    grade: Optional[str] = Field(None, description="Note ou mention obtenue")
    
    # Métadonnées
    confidence: ConfidenceLevel = Field(ConfidenceLevel.MEDIUM, description="Confiance extraction")
    
    # Contenu détaillé
    description: Optional[str] = Field(None, description="Description du cursus")
    courses: Optional[List[str]] = Field(default_factory=list, description="Cours principaux")
    achievements: Optional[List[str]] = Field(default_factory=list, description="Réalisations académiques")
    
    # Informations d'extraction
    source_lines: Optional[List[int]] = Field(default_factory=list, description="Lignes sources")
    extraction_method: Optional[str] = Field(None, description="Méthode d'extraction")
    raw_text: Optional[str] = Field(None, description="Texte brut")
    
    @field_validator('degree')
    @classmethod
    def validate_degree(cls, v):
        """Valide et nettoie le diplôme."""
        cleaned = v.strip().replace('\n', ' ').replace('\t', ' ')
        cleaned = ' '.join(cleaned.split())
        
        if len(cleaned) < 2:
            raise ValueError("Le diplôme doit contenir au moins 2 caractères")
        
        return cleaned
    
    @field_validator('institution')
    @classmethod
    def validate_institution(cls, v):
        """Valide et nettoie l'établissement."""
        cleaned = v.strip()
        
        if cleaned in ["", "Institution à définir", "N/A"]:
            raise ValueError("Institution requise et valide")
        
        return cleaned
    
    @field_validator('start_year', 'end_year')
    @classmethod
    def validate_years(cls, v):
        """Valide les années."""
        if v is None:
            return v
        
        if not (1990 <= v <= 2030):
            raise ValueError(f"Année hors plage valide (1990-2030): {v}")
        
        return v
    
    @model_validator(mode='after')
    def validate_year_consistency(self):
        """Valide la cohérence des années."""
        start_year = self.start_year
        end_year = self.end_year
        
        if start_year and end_year and start_year > end_year:
            raise ValueError(f"Année début ({start_year}) > année fin ({end_year})")
        
        return self
    
    @model_validator(mode='after')
    def infer_education_level(self):
        """Infère le niveau d'éducation depuis le diplôme si non fourni."""
        if self.education_level is not None:
            return self
        
        degree = self.degree.lower() if self.degree else ''
        
        if any(word in degree for word in ['bac', 'baccalauréat']):
            self.education_level = EducationLevel.BAC
        elif any(word in degree for word in ['bts', 'dut', 'deug']):
            self.education_level = EducationLevel.BAC_PLUS_2
        elif any(word in degree for word in ['licence', 'bachelor', 'but']):
            self.education_level = EducationLevel.BAC_PLUS_3
        elif any(word in degree for word in ['master', 'ingénieur', 'mba']):
            self.education_level = EducationLevel.BAC_PLUS_5
        elif any(word in degree for word in ['doctorat', 'phd', 'thèse']):
            self.education_level = EducationLevel.DOCTORATE
        else:
            self.education_level = EducationLevel.OTHER
        
        return self
    
    def to_legacy_dict(self) -> Dict[str, Any]:
        """Convertit vers le format dictionnaire legacy."""
        return {
            'degree': self.degree,
            'institution': self.institution,
            'field_of_study': self.field_of_study,
            'location': self.location,
            'year': self.year,
            'grade': self.grade,
            'description': self.description,
            'confidence': self.confidence.value
        }
    
    @classmethod
    def from_legacy_dict(cls, data: Dict[str, Any]) -> 'EducationItem':
        """Crée une instance depuis un dictionnaire legacy."""
        mapped_data = {
            'degree': data.get('degree', 'Formation à définir'),
            'institution': data.get('institution', 'Institution à définir'),
            'field_of_study': data.get('field_of_study'),
            'location': data.get('location'),
            'year': data.get('year'),
            'grade': data.get('grade'),
            'description': data.get('description'),
            'confidence': data.get('confidence', 'medium')
        }
        
        # Filtrer les valeurs None
        filtered_data = {k: v for k, v in mapped_data.items() if v is not None}
        
        return cls(**filtered_data)


class ExtractionResult(BaseModel):
    """
    Résultat global d'extraction avec expériences et éducation validées.
    """
    
    experiences: List[ExperienceItem] = Field(default_factory=list, description="Expériences extraites")
    education: List[EducationItem] = Field(default_factory=list, description="Formations extraites")
    
    # Métadonnées d'extraction
    extraction_timestamp: datetime = Field(default_factory=datetime.now, description="Timestamp extraction")
    source_file: Optional[str] = Field(None, description="Fichier CV source")
    extractor_version: Optional[str] = Field(None, description="Version extracteur")
    
    # Métriques d'extraction
    metrics: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Métriques d'extraction")
    
    def get_experience_summary(self) -> Dict[str, Any]:
        """Résumé des expériences extraites."""
        if not self.experiences:
            return {"count": 0}
        
        return {
            "count": len(self.experiences),
            "with_dates": sum(1 for exp in self.experiences if exp.start_date),
            "with_company": sum(1 for exp in self.experiences if exp.company),
            "avg_confidence": sum(
                {"high": 3, "medium": 2, "low": 1}.get(exp.confidence.value, 1) 
                for exp in self.experiences
            ) / len(self.experiences)
        }
    
    def get_education_summary(self) -> Dict[str, Any]:
        """Résumé de l'éducation extraite."""
        if not self.education:
            return {"count": 0}
        
        return {
            "count": len(self.education),
            "with_years": sum(1 for edu in self.education if edu.start_year or edu.end_year),
            "levels": [edu.education_level.value for edu in self.education if edu.education_level],
            "avg_confidence": sum(
                {"high": 3, "medium": 2, "low": 1}.get(edu.confidence.value, 1)
                for edu in self.education
            ) / len(self.education)
        }


# Fonctions utilitaires pour la migration

def migrate_legacy_experiences(legacy_experiences: List[Dict[str, Any]]) -> List[ExperienceItem]:
    """Migre une liste d'expériences legacy vers le nouveau format."""
    migrated = []
    
    for exp_data in legacy_experiences:
        try:
            exp_item = ExperienceItem.from_legacy_dict(exp_data)
            migrated.append(exp_item)
        except Exception as e:
            # Log l'erreur mais continue la migration
            print(f"Erreur migration expérience {exp_data}: {e}")
    
    return migrated


def migrate_legacy_education(legacy_education: List[Dict[str, Any]]) -> List[EducationItem]:
    """Migre une liste d'éducation legacy vers le nouveau format."""
    migrated = []
    
    for edu_data in legacy_education:
        try:
            edu_item = EducationItem.from_legacy_dict(edu_data)
            migrated.append(edu_item)
        except Exception as e:
            # Log l'erreur mais continue la migration
            print(f"Erreur migration éducation {edu_data}: {e}")
    
    return migrated


if __name__ == "__main__":
    # Tests rapides des modèles
    
    # Test ExperienceItem
    exp_data = {
        "title": "Développeur Senior Python",
        "company": "TechCorp SAS",
        "start_date": "01/2020",
        "end_date": "12/2022",
        "location": "Paris"
    }
    
    exp = ExperienceItem(**exp_data)
    print("✅ ExperienceItem validé:", exp.title)
    
    # Test EducationItem
    edu_data = {
        "degree": "Master Informatique",
        "institution": "Université de Paris",
        "start_year": 2018,
        "end_year": 2020
    }
    
    edu = EducationItem(**edu_data)
    print("✅ EducationItem validé:", edu.degree)
    
    # Test ExtractionResult
    result = ExtractionResult(
        experiences=[exp],
        education=[edu],
        source_file="test_cv.pdf"
    )
    
    print("✅ ExtractionResult validé")
    print("📊 Résumé expériences:", result.get_experience_summary())
    print("📊 Résumé éducation:", result.get_education_summary())
