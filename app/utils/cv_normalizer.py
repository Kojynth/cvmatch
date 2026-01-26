"""
CV Normalizer - Phase 4: NORMALISATION offline des données extraites
===================================================================

Normalisation complète 100% offline : dates → ISO, contacts validés,
lieux canoniques, niveaux langues → CECR, intitulés postes standardisés.
"""

import re
import json
from typing import Dict, List, Any, Optional, Tuple, Union
from dataclasses import dataclass, asdict
from datetime import datetime, date
from pathlib import Path
from loguru import logger

import phonenumbers
from phonenumbers import geocoder, carrier
from email_validator import validate_email, EmailNotValidError
import pycountry
import babel.dates
from babel import Locale

from .cv_extractor_advanced import ExtractedData, ExtractedExperience, ExtractedEducation, ExtractedPersonalInfo, DateRange, LocationInfo


@dataclass
class NormalizedDate:
    """Date normalisée avec métadonnées."""
    iso_date: Optional[str]  # Format YYYY-MM-DD
    year: Optional[int]
    month: Optional[int]
    is_current: bool
    precision: str  # 'day', 'month', 'year', 'unknown'
    raw_text: str
    confidence: float


@dataclass
class NormalizedLocation:
    """Localisation normalisée."""
    city: Optional[str]
    region: Optional[str]
    country: Optional[str]
    country_code: Optional[str]  # ISO 3166-1 alpha-2
    raw_text: str
    confidence: float


@dataclass
class NormalizedContact:
    """Contact normalisé et validé."""
    email: Optional[str]
    email_valid: bool
    phone: Optional[str]
    phone_formatted: Optional[str]  # Format E.164
    phone_country: Optional[str]
    phone_carrier: Optional[str]
    phone_valid: bool


class DateNormalizer:
    """Normalisateur de dates multi-langue."""
    
    # Indicateurs "présent/actuel" par langue
    CURRENT_INDICATORS = {
        'fr': ['présent', 'actuel', 'aujourd\'hui', 'maintenant', 'en cours', 'actuellement', 'à ce jour'],
        'en': ['present', 'current', 'now', 'today', 'ongoing', 'currently', 'to date'],
        'es': ['presente', 'actual', 'hoy', 'ahora', 'en curso', 'actualmente', 'hasta la fecha'],
        'de': ['gegenwart', 'aktuell', 'heute', 'jetzt', 'laufend', 'derzeit', 'bis heute'],
        'it': ['presente', 'attuale', 'oggi', 'ora', 'in corso', 'attualmente', 'ad oggi'],
        'pt': ['presente', 'atual', 'hoje', 'agora', 'em curso', 'atualmente', 'até hoje'],
        'zh': ['现在', '当前', '今天', '目前', '至今', '截至今日'],
        'ar': ['الحاضر', 'الحالي', 'اليوم', 'الآن', 'جاري', 'حاليا', 'حتى اليوم'],
        'he': ['נוכחי', 'עכשווי', 'היום', 'עכשיו', 'נמשך', 'כיום', 'עד היום']
    }
    
    def __init__(self, language: str = 'fr'):
        self.language = language
        self.current_keywords = self.CURRENT_INDICATORS.get(language, self.CURRENT_INDICATORS['fr'])
    
    def normalize_date_range(self, date_range: Optional[DateRange]) -> Tuple[Optional[NormalizedDate], Optional[NormalizedDate]]:
        """Normalise une plage de dates."""
        if not date_range:
            return None, None
        
        # Date de début
        start_normalized = None
        if date_range.start_date:
            start_normalized = NormalizedDate(
                iso_date=date_range.start_date.isoformat(),
                year=date_range.start_date.year,
                month=date_range.start_date.month,
                is_current=False,
                precision='day',
                raw_text=date_range.raw_text,
                confidence=date_range.confidence
            )
        
        # Date de fin
        end_normalized = None
        if date_range.is_current:
            end_normalized = NormalizedDate(
                iso_date=None,
                year=None,
                month=None,
                is_current=True,
                precision='current',
                raw_text=date_range.raw_text,
                confidence=date_range.confidence
            )
        elif date_range.end_date:
            end_normalized = NormalizedDate(
                iso_date=date_range.end_date.isoformat(),
                year=date_range.end_date.year,
                month=date_range.end_date.month,
                is_current=False,
                precision='day',
                raw_text=date_range.raw_text,
                confidence=date_range.confidence
            )
        
        return start_normalized, end_normalized
    
    def detect_current_indicators(self, text: str) -> bool:
        """Détecte si le texte contient des indicateurs de date actuelle."""
        text_lower = text.lower()
        return any(indicator in text_lower for indicator in self.current_keywords)


class LocationNormalizer:
    """Normalisateur de localisations offline."""
    
    # Mapping manuel pour villes principales (offline)
    CITY_MAPPINGS = {
        'fr': {
            'paname': 'Paris',
            'lutece': 'Paris',
            'ville lumiere': 'Paris',
            'marseille': 'Marseille',
            'phocéens': 'Marseille',
            'lyon': 'Lyon',
            'ville des gones': 'Lyon',
            'nice': 'Nice',
            'nissa': 'Nice',
            'toulouse': 'Toulouse',
            'ville rose': 'Toulouse'
        },
        'en': {
            'nyc': 'New York',
            'ny': 'New York',
            'big apple': 'New York',
            'la': 'Los Angeles',
            'city of angels': 'Los Angeles',
            'sf': 'San Francisco',
            'bay area': 'San Francisco',
            'london': 'London',
            'paris': 'Paris'
        }
    }
    
    # Codes pays courants
    COUNTRY_MAPPINGS = {
        'france': 'FR',
        'frança': 'FR',
        'frankreich': 'FR',
        'francia': 'FR',
        'usa': 'US',
        'united states': 'US',
        'états-unis': 'US',
        'america': 'US',
        'uk': 'GB',
        'united kingdom': 'GB',
        'royaume-uni': 'GB',
        'england': 'GB',
        'angleterre': 'GB',
        'germany': 'DE',
        'allemagne': 'DE',
        'deutschland': 'DE',
        'spain': 'ES',
        'espagne': 'ES',
        'españa': 'ES',
        'italy': 'IT',
        'italie': 'IT',
        'italia': 'IT'
    }
    
    def __init__(self, language: str = 'fr'):
        self.language = language
    
    def normalize_location(self, location: Optional[LocationInfo]) -> Optional[NormalizedLocation]:
        """Normalise une localisation."""
        if not location:
            return None
        
        # Nettoyage initial
        raw_text = location.raw_text.strip()
        
        # Extraction ville/pays
        normalized_city = self._normalize_city(location.city) if location.city else None
        normalized_country = self._normalize_country(location.country) if location.country else None
        country_code = None
        
        if normalized_country:
            country_code = self._get_country_code(normalized_country)
        
        return NormalizedLocation(
            city=normalized_city,
            region=location.region,
            country=normalized_country,
            country_code=country_code,
            raw_text=raw_text,
            confidence=location.confidence
        )
    
    def _normalize_city(self, city: str) -> str:
        """Normalise le nom de ville."""
        city_lower = city.lower().strip()
        
        # Mapping manuel
        city_mappings = self.CITY_MAPPINGS.get(self.language, {})
        if city_lower in city_mappings:
            return city_mappings[city_lower]
        
        # Nettoyage basique
        # Supprimer caractères spéciaux, normaliser casse
        clean_city = re.sub(r'[^\w\s-]', '', city).strip().title()
        
        return clean_city
    
    def _normalize_country(self, country: str) -> str:
        """Normalise le nom de pays."""
        country_lower = country.lower().strip()
        
        # Mapping manuel d'abord
        if country_lower in self.COUNTRY_MAPPINGS:
            country_code = self.COUNTRY_MAPPINGS[country_lower]
            try:
                country_obj = pycountry.countries.get(alpha_2=country_code)
                return country_obj.name if country_obj else country.title()
            except:
                pass
        
        # Essayer lookup direct pycountry
        try:
            # Par nom
            country_obj = pycountry.countries.get(name=country.title())
            if country_obj:
                return country_obj.name
            
            # Par nom officiel
            country_obj = pycountry.countries.get(official_name=country.title())
            if country_obj:
                return country_obj.name
                
        except:
            pass
        
        return country.title()  # Fallback
    
    def _get_country_code(self, country_name: str) -> Optional[str]:
        """Récupère le code pays ISO."""
        try:
            country_obj = pycountry.countries.get(name=country_name)
            return country_obj.alpha_2 if country_obj else None
        except:
            return None


class ContactNormalizer:
    """Normalisateur de contacts avec validation."""
    
    def __init__(self, default_region: str = 'FR'):
        self.default_region = default_region
    
    def normalize_contact(self, personal_info: Optional[ExtractedPersonalInfo]) -> Optional[NormalizedContact]:
        """Normalise et valide les informations de contact."""
        if not personal_info:
            return None
        
        # Email
        email_valid = False
        normalized_email = None
        if personal_info.email:
            normalized_email, email_valid = self._validate_email(personal_info.email)
        
        # Téléphone
        phone_valid = False
        phone_formatted = None
        phone_country = None
        phone_carrier = None
        
        if personal_info.phone:
            phone_formatted, phone_country, phone_carrier, phone_valid = self._validate_phone(personal_info.phone)
        
        return NormalizedContact(
            email=normalized_email,
            email_valid=email_valid,
            phone=personal_info.phone,
            phone_formatted=phone_formatted,
            phone_country=phone_country,
            phone_carrier=phone_carrier,
            phone_valid=phone_valid
        )
    
    def _validate_email(self, email: str) -> Tuple[Optional[str], bool]:
        """Valide et normalise un email."""
        try:
            validated = validate_email(email)
            return validated.email, True
        except EmailNotValidError:
            # Tentative nettoyage basique
            cleaned = re.sub(r'\s+', '', email.lower())
            try:
                validated = validate_email(cleaned)
                return validated.email, True
            except EmailNotValidError:
                return email, False
    
    def _validate_phone(self, phone: str) -> Tuple[Optional[str], Optional[str], Optional[str], bool]:
        """Valide et normalise un numéro de téléphone."""
        try:
            # Nettoyage initial
            cleaned_phone = re.sub(r'[^\d+()]', '', phone)
            
            # Parse avec région par défaut
            parsed_phone = phonenumbers.parse(cleaned_phone, self.default_region)
            
            if phonenumbers.is_valid_number(parsed_phone):
                formatted = phonenumbers.format_number(parsed_phone, phonenumbers.PhoneNumberFormat.E164)
                country = geocoder.description_for_number(parsed_phone, 'fr')
                carrier_name = carrier.name_for_number(parsed_phone, 'fr')
                
                return formatted, country, carrier_name, True
            else:
                return phone, None, None, False
                
        except Exception as e:
            logger.debug(f"Erreur validation téléphone {phone}: {e}")
            return phone, None, None, False


class LanguageNormalizer:
    """Normalisateur de niveaux de langues vers CECR."""
    
    # Mappings vers niveaux CECR
    CEFR_MAPPINGS = {
        'fr': {
            'débutant': 'A1',
            'faux débutant': 'A1',
            'élémentaire': 'A2',
            'pré-intermédiaire': 'A2',
            'intermédiaire': 'B1',
            'intermédiaire supérieur': 'B2',
            'avancé': 'B2',
            'confirmé': 'C1',
            'courant': 'C1',
            'expert': 'C2',
            'bilingue': 'C2',
            'natif': 'C2',
            'langue maternelle': 'C2',
            'notions': 'A1',
            'bonnes notions': 'A2',
            'lu, écrit': 'B1',
            'lu, écrit, parlé': 'B2'
        },
        'en': {
            'beginner': 'A1',
            'elementary': 'A2',
            'pre-intermediate': 'A2',
            'intermediate': 'B1',
            'upper-intermediate': 'B2',
            'advanced': 'B2',
            'proficient': 'C1',
            'fluent': 'C1',
            'expert': 'C2',
            'bilingual': 'C2',
            'native': 'C2',
            'mother tongue': 'C2',
            'basic': 'A1',
            'conversational': 'B1',
            'business level': 'B2',
            'professional': 'C1'
        }
    }
    
    def __init__(self, language: str = 'fr'):
        self.language = language
        self.mappings = self.CEFR_MAPPINGS.get(language, self.CEFR_MAPPINGS['fr'])
    
    def normalize_languages(self, languages: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """Normalise les niveaux de langues vers CECR."""
        normalized_languages = []
        
        for lang_entry in languages:
            language_name = lang_entry.get('language', '')
            level_text = lang_entry.get('level', '')
            existing_cefr = lang_entry.get('cefr_level')
            
            # Si CECR déjà présent et valide, le garder
            if existing_cefr and existing_cefr in ['A1', 'A2', 'B1', 'B2', 'C1', 'C2']:
                cefr_level = existing_cefr
                confidence = 1.0
            else:
                # Mapper vers CECR
                cefr_level, confidence = self._map_to_cefr(level_text)
            
            normalized_lang = {
                'language': self._normalize_language_name(language_name),
                'level_text': level_text,
                'cefr_level': cefr_level,
                'confidence': confidence,
                'source': 'mapped' if not existing_cefr else 'extracted'
            }
            
            normalized_languages.append(normalized_lang)
        
        return normalized_languages
    
    def _map_to_cefr(self, level_text: str) -> Tuple[Optional[str], float]:
        """Mappe un niveau textuel vers CECR."""
        if not level_text:
            return None, 0.0
        
        level_lower = level_text.lower().strip()
        
        # Recherche exacte
        if level_lower in self.mappings:
            return self.mappings[level_lower], 0.9
        
        # Recherche partielle
        for text_level, cefr_level in self.mappings.items():
            if text_level in level_lower or level_lower in text_level:
                return cefr_level, 0.7
        
        # Patterns CECR directs
        cefr_match = re.search(r'\b([ABC][12])\b', level_text.upper())
        if cefr_match:
            return cefr_match.group(1), 1.0
        
        return None, 0.0
    
    def _normalize_language_name(self, language: str) -> str:
        """Normalise le nom de langue."""
        language = language.strip().lower()
        
        # Mappings courants
        name_mappings = {
            'fr': 'français',
            'francais': 'français',
            'french': 'français',
            'en': 'anglais',
            'english': 'anglais',
            'ang': 'anglais',
            'es': 'espagnol',
            'spanish': 'espagnol',
            'esp': 'espagnol',
            'de': 'allemand',
            'german': 'allemand',
            'deutsch': 'allemand',
            'it': 'italien',
            'italian': 'italien',
            'pt': 'portugais',
            'portuguese': 'portugais'
        }
        
        return name_mappings.get(language, language.title())


class JobTitleNormalizer:
    """Normalisateur d'intitulés de postes (optionnel)."""
    
    # Mini-taxonomie intégrée
    JOB_CATEGORIES = {
        'development': [
            'développeur', 'developer', 'programmeur', 'programmer',
            'ingénieur logiciel', 'software engineer', 'dev'
        ],
        'management': [
            'manager', 'chef', 'directeur', 'director', 'responsable',
            'lead', 'head', 'supervisor', 'coordinateur'
        ],
        'design': [
            'designer', 'graphiste', 'ux', 'ui', 'design',
            'créatif', 'artistic', 'visual'
        ],
        'consulting': [
            'consultant', 'conseil', 'expert', 'advisor',
            'specialist', 'spécialiste'
        ]
    }
    
    def normalize_job_title(self, title: str) -> Dict[str, Any]:
        """Normalise un intitulé de poste."""
        if not title:
            return {'original': title, 'normalized': title, 'category': None, 'seniority': None}
        
        title_lower = title.lower()
        
        # Détection séniorité
        seniority = None
        if any(word in title_lower for word in ['senior', 'sr', 'confirmé', 'expérimenté']):
            seniority = 'senior'
        elif any(word in title_lower for word in ['junior', 'jr', 'débutant', 'stagiaire']):
            seniority = 'junior'
        elif any(word in title_lower for word in ['lead', 'principal', 'chef', 'head']):
            seniority = 'lead'
        
        # Détection catégorie
        category = None
        for cat, keywords in self.JOB_CATEGORIES.items():
            if any(keyword in title_lower for keyword in keywords):
                category = cat
                break
        
        # Nettoyage basique
        normalized_title = title.strip().title()
        
        return {
            'original': title,
            'normalized': normalized_title,
            'category': category,
            'seniority': seniority,
            'confidence': 0.8 if category else 0.5
        }


class CVNormalizer:
    """Normalisateur principal pour données CV extraites."""
    
    def __init__(self, language: str = 'fr', default_region: str = 'FR'):
        self.language = language
        self.date_normalizer = DateNormalizer(language)
        self.location_normalizer = LocationNormalizer(language)
        self.contact_normalizer = ContactNormalizer(default_region)
        self.language_normalizer = LanguageNormalizer(language)
        self.job_title_normalizer = JobTitleNormalizer()
    
    def normalize_extracted_data(self, data: ExtractedData) -> Dict[str, Any]:
        """
        Normalisation complète des données extraites.
        
        Args:
            data: Données extraites brutes
            
        Returns:
            Dict avec données normalisées et métadonnées
        """
        logger.info("🔧 Normalisation des données extraites")
        
        normalized = {
            'personal_info': self._normalize_personal_info(data.personal_info),
            'summary': data.summary,
            'experiences': self._normalize_experiences(data.experiences),
            'education': self._normalize_education(data.education),
            'skills': data.skills,  # Pas de normalisation spéciale pour l'instant
            'languages': self.language_normalizer.normalize_languages(data.languages),
            'projects': data.projects,
            'certifications': data.certifications,
            'awards': data.awards,
            'volunteering': data.volunteering,
            'interests': data.interests,
            'references': data.references,
            'normalization_metadata': {
                'language': self.language,
                'normalized_at': datetime.now().isoformat(),
                'normalizers_used': [
                    'dates', 'locations', 'contacts', 'languages', 'job_titles'
                ]
            }
        }
        
        logger.info("✅ Normalisation terminée")
        return normalized
    
    def _normalize_personal_info(self, personal_info: Optional[ExtractedPersonalInfo]) -> Optional[Dict[str, Any]]:
        """Normalise les informations personnelles."""
        if not personal_info:
            return None
        
        # Contacts normalisés
        normalized_contact = self.contact_normalizer.normalize_contact(personal_info)
        
        # Location normalisée
        normalized_location = None
        if personal_info.location:
            normalized_location = self.location_normalizer.normalize_location(personal_info.location)
        
        return {
            'full_name': personal_info.full_name,
            'first_name': personal_info.first_name,
            'last_name': personal_info.last_name,
            'contact': asdict(normalized_contact) if normalized_contact else None,
            'location': asdict(normalized_location) if normalized_location else None,
            'linkedin_url': personal_info.linkedin_url,
            'portfolio_url': personal_info.portfolio_url,
            'github_url': personal_info.github_url,
            'confidence_score': personal_info.confidence_score
        }
    
    def _normalize_experiences(self, experiences: List[ExtractedExperience]) -> List[Dict[str, Any]]:
        """Normalise les expériences professionnelles."""
        normalized_experiences = []
        
        for exp in experiences:
            # Dates normalisées
            start_date, end_date = self.date_normalizer.normalize_date_range(exp.date_range)
            
            # Location normalisée
            normalized_location = None
            if exp.location:
                normalized_location = self.location_normalizer.normalize_location(exp.location)
            
            # Titre de poste normalisé
            normalized_title = None
            if exp.title:
                normalized_title = self.job_title_normalizer.normalize_job_title(exp.title)
            
            normalized_exp = {
                'title': exp.title,
                'title_normalized': normalized_title,
                'company': exp.company,
                'location': asdict(normalized_location) if normalized_location else None,
                'dates': {
                    'start_date': asdict(start_date) if start_date else None,
                    'end_date': asdict(end_date) if end_date else None,
                    'duration_months': self._calculate_duration_months(start_date, end_date)
                },
                'description': exp.description,
                'responsibilities': exp.responsibilities,
                'achievements': exp.achievements,
                'technologies': exp.technologies,
                'team_size': exp.team_size,
                'budget_managed': exp.budget_managed,
                'confidence_score': exp.confidence_score,
                'extraction_source': exp.extraction_source
            }
            
            normalized_experiences.append(normalized_exp)
        
        return normalized_experiences
    
    def _normalize_education(self, education: List[ExtractedEducation]) -> List[Dict[str, Any]]:
        """Normalise les formations."""
        normalized_education = []
        
        for edu in education:
            # Dates normalisées
            start_date, end_date = self.date_normalizer.normalize_date_range(edu.date_range)
            
            # Location normalisée
            normalized_location = None
            if edu.location:
                normalized_location = self.location_normalizer.normalize_location(edu.location)
            
            normalized_edu = {
                'degree': edu.degree,
                'institution': edu.institution,
                'location': asdict(normalized_location) if normalized_location else None,
                'dates': {
                    'start_date': asdict(start_date) if start_date else None,
                    'end_date': asdict(end_date) if end_date else None,
                    'duration_months': self._calculate_duration_months(start_date, end_date)
                },
                'grade': edu.grade,
                'specialization': edu.specialization,
                'confidence_score': edu.confidence_score
            }
            
            normalized_education.append(normalized_edu)
        
        return normalized_education
    
    def _calculate_duration_months(
        self, 
        start_date: Optional[NormalizedDate], 
        end_date: Optional[NormalizedDate]
    ) -> Optional[int]:
        """Calcule la durée en mois entre deux dates."""
        if not start_date or not start_date.year:
            return None
        
        # Date de fin = maintenant si current
        if end_date and end_date.is_current:
            end_year = datetime.now().year
            end_month = datetime.now().month
        elif end_date and end_date.year:
            end_year = end_date.year
            end_month = end_date.month or 12
        else:
            return None
        
        start_year = start_date.year
        start_month = start_date.month or 1
        
        # Calcul simple en mois
        duration = (end_year - start_year) * 12 + (end_month - start_month)
        return max(duration, 0)
