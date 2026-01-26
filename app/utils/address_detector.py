"""
Address Detector - Détecte les adresses et coordonnées pour éviter les faux positifs
"""

import re
from typing import List, Tuple, Set
from ..logging.safe_logger import get_safe_logger
from ..config import DEFAULT_PII_CONFIG

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


class AddressDetector:
    """Détecte les adresses et informations de contact pour éviter les faux positifs."""
    
    def __init__(self):
        self.logger = get_safe_logger(f"{__name__}.AddressDetector", cfg=DEFAULT_PII_CONFIG)
        
        # Patterns d'adresses françaises
        self.address_patterns = [
            # Numéros et noms de rues
            r'\b\d+\s+(rue|avenue|av|boulevard|bd|place|pl|cours|allée|impasse|chemin|route)\s+',
            r'\b(rue|avenue|av|boulevard|bd|place|pl|cours|allée|impasse|chemin|route)\s+[\w\s]+\d+',
            
            # Codes postaux et villes  
            r'\b\d{5}\s+[A-Z][a-z]+',  # 75020 Paris
            r'\b[A-Z][a-z]+\s+\d{5}',  # Paris 75020
            r'\bCedex\s+\d+',          # Cedex 04
            
            # Coordonnées téléphoniques
            r'\b(tel|tél|téléphone|phone|mobile|fixe)\b',
            r'\b0[1-9](\s|-|\.|\d){8,9}\b',  # Numéros français
            r'\+33\s*[1-9](\s|-|\.|\d){8,9}',
            
            # Éléments d'adresse spécifiques
            r'\b(domicile|adresse|address|contact)\b',
            r'\b(appartement|apt|étage|ème|er)\b',
        ]
        
        # Headers de sections à éviter
        self.section_headers = [
            "ACTIVITÉS EXTRA-PROFESSIONNELLES",
            "ACTIVITÉS EXTRA",
            "FORMATION", 
            "FORMATIONS",
            "ÉDUCATION",
            "EDUCATION", 
            "EXPÉRIENCE PROFESSIONNELLE",
            "EXPÉRIENCES PROFESSIONNELLES",
            "EXPÉRIENCES",
            "COMPÉTENCES",
            "COMPETENCES",
            "LANGUES",
            "LANGUAGES",
            "CENTRES D'INTÉRÊT",
            "CENTRES D'INTERET",
            "INTÉRÊTS",
            "INTERETS",
            "CERTIFICATIONS",
            "PROJETS",
            "PROJECTS",
            "RÉFÉRENCES",
            "REFERENCES"
        ]
        
        # Mots-clés d'adresse
        self.address_keywords = {
            'street': ['rue', 'avenue', 'av', 'boulevard', 'bd', 'place', 'pl', 'cours', 'allée', 'impasse', 'chemin', 'route'],
            'contact': ['tel', 'tél', 'téléphone', 'phone', 'mobile', 'fixe', 'domicile', 'adresse', 'contact'],
            'postal': ['cedex', 'cp', 'code postal'],
            'location': ['étage', 'ème', 'er', 'appartement', 'apt', 'bâtiment', 'bat']
        }
        
        # Compile patterns pour performance
        self.compiled_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in self.address_patterns]
        self.section_headers_normalized = [header.lower().strip() for header in self.section_headers]
        
        # Job title keywords that should NOT be considered as address elements
        self.job_title_keywords = [
            'developer', 'dev', 'engineer', 'ingenieur', 'consultant', 'manager', 'chef',
            'lead', 'senior', 'junior', 'analyst', 'architect', 'designer', 'specialist',
            'coordinator', 'director', 'responsable', 'technicien', 'full stack', 'backend',
            'frontend', 'data scientist', 'product manager', 'project manager'
        ]
    
    def _is_job_title_false_positive(self, text_normalized: str, detected_keyword: str) -> bool:
        """
        Vérifie si un mot-clé d'adresse détecté est en fait dans un titre de poste.
        
        Args:
            text_normalized: Texte normalisé en minuscules
            detected_keyword: Mot-clé d'adresse détecté
            
        Returns:
            True si c'est un faux positif (titre de poste), False sinon
        """
        # Si le texte contient des mots-clés de titre de poste, on filtre certains patterns
        has_job_keywords = any(job_keyword in text_normalized for job_keyword in self.job_title_keywords)
        
        if has_job_keywords:
            # Ces mots sont souvent des faux positifs dans les titres de poste et noms d'entreprises
            problematic_keywords = ['er', 'eme', 'contact', 'mobile']
            if detected_keyword in problematic_keywords:
                self.logger.debug(f"ADDRESS_DETECTOR: filtered_job_title_fp | text='{text_normalized[:30]}...' keyword='{detected_keyword}'")
                return True
                
        # Si le texte contient des mots d'entreprise, on filtre certains patterns
        business_keywords = ['inc', 'corp', 'ltd', 'llc', 'technologies', 'solutions', 'systems', 'services']
        has_business_keywords = any(biz_keyword in text_normalized for biz_keyword in business_keywords)
        
        if has_business_keywords:
            # Ces mots sont souvent des faux positifs dans les noms d'entreprise
            business_problematic = ['er', 'eme', 'contact', 'mobile', 'tel']
            if detected_keyword in business_problematic:
                self.logger.debug(f"ADDRESS_DETECTOR: filtered_business_fp | text='{text_normalized[:30]}...' keyword='{detected_keyword}'")
                return True
                
        return False
    
    def is_address_or_contact(self, text: str) -> Tuple[bool, List[str]]:
        """
        Détermine si un texte est une adresse ou information de contact.
        
        Args:
            text: Texte à analyser
            
        Returns:
            (is_address, detected_indicators)
        """
        if not text:
            return False, []
            
        text_normalized = text.lower().strip()
        indicators = []
        
        # Vérifier les patterns compilés
        for i, pattern in enumerate(self.compiled_patterns):
            if pattern.search(text):
                indicators.append(f"pattern_{i}")
        
        # Vérifier les mots-clés par catégorie (avec filtres pour éviter faux positifs)
        for category, keywords in self.address_keywords.items():
            for keyword in keywords:
                if keyword in text_normalized:
                    # HARDENED: Filter out false positives in job titles
                    if self._is_job_title_false_positive(text_normalized, keyword):
                        continue
                    indicators.append(f"{category}:{keyword}")
        
        # Vérifier codes postaux français
        if re.search(r'\b\d{5}\b', text):
            indicators.append("postal_code")
            
        # Vérifier numéros de téléphone
        if re.search(r'\b0[1-9][\s\-\.0-9]{8,9}\b', text):
            indicators.append("phone_number")
            
        is_address = len(indicators) > 0
        
        if is_address:
            self.logger.debug(f"ADDRESS_DETECTED: text='{text[:30]}...' indicators={indicators}")
            
        return is_address, indicators
    
    def is_section_header(self, text: str) -> Tuple[bool, str]:
        """
        Détermine si un texte est un header de section.
        
        Args:
            text: Texte à analyser
            
        Returns:
            (is_header, matched_header)
        """
        if not text:
            return False, ""
            
        text_normalized = text.lower().strip()
        
        for header in self.section_headers_normalized:
            if text_normalized == header or header in text_normalized:
                self.logger.debug(f"SECTION_HEADER: detected='{header}' in '{text[:30]}...'")
                return True, header
                
        return False, ""
    
    def contains_geographic_info(self, text: str) -> bool:
        """Vérifie si le texte contient des informations géographiques."""
        if not text:
            return False
            
        # Indicateurs géographiques communs
        geo_patterns = [
            r'\b\d{5}\s+[A-Z]',  # Code postal + ville
            r'\bFrance\b',
            r'\bParis\b',
            r'\bLyon\b', 
            r'\bMarseille\b',
            r'\bToulouse\b',
            r'\bNice\b',
            r'\bNantes\b',
            r'\bStrasbourg\b',
            r'\bMontpellier\b',
            r'\bBordeaux\b',
            r'\bLille\b'
        ]
        
        for pattern in geo_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
                
        return False
    
    def extract_address_elements(self, text: str) -> dict:
        """
        Extrait les éléments d'adresse d'un texte.
        
        Args:
            text: Texte à analyser
            
        Returns:
            Dict avec les éléments trouvés
        """
        elements = {
            'street_number': None,
            'street_name': None,
            'postal_code': None,
            'city': None,
            'phone': None,
            'keywords': []
        }
        
        if not text:
            return elements
            
        # Extraire code postal
        postal_match = re.search(r'\b(\d{5})\b', text)
        if postal_match:
            elements['postal_code'] = postal_match.group(1)
        
        # Extraire numéro de téléphone
        phone_match = re.search(r'\b(0[1-9][\s\-\.0-9]{8,9})\b', text)
        if phone_match:
            elements['phone'] = phone_match.group(1)
            
        # Extraire mots-clés d'adresse
        for category, keywords in self.address_keywords.items():
            for keyword in keywords:
                if keyword in text.lower():
                    elements['keywords'].append(f"{category}:{keyword}")
                    
        return elements


def get_address_detector() -> AddressDetector:
    """Singleton pour le détecteur d'adresses."""
    if not hasattr(get_address_detector, '_instance'):
        get_address_detector._instance = AddressDetector()
    return get_address_detector._instance