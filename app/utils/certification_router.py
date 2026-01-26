"""
Routeur de certifications avec normalisation et correction d'orthographe.
Implémente la logique de routage PIX, TOEFL, etc. avec fuzzy matching.
"""

import re
from typing import List, Dict, Any, Optional, Tuple
from ..logging.safe_logger import get_safe_logger
from ..config import DEFAULT_PII_CONFIG, CERT_CANON, CERT_TYPO
from .experience_filters import normalize_text_for_matching

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


class CertificationRouter:
    """Routeur intelligent pour les certifications avec correction d'orthographe."""
    
    def __init__(self):
        self.canonical_certs = CERT_CANON
        self.typo_corrections = CERT_TYPO
        self.logger = get_safe_logger(f"{__name__}.CertificationRouter", cfg=DEFAULT_PII_CONFIG)
    
    def normalize_certification_name(self, cert_text: str) -> Optional[str]:
        """
        Normalise et corrige le nom d'une certification.
        
        Args:
            cert_text: Texte potentiel de certification
        
        Returns:
            Nom canonique de la certification ou None si pas trouvé
        """
        if not cert_text:
            return None
        
        normalized = normalize_text_for_matching(cert_text)
        
        # Étape 1: Corrections typographiques
        for typo, correct in self.typo_corrections.items():
            if typo in normalized:
                self.logger.debug(f"CERT_TYPO: corrected | '{typo}' -> '{correct}' in '{cert_text}'")
                normalized = normalized.replace(typo, correct)
        
        # Étape 2: Correspondances canoniques
        for canon_cert in self.canonical_certs:
            canon_normalized = normalize_text_for_matching(canon_cert)
            if canon_normalized in normalized:
                self.logger.debug(f"CERT_CANONICAL: matched | '{canon_cert}' in '{cert_text}'")
                # Retourner la version en majuscules pour PIX, TOEFL, etc.
                normalized_canon = canon_cert
                if canon_cert.islower() and canon_cert.lower() not in {'pix', 'toefl', 'toeic', 'ielts'}:
                    normalized_canon = canon_cert.title()
                if normalized_canon.lower() in {'pix', 'toefl', 'toeic', 'ielts'}:
                    return normalized_canon.upper()
                return normalized_canon
        
        return None
    
    def is_certification_text(self, text: str, context_lines: List[str] = None, line_idx: int = -1) -> bool:
        """
        Vérifie si un texte fait référence à une certification.
        
        Args:
            text: Texte à vérifier
            context_lines: Lignes de contexte pour vérification étendue
            line_idx: Index de la ligne dans le contexte
        
        Returns:
            True si le texte est une certification
        """
        # Vérification directe
        if self.normalize_certification_name(text):
            return True
        
        # Vérification dans le contexte élargi (±2 lignes)
        if context_lines and line_idx >= 0:
            start_idx = max(0, line_idx - 2)
            end_idx = min(len(context_lines), line_idx + 3)
            
            for i in range(start_idx, end_idx):
                if i < len(context_lines) and self.normalize_certification_name(context_lines[i]):
                    self.logger.debug(f"CERT_CONTEXT: certification_detected | line_idx={i} context_distance={abs(i - line_idx)}")
                    return True
        
        return False
    
    def extract_certification_details(self, text: str, context_lines: List[str] = None, line_idx: int = -1) -> Optional[Dict[str, Any]]:
        """
        Extrait les détails d'une certification depuis le texte.
        
        Args:
            text: Texte de la certification
            context_lines: Lignes de contexte pour extraction d'informations supplémentaires
            line_idx: Index de ligne pour contexte
        
        Returns:
            Dictionnaire avec les détails de la certification ou None
        """
        canonical_name = self.normalize_certification_name(text)
        if not canonical_name:
            return None
        
        # Extraction des détails de base
        cert_details = {
            "name": canonical_name,
            "original_text": text.strip(),
            "issuer": "",
            "level": "",
            "score": "",
            "date": "",
            "source": "cv"
        }
        
        # Extraction de l'organisme émetteur depuis NER ou patterns
        issuer = self._extract_issuer(text, context_lines, line_idx)
        if issuer:
            cert_details["issuer"] = issuer
        
        # Extraction du niveau ou score
        level, score = self._extract_level_and_score(text, context_lines, line_idx)
        if level:
            cert_details["level"] = level
        if score:
            cert_details["score"] = score
        
        # Extraction de la date
        date = self._extract_certification_date(text, context_lines, line_idx)
        if date:
            cert_details["date"] = date
        
        self.logger.info(f"CERT_EXTRACTED: name='{canonical_name}' level='{level}' issuer='{issuer}' date='{date}'")
        
        return cert_details
    
    def _extract_issuer(self, text: str, context_lines: List[str] = None, line_idx: int = -1) -> str:
        """Extrait l'organisme émetteur d'une certification."""
        # Patterns d'organismes connus
        issuer_patterns = [
            r'\b(ETS|Educational Testing Service)\b',  # TOEFL/TOEIC
            r'\b(Cambridge|University of Cambridge)\b',  # Cambridge
            r'\b(British Council|IELTS)\b',  # IELTS
            r'\b(PIX|GIP PIX)\b',  # PIX
            r'\b(AWS|Amazon Web Services)\b',  # AWS
            r'\b(Microsoft|Azure)\b',  # Microsoft
            r'\b(Google|GCP)\b',  # Google
            r'\b(Coursera|edX|OpenClassrooms)\b',  # MOOCs
        ]
        
        # Recherche dans le texte principal
        for pattern in issuer_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)
        
        # Recherche dans le contexte si disponible
        if context_lines and line_idx >= 0:
            start_idx = max(0, line_idx - 1)
            end_idx = min(len(context_lines), line_idx + 2)
            
            for i in range(start_idx, end_idx):
                if i < len(context_lines):
                    for pattern in issuer_patterns:
                        match = re.search(pattern, context_lines[i], re.IGNORECASE)
                        if match:
                            return match.group(1)
        
        return ""
    
    def _extract_level_and_score(self, text: str, context_lines: List[str] = None, line_idx: int = -1) -> Tuple[str, str]:
        """Extrait le niveau et/ou score d'une certification."""
        level = ""
        score = ""
        
        # Patterns pour niveaux CECRL
        level_patterns = [
            r'\bniveau\s*([ABC][12])\b',
            r'\b([ABC][12])\s*niveau\b', 
            r'\b(beginner|elementary|intermediate|upper[- ]?intermediate|advanced|proficiency)\b',
            r'\b(débutant|élémentaire|intermédiaire|avancé|maîtrise)\b'
        ]
        
        # Patterns pour scores
        score_patterns = [
            r'\bscore[:\s]*(\d{2,3})\b',
            r'\b(\d{2,3})\s*(?:points?|pts?)\b',
            r'\b(\d{2,3})\s*(?:/\s*\d{2,3})?\s*(?:sur|out of)\s*\d{2,3}\b'
        ]
        
        # Recherche de niveau
        full_text = text
        if context_lines and line_idx >= 0:
            # Inclure le contexte pour une recherche plus large
            context_start = max(0, line_idx - 1)
            context_end = min(len(context_lines), line_idx + 2)
            full_text = " ".join(context_lines[context_start:context_end])
        
        for pattern in level_patterns:
            match = re.search(pattern, full_text, re.IGNORECASE)
            if match:
                level = match.group(1).upper()
                break
        
        # Recherche de score
        for pattern in score_patterns:
            match = re.search(pattern, full_text, re.IGNORECASE)
            if match:
                score = match.group(1)
                break
        
        return level, score
    
    def _extract_certification_date(self, text: str, context_lines: List[str] = None, line_idx: int = -1) -> str:
        """Extrait la date d'obtention d'une certification."""
        # Patterns de dates pour certifications
        date_patterns = [
            r'\bobtention\s+(?:en\s+)?([A-Za-z]+\s+\d{4})\b',
            r'\b(?:obtenu|obtained|passed)\s+(?:in|en)\s+([A-Za-z]+\s+\d{4})\b',
            r'\b([A-Za-z]+\s+\d{4})\s*\)',
            r'\b(\d{1,2}/\d{1,2}/\d{4})\b',
            r'\b(\d{4})\b'
        ]
        
        full_text = text
        if context_lines and line_idx >= 0:
            context_start = max(0, line_idx - 1) 
            context_end = min(len(context_lines), line_idx + 2)
            full_text = " ".join(context_lines[context_start:context_end])
        
        for pattern in date_patterns:
            match = re.search(pattern, full_text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        return ""
    
    def force_route_to_certifications(self, text: str, context_lines: List[str] = None, line_idx: int = -1) -> bool:
        """
        Détermine si un texte doit être forcé vers la section certifications.

        Cette fonction implémente la "routing rule (hard)" du prompt.
        """
        if self.is_certification_text(text, context_lines, line_idx):
            self.logger.info(f"CERT_FORCE_ROUTE: certification_detected | text='{text[:50]}...'")
            return True
        
        return False
        
    def run_pre_merge_detection(self, text_lines: List[str], 
                               entities: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Run certification detection BEFORE experience merges (new requirement).
        
        Args:
            text_lines: List of text lines
            entities: Optional NER entities
            
        Returns:
            Dict with detected certifications and stop_tags for lines to exclude from experience seeds
        """
        detected_certifications = []
        stop_tags = set()  # Line indices to exclude from experience processing
        
        for i, line in enumerate(text_lines):
            if not line.strip():
                continue
                
            # Check if line contains certification
            if self.is_certification_text(line, text_lines, i):
                cert_details = self.extract_certification_details(line, text_lines, i)
                
                if cert_details:
                    # Add canonical issuer inference if not already present
                    if not cert_details.get('issuer'):
                        cert_details['issuer'] = self._infer_issuer_from_canonical(cert_details['name'])
                    
                    # Check for date precision requirement
                    date_precision = self._get_date_precision(cert_details.get('date', ''))
                    if date_precision in ['year', 'month', 'day']:  # Accept year precision for certs
                        detected_certifications.append({
                            **cert_details,
                            'line_idx': i,
                            'date_precision': date_precision,
                            'stage': 'pre_merge'
                        })
                        
                        # Add stop tag to prevent this line from seeding experiences
                        stop_tags.add(i)
                        
                        self.logger.info(f"CERT_PRE_MERGE: detected | line={i} name='{cert_details['name']}' "
                                       f"issuer='{cert_details.get('issuer', 'unknown')}' "
                                       f"date_precision='{date_precision}'")
        
        return {
            'detected_certifications': detected_certifications,
            'stop_tags': stop_tags,
            'pre_merge_count': len(detected_certifications)
        }
        
    def _infer_issuer_from_canonical(self, canonical_name: str) -> str:
        """Infer issuer from canonical certification name."""
        canonical_lower = canonical_name.lower()
        
        issuer_map = {
            'toefl': 'ETS',
            'toeic': 'ETS', 
            'cambridge': 'University of Cambridge',
            'ielts': 'British Council',
            'pix': 'GIP PIX',
            'aws certified': 'Amazon Web Services',
            'azure': 'Microsoft',
            'gcp': 'Google',
            'google': 'Google',
            'cisco': 'Cisco',
            'microsoft': 'Microsoft',
            'oracle': 'Oracle',
            'comptia': 'CompTIA'
        }
        
        for cert_key, issuer in issuer_map.items():
            if cert_key in canonical_lower:
                return issuer
                
        return ''
        
    def _get_date_precision(self, date_str: str) -> str:
        """Determine the precision of a date string."""
        if not date_str:
            return 'none'
            
        # Year only
        if re.match(r'^\d{4}$', date_str.strip()):
            return 'year'
            
        # Month and year
        if re.match(r'^\d{1,2}/\d{4}$|^[A-Za-z]+\s+\d{4}$', date_str.strip()):
            return 'month'
            
        # Full date
        if re.match(r'^\d{1,2}/\d{1,2}/\d{4}$', date_str.strip()):
            return 'day'
            
        return 'unknown'
        
    def should_exclude_from_experience_seeds(self, line_text: str, line_idx: int, 
                                           context_lines: List[str] = None) -> bool:
        """
        Check if a line should be excluded from experience seed generation.
        
        This prevents certification tokens from seeding experience merges.
        """
        return self.is_certification_text(line_text, context_lines, line_idx)
    
    def split_education_certifications(self, education_items: List[Dict[str, Any]], *, min_confidence: float = 0.0, **kwargs) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Backward-compatible alias for legacy API expecting split results."""
        cleaned, extracted = self.clean_education_certifications(education_items)
        return cleaned, extracted

    def clean_education_certifications(self, education_items: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Nettoie la section éducation en extrayant les certifications mal classées.

        Args:
            education_items: Liste des éléments d'éducation

        Returns:
            Tuple (education_cleaned, extracted_certifications)
        """
        cleaned_education = []
        extracted_certifications = []
        
        for edu_item in education_items:
            degree = edu_item.get('degree', '')
            school = edu_item.get('school', '')
            
            # Vérifier si le diplôme commence par "- Certification"
            if degree.strip().startswith('- Certification'):
                cert_text = degree.replace('- Certification', '').strip()
                cert_details = self.extract_certification_details(cert_text)
                
                if cert_details:
                    # Préserver l'école comme émetteur si pas d'émetteur détecté
                    if not cert_details.get('issuer') and school:
                        cert_details['issuer'] = school
                    
                    # Préserver les dates
                    if not cert_details.get('date') and edu_item.get('start_date'):
                        cert_details['date'] = edu_item.get('start_date')
                    
                    extracted_certifications.append(cert_details)
                    self.logger.info(f"CERT_EDUCATION_CLEANUP: moved_to_cert | degree='{degree}' -> name='{cert_details['name']}'")
                    continue
            
            # Vérifier si le diplôme contient des termes de certification canoniques
            canonical_name = self.normalize_certification_name(degree)
            if canonical_name:
                cert_details = self.extract_certification_details(degree)
                if cert_details:
                    if not cert_details.get('issuer') and school:
                        cert_details['issuer'] = school
                    if not cert_details.get('date') and edu_item.get('start_date'):
                        cert_details['date'] = edu_item.get('start_date')
                    
                    extracted_certifications.append(cert_details)
                    self.logger.info(f"CERT_EDUCATION_CLEANUP: canonical_moved | degree='{degree}' -> name='{canonical_name}'")
                    continue
            
            # Conserver l'élément d'éducation
            cleaned_education.append(edu_item)
        
        self.logger.info(f"CERT_EDUCATION_CLEANUP: summary | education_before={len(education_items)} education_after={len(cleaned_education)} certifications_extracted={len(extracted_certifications)}")
        
        return cleaned_education, extracted_certifications


def create_certification_router() -> CertificationRouter:
    """Factory function pour créer un routeur de certifications."""
    return CertificationRouter()


# Fonction utilitaire pour la compatibilité
def normalize_certification_name(cert_text: str) -> Optional[str]:
    """Fonction utilitaire pour normaliser un nom de certification."""
    router = create_certification_router()
    return router.normalize_certification_name(cert_text)


def is_certification_text(text: str) -> bool:
    """Fonction utilitaire pour vérifier si un texte est une certification."""
    router = create_certification_router()
    return router.is_certification_text(text)


def try_extract(lines: List[str], ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Offline heuristic certification router.
    
    Args:
        lines: List of text lines to analyze
        ctx: Extraction context with metadata
        
    Returns:
        List of extracted certification items or empty list
        
    Note:
        This function provides deterministic offline extraction with no network calls.
        PII must be masked upstream before calling this function.
    """
    if not lines:
        return []
    
    router = create_certification_router()
    certifications = []
    
    for i, line in enumerate(lines):
        text = line.strip()
        if not text:
            continue
        
        # Check if line contains certification text
        if router.is_certification_text(text):
            # Extract certification details
            context_lines = []
            if i > 0:
                context_lines.append(lines[i-1])
            context_lines.append(text)
            if i < len(lines) - 1:
                context_lines.append(lines[i+1])
            
            certification = router.extract_certification_details(
                text, context_lines, i
            )
            
            if certification:
                # Add metadata from context
                certification['line_idx'] = i
                certification['confidence'] = ctx.get('confidence', 0.8)
                certification['source'] = 'heuristic'
                certifications.append(certification)
    
    logger.info(f"CERT_TRY_EXTRACT: processed {len(lines)} lines | found {len(certifications)} certifications")
    return certifications


# Alias pour compatibilité avec l'interface "enhanced" attendue
create_enhanced_certification_router = create_certification_router
