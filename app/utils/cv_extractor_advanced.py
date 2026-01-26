"""
CV Extractor Advanced - Phase 3: EXTRACTION avec appariement géométrique
========================================================================

Extraction intelligente des données structurées avec appariement dates↔rôle↔entreprise↔lieu
basé sur la proximité géométrique et patterns spécialisés (timeline, tableau, sidebar).
"""

import re
import json
import math
from typing import Dict, List, Any, Optional, Tuple, NamedTuple
from dataclasses import dataclass
from datetime import datetime, date
from pathlib import Path
from loguru import logger

import numpy as np
from rapidfuzz import fuzz, process
from dateparser import parse as dateparse
import dateutil.parser as dateutil_parser

from .cv_analyzer import TextBlock, BoundingBox, LayoutAnalysis
from .cv_mapper import SectionMapping


class DateRange(NamedTuple):
    """Période avec dates de début et fin."""
    start_date: Optional[date]
    end_date: Optional[date]
    is_current: bool
    raw_text: str
    confidence: float


class LocationInfo(NamedTuple):
    """Information de localisation."""
    city: Optional[str]
    region: Optional[str]
    country: Optional[str]
    raw_text: str
    confidence: float


@dataclass
class ExperienceComponent:
    """Composant d'expérience avec métadonnées spatiales."""
    component_type: str  # 'date', 'title', 'company', 'location', 'description'
    text: str
    bbox: BoundingBox
    confidence: float
    block_id: str


@dataclass
class ExtractedExperience:
    """Expérience extraite complète."""
    title: Optional[str]
    company: Optional[str]
    location: Optional[LocationInfo]
    date_range: Optional[DateRange]
    description: Optional[str]
    responsibilities: List[str]
    achievements: List[str]
    technologies: List[str]
    team_size: Optional[int]
    budget_managed: Optional[str]
    confidence_score: float
    extraction_source: Dict[str, Any]  # Métadonnées traçabilité


@dataclass
class ExtractedEducation:
    """Formation extraite."""
    degree: Optional[str]
    institution: Optional[str]
    location: Optional[LocationInfo]
    date_range: Optional[DateRange]
    grade: Optional[str]
    specialization: Optional[str]
    confidence_score: float


@dataclass
class ExtractedPersonalInfo:
    """Informations personnelles extraites."""
    full_name: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    location: Optional[LocationInfo]
    linkedin_url: Optional[str]
    portfolio_url: Optional[str]
    github_url: Optional[str]
    confidence_score: float


@dataclass
class ExtractedData:
    """Données extraites complètes."""
    personal_info: Optional[ExtractedPersonalInfo]
    summary: Optional[str]
    experiences: List[ExtractedExperience]
    education: List[ExtractedEducation]
    skills: Dict[str, List[str]]
    languages: List[Dict[str, str]]
    projects: List[Dict[str, Any]]
    certifications: List[Dict[str, Any]]
    awards: List[Dict[str, Any]]
    volunteering: List[Dict[str, Any]]
    interests: List[str]
    references: List[Dict[str, Any]]


class PatternMatcher:
    """Matchers pour différents patterns de layout."""
    
    # Indicateurs de date actuelle multi-langues
    CURRENT_INDICATORS = {
        'fr': ['présent', 'actuel', 'aujourd\'hui', 'maintenant', 'en cours', 'actuellement'],
        'en': ['present', 'current', 'now', 'today', 'ongoing', 'currently'],
        'es': ['presente', 'actual', 'hoy', 'ahora', 'en curso', 'actualmente'],
        'de': ['gegenwart', 'aktuell', 'heute', 'jetzt', 'laufend', 'derzeit']
    }
    
    # Patterns de dates multi-langues
    DATE_PATTERNS = [
        # Formats français
        r'(\d{1,2}/\d{1,2}/\d{4})',  # DD/MM/YYYY
        r'(\d{1,2}\.\d{1,2}\.\d{4})',  # DD.MM.YYYY
        r'(\d{1,2}\s+(janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)\s+\d{4})',
        r'(\d{4})',  # Année seule
        r'(\d{1,2}/\d{4})',  # MM/YYYY
        
        # Formats anglais
        r'(\d{1,2}/\d{1,2}/\d{4})',  # MM/DD/YYYY
        r'(\d{1,2}\s+(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{4})',
        r'(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{4}',
        
        # Formats génériques
        r'(\d{4}\s*-\s*\d{4})',  # Période années
        r'(\d{1,2}/\d{4}\s*-\s*\d{1,2}/\d{4})',  # Période MM/YYYY
    ]
    
    def __init__(self, language: str = 'fr'):
        self.language = language
        self.current_keywords = self.CURRENT_INDICATORS.get(language, self.CURRENT_INDICATORS['fr'])
    
    def extract_dates_from_text(self, text: str) -> List[DateRange]:
        """Extrait les dates d'un texte avec gestion multi-langue."""
        dates_found = []
        
        # 1. Recherche patterns explicites
        for pattern in self.DATE_PATTERNS:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                date_text = match.group(1)
                date_range = self._parse_date_range(date_text)
                if date_range:
                    dates_found.append(date_range)
        
        # 2. Parser généraliste (dateparser)
        if not dates_found:
            try:
                parsed_date = dateparse(text, settings={'PREFER_DAY_OF_MONTH': 'first'})
                if parsed_date:
                    date_range = DateRange(
                        start_date=parsed_date.date(),
                        end_date=None,
                        is_current=False,
                        raw_text=text,
                        confidence=0.7
                    )
                    dates_found.append(date_range)
            except:
                pass
        
        return dates_found
    
    def _parse_date_range(self, text: str) -> Optional[DateRange]:
        """Parse une plage de dates à partir du texte."""
        text = text.strip().lower()
        
        # Détecter "présent/current"
        is_current = any(keyword in text for keyword in self.current_keywords)
        
        # Pattern période (ex: "2020-2023", "Jan 2020 - Dec 2022")
        if '-' in text or '–' in text or 'à' in text or 'to' in text:
            separators = ['-', '–', ' à ', ' to ', ' till ', ' until ']
            
            for sep in separators:
                if sep in text:
                    parts = text.split(sep, 1)
                    if len(parts) == 2:
                        start_text, end_text = parts
                        start_date = self._parse_single_date(start_text.strip())
                        
                        end_text = end_text.strip()
                        if any(keyword in end_text for keyword in self.current_keywords):
                            end_date = None
                            is_current = True
                        else:
                            end_date = self._parse_single_date(end_text)
                        
                        if start_date:
                            return DateRange(
                                start_date=start_date,
                                end_date=end_date,
                                is_current=is_current,
                                raw_text=text,
                                confidence=0.8
                            )
        
        # Date unique
        single_date = self._parse_single_date(text)
        if single_date:
            return DateRange(
                start_date=single_date,
                end_date=None,
                is_current=is_current,
                raw_text=text,
                confidence=0.6
            )
        
        return None
    
    def _parse_single_date(self, text: str) -> Optional[date]:
        """Parse une date unique."""
        try:
            # Essayer dateutil d'abord
            parsed = dateutil_parser.parse(text, fuzzy=True)
            return parsed.date()
        except:
            try:
                # Fallback dateparser
                parsed = dateparse(text, settings={'PREFER_DAY_OF_MONTH': 'first'})
                if parsed:
                    return parsed.date()
            except:
                pass
        
        return None
    
    def extract_companies_from_text(self, text: str) -> List[str]:
        """Extrait les noms d'entreprises du texte."""
        companies = []
        
        # Patterns indicateurs d'entreprises
        company_indicators = [
            r'(?:chez|at|@)\s+([A-Z][a-zA-Z\s&\.]+)',
            r'([A-Z][a-zA-Z\s&\.]+)(?:\s*(?:inc|ltd|llc|sa|sas|sarl|gmbh|corp|corporation)\.?)',
            r'^([A-Z][a-zA-Z\s&\.]{2,30})$'  # Ligne avec juste nom entreprise
        ]
        
        for pattern in company_indicators:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                company = match.group(1).strip()
                if len(company) > 2 and company not in companies:
                    companies.append(company)
        
        return companies
    
    def extract_job_titles_from_text(self, text: str) -> List[str]:
        """Extrait les intitulés de postes du texte."""
        titles = []
        
        # Patterns typiques de titres
        title_indicators = [
            r'(?:poste|titre|position|role)\s*:\s*(.+)',
            r'^((?:senior|junior|lead|principal|chef|director|manager|développeur|developer|ingénieur|engineer|consultant|analyst|specialist)\s*[a-zA-Z\s]+)',
            r'^([A-Z][a-zA-Z\s]{5,40})$'  # Ligne probable titre
        ]
        
        for pattern in title_indicators:
            matches = re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                title = match.group(1).strip()
                if len(title) > 3 and title not in titles:
                    titles.append(title)
        
        return titles
    
    def extract_locations_from_text(self, text: str) -> List[LocationInfo]:
        """Extrait les lieux du texte."""
        locations = []
        
        # Patterns de lieux
        location_patterns = [
            r'(\w+),\s*(\w+)',  # Ville, Pays
            r'(\w+)\s*\((\w+)\)',  # Ville (Pays)
            r'^(\w+(?:\s+\w+)?)$'  # Ligne avec juste lieu
        ]
        
        for pattern in location_patterns:
            matches = re.finditer(pattern, text)
            for match in matches:
                if len(match.groups()) >= 2:
                    city, country = match.groups()[:2]
                    location = LocationInfo(
                        city=city.strip(),
                        region=None,
                        country=country.strip(),
                        raw_text=match.group(0),
                        confidence=0.7
                    )
                    locations.append(location)
                else:
                    location = LocationInfo(
                        city=match.group(1).strip(),
                        region=None,
                        country=None,
                        raw_text=match.group(0),
                        confidence=0.5
                    )
                    locations.append(location)
        
        return locations


class CVExtractorAdvanced:
    """Extracteur avancé avec appariement géométrique intelligent."""
    
    def __init__(self, language: str = 'fr'):
        self.language = language
        self.pattern_matcher = PatternMatcher(language)
        self.distance_threshold = 100.0  # pixels
        self.debug_mode = False
    
    def extract_structured_data(
        self, 
        sections: SectionMapping, 
        layout: LayoutAnalysis
    ) -> ExtractedData:
        """
        Extraction complète des données structurées.
        
        Args:
            sections: Mapping sémantique validé
            layout: Analyse layout du document
            
        Returns:
            ExtractedData: Données extraites structurées
        """
        logger.info(f"🔧 Extraction données structurées de {len(sections.sections)} sections")
        
        result = ExtractedData(
            personal_info=None,
            summary=None,
            experiences=[],
            education=[],
            skills={},
            languages=[],
            projects=[],
            certifications=[],
            awards=[],
            volunteering=[],
            interests=[],
            references=[]
        )
        
        # Extraction par section
        if 'contact' in sections.sections:
            result.personal_info = self._extract_personal_info(sections.sections['contact'])
        
        if 'summary' in sections.sections:
            result.summary = self._extract_summary(sections.sections['summary'])
        
        if 'experience' in sections.sections:
            result.experiences = self._extract_experiences_advanced(
                sections.sections['experience'], layout
            )
        
        if 'education' in sections.sections:
            result.education = self._extract_education_advanced(
                sections.sections['education'], layout
            )
        
        if 'skills' in sections.sections:
            result.skills = self._extract_skills(sections.sections['skills'])
        
        if 'languages' in sections.sections:
            result.languages = self._extract_languages(sections.sections['languages'])
        
        if 'projects' in sections.sections:
            result.projects = self._extract_projects(sections.sections['projects'])
        
        if 'certifications' in sections.sections:
            result.certifications = self._extract_certifications(sections.sections['certifications'])
        
        if 'awards' in sections.sections:
            result.awards = self._extract_awards(sections.sections['awards'])
        
        if 'volunteering' in sections.sections:
            result.volunteering = self._extract_volunteering(sections.sections['volunteering'])
        
        if 'interests' in sections.sections:
            result.interests = self._extract_interests(sections.sections['interests'])
        
        if 'references' in sections.sections:
            result.references = self._extract_references(sections.sections['references'])
        
        logger.info(f"✅ Extraction terminée: {len(result.experiences)} expériences, "
                   f"{len(result.education)} formations")
        
        return result
    
    def _extract_experiences_advanced(
        self, 
        blocks: List[TextBlock], 
        layout: LayoutAnalysis
    ) -> List[ExtractedExperience]:
        """Extraction avancée des expériences avec appariement géométrique."""
        
        if not blocks:
            return []
        
        logger.info(f"🏢 Extraction {len(blocks)} blocs d'expérience")
        
        # 1. Extraction composants de tous les blocs
        all_components = []
        for block in blocks:
            components = self._extract_experience_components_from_block(block)
            all_components.extend(components)
        
        # 2. Détection du pattern layout (timeline, tableau, sidebar)
        layout_pattern = self._detect_experience_layout_pattern(all_components, layout)
        logger.info(f"📋 Pattern détecté: {layout_pattern}")
        
        # 3. Appariement selon le pattern
        if layout_pattern == 'timeline':
            experiences = self._match_timeline_pattern(all_components)
        elif layout_pattern == 'table':
            experiences = self._match_table_pattern(all_components)
        elif layout_pattern == 'sidebar':
            experiences = self._match_sidebar_pattern(all_components)
        else:
            experiences = self._match_proximity_pattern(all_components)
        
        # 4. Post-processing et validation
        validated_experiences = self._validate_and_enhance_experiences(experiences)
        
        return validated_experiences
    
    def _extract_experience_components_from_block(
        self, 
        block: TextBlock
    ) -> List[ExperienceComponent]:
        """Extrait les composants d'expérience d'un bloc."""
        
        components = []
        text = block.text
        
        # Dates
        dates = self.pattern_matcher.extract_dates_from_text(text)
        for date_range in dates:
            components.append(ExperienceComponent(
                component_type='date',
                text=date_range.raw_text,
                bbox=block.bbox,
                confidence=date_range.confidence,
                block_id=block.id
            ))
        
        # Entreprises
        companies = self.pattern_matcher.extract_companies_from_text(text)
        for company in companies:
            components.append(ExperienceComponent(
                component_type='company',
                text=company,
                bbox=block.bbox,
                confidence=0.8,
                block_id=block.id
            ))
        
        # Titres de poste
        titles = self.pattern_matcher.extract_job_titles_from_text(text)
        for title in titles:
            components.append(ExperienceComponent(
                component_type='title',
                text=title,
                bbox=block.bbox,
                confidence=0.7,
                block_id=block.id
            ))
        
        # Lieux
        locations = self.pattern_matcher.extract_locations_from_text(text)
        for location in locations:
            components.append(ExperienceComponent(
                component_type='location',
                text=location.raw_text,
                bbox=block.bbox,
                confidence=location.confidence,
                block_id=block.id
            ))
        
        # Description (le reste du texte si pas d'autres composants trouvés)
        if not any(comp.component_type != 'description' for comp in components):
            components.append(ExperienceComponent(
                component_type='description',
                text=text,
                bbox=block.bbox,
                confidence=0.5,
                block_id=block.id
            ))
        
        return components
    
    def _detect_experience_layout_pattern(
        self, 
        components: List[ExperienceComponent], 
        layout: LayoutAnalysis
    ) -> str:
        """Détecte le pattern de layout des expériences."""
        
        if not components:
            return 'unknown'
        
        # Séparer composants par type
        dates = [c for c in components if c.component_type == 'date']
        titles = [c for c in components if c.component_type == 'title']
        companies = [c for c in components if c.component_type == 'company']
        
        # Timeline pattern: dates puis contenu dans ordre de lecture
        if dates and (titles or companies):
            # Vérifier si dates sont généralement avant le contenu
            before_count = 0
            total_pairs = 0
            
            for date_comp in dates:
                for content_comp in (titles + companies):
                    if date_comp.bbox.top <= content_comp.bbox.top:
                        before_count += 1
                    total_pairs += 1
            
            if total_pairs > 0 and before_count / total_pairs > 0.7:
                return 'timeline'
        
        # Table pattern: alignement régulier sur colonnes
        if layout.column_count > 1:
            # Vérifier alignement vertical des composants
            date_x_positions = [c.bbox.left for c in dates]
            if len(set(date_x_positions)) == 1 and len(date_x_positions) > 1:
                return 'table'
        
        # Sidebar pattern: dates dans colonne séparée
        if layout.has_sidebar and dates:
            sidebar_x = layout.columns[0].bbox.center_x if layout.sidebar_position == 'left' else layout.columns[-1].bbox.center_x
            dates_in_sidebar = sum(1 for d in dates if abs(d.bbox.center_x - sidebar_x) < 50)
            
            if dates_in_sidebar / len(dates) > 0.7:
                return 'sidebar'
        
        return 'proximity'  # Default: appariement par proximité
    
    def _match_timeline_pattern(
        self, 
        components: List[ExperienceComponent]
    ) -> List[ExtractedExperience]:
        """Appariement pattern timeline (dates puis contenu)."""
        
        experiences = []
        
        # Grouper composants par proximité verticale
        sorted_components = sorted(components, key=lambda c: c.bbox.top)
        
        current_group = []
        current_y = None
        y_threshold = 50  # pixels
        
        for component in sorted_components:
            if current_y is None or abs(component.bbox.top - current_y) < y_threshold:
                current_group.append(component)
                current_y = component.bbox.top
            else:
                # Nouveau groupe
                if current_group:
                    exp = self._build_experience_from_components(current_group)
                    if exp:
                        experiences.append(exp)
                
                current_group = [component]
                current_y = component.bbox.top
        
        # Traiter dernier groupe
        if current_group:
            exp = self._build_experience_from_components(current_group)
            if exp:
                experiences.append(exp)
        
        return experiences
    
    def _match_table_pattern(
        self, 
        components: List[ExperienceComponent]
    ) -> List[ExtractedExperience]:
        """Appariement pattern tableau (colonnes alignées)."""
        
        # Grouper par ligne (même Y)
        lines = {}
        for component in components:
            y = round(component.bbox.top / 10) * 10  # Quantification 10px
            if y not in lines:
                lines[y] = []
            lines[y].append(component)
        
        experiences = []
        for y_pos, line_components in lines.items():
            # Trier par X pour respecter ordre colonnes
            line_components.sort(key=lambda c: c.bbox.left)
            exp = self._build_experience_from_components(line_components)
            if exp:
                experiences.append(exp)
        
        return experiences
    
    def _match_sidebar_pattern(
        self, 
        components: List[ExperienceComponent]
    ) -> List[ExtractedExperience]:
        """Appariement pattern sidebar (dates séparées)."""
        
        # Séparer dates et contenu
        dates = [c for c in components if c.component_type == 'date']
        content = [c for c in components if c.component_type != 'date']
        
        experiences = []
        
        for date_comp in dates:
            # Trouver contenu le plus proche verticalement
            closest_content = []
            for content_comp in content:
                distance = abs(date_comp.bbox.center_y - content_comp.bbox.center_y)
                if distance < self.distance_threshold:
                    closest_content.append((content_comp, distance))
            
            # Prendre les plus proches
            closest_content.sort(key=lambda x: x[1])
            related_components = [date_comp] + [c[0] for c in closest_content[:3]]
            
            exp = self._build_experience_from_components(related_components)
            if exp:
                experiences.append(exp)
        
        return experiences
    
    def _match_proximity_pattern(
        self, 
        components: List[ExperienceComponent]
    ) -> List[ExtractedExperience]:
        """Appariement par proximité générale."""
        
        experiences = []
        used_components = set()
        
        # Pour chaque composant non utilisé, construire un groupe de proximité
        for component in components:
            if component.block_id in used_components:
                continue
            
            # Trouver tous les composants proches
            nearby_components = [component]
            used_components.add(component.block_id)
            
            for other_comp in components:
                if other_comp.block_id in used_components:
                    continue
                
                distance = np.linalg.norm([
                    component.bbox.center_x - other_comp.bbox.center_x,
                    component.bbox.center_y - other_comp.bbox.center_y
                ])
                
                if distance < self.distance_threshold:
                    nearby_components.append(other_comp)
                    used_components.add(other_comp.block_id)
            
            exp = self._build_experience_from_components(nearby_components)
            if exp:
                experiences.append(exp)
        
        return experiences
    
    def _build_experience_from_components(
        self, 
        components: List[ExperienceComponent]
    ) -> Optional[ExtractedExperience]:
        """Construit une expérience à partir des composants."""
        
        if not components:
            return None
        
        # Séparer par type
        dates = [c for c in components if c.component_type == 'date']
        titles = [c for c in components if c.component_type == 'title']
        companies = [c for c in components if c.component_type == 'company']
        locations = [c for c in components if c.component_type == 'location']
        descriptions = [c for c in components if c.component_type == 'description']
        
        # Construire l'expérience
        date_range = None
        if dates:
            # Prendre la première date trouvée
            date_text = dates[0].text
            date_ranges = self.pattern_matcher.extract_dates_from_text(date_text)
            if date_ranges:
                date_range = date_ranges[0]
        
        location_info = None
        if locations:
            location_infos = self.pattern_matcher.extract_locations_from_text(locations[0].text)
            if location_infos:
                location_info = location_infos[0]
        
        # Score de confiance basé sur completude
        confidence_factors = []
        if titles:
            confidence_factors.append(0.3)
        if companies:
            confidence_factors.append(0.3)
        if dates:
            confidence_factors.append(0.2)
        if locations:
            confidence_factors.append(0.1)
        if descriptions:
            confidence_factors.append(0.1)
        
        confidence_score = sum(confidence_factors)
        
        # Métadonnées de traçabilité
        extraction_source = {
            'components_used': len(components),
            'has_date': bool(dates),
            'has_title': bool(titles),
            'has_company': bool(companies),
            'blocks_source': [c.block_id for c in components]
        }
        
        return ExtractedExperience(
            title=titles[0].text if titles else None,
            company=companies[0].text if companies else None,
            location=location_info,
            date_range=date_range,
            description=descriptions[0].text if descriptions else None,
            responsibilities=[],  # À enrichir en post-processing
            achievements=[],
            technologies=[],
            team_size=None,
            budget_managed=None,
            confidence_score=confidence_score,
            extraction_source=extraction_source
        )
    
    def _validate_and_enhance_experiences(
        self, 
        experiences: List[ExtractedExperience]
    ) -> List[ExtractedExperience]:
        """Valide et enrichit les expériences extraites."""
        
        validated = []
        
        for exp in experiences:
            # Validation minimale: au moins titre OU entreprise
            if not exp.title and not exp.company:
                continue
            
            # Enrichissement: extraction responsabilités/achievements du description
            if exp.description:
                responsibilities, achievements, technologies = self._parse_description_content(exp.description)
                exp.responsibilities = responsibilities
                exp.achievements = achievements  
                exp.technologies = technologies
            
            validated.append(exp)
        
        # Trier par date (plus récent en premier)
        validated.sort(key=lambda e: (
            e.date_range.start_date if e.date_range and e.date_range.start_date else date.min
        ), reverse=True)
        
        return validated
    
    def _parse_description_content(
        self, 
        description: str
    ) -> Tuple[List[str], List[str], List[str]]:
        """Parse le contenu description pour extraire responsabilités/achievements/technologies."""
        
        lines = description.split('\n')
        responsibilities = []
        achievements = []
        technologies = []
        
        # Patterns pour achievements (résultats chiffrés)
        achievement_patterns = [
            r'(\d+%\s*(?:d\')?(?:amélioration|réduction|augmentation|croissance))',
            r'(réduction\s*.*?\s*\d+%)',
            r'(économie\s*.*?\s*\d+[k€$])',
            r'(\d+\s*(?:utilisateurs|clients|projets|équipes?))'
        ]
        
        # Patterns pour technologies
        tech_patterns = [
            r'\b(python|java|javascript|react|angular|vue|php|c\+\+|c#|ruby|go|rust|scala)\b',
            r'\b(mysql|postgresql|mongodb|redis|elasticsearch|cassandra)\b',
            r'\b(docker|kubernetes|jenkins|gitlab|github|aws|azure|gcp)\b',
            r'\b(agile|scrum|kanban|devops|ci/cd)\b'
        ]
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Chercher achievements
            is_achievement = False
            for pattern in achievement_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    achievements.append(line)
                    is_achievement = True
                    break
            
            if not is_achievement:
                responsibilities.append(line)
            
            # Chercher technologies
            for pattern in tech_patterns:
                matches = re.findall(pattern, line, re.IGNORECASE)
                for match in matches:
                    if match.lower() not in [t.lower() for t in technologies]:
                        technologies.append(match)
        
        return responsibilities, achievements, technologies
    
    # Méthodes simplifiées pour autres sections...
    
    def _extract_personal_info(self, blocks: List[TextBlock]) -> Optional[ExtractedPersonalInfo]:
        """Extraction informations personnelles."""
        if not blocks:
            return None
        
        full_text = ' '.join(block.text for block in blocks)
        
        # Regex patterns
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        phone_pattern = r'(\+33|0)[1-9](?:[0-9]{8})'
        linkedin_pattern = r'linkedin\.com/in/[\w-]+'
        
        email = re.search(email_pattern, full_text)
        phone = re.search(phone_pattern, full_text)
        linkedin = re.search(linkedin_pattern, full_text)
        
        return ExtractedPersonalInfo(
            full_name=None,  # À améliorer avec NER
            first_name=None,
            last_name=None,
            email=email.group(0) if email else None,
            phone=phone.group(0) if phone else None,
            location=None,
            linkedin_url=f"https://{linkedin.group(0)}" if linkedin else None,
            portfolio_url=None,
            github_url=None,
            confidence_score=0.7
        )
    
    def _extract_summary(self, blocks: List[TextBlock]) -> Optional[str]:
        """Extraction résumé."""
        if not blocks:
            return None
        return ' '.join(block.text for block in blocks)
    
    def _extract_education_advanced(
        self, 
        blocks: List[TextBlock], 
        layout: LayoutAnalysis
    ) -> List[ExtractedEducation]:
        """Extraction formations avec patterns similaires aux expériences."""
        # Simplifiée pour l'exemple
        education_list = []
        
        for block in blocks:
            dates = self.pattern_matcher.extract_dates_from_text(block.text)
            date_range = dates[0] if dates else None
            
            education = ExtractedEducation(
                degree=None,  # À enrichir
                institution=None,
                location=None,
                date_range=date_range,
                grade=None,
                specialization=None,
                confidence_score=0.6
            )
            education_list.append(education)
        
        return education_list
    
    def _extract_skills(self, blocks: List[TextBlock]) -> Dict[str, List[str]]:
        """Extraction compétences."""
        skills = {}
        for block in blocks:
            # Parsing simple pour l'exemple
            lines = block.text.split('\n')
            for line in lines:
                if ':' in line:
                    category, items = line.split(':', 1)
                    skill_items = [item.strip() for item in items.split(',')]
                    skills[category.strip()] = skill_items
        
        return skills
    
    def _extract_languages(self, blocks: List[TextBlock]) -> List[Dict[str, str]]:
        """Extraction langues."""
        languages = []
        for block in blocks:
            # Patterns niveau CECR
            cecr_pattern = r'([a-z]+)\s*[:-]?\s*(A[12]|B[12]|C[12]|natif|courant|bilingue)'
            matches = re.findall(cecr_pattern, block.text, re.IGNORECASE)
            
            for lang, level in matches:
                languages.append({
                    'language': lang.lower(),
                    'level': level.lower(),
                    'cefr_level': level.upper() if level.upper() in ['A1', 'A2', 'B1', 'B2', 'C1', 'C2'] else None
                })
        
        return languages
    
    def _extract_projects(self, blocks: List[TextBlock]) -> List[Dict[str, Any]]:
        """Extraction projets."""
        return [{'name': 'Projet exemple', 'description': block.text} for block in blocks[:3]]
    
    def _extract_certifications(self, blocks: List[TextBlock]) -> List[Dict[str, Any]]:
        """Extraction certifications."""
        return []
    
    def _extract_awards(self, blocks: List[TextBlock]) -> List[Dict[str, Any]]:
        """Extraction récompenses."""
        return []
    
    def _extract_volunteering(self, blocks: List[TextBlock]) -> List[Dict[str, Any]]:
        """Extraction bénévolat."""
        return []
    
    def _extract_interests(self, blocks: List[TextBlock]) -> List[str]:
        """Extraction centres d'intérêt."""
        interests = []
        for block in blocks:
            items = re.split(r'[,;•\n]', block.text)
            interests.extend([item.strip() for item in items if item.strip()])
        return interests
    
    def _extract_references(self, blocks: List[TextBlock]) -> List[Dict[str, Any]]:
        """Extraction références."""
        return []
