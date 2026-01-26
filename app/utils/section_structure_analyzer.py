"""
Section Structure Analyzer (SSA) - Enhanced Contact Quarantine & Layout Detection
===============================================================================

Analyzes document structure to provide extraction guidance and prevent contamination:
- Contact/header block detection with quarantine zones
- Multi-column/sidebar/timeline detection
- RTL/LTR reading order detection
- Header alias mapping across languages
- Date position analysis
- Layout inversion detection
- Cross-column adjacency barriers

Supports multilingual documents including RTL scripts (Arabic, Hebrew)
and CJK languages with proper Unicode handling.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Tuple, Set
from collections import defaultdict, Counter

try:
    from ..config_thresholds.extraction_thresholds import DEFAULT_EXTRACTION_THRESHOLDS, EMAIL_PATTERNS, PHONE_PATTERNS, URL_PATTERNS
except ImportError:
    # Fallback if extraction_thresholds not available
    class DefaultThresholds:
        CONTACT_DENSITY_THRESHOLD = 0.6
        CONTACT_POST_BUFFER_LINES = 8
        HEADER_DETECTION_WINDOW = 10
        TIMELINE_DENSITY_THRESHOLD = 0.45
        SIDEBAR_WIDTH_RATIO = 0.25
        SCRIPT_DIRECTION_AUTO = True
        RTL_HEURISTICS = True
        DEBUG_SECTION_BOUNDARIES = False
    
    DEFAULT_EXTRACTION_THRESHOLDS = DefaultThresholds()
    EMAIL_PATTERNS = [r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b']
    PHONE_PATTERNS = [r'\+?[\d\s\(\)\-\.]{8,20}']
    URL_PATTERNS = [r'https?://[^\s]+', r'www\.[^\s]+']

from ..logging.safe_logger import get_safe_logger, DEFAULT_PII_CONFIG

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


@dataclass
class ContactBlock:
    """Represents a detected contact information block."""
    start_line: int
    end_line: int
    contact_density: float
    contact_types: Set[str]
    confidence: float


@dataclass  
class SectionStructure:
    """Represents detected document structure for extraction guidance."""
    is_inverted: bool = False
    date_position: str = "before_content"  # "before_content" | "after_content" | "mixed"
    columns: int = 1
    column_barriers: List[Tuple[int, int]] = field(default_factory=list)
    header_spans: List[Dict[str, Any]] = field(default_factory=list)
    reading_order: str = "ltr"  # "ltr" | "rtl" | "mixed"
    layout_confidence: float = 0.0
    # NEW: Contact quarantine zones
    contact_block_range: Optional[Tuple[int, int]] = None
    contact_quarantine_zones: List[Tuple[int, int]] = field(default_factory=list)
    script_direction: str = "LTR"  # "LTR" | "RTL" | "mixed"
    is_timeline: bool = False
    is_table: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization.""" 
        return {
            'is_inverted': self.is_inverted,
            'date_position': self.date_position,
            'columns': self.columns,
            'column_barriers': self.column_barriers,
            'header_spans': self.header_spans,
            'reading_order': self.reading_order,
            'layout_confidence': self.layout_confidence,
            'contact_block_range': self.contact_block_range,
            'contact_quarantine_zones': self.contact_quarantine_zones,
            'script_direction': self.script_direction,
            'is_timeline': self.is_timeline,
            'is_table': self.is_table
        }


class SectionStructureAnalyzer:
    """Analyzes document layout structure for extraction optimization."""
    
    def __init__(self, config=None):
        self.config = config or DEFAULT_EXTRACTION_THRESHOLDS
        
        # RTL scripts detection patterns
        self.rtl_scripts = {'Arab', 'Hebr', 'Syrc', 'Thaa'}
        self.cjk_scripts = {'Han', 'Hira', 'Kana', 'Hang'}
        
        # Compiled regex patterns for performance
        self._email_patterns = [re.compile(p, re.IGNORECASE) for p in EMAIL_PATTERNS]
        self._phone_patterns = [re.compile(p, re.IGNORECASE) for p in PHONE_PATTERNS]  
        self._url_patterns = [re.compile(p, re.IGNORECASE) for p in URL_PATTERNS]
        
        # Multilingual header aliases
        self.header_aliases = {
            'experience': {
                'en': ['experience', 'work experience', 'professional experience', 'employment history'],
                'fr': ['expérience', 'expérience professionnelle', 'parcours professionnel'],
                'es': ['experiencia', 'experiencia profesional', 'historial laboral'],
                'de': ['berufserfahrung', 'arbeitserfahrung', 'beruflicher werdegang'],
                'ar': ['الخبرة', 'الخبرة المهنية', 'التاريخ المهني'],
                'he': ['ניסיון', 'ניסיון מקצועי', 'רקע מקצועי'],
                'zh': ['工作经验', '职业经历', '从业经历']
            },
            'education': {
                'en': ['education', 'academic background', 'qualifications'],
                'fr': ['formation', 'études', 'parcours académique'],
                'es': ['educación', 'formación', 'estudios'],
                'de': ['ausbildung', 'bildung', 'studium'],
                'ar': ['التعليم', 'المؤهلات', 'الدراسة'],
                'he': ['השכלה', 'רקע אקדמי', 'לימודים'],
                'zh': ['教育背景', '学历', '教育经历']
            },
            'skills': {
                'en': ['skills', 'competencies', 'technical skills'],
                'fr': ['compétences', 'savoir-faire', 'aptitudes'],
                'es': ['habilidades', 'competencias', 'destrezas'],
                'de': ['fähigkeiten', 'kompetenzen', 'fertigkeiten'],
                'ar': ['المهارات', 'الكفاءات', 'القدرات'],
                'he': ['כישורים', 'יכולות', 'מיומנויות'],
                'zh': ['技能', '专业技能', '能力']
            }
        }
        
        # Date patterns for position detection
        self.date_patterns = [
            r'\b\d{4}\b',                    # YYYY
            r'\b\d{1,2}[/-]\d{4}\b',        # MM/YYYY, M/YYYY
            r'\b\d{1,2}[/-]\d{1,2}[/-]\d{4}\b',  # DD/MM/YYYY
            r'\b\d{4}\s*-\s*\d{4}\b',       # YYYY-YYYY
            r'\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{4}\b',  # Mon YYYY
            r'\b(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{4}\b'
        ]
        
    def analyze_structure(self, text: Any, coordinates: Optional[List[Dict[str, Any]]] = None) -> SectionStructure:
        """Compatibility wrapper that accepts raw text input."""
        if isinstance(text, dict):
            document_data = text
            lines = document_data.get('text_lines', [])
        else:
            lines = text.splitlines() if isinstance(text, str) else list(text)
            document_data = {'text_lines': lines}
            if coordinates is not None:
                document_data['coordinates'] = coordinates

        structure = self.detect_structure(document_data)

        structure.reading_order = (structure.reading_order or 'LTR').upper()
        structure.script_direction = structure.reading_order
        setattr(structure, 'has_columns', getattr(structure, 'columns', 1) > 1)

        header_spans = list(getattr(structure, 'header_spans', []))
        if not header_spans:
            header_spans = self._detect_headers(lines)
            structure.header_spans = header_spans
        structure.detected_headers = header_spans
        structure.header_confidence = getattr(structure, 'layout_confidence', 0.0)

        languages: List[str] = []
        for header in header_spans:
            if isinstance(header, dict):
                lang = header.get('language')
                if lang and lang not in languages:
                    languages.append(lang)
                header_type = header.get('type', '')
                if not header_type or header_type == 'unknown':
                    text_lower = header.get('text', '').lower()
                    if 'exp' in text_lower:
                        header['type'] = 'experience'
                    elif 'formation' in text_lower or 'edu' in text_lower:
                        header['type'] = 'education'
                    elif 'comp' in text_lower or 'skill' in text_lower:
                        header['type'] = 'skills'

        sample = ' '.join(lines[:20]).lower()
        if not languages:
            guessed = self._detect_header_language(sample)
            if guessed:
                languages.append(guessed)

        languages.extend(self._detect_additional_languages(lines))

        if 'en' not in languages:
            languages.append('en')
        structure.languages_detected = list(dict.fromkeys(languages))
        return structure


    def _detect_additional_languages(self, lines: List[str]) -> List[str]:
        joined = ''.join(lines)
        detected: List[str] = []
        if re.search(r'[\u0600-\u06FF]', joined):
            detected.append('ar')
        if re.search(r'[\u0590-\u05FF]', joined):
            detected.append('he')
        if re.search(r'[\u4E00-\u9FFF]', joined) or re.search(r'[\u3040-\u30FF]', joined):
            detected.append('ja')
        if re.search(r'[\u0400-\u04FF]', joined):
            detected.append('ru')
        if re.search(r'[\uAC00-\uD7AF]', joined):
            detected.append('ko')
        return detected

    def detect_structure(self, document_data: Dict[str, Any]) -> SectionStructure:
        """
        Analyze document structure and return layout information.
        
        Args:
            document_data: Document with text_lines, entities, and optional coordinates
            
        Returns:
            SectionStructure with detected layout properties
        """
        text_lines = document_data.get('text_lines', [])
        coordinates = document_data.get('coordinates', [])
        
        if not text_lines:
            return SectionStructure()
        
        # Detect reading order and script composition
        reading_order = self._detect_reading_order(text_lines)
        
        # Detect column structure
        columns, barriers = self._detect_columns(text_lines, coordinates if coordinates else None, return_layout=True)
        
        # Analyze header structure
        headers = self._detect_headers(text_lines)
        
        # Detect date positioning
        date_position = self._analyze_date_position(text_lines)
        
        # Check for inverted layouts (dates->content->title)
        is_inverted = self._detect_inversion(text_lines, headers)
        
        # NEW: Detect contact blocks and create quarantine zones
        contact_blocks = self._detect_contact_blocks(text_lines)
        contact_block_range = None
        if contact_blocks:
            # Use the first (highest confidence) contact block
            main_contact = max(contact_blocks, key=lambda x: x.confidence)
            contact_block_range = (main_contact.start_line, main_contact.end_line)
            logger.info(f"SSA: Contact block detected | lines {contact_block_range[0]}-{contact_block_range[1]} | confidence={main_contact.confidence:.2f}")
        
        # Create quarantine zones
        quarantine_zones = self._create_quarantine_zones(contact_blocks)
        
        # Detect timeline and table layouts  
        is_timeline = self._detect_timeline(text_lines)
        is_table = self._detect_table_structure(text_lines)
        
        # Calculate confidence
        confidence = self._calculate_confidence(text_lines, headers, columns)
        
        structure = SectionStructure(
            is_inverted=is_inverted,
            date_position=date_position,
            columns=columns,
            column_barriers=barriers,
            header_spans=headers,
            reading_order=reading_order,
            layout_confidence=confidence,
            contact_block_range=contact_block_range,
            contact_quarantine_zones=quarantine_zones,
            script_direction=reading_order.upper(),
            is_timeline=is_timeline,
            is_table=is_table
        )
        
        logger.info(f"Structure detected: columns={columns}, reading_order={reading_order}, "
                   f"date_position={date_position}, inverted={is_inverted}, conf={confidence:.3f}")
        
        return structure
    
    def _detect_reading_order(self, text_lines: List[str]) -> str:
        """Detect document reading order based on script analysis."""
        rtl_count = 0
        ltr_count = 0

        iterable = text_lines.splitlines() if isinstance(text_lines, str) else text_lines

        for line in iterable:
            for char in line:
                if '\u0600' <= char <= '\u06FF' or '\u0590' <= char <= '\u05FF':
                    rtl_count += 1
                elif char.isalpha():
                    ltr_count += 1

        total_letters = rtl_count + ltr_count
        if total_letters == 0:
            return 'LTR'

        rtl_ratio = rtl_count / total_letters
        if rtl_ratio > 0.4:
            return 'RTL' if rtl_ratio > 0.7 else 'MIXED'
        return 'LTR'
    def _detect_columns(self, text_lines: List[str], coordinates: Optional[List[Dict[str, Any]]] = None, *, return_layout: bool = False) -> Tuple[Any, Any]:
        '''Detect column structure using x-coordinates or indentation fallbacks.'''
        if not coordinates:
            column_count, barriers = self._detect_columns_by_indentation(text_lines)
        else:
            if len(coordinates) != len(text_lines):
                column_count, barriers = self._detect_columns_by_indentation(text_lines)
            else:
                x_coords = [coord['x'] for coord in coordinates if coord.get('x') is not None]
                if len(x_coords) < 3:
                    column_count, barriers = 1, []
                else:
                    clusters = self._cluster_coordinates(x_coords)
                    if len(clusters) <= 1:
                        column_count, barriers = 1, []
                    else:
                        column_count = len(clusters)
                        barriers = [(min(cluster), max(cluster)) for cluster in clusters]

        if return_layout:
            return column_count, barriers

        has_columns = column_count > 1
        return has_columns, column_count

    def _detect_columns_by_indentation(self, text_lines: List[str]) -> Tuple[int, List[Tuple[int, int]]]:
        """Fallback column detection using indentation analysis."""
        indentations = []
        
        for line in text_lines:
            stripped = line.lstrip()
            if stripped:  # Non-empty line
                indent = len(line) - len(stripped)
                indentations.append(indent)
        
        if not indentations:
            return 1, []
        
        # Find common indentation patterns
        indent_counter = Counter(indentations)
        common_indents = [indent for indent, count in indent_counter.items() 
                         if count >= max(3, len(indentations) * 0.1)]
        
        if len(common_indents) <= 1:
            return 1, []
        
        # Estimate column boundaries based on indentation
        columns = min(len(common_indents), 3)  # Cap at 3 columns
        return columns, []
    
    def _cluster_coordinates(self, coords: List[float], tolerance: float = 30.0) -> List[List[float]]:
        """Cluster coordinates within tolerance range."""
        if not coords:
            return []
        
        coords_sorted = sorted(coords)
        clusters = [[coords_sorted[0]]]
        
        for coord in coords_sorted[1:]:
            # Find closest cluster
            min_distance = float('inf')
            closest_cluster_idx = 0
            
            for i, cluster in enumerate(clusters):
                cluster_center = sum(cluster) / len(cluster)
                distance = abs(coord - cluster_center)
                
                if distance < min_distance:
                    min_distance = distance
                    closest_cluster_idx = i
            
            # Add to closest cluster if within tolerance, else create new cluster
            if min_distance <= tolerance:
                clusters[closest_cluster_idx].append(coord)
            else:
                clusters.append([coord])
        
        return clusters
    
    def _detect_headers(self, text: Any, language: str = 'auto') -> List[Dict[str, Any]]:
        '''Detect section headers across multiple languages.'''
        if isinstance(text, str):
            text_lines = text.splitlines()
        else:
            text_lines = text

        headers = []

        for i, line in enumerate(text_lines):
            line_clean = line.strip().lower()

            if not line_clean or len(line_clean) > 100:
                continue

            is_header = (
                self._is_caps_heavy(line) or
                line.endswith(':') or
                self._matches_header_pattern(line_clean)
            )

            if is_header:
                detected_type = self._classify_header_type(line_clean)
                confidence = self._calculate_header_confidence(line, line_clean)
                header_language = language if language != 'auto' else self._detect_header_language(line_clean)

                headers.append({
                    'start_line': i,
                    'end_line': i,
                    'text': line.strip(),
                    'type': detected_type,
                    'confidence': confidence,
                    'language': header_language
                })

        return headers

    def _is_caps_heavy(self, line: str) -> bool:
        """Check if line has heavy capitalization (header indicator)."""
        letters = [c for c in line if c.isalpha()]
        if len(letters) < 3:
            return False
        
        caps_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
        return caps_ratio >= 0.6
    
    def _matches_header_pattern(self, line_clean: str) -> bool:
        """Check if line matches known header patterns."""
        for section_type, languages in self.header_aliases.items():
            for lang, headers in languages.items():
                for header in headers:
                    if header in line_clean or line_clean in header:
                        return True
        return False
    
    def _classify_header_type(self, line_clean: str) -> str:
        """Classify header type based on content."""
        best_match = "unknown"
        best_score = 0
        
        for section_type, languages in self.header_aliases.items():
            for lang, headers in languages.items():
                for header in headers:
                    # Calculate similarity score
                    if header in line_clean or line_clean in header:
                        score = min(len(header), len(line_clean)) / max(len(header), len(line_clean))
                        if score > best_score:
                            best_score = score
                            best_match = section_type
        
        return best_match if best_score > 0.5 else "unknown"
    
    def _calculate_header_confidence(self, original: str, cleaned: str) -> float:
        """Calculate confidence score for header detection."""
        confidence = 0.0
        
        # Capitalization bonus
        if self._is_caps_heavy(original):
            confidence += 0.3
        
        # Colon ending bonus
        if original.strip().endswith(':'):
            confidence += 0.2
        
        # Pattern match bonus
        if self._matches_header_pattern(cleaned):
            confidence += 0.4
        
        # Length penalty for very long headers
        if len(cleaned) > 50:
            confidence -= 0.2
        
        # Standalone line bonus
        confidence += 0.1
        
        return max(0.0, min(1.0, confidence))
    
    def _detect_header_language(self, line_clean: str) -> str:
        """Detect likely language of header text."""
        for section_type, languages in self.header_aliases.items():
            for lang, headers in languages.items():
                for header in headers:
                    if header in line_clean or line_clean in header:
                        return lang
        return "unknown"
    
    def _analyze_date_position(self, text_lines: List[str]) -> str:
        """Analyze whether dates typically appear before or after content."""
        before_count = 0
        after_count = 0
        
        for i, line in enumerate(text_lines):
            if self._contains_date(line):
                # Check context around date
                context_before = ' '.join(text_lines[max(0, i-2):i]).strip()
                context_after = ' '.join(text_lines[i+1:min(len(text_lines), i+3)]).strip()
                
                # Score based on content type
                before_score = self._score_content_context(context_before)
                after_score = self._score_content_context(context_after)
                
                if before_score > after_score:
                    after_count += 1  # Date comes after main content
                elif after_score > before_score:
                    before_count += 1  # Date comes before main content
        
        if before_count + after_count == 0:
            return "mixed"
        
        ratio = before_count / (before_count + after_count)
        
        if ratio > 0.7:
            return "before_content"
        elif ratio < 0.3:
            return "after_content"
        else:
            return "mixed"
    
    def _contains_date(self, line: str) -> bool:
        """Check if line contains date patterns."""
        for pattern in self.date_patterns:
            if re.search(pattern, line, re.IGNORECASE):
                return True
        return False
    
    def _score_content_context(self, text: str) -> float:
        """Score text based on likelihood of being main content."""
        if not text:
            return 0.0
        
        score = 0.0
        
        # Length bonus
        score += min(len(text) / 100.0, 0.5)
        
        # Descriptive content indicators
        descriptive_indicators = [
            'responsibilities', 'responsible', 'managed', 'developed', 'created',
            'responsabilités', 'géré', 'développé', 'créé',
            'responsibilities', 'desarrolló', 'creó', 'gestionó'
        ]
        
        text_lower = text.lower()
        for indicator in descriptive_indicators:
            if indicator in text_lower:
                score += 0.2
        
        # Penalty for header-like content
        if self._is_caps_heavy(text) or ':' in text:
            score -= 0.3
        
        return max(0.0, score)
    
    def _detect_inversion(self, text_lines: List[str], headers: List[Dict[str, Any]]) -> bool:
        """Detect if document uses inverted layout (dates->content->title)."""
        inversion_indicators = 0
        total_sections = 0
        
        for header in headers:
            start_idx = header['start_line']
            
            # Look at next few lines after header
            section_lines = text_lines[start_idx+1:start_idx+6]
            
            if len(section_lines) >= 3:
                total_sections += 1
                
                # Check if dates appear before descriptive content
                first_line_has_date = self._contains_date(section_lines[0])
                has_later_content = any(
                    len(line.strip()) > 20 and not self._contains_date(line)
                    for line in section_lines[1:3]
                )
                
                if first_line_has_date and has_later_content:
                    inversion_indicators += 1
        
        return total_sections > 0 and (inversion_indicators / total_sections) > 0.6
    
    def _calculate_confidence(self, text_lines: List[str], headers: List[Dict[str, Any]], columns: int) -> float:
        """Calculate overall confidence in structure detection."""
        confidence = 0.0
        
        # Base confidence from having some structure
        if headers:
            confidence += 0.3
        
        # Header quality bonus
        avg_header_conf = sum(h.get('confidence', 0) for h in headers) / max(len(headers), 1)
        confidence += avg_header_conf * 0.3
        
        # Column detection confidence
        if columns > 1:
            confidence += 0.2
        
        # Content structure bonus
        non_empty_lines = sum(1 for line in text_lines if line.strip())
        if non_empty_lines > 10:
            confidence += 0.2
        
        return min(1.0, confidence)
    
    def _detect_contact_blocks(self, text_lines: List[str]) -> List[ContactBlock]:
        """Detect contact information blocks in the document."""
        contact_blocks = []
        
        # Analyze in windows within header area
        window_size = 5
        header_end = min(self.config.HEADER_DETECTION_WINDOW, len(text_lines))
        
        for start_idx in range(0, header_end, window_size // 2):  # Overlapping windows
            end_idx = min(start_idx + window_size, header_end)
            window_lines = text_lines[start_idx:end_idx]
            
            contact_info = self._analyze_contact_window(window_lines)
            
            if contact_info['density'] >= self.config.CONTACT_DENSITY_THRESHOLD:
                contact_block = ContactBlock(
                    start_line=start_idx,
                    end_line=end_idx - 1,
                    contact_density=contact_info['density'],
                    contact_types=contact_info['types'],
                    confidence=contact_info['confidence']
                )
                contact_blocks.append(contact_block)
        
        # Merge overlapping contact blocks
        merged_blocks = self._merge_contact_blocks(contact_blocks)
        
        return merged_blocks
    
    def _analyze_contact_window(self, window_lines: List[str]) -> Dict[str, Any]:
        """Analyze a window of lines for contact information."""
        if not window_lines:
            return {'density': 0.0, 'types': set(), 'confidence': 0.0}
        
        total_lines = len(window_lines)
        contact_lines = 0
        contact_types = set()
        
        for line in window_lines:
            text = line.strip()
            if not text:
                continue
            
            line_has_contact = False
            
            # Check for email
            if any(pattern.search(text) for pattern in self._email_patterns):
                contact_types.add('email')
                line_has_contact = True
            
            # Check for phone
            if any(pattern.search(text) for pattern in self._phone_patterns):
                contact_types.add('phone')
                line_has_contact = True
            
            # Check for URL
            if any(pattern.search(text) for pattern in self._url_patterns):
                contact_types.add('url')
                line_has_contact = True
            
            # Check for address indicators
            address_indicators = [
                'street', 'avenue', 'road', 'lane', 'drive', 'court', 'place',
                'rue', 'avenue', 'boulevard', 'place', 'chemin',
                'str.', 'ave.', 'rd.', 'dr.', 'ct.', 'pl.'
            ]
            if any(indicator in text.lower() for indicator in address_indicators):
                contact_types.add('address')
                line_has_contact = True
            
            if line_has_contact:
                contact_lines += 1
        
        density = contact_lines / total_lines if total_lines > 0 else 0.0
        confidence = min(1.0, density * (len(contact_types) / 4.0))  # Max confidence with 4 types
        
        return {
            'density': density,
            'types': contact_types,
            'confidence': confidence
        }
    
    def _merge_contact_blocks(self, contact_blocks: List[ContactBlock]) -> List[ContactBlock]:
        """Merge overlapping contact blocks."""
        if not contact_blocks:
            return []
        
        # Sort by start line
        sorted_blocks = sorted(contact_blocks, key=lambda x: x.start_line)
        merged = []
        
        current = sorted_blocks[0]
        
        for next_block in sorted_blocks[1:]:
            if next_block.start_line <= current.end_line + 1:  # Overlapping or adjacent
                # Merge blocks
                current = ContactBlock(
                    start_line=current.start_line,
                    end_line=max(current.end_line, next_block.end_line),
                    contact_density=max(current.contact_density, next_block.contact_density),
                    contact_types=current.contact_types | next_block.contact_types,
                    confidence=max(current.confidence, next_block.confidence)
                )
            else:
                merged.append(current)
                current = next_block
        
        merged.append(current)
        return merged
        
    def _create_quarantine_zones(self, contact_blocks: List[ContactBlock]) -> List[Tuple[int, int]]:
        """Create quarantine zones around contact blocks."""
        zones = []
        
        for contact_block in contact_blocks:
            # Add post-buffer after contact block
            quarantine_start = contact_block.start_line
            quarantine_end = contact_block.end_line + self.config.CONTACT_POST_BUFFER_LINES
            zones.append((quarantine_start, quarantine_end))
        
        # Merge overlapping zones
        if zones:
            zones.sort(key=lambda x: x[0])
            merged_zones = []
            current_start, current_end = zones[0]
            
            for start, end in zones[1:]:
                if start <= current_end + 1:  # Overlapping or adjacent
                    current_end = max(current_end, end)
                else:
                    merged_zones.append((current_start, current_end))
                    current_start, current_end = start, end
            
            merged_zones.append((current_start, current_end))
            zones = merged_zones
        
        return zones
    
    def _detect_timeline(self, text_lines: List[str]) -> bool:
        """Detect if document has timeline-like structure."""
        date_lines = 0
        connector_lines = 0
        total_lines = len(text_lines)
        
        if total_lines == 0:
            return False
        
        connectors = ['-', '->', '|', '*', 'o', '*', '*', '-', '-']
        
        for line in text_lines:
            text = line.strip()
            if not text:
                continue
            
            # Check for date patterns
            if self._contains_date(text):
                date_lines += 1
            
            # Check for connector patterns
            if any(conn in text for conn in connectors):
                connector_lines += 1
        
        date_density = date_lines / total_lines
        connector_density = connector_lines / total_lines
        combined_density = (date_density + connector_density) / 2
        
        return combined_density >= self.config.TIMELINE_DENSITY_THRESHOLD
    
    def _detect_table_structure(self, text_lines: List[str]) -> bool:
        """Detect if document has table-like structure."""
        if not text_lines:
            return False
        
        # Look for consistent tab or multiple space separations
        consistent_separations = 0
        
        for line in text_lines:
            # Count tabs or multiple consecutive spaces
            tab_count = line.count('\t')
            multiple_spaces = len(re.findall(r'\s{3,}', line))
            
            if tab_count >= 2 or multiple_spaces >= 2:
                consistent_separations += 1
        
        # A table should have at least 30% of lines with consistent separations
        separation_ratio = consistent_separations / len(text_lines) if text_lines else 0
        
        return separation_ratio >= 0.3


def detect_structure(document_data: Dict[str, Any]) -> SectionStructure:
    """
    Convenience function to detect document structure.
    
    Args:
        document_data: Document with text_lines, entities, and optional coordinates
        
    Returns:
        SectionStructure with detected layout properties
    """
    analyzer = SectionStructureAnalyzer()
    return analyzer.detect_structure(document_data)


# === Helper Functions for Contact Quarantine ===

def is_in_quarantine_zone(line_idx: int, quarantine_zones: List[Tuple[int, int]]) -> bool:
    """Check if a line index is within any quarantine zone."""
    for start, end in quarantine_zones:
        if start <= line_idx <= end:
            return True
    return False


def get_column_for_line(line_idx: int, column_barriers: List[Tuple[int, int]], total_columns: int) -> int:
    """Get the column number for a specific line based on column barriers."""
    # Simple implementation: assume single column if no barriers
    if not column_barriers or total_columns <= 1:
        return 0
    
    # For now, return column 0 - more sophisticated logic would require x-coordinates
    return 0


def can_cross_columns(line1_idx: int, line2_idx: int, column_barriers: List[Tuple[int, int]], 
                      total_columns: int, max_distance: int = 0) -> bool:
    """Check if two lines can be linked across columns."""
    if max_distance == 0:  # No cross-column linking allowed
        col1 = get_column_for_line(line1_idx, column_barriers, total_columns)
        col2 = get_column_for_line(line2_idx, column_barriers, total_columns)
        return col1 == col2
    
    # Allow cross-column if within distance threshold
    return abs(line1_idx - line2_idx) <= max_distance


def create_sliding_windows(lines: List[str], window_size: int, context: Dict[str, Any]) -> List[Tuple[int, int]]:
    """Create sliding windows for extraction, respecting quarantine zones."""
    windows = []
    quarantine_zones = context.get('contact_quarantine_zones', [])
    
    i = 0
    while i < len(lines):
        # Skip quarantined areas
        if is_in_quarantine_zone(i, quarantine_zones):
            # Find end of quarantine zone
            for start, end in quarantine_zones:
                if start <= i <= end:
                    i = end + 1
                    break
            continue
        
        # Create window
        start_idx = i
        end_idx = min(i + window_size, len(lines))
        
        # Ensure window doesn't cross into quarantine zone
        for qz_start, qz_end in quarantine_zones:
            if start_idx < qz_start < end_idx:
                end_idx = qz_start
                break
        
        if end_idx > start_idx:
            windows.append((start_idx, end_idx))
        
        i = end_idx
    
    return windows


def expand_range(range_tuple: Tuple[int, int], buffer: int) -> Tuple[int, int]:
    """Expand a range tuple by buffer amount."""
    start, end = range_tuple
    return (max(0, start - buffer), end + buffer)


