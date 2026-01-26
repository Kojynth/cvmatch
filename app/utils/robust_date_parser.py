"""
Robust Date Parser
=================

Parser de dates robuste avec support :
- Unicode dashes (–, —, -)
- Mois multilingues FR/EN
- "À ce jour" patterns (ongoing/present/current)
- OCR tolerance pour tokens bruités
"""

import re
from typing import List, Optional, Tuple, Dict, Any
from dataclasses import dataclass
from datetime import datetime, date
from enum import Enum
from ..logging.safe_logger import get_safe_logger
from ..config import DEFAULT_PII_CONFIG

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)

class DateType(Enum):
    """Types de dates détectées"""
    RANGE = "range"           # 2020-2023
    ONGOING = "ongoing"       # 2020-présent  
    SINGLE = "single"         # 2023
    DURATION = "duration"     # 6 mois
    RELATIVE = "relative"     # depuis 2020

@dataclass
class ParsedDate:
    """Résultat de parsing de date"""
    original_text: str
    date_type: DateType
    start_year: Optional[int] = None
    end_year: Optional[int] = None
    start_month: Optional[int] = None
    end_month: Optional[int] = None
    is_current: bool = False
    duration_months: Optional[int] = None
    confidence: float = 0.0
    normalized_text: str = ""

# Mapping des mois FR/EN vers numéros
MONTH_MAPPING = {
    # Français
    'janvier': 1, 'jan': 1,
    'février': 2, 'fév': 2, 'feb': 2,
    'mars': 3, 'mar': 3,
    'avril': 4, 'avr': 4, 'apr': 4,
    'mai': 5, 'may': 5,
    'juin': 6, 'jun': 6,
    'juillet': 7, 'juil': 7, 'jul': 7,
    'août': 8, 'aou': 8, 'aug': 8,
    'septembre': 9, 'sep': 9, 'sept': 9,
    'octobre': 10, 'oct': 10,
    'novembre': 11, 'nov': 11,
    'décembre': 12, 'déc': 12, 'dec': 12,
    
    # English
    'january': 1, 'february': 2, 'march': 3, 'april': 4,
    'june': 6, 'july': 7, 'august': 8, 'september': 9,
    'october': 10, 'november': 11, 'december': 12
}

# Patterns "ongoing/current"
ONGOING_PATTERNS = {
    # Français
    'présent', 'present', 'actuel', 'actuellement', 'aujourd\'hui',
    'à ce jour', 'ce jour', 'maintenant', 'en cours',
    
    # English
    'now', 'current', 'currently', 'present', 'ongoing', 
    'today', 'to date', 'up to now'
}

# Unicode dashes normalization
DASH_VARIANTS = {
    '–': '-',  # en dash
    '—': '-',  # em dash  
    '−': '-',  # minus sign
    '‒': '-',  # figure dash
    '⁃': '-',  # hyphen bullet
    '﹣': '-'   # small em dash
}

# OCR error corrections communes
OCR_CORRECTIONS = {
    # Numbers
    'O': '0', 'o': '0', 'l': '1', 'I': '1', 'S': '5', 'G': '6',
    
    # Letters that can be mistaken for numbers in dates
    'ZOZO': '2020', 'ZOZ1': '2021', 'ZOZ2': '2022', 'ZOZ3': '2023',
    'l9': '19', '2O': '20'
}

class RobustDateParser:
    """
    ENHANCED: Parser de dates robuste avec normalisation OCR et Unicode

    Nouvelles fonctionnalités:
    - Support complet des formats français dd/mm/yyyy
    - Validation de proximité role/org
    - Prévention des titres en dates pures
    - Gestion des années ambiguës (2-digit)
    - Chronologie enforcement
    """

    def __init__(self):
        self.month_mapping = MONTH_MAPPING
        self.ongoing_patterns = ONGOING_PATTERNS
        self.dash_variants = DASH_VARIANTS
        self.ocr_corrections = OCR_CORRECTIONS

        # Enhanced French date patterns
        self.french_date_patterns = [
            # DD/MM/YYYY - DD/MM/YYYY
            r'\b(\d{1,2})/(\d{1,2})/(\d{2,4})\s*[-–—]\s*(\d{1,2})/(\d{1,2})/(\d{2,4})\b',
            # DD/MM/YYYY - présent/actuel
            r'\b(\d{1,2})/(\d{1,2})/(\d{2,4})\s*[-–—]\s*(présent|actuel|à\s+ce\s+jour|en\s+cours)\b',
            # Année YYYY-YYYY (with french context)
            r'\b(?:année\s+)?(\d{4})\s*[-–—]\s*(\d{4})\b',
            # Année YYYY/YYYY
            r'\b(?:année\s+)?(\d{4})/(\d{4})\b',
            # Depuis MM/YYYY
            r'\bdepuis\s+(\d{1,2})/(\d{4})\b',
            # Depuis YYYY
            r'\bdepuis\s+(\d{4})\b',
        ]

        # Role/org proximity patterns for validation
        self.role_patterns = [
            r'\b(?:développeur|ingénieur|chef|responsable|manager|directeur|consultant)\b',
            r'\b(?:developer|engineer|manager|analyst|consultant|director|lead)\b',
            r'\b(?:stage|stagiaire|alternant|apprenti|intern|trainee)\b',
            r'\b(?:assistant|coordinateur|technicien|specialist|officer)\b'
        ]

        self.org_patterns = [
            r'\b(?:chez|at|pour|with|dans|in)\s+[A-Z][a-zA-Z\s&]{2,30}\b',
            r'\b[A-Z][a-zA-Z\s&]*(?:\s+(?:SARL|SAS|SASU|SA|EURL|SCI|Ltd|Inc|Corp|LLC))\b',
            r'\b(?:société|entreprise|compagnie|groupe|cabinet|studio|agence)\s+[A-Z][a-zA-Z\s&]+\b',
        ]
    
    def parse_dates_from_text(self, text: str, line_context: List[str] = None, 
                             target_line_idx: int = None) -> List[ParsedDate]:
        """
        Parse toutes les dates d'un texte avec contexte de ligne étendu
        
        Args:
            text: Texte à parser
            line_context: Liste des lignes pour contexte bi-directionnel
            target_line_idx: Index de la ligne cible pour fenêtre étendue
            
        Returns:
            Liste des dates trouvées avec contexte étendu
        """
        if not text or not text.strip():
            return []
        
        # Step 1: Normalize Unicode and OCR errors
        normalized_text = self._normalize_text(text)
        
        # Step 2: Find all date patterns with enhanced French support
        all_matches = []

        # NEW: French-specific patterns first (highest priority)
        all_matches.extend(self._find_french_date_patterns(normalized_text))

        # Enhanced range patterns with French formats
        all_matches.extend(self._find_enhanced_range_patterns(normalized_text))

        # Range patterns (2020-2023, 2020–present)
        all_matches.extend(self._find_range_patterns(normalized_text))

        # Single year patterns (2023) - with pure date title prevention
        all_matches.extend(self._find_single_year_patterns(normalized_text))

        # Month-year patterns (janvier 2020, Jan 2023)
        all_matches.extend(self._find_month_year_patterns(normalized_text))

        # Duration patterns (6 mois, 2 ans)
        all_matches.extend(self._find_duration_patterns(normalized_text))

        # Relative patterns (depuis 2020, from 2021)
        all_matches.extend(self._find_relative_patterns(normalized_text))

        # Step 2.5: Bi-directional context search if line context provided
        if line_context and target_line_idx is not None:
            context_matches = self._find_dates_with_bidirectional_context(
                line_context, target_line_idx, window=4
            )
            all_matches.extend(context_matches)
        
        # Step 3: Deduplicate and sort by confidence
        deduplicated = self._deduplicate_dates(all_matches)
        
        # Step 4: Validate and normalize
        validated = [self._validate_and_enrich(date_match) for date_match in deduplicated]
        
        return [d for d in validated if d.confidence > 0.3]

    def _find_french_date_patterns(self, text: str) -> List[ParsedDate]:
        """
        Find French-specific date patterns with enhanced DD/MM/YYYY support.

        Args:
            text: Normalized text to search

        Returns:
            List of parsed dates with French-specific patterns
        """
        matches = []

        for pattern in self.french_date_patterns:
            regex_matches = re.finditer(pattern, text, re.IGNORECASE)

            for match in regex_matches:
                groups = match.groups()

                if 'dd/mm/yyyy' in pattern.lower() and len(groups) >= 6:
                    # DD/MM/YYYY - DD/MM/YYYY pattern
                    start_day, start_month, start_year = int(groups[0]), int(groups[1]), self._normalize_year(groups[2])
                    end_day, end_month, end_year = int(groups[3]), int(groups[4]), self._normalize_year(groups[5])

                    parsed_date = ParsedDate(
                        original_text=match.group(0),
                        date_type=DateType.RANGE,
                        start_year=start_year,
                        end_year=end_year,
                        start_month=start_month,
                        end_month=end_month,
                        is_current=False,
                        confidence=0.95,  # High confidence for explicit DD/MM/YYYY
                        normalized_text=f"{start_day:02d}/{start_month:02d}/{start_year} - {end_day:02d}/{end_month:02d}/{end_year}"
                    )
                    matches.append(parsed_date)

                elif len(groups) >= 3 and groups[3] in ['présent', 'actuel', 'à ce jour', 'en cours']:
                    # DD/MM/YYYY - présent pattern
                    start_day, start_month, start_year = int(groups[0]), int(groups[1]), self._normalize_year(groups[2])

                    parsed_date = ParsedDate(
                        original_text=match.group(0),
                        date_type=DateType.ONGOING,
                        start_year=start_year,
                        end_year=None,
                        start_month=start_month,
                        end_month=None,
                        is_current=True,
                        confidence=0.95,
                        normalized_text=f"{start_day:02d}/{start_month:02d}/{start_year} - présent"
                    )
                    matches.append(parsed_date)

                elif 'année' in pattern.lower() and len(groups) >= 2:
                    # Année YYYY-YYYY or YYYY/YYYY patterns
                    start_year = self._normalize_year(groups[0])
                    end_year = self._normalize_year(groups[1])

                    parsed_date = ParsedDate(
                        original_text=match.group(0),
                        date_type=DateType.RANGE,
                        start_year=start_year,
                        end_year=end_year,
                        start_month=None,  # Don't default to January for year-only spans
                        end_month=None,
                        is_current=False,
                        confidence=0.85,
                        normalized_text=f"Année {start_year}-{end_year}"
                    )
                    matches.append(parsed_date)

                elif 'depuis' in pattern.lower():
                    # Depuis YYYY or depuis MM/YYYY patterns
                    if '/' in groups[0]:
                        # MM/YYYY format
                        month_year = groups[0].split('/')
                        start_month, start_year = int(month_year[0]), int(month_year[1])
                    else:
                        # YYYY only
                        start_month, start_year = None, self._normalize_year(groups[0])

                    parsed_date = ParsedDate(
                        original_text=match.group(0),
                        date_type=DateType.ONGOING,
                        start_year=start_year,
                        end_year=None,
                        start_month=start_month,
                        end_month=None,
                        is_current=True,
                        confidence=0.80,
                        normalized_text=f"Depuis {groups[0]}"
                    )
                    matches.append(parsed_date)

                logger.debug(f"FRENCH_DATE: found pattern | pattern='{pattern}' "
                           f"original='{match.group(0)}' groups={groups}")

        return matches

    def validate_proximity_context(self, date_candidate: ParsedDate,
                                 line_context: List[str],
                                 target_line_idx: int,
                                 proximity_window: int = 4) -> Dict[str, Any]:
        """
        Validate that a date candidate has role/organization context within proximity.

        Args:
            date_candidate: Parsed date candidate
            line_context: List of text lines for context search
            target_line_idx: Target line index
            proximity_window: Lines to search around target (default 4)

        Returns:
            Dict with validation results and context information
        """
        if not line_context or target_line_idx < 0:
            return {'valid': False, 'reason': 'no_context'}

        start_idx = max(0, target_line_idx - proximity_window)
        end_idx = min(len(line_context), target_line_idx + proximity_window + 1)

        context_lines = line_context[start_idx:end_idx]
        context_text = ' '.join(context_lines).lower()

        # Check for role indicators
        role_found = False
        for pattern in self.role_patterns:
            if re.search(pattern, context_text, re.IGNORECASE):
                role_found = True
                break

        # Check for organization indicators
        org_found = False
        for pattern in self.org_patterns:
            if re.search(pattern, context_text, re.IGNORECASE):
                org_found = True
                break

        # Require at least one of {role, organization} within proximity
        has_context = role_found or org_found

        result = {
            'valid': has_context,
            'role_found': role_found,
            'org_found': org_found,
            'proximity_window': proximity_window,
            'lines_analyzed': len(context_lines)
        }

        if not has_context:
            result['reason'] = 'no_role_org_proximity'
            logger.debug(f"PROXIMITY_VALIDATION: failed | date='{date_candidate.original_text}' "
                        f"target_line={target_line_idx} window={proximity_window} "
                        f"role_found={role_found} org_found={org_found}")
        else:
            logger.debug(f"PROXIMITY_VALIDATION: passed | date='{date_candidate.original_text}' "
                        f"role_found={role_found} org_found={org_found}")

        return result

    def prevent_pure_date_titles(self, text: str) -> bool:
        """
        Prevent pure date strings like "07/06/22" or "2023" from being used as titles.

        Args:
            text: Text to check

        Returns:
            True if text is a pure date and should not be a title
        """
        text = text.strip()

        # Pure date patterns that should not be titles
        pure_date_patterns = [
            r'^\d{1,2}/\d{1,2}/\d{2,4}$',  # DD/MM/YY(YY)
            r'^\d{4}$',  # YYYY
            r'^\d{1,2}/\d{4}$',  # MM/YYYY
            r'^Année\s+\d{4}$',  # Année YYYY
        ]

        for pattern in pure_date_patterns:
            if re.match(pattern, text, re.IGNORECASE):
                logger.debug(f"PURE_DATE_PREVENTION: blocked_as_title | text='{text}' pattern='{pattern}'")
                return True

        return False

    def _normalize_year(self, year_str: str) -> int:
        """
        Normalize year string handling 2-digit years with reasonable cutoff.

        Args:
            year_str: Year string to normalize

        Returns:
            Normalized 4-digit year
        """
        try:
            year = int(year_str)

            if year < 100:  # 2-digit year
                current_year = datetime.now().year
                century_cutoff = 50

                if year <= century_cutoff:
                    # Assume 20xx
                    year += 2000
                else:
                    # Assume 19xx
                    year += 1900

                logger.debug(f"YEAR_NORMALIZATION: 2digit_to_4digit | input='{year_str}' output={year}")

            return year
        except ValueError:
            logger.warning(f"YEAR_NORMALIZATION: invalid_year | input='{year_str}'")
            return None

    def _find_enhanced_range_patterns(self, text: str) -> List[ParsedDate]:
        """
        Find enhanced French date range patterns
        
        Args:
            text: Normalized text to search
            
        Returns:
            List of parsed date ranges with French patterns
        """
        matches = []
        
        # Enhanced French patterns
        enhanced_patterns = [
            # Format Année 20XX-20XX, Année 20XX–20XX  
            r'Année\s+(\d{4})[-–—](\d{4})',
            # MM/YYYY–MM/YYYY, MM/YYYY–présent
            r'(\d{1,2}/\d{4})[-–—](\d{1,2}/\d{4}|présent|present|en cours|current)',
            # MM/YYYY–à ce jour 
            r'(\d{1,2}/\d{4})[-–—]à\s+ce\s+jour',
            # depuis MM/YYYY, depuis YYYY
            r'depuis\s+(\d{1,2}/\d{4}|\d{4})',
            # More flexible year ranges with various separators
            r'(\d{4})\s*[-–—/→▶►]\s*(\d{4}|présent|present|en cours|current)',
        ]
        
        for pattern in enhanced_patterns:
            regex_matches = re.finditer(pattern, text, re.IGNORECASE)
            
            for match in regex_matches:
                groups = match.groups()
                
                if len(groups) >= 1:
                    start_text = groups[0]
                    end_text = groups[1] if len(groups) > 1 else None
                    
                    # Parse start date
                    start_year = self._extract_year(start_text)
                    start_month = self._extract_month(start_text)
                    
                    # Parse end date
                    is_current = False
                    end_year = None
                    end_month = None
                    
                    if end_text:
                        if any(ongoing in end_text.lower() for ongoing in 
                               ['présent', 'present', 'en cours', 'current', 'à ce jour',
                                'maintenant', 'now', 'today', 'ongoing', 'actuel', 'actuellement']):
                            is_current = True
                        else:
                            end_year = self._extract_year(end_text)
                            end_month = self._extract_month(end_text)
                    
                    if start_year:
                        parsed_date = ParsedDate(
                            original_text=match.group(0),
                            date_type=DateType.ONGOING if is_current else DateType.RANGE,
                            start_year=start_year,
                            end_year=end_year,
                            start_month=start_month,
                            end_month=end_month,
                            is_current=is_current,
                            confidence=0.9,  # High confidence for explicit patterns
                            normalized_text=self._normalize_date_text(match.group(0))
                        )
                        matches.append(parsed_date)
                        
                        logger.debug(f"ENHANCED_DATE: found range | pattern='{pattern}' "
                                   f"original='{match.group(0)}' parsed={parsed_date.start_year}-"
                                   f"{parsed_date.end_year or 'ongoing'}")
        
        return matches
    
    def _find_dates_with_bidirectional_context(self, text_lines: List[str], 
                                             target_line_idx: int, 
                                             window: int = 24) -> List[ParsedDate]:
        """
        Find dates with bidirectional context search around target line
        
        Args:
            text_lines: List of text lines
            target_line_idx: Target line index
            window: Search window in lines (default 24)
            
        Returns:
            List of dates found with bidirectional context
        """
        matches = []
        
        start_idx = max(0, target_line_idx - window)
        end_idx = min(len(text_lines), target_line_idx + window + 1)
        
        logger.debug(f"BIDIRECTIONAL_DATE: searching around line {target_line_idx} | "
                    f"window=[{start_idx}:{end_idx}] size={window}")
        
        for i in range(start_idx, end_idx):
            if i >= len(text_lines):
                continue
                
            line = text_lines[i].strip()
            if not line:
                continue
            
            # Parse dates from this line
            line_dates = self.parse_dates_from_text(line)
            
            # Enhance with line context information
            for date in line_dates:
                # Adjust confidence based on distance from target
                distance = abs(i - target_line_idx)
                distance_factor = max(0.5, 1.0 - (distance / window))
                date.confidence *= distance_factor
                
                # Look for role/company indicators in adjacent lines
                context_strength = self._analyze_context_strength(text_lines, i)
                date.confidence *= context_strength
                
                if date.confidence > 0.3:  # Only keep confident matches
                    matches.append(date)
                    logger.debug(f"BIDIRECTIONAL_DATE: found contextual date | "
                               f"line={i} distance={distance} strength={context_strength:.2f} "
                               f"final_confidence={date.confidence:.2f}")
        
        return matches
    
    def _analyze_context_strength(self, text_lines: List[str], line_idx: int) -> float:
        """
        Analyze context strength around a date by looking for role/company indicators
        
        Args:
            text_lines: List of text lines
            line_idx: Current line index with date
            
        Returns:
            Context strength multiplier (0.5-1.5)
        """
        context_window = 3  # Look 3 lines before/after
        strength = 1.0
        
        start_ctx = max(0, line_idx - context_window)
        end_ctx = min(len(text_lines), line_idx + context_window + 1)
        
        # Role indicators
        role_patterns = [
            r'\b(?:développeur|developer|ingénieur|engineer|responsable|manager|chef|director)\b',
            r'\b(?:consultant|analyst|architecte|architect|lead|senior|junior)\b',
            r'\b(?:stagiaire|intern|apprenti|apprentice|alternant)\b'
        ]
        
        # Company indicators  
        company_patterns = [
            r'\b(?:chez|at|company|entreprise|société|group|corp|inc|ltd|sarl|sas)\b',
            r'\b[A-Z][A-Za-z\s&]{2,20}(?:\s+(?:SARL|SAS|SA|Inc|Corp|Ltd))\b'
        ]
        
        role_found = False
        company_found = False
        
        for i in range(start_ctx, end_ctx):
            if i >= len(text_lines) or i == line_idx:
                continue
                
            line = text_lines[i].lower()
            
            # Check for role indicators
            for pattern in role_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    role_found = True
                    break
            
            # Check for company indicators
            for pattern in company_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    company_found = True
                    break
        
        # Adjust strength based on context
        if role_found and company_found:
            strength = 1.3  # Strong context
        elif role_found or company_found:
            strength = 1.1  # Moderate context
        else:
            strength = 0.8  # Weak context
        
        return strength
    
    def _normalize_text(self, text: str) -> str:
        """Normalise le texte : Unicode dashes + OCR corrections"""
        normalized = text
        
        # Normalize Unicode dashes
        for unicode_dash, standard_dash in self.dash_variants.items():
            normalized = normalized.replace(unicode_dash, standard_dash)
        
        # OCR corrections for common date errors
        for error, correction in self.ocr_corrections.items():
            # Only apply if it looks like it's in a date context
            if re.search(r'\b' + re.escape(error) + r'\b', normalized):
                # Check if surrounded by likely date context (years, months)
                pattern = r'\b' + re.escape(error) + r'\b'
                if re.search(r'(?:19|20)\d{0,2}.*' + pattern + r'|' + pattern + r'.*(?:19|20)\d{0,2}', normalized):
                    normalized = re.sub(pattern, correction, normalized)
        
        # Normalize common separators
        normalized = re.sub(r'\s*[/àa]\s*', ' à ', normalized)  # "01/2020" -> "01 à 2020"
        normalized = re.sub(r'\s+', ' ', normalized)  # Multiple spaces
        
        return normalized.strip()
    
    def _extract_year(self, text: str) -> Optional[int]:
        """Extract year from text string"""
        year_match = re.search(r'\b(19|20)(\d{2})\b', text)
        if year_match:
            return int(year_match.group(0))
        return None
    
    def _extract_month(self, text: str) -> Optional[int]:
        """Extract month number from text string"""
        for month_name, month_num in self.month_mapping.items():
            if month_name.lower() in text.lower():
                return month_num
        
        # Try numeric month format MM/YYYY
        month_match = re.search(r'\b(\d{1,2})/\d{4}\b', text)
        if month_match:
            month = int(month_match.group(1))
            if 1 <= month <= 12:
                return month
        return None
    
    def _normalize_date_text(self, text: str) -> str:
        """Normalize date text for display"""
        return re.sub(r'\s+', ' ', text.strip())
    
    def _find_range_patterns(self, text: str) -> List[ParsedDate]:
        """Trouve les patterns de plages de dates"""
        matches = []
        
        # Pattern 1: 2020-2023, 2020–present, etc.
        range_pattern = r'(\d{4})\s*[-–—]\s*(?:(\d{4})|([a-zA-Zàâäéèêëïîôöùûüÿç\'\s]+))'
        
        for match in re.finditer(range_pattern, text, re.IGNORECASE):
            start_year = int(match.group(1))
            end_year_str = match.group(2)
            ongoing_str = match.group(3)
            
            # Check if end is a year or ongoing indicator
            if end_year_str:
                end_year = int(end_year_str)
                is_current = False
                date_type = DateType.RANGE
            elif ongoing_str:
                is_current = self._is_ongoing_indicator(ongoing_str.strip())
                end_year = datetime.now().year if is_current else None
                date_type = DateType.ONGOING
            else:
                continue
            
            parsed_date = ParsedDate(
                original_text=match.group(0),
                date_type=date_type,
                start_year=start_year,
                end_year=end_year,
                is_current=is_current,
                confidence=0.9
            )
            
            matches.append(parsed_date)
        
        # Pattern 2: Month range (Jan 2020 - Dec 2021)
        month_range_pattern = r'(\w+)\s+(\d{4})\s*[-–—]\s*(\w+)\s+(\d{4})'
        
        for match in re.finditer(month_range_pattern, text, re.IGNORECASE):
            start_month_str = match.group(1).lower()
            start_year = int(match.group(2))
            end_month_str = match.group(3).lower()
            end_year = int(match.group(4))
            
            start_month = self.month_mapping.get(start_month_str)
            end_month = self.month_mapping.get(end_month_str)
            
            if start_month and end_month:
                parsed_date = ParsedDate(
                    original_text=match.group(0),
                    date_type=DateType.RANGE,
                    start_year=start_year,
                    end_year=end_year,
                    start_month=start_month,
                    end_month=end_month,
                    confidence=0.85
                )
                
                matches.append(parsed_date)
        
        return matches
    
    def _find_single_year_patterns(self, text: str) -> List[ParsedDate]:
        """Trouve les patterns d'années simples"""
        matches = []
        
        # Pattern: isolated 4-digit years (19xx, 20xx)
        year_pattern = r'\b(19\d{2}|20\d{2})\b'
        
        for match in re.finditer(year_pattern, text):
            year = int(match.group(1))
            
            # Skip if it's part of a range (already captured)
            before_text = text[max(0, match.start()-5):match.start()]
            after_text = text[match.end():match.end()+5]
            
            if re.search(r'[-–—]\s*$', before_text) or re.search(r'^\s*[-–—]', after_text):
                continue  # Part of range
            
            parsed_date = ParsedDate(
                original_text=match.group(0),
                date_type=DateType.SINGLE,
                start_year=year,
                confidence=0.6
            )
            
            matches.append(parsed_date)
        
        return matches
    
    def _find_month_year_patterns(self, text: str) -> List[ParsedDate]:
        """Trouve les patterns mois-année"""
        matches = []
        
        # Pattern: Month Year (January 2023, janvier 2020)
        month_year_pattern = r'\b(\w+)\s+(\d{4})\b'
        
        for match in re.finditer(month_year_pattern, text, re.IGNORECASE):
            month_str = match.group(1).lower()
            year = int(match.group(2))
            
            month_num = self.month_mapping.get(month_str)
            
            if month_num:
                parsed_date = ParsedDate(
                    original_text=match.group(0),
                    date_type=DateType.SINGLE,
                    start_year=year,
                    start_month=month_num,
                    confidence=0.8
                )
                
                matches.append(parsed_date)
        
        return matches
    
    def _find_duration_patterns(self, text: str) -> List[ParsedDate]:
        """Trouve les patterns de durée"""
        matches = []
        
        # Pattern: X mois, X ans, X years, etc.
        duration_pattern = r'(\d+)\s*(?:mois|months?|ans?|années?|years?)'
        
        for match in re.finditer(duration_pattern, text, re.IGNORECASE):
            duration_num = int(match.group(1))
            duration_unit = match.group(0).lower()
            
            # Convert to months
            if any(unit in duration_unit for unit in ['mois', 'month']):
                duration_months = duration_num
            elif any(unit in duration_unit for unit in ['an', 'year']):
                duration_months = duration_num * 12
            else:
                duration_months = duration_num
            
            parsed_date = ParsedDate(
                original_text=match.group(0),
                date_type=DateType.DURATION,
                duration_months=duration_months,
                confidence=0.7
            )
            
            matches.append(parsed_date)
        
        return matches
    
    def _find_relative_patterns(self, text: str) -> List[ParsedDate]:
        """Trouve les patterns relatifs (depuis, from, etc.)"""
        matches = []
        
        # Pattern: depuis/from/pendant + year
        relative_pattern = r'(?:depuis|from|pendant|during|for)\s+(\d{4}|\w+\s+\d{4})'
        
        for match in re.finditer(relative_pattern, text, re.IGNORECASE):
            date_part = match.group(1)
            
            # Try to extract year
            year_match = re.search(r'(\d{4})', date_part)
            if year_match:
                year = int(year_match.group(1))
                
                parsed_date = ParsedDate(
                    original_text=match.group(0),
                    date_type=DateType.RELATIVE,
                    start_year=year,
                    is_current=True,  # Relative dates are usually ongoing
                    confidence=0.75
                )
                
                matches.append(parsed_date)
        
        return matches
    
    def _is_ongoing_indicator(self, text: str) -> bool:
        """Vérifie si le texte indique une date ongoing"""
        text_lower = text.lower().strip()
        
        return any(pattern in text_lower for pattern in self.ongoing_patterns)
    
    def _deduplicate_dates(self, dates: List[ParsedDate]) -> List[ParsedDate]:
        """Déduplique les dates par similarité"""
        if not dates:
            return dates
        
        # Sort by confidence descending
        sorted_dates = sorted(dates, key=lambda d: d.confidence, reverse=True)
        
        deduplicated = []
        
        for date_candidate in sorted_dates:
            is_duplicate = False
            
            for existing_date in deduplicated:
                if self._are_dates_similar(date_candidate, existing_date):
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                deduplicated.append(date_candidate)
        
        return deduplicated
    
    def _are_dates_similar(self, date1: ParsedDate, date2: ParsedDate) -> bool:
        """Vérifie si deux dates sont similaires (duplicates)"""
        # Same years (start and end)
        if (date1.start_year == date2.start_year and 
            date1.end_year == date2.end_year):
            return True
        
        # Overlapping text (>50% common words)
        words1 = set(date1.original_text.lower().split())
        words2 = set(date2.original_text.lower().split())
        
        if words1 and words2:
            common_words = words1.intersection(words2)
            similarity = len(common_words) / max(len(words1), len(words2))
            if similarity > 0.5:
                return True
        
        return False
    
    def _validate_and_enrich(self, parsed_date: ParsedDate) -> ParsedDate:
        """Valide et enrichit une date parsée"""
        current_year = datetime.now().year
        
        # Validation des années
        if parsed_date.start_year:
            if parsed_date.start_year < 1950 or parsed_date.start_year > current_year + 1:
                parsed_date.confidence *= 0.5  # Penalize unrealistic years
        
        if parsed_date.end_year:
            if parsed_date.end_year < 1950 or parsed_date.end_year > current_year + 5:
                parsed_date.confidence *= 0.5
            
            # Validate range order
            if parsed_date.start_year and parsed_date.end_year < parsed_date.start_year:
                parsed_date.confidence *= 0.3  # Invalid range
        
        # Normalize text
        parsed_date.normalized_text = self._normalize_date_text(parsed_date.original_text)
        
        # Adjust confidence based on date type
        confidence_adjustments = {
            DateType.RANGE: 0.1,      # Bonus for ranges
            DateType.ONGOING: 0.05,   # Small bonus for ongoing
            DateType.SINGLE: 0.0,     # No adjustment
            DateType.DURATION: -0.1,  # Small penalty (less specific)
            DateType.RELATIVE: 0.0    # No adjustment
        }
        
        adjustment = confidence_adjustments.get(parsed_date.date_type, 0)
        parsed_date.confidence = max(0.0, min(1.0, parsed_date.confidence + adjustment))
        
        return parsed_date
    
    def _normalize_date_text(self, text: str) -> str:
        """Normalise le texte de date pour affichage"""
        normalized = text
        
        # Replace dashes with standard dash
        for dash_variant in self.dash_variants.keys():
            normalized = normalized.replace(dash_variant, '-')
        
        # Normalize spaces
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        
        return normalized


# Factory functions
def parse_dates(text: str) -> List[ParsedDate]:
    """
    Factory function pour parser les dates d'un texte
    
    Args:
        text: Texte à parser
        
    Returns:
        Liste des dates trouvées
    """
    parser = RobustDateParser()
    return parser.parse_dates_from_text(text)


def extract_date_range(text: str) -> Optional[Tuple[int, Optional[int], bool]]:
    """
    Extrait la plage de dates principale d'un texte
    
    Returns:
        Tuple (start_year, end_year, is_current) ou None
    """
    dates = parse_dates(text)
    
    if not dates:
        return None
    
    # Find the best range or ongoing date
    range_dates = [d for d in dates if d.date_type in [DateType.RANGE, DateType.ONGOING]]
    
    if range_dates:
        best_date = max(range_dates, key=lambda d: d.confidence)
        return (best_date.start_year, best_date.end_year, best_date.is_current)
    
    # Fallback to single dates
    single_dates = [d for d in dates if d.date_type == DateType.SINGLE]
    if single_dates:
        best_date = max(single_dates, key=lambda d: d.confidence)
        return (best_date.start_year, None, False)
    
    return None


def normalize_date_text(text: str) -> str:
    """
    Normalise un texte contenant des dates
    
    Args:
        text: Texte à normaliser
        
    Returns:
        Texte avec dates normalisées
    """
    parser = RobustDateParser()
    return parser._normalize_text(text)


def detect_ongoing_date(text: str) -> bool:
    """
    Détecte si le texte contient une indication de date ongoing
    
    Returns:
        True si ongoing détecté
    """
    parser = RobustDateParser()
    dates = parser.parse_dates_from_text(text)
    
    return any(d.is_current for d in dates)


def parse_dates_with_validation(text: str, context_lines: List[str] = None, 
                               context_window: List[str] = None) -> Tuple[Optional[str], Optional[str], bool, Dict[str, Any]]:
    """
    Parse les dates d'un texte avec validation contextuelle.
    
    Args:
        text: Texte contenant potentiellement des dates
        context_lines: Lignes de contexte pour validation (alias de context_window)
        context_window: Lignes de contexte pour validation
        
    Returns:
        Tuple (start_date, end_date, is_current, validation_flags)
        - start_date: Date de début au format str ou None
        - end_date: Date de fin au format str ou None  
        - is_current: True si la date est ongoing/current
        - validation_flags: Dict avec informations de validation
    """
    if not text or not text.strip():
        return None, None, False, {'valid': False, 'reason': 'empty_text'}
    
    # Handle both parameter names for context
    context = context_window or context_lines or []
    
    # Parse dates using existing robust parser
    parser = RobustDateParser()
    dates = parser.parse_dates_from_text(text)
    
    if not dates:
        return None, None, False, {'valid': False, 'reason': 'no_dates_found'}
    
    # Find the best date (highest confidence)
    best_date = max(dates, key=lambda d: d.confidence)
    
    # Prepare validation flags
    validation_flags = {
        'valid': True,
        'confidence': best_date.confidence,
        'date_type': best_date.date_type.value,
        'original_text': best_date.original_text,
        'normalized_text': best_date.normalized_text,
        'context_validation': False
    }
    
    # Context validation if provided
    if context:
        context_text = ' '.join(context).lower()
        
        # Check for additional date indicators in context
        has_date_context = any(indicator in context_text for indicator in [
            'depuis', 'from', 'à', 'until', 'pendant', 'during', 'en', 'in'
        ])
        
        validation_flags['context_validation'] = has_date_context
        
        # Bonus confidence if good context
        if has_date_context:
            validation_flags['confidence'] = min(1.0, validation_flags['confidence'] + 0.1)
    
    # Format output dates
    start_date = None
    end_date = None
    is_current = best_date.is_current
    
    if best_date.start_year:
        if best_date.start_month:
            start_date = f"{best_date.start_month:02d}/{best_date.start_year}"
        else:
            start_date = str(best_date.start_year)
    
    if best_date.end_year:
        if best_date.end_month:
            end_date = f"{best_date.end_month:02d}/{best_date.end_year}"
        else:
            end_date = str(best_date.end_year)
    elif best_date.is_current:
        end_date = "present"
    
    # Additional validation checks
    current_year = datetime.now().year
    
    if best_date.start_year and (best_date.start_year < 1950 or best_date.start_year > current_year + 1):
        validation_flags['valid'] = False
        validation_flags['reason'] = 'invalid_start_year'
    
    if best_date.end_year and (best_date.end_year < 1950 or best_date.end_year > current_year + 5):
        validation_flags['valid'] = False
        validation_flags['reason'] = 'invalid_end_year'
    
    if (best_date.start_year and best_date.end_year and 
        best_date.end_year < best_date.start_year):
        validation_flags['valid'] = False
        validation_flags['reason'] = 'invalid_date_range'
    
    # Mark as invalid if confidence too low
    if validation_flags['confidence'] < 0.3:
        validation_flags['valid'] = False
        validation_flags['reason'] = 'low_confidence'
    
    logger.debug(f"DATE_VALIDATION: text='{text[:30]}...' start='{start_date}' end='{end_date}' current={is_current} valid={validation_flags['valid']}")
    
    return start_date, end_date, is_current, validation_flags
