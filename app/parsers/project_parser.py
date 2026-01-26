from .metrics_mixin import ParserMetricsMixin
"""
Project Parser for CV Extraction Pipeline.

Enhanced project parser with rich metadata extraction, date inversion detection,
technology stack recognition, and project type classification.
"""

import json
import re
from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass
from pathlib import Path
from difflib import SequenceMatcher

from ..logging.safe_logger import get_safe_logger
from ..config import DEFAULT_PII_CONFIG


logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


@dataclass
class ProjectParsingMetrics:
    """Metrics for project parsing performance."""
    chunks_processed: int = 0
    projects_extracted: int = 0
    academic_projects: int = 0
    professional_projects: int = 0
    personal_projects: int = 0
    dates_parsed: int = 0
    dates_fixed_inversions: int = 0
    tech_stacks_detected: int = 0
    urls_extracted: int = 0
    duplicates_removed: int = 0


class ProjectParser(ParserMetricsMixin):
    """
    Enhanced Project Parser for CV Extraction.
    
    Provides comprehensive project extraction with:
    - Rich metadata extraction (title, dates, tech stack, organization, role)
    - Date inversion detection and correction
    - Project type classification (academic, professional, personal)
    - Technology stack recognition
    - URL extraction and validation
    - Deduplication based on similarity
    """
    METRICS_COPY = True
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize project parser with configuration."""
        self.logger = get_safe_logger(f"{__name__}.ProjectParser", cfg=DEFAULT_PII_CONFIG)
        self.metrics = self._init_metrics()
        
        # Load rules and patterns
        self.rules = self._load_rules(config_path)
        self.tech_whitelist = set()
        
        # Compile regex patterns
        self._compile_patterns()
        
        # Build technology whitelist
        self._build_tech_lookup()
        
        self.logger.info("PROJ_PARSER: initialized | "
                        f"date_patterns={len(self.date_patterns)} "
                        f"tech_whitelist={len(self.tech_whitelist)}")
    
    def _init_metrics(self) -> Dict[str, int]:
        """Initialize metrics counters."""
        return {
            "chunks_processed": 0,
            "projects_extracted": 0,
            "academic_projects": 0,
            "professional_projects": 0,
            "personal_projects": 0,
            "dates_parsed": 0,
            "dates_fixed_inversions": 0,
            "tech_stacks_detected": 0,
            "urls_extracted": 0,
            "duplicates_removed": 0
        }
    
    def _load_rules(self, config_path: Optional[str] = None) -> Dict[str, Any]:
        """Load project parsing rules from configuration file."""
        if config_path is None:
            config_path = Path(__file__).parent.parent / "rules" / "projects_enhanced.json"
        
        try:
            if Path(config_path).exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    rules = json.load(f)
                self.logger.info(f"PROJ_PARSER: rules loaded | path={config_path}")
                return rules
            else:
                self.logger.warning(f"PROJ_PARSER: rules file not found | path={config_path} | using defaults")
        except Exception as e:
            self.logger.error(f"PROJ_PARSER: rules load failed | path={config_path} | error={e}")
        
        # Return minimal default rules
        return {
            "date_patterns": [
                r"(\d{4}[-/]\d{1,2})\s*[-–—]\s*(\d{4}[-/]\d{1,2}|present|current|actuel)",
                r"(\d{1,2}/\d{4})\s*[-–—]\s*(\d{1,2}/\d{4}|present|current|actuel)",
                r"(\w+ \d{4})\s*[-–—]\s*(\w+ \d{4}|present|current|actuel)"
            ],
            "current_markers": ["present", "current", "actuel", "aujourd'hui"],
            "tech_whitelist": ["python", "java", "javascript", "react", "node", "sql", "git"],
            "type_markers": {
                "academic": ["university", "research", "thesis", "academic", "student", "école", "université"],
                "professional": ["company", "client", "business", "commercial", "enterprise", "corporate"],
                "personal": ["personal", "hobby", "side", "open source", "github", "portfolio"]
            },
            "confidence_scoring": {
                "base_score": 0.6,
                "title_bonus": 0.15,
                "date_bonus": 0.10,
                "tech_bonus": 0.05,
                "description_bonus": 0.05,
                "url_bonus": 0.05,
                "role_bonus": 0.05,
                "org_bonus": 0.05,
                "max_score": 0.95,
                "min_viable_score": 0.65
            },
            "deduplication": {
                "title_similarity_threshold": 0.8,
                "description_overlap_threshold": 0.7,
                "merge_tech_stacks": True
            }
        }
    
    def _compile_patterns(self):
        """Compile regex patterns for efficient matching."""
        # Date patterns
        date_pattern_strings = self.rules.get("date_patterns", [])
        self.date_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in date_pattern_strings]
        
        # Current markers pattern
        current_markers = self.rules.get("current_markers", [])
        current_pattern = r'\b(?:' + '|'.join(re.escape(marker) for marker in current_markers) + r')\b'
        self.current_regex = re.compile(current_pattern, re.IGNORECASE)
        
        # Bullet point pattern
        self.bullet_regex = re.compile(r'^[-•◦▪◾▶▸*+]\s*', re.MULTILINE)
        
        # URL patterns
        self.url_patterns = [
            re.compile(r'https?://[^\s]+', re.IGNORECASE),
            re.compile(r'www\.[^\s]+\.[a-z]{2,}', re.IGNORECASE),
            re.compile(r'github\.com/[^\s]+', re.IGNORECASE)
        ]
        
        # Role extraction patterns
        self.role_patterns = [
            re.compile(r'role\s*[:\-]\s*([^,\n]+)', re.IGNORECASE),
            re.compile(r'position\s*[:\-]\s*([^,\n]+)', re.IGNORECASE),
            re.compile(r'as\s+([^,\n]+)', re.IGNORECASE)
        ]
        
        # Organization patterns
        self.org_patterns = [
            re.compile(r'@\s*([^,\n]+)', re.IGNORECASE),
            re.compile(r'at\s+([^,\n]+)', re.IGNORECASE),
            re.compile(r'for\s+([^,\n]+)', re.IGNORECASE)
        ]
    
    def _build_tech_lookup(self):
        """Build technology whitelist lookup."""
        whitelist = self.rules.get("tech_whitelist", [])
        
        for tech in whitelist:
            self.tech_whitelist.add(tech.lower())
            
        self.logger.debug(f"PROJ_PARSER: built tech lookup | technologies={len(self.tech_whitelist)}")
    
    def parse_section_lines(self, lines: List[str]) -> List[Dict[str, Any]]:
        """
        Parse projects from a list of lines within a section.
        
        Args:
            lines: List of text lines from the projects section
            
        Returns:
            List of parsed projects with rich metadata
        """
        if not lines:
            return []
        
        self.logger.info(f"PROJ_PARSER: starting parsing | lines={len(lines)}")
        
        # Chunk lines into project entries
        chunks = self._chunk_bullets(lines)
        
        projects = []
        for chunk_idx, chunk in enumerate(chunks):
            if not chunk.strip():
                continue
            
            self.metrics["chunks_processed"] += 1
            
            # Extract project metadata from chunk
            project = self._extract_project_metadata(chunk, chunk_idx)
            
            if project and self._is_viable_project(project):
                projects.append(project)
                self.metrics["projects_extracted"] += 1
                
                # Update type metrics
                project_type = project.get("type", "unknown")
                if project_type == "academic":
                    self.metrics["academic_projects"] += 1
                elif project_type == "professional":
                    self.metrics["professional_projects"] += 1
                elif project_type == "personal":
                    self.metrics["personal_projects"] += 1
        
        # Deduplicate projects
        if projects:
            deduplicated = self._deduplicate_projects(projects)
            self.metrics["duplicates_removed"] = len(projects) - len(deduplicated)
        else:
            deduplicated = []
        
        self.logger.info(f"PROJ_PARSER: completed | extracted={len(deduplicated)} "
                        f"academic={self.metrics['academic_projects']} "
                        f"professional={self.metrics['professional_projects']} "
                        f"personal={self.metrics['personal_projects']}")
        
        return deduplicated
    
    def _chunk_bullets(self, lines: List[str]) -> List[str]:
        """
        Chunk bullet points and wrapped lines into project entries.
        
        Args:
            lines: List of text lines
            
        Returns:
            List of chunked text blocks, each representing a project
        """
        chunks = []
        current_chunk = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Check if this line starts a new bullet/project
            is_bullet = self.bullet_regex.match(line)
            is_likely_new_project = (
                is_bullet or
                self._contains_project_indicators(line) or
                (len(current_chunk) > 0 and self._looks_like_project_title(line))
            )
            
            if is_likely_new_project and current_chunk:
                # Start new chunk
                chunks.append("\n".join(current_chunk))
                current_chunk = [line]
            else:
                # Continue current chunk
                current_chunk.append(line)
        
        # Add final chunk
        if current_chunk:
            chunks.append("\n".join(current_chunk))
        
        return chunks
    
    def _contains_project_indicators(self, line: str) -> bool:
        """Check if line contains project indicators."""
        line_lower = line.lower()
        
        # URL indicators
        if any(pattern.search(line) for pattern in self.url_patterns):
            return True
        
        # Tech stack indicators
        tech_count = sum(1 for tech in self.tech_whitelist if tech in line_lower)
        if tech_count >= 2:
            return True
        
        # Date range indicators
        if any(pattern.search(line) for pattern in self.date_patterns):
            return True
        
        return False
    
    def _looks_like_project_title(self, line: str) -> bool:
        """Check if line looks like a project title."""
        # Short lines with title-like characteristics
        if 5 <= len(line.strip()) <= 60:
            # Contains title case or tech terms
            has_title_case = bool(re.search(r'\b[A-Z][a-z]+', line))
            has_tech_terms = any(tech in line.lower() for tech in list(self.tech_whitelist)[:20])
            
            return has_title_case or has_tech_terms
        
        return False
    
    def _extract_project_metadata(self, chunk: str, chunk_idx: int) -> Dict[str, Any]:
        """
        Extract rich metadata from a project chunk.
        
        Args:
            chunk: Text chunk representing a project
            chunk_idx: Index of the chunk
            
        Returns:
            Dictionary with project metadata
        """
        project = {
            "title": "",
            "description": "",
            "role": "",
            "organization": "",
            "start_date": None,
            "end_date": None,
            "current": False,
            "tech_stack": [],
            "type": "personal",  # Default
            "url": "",
            "confidence": 0.0,
            "source": f"chunk_{chunk_idx}"
        }
        
        # Extract title (first meaningful line or text before colon/dash)
        project["title"] = self._extract_title(chunk)
        
        # Extract dates
        date_info = self._parse_dates(chunk)
        project.update(date_info)
        
        # Extract role
        project["role"] = self._extract_role(chunk)
        
        # Extract organization
        project["organization"] = self._extract_organization(chunk)
        
        # Extract tech stack
        project["tech_stack"] = self._extract_tech_stack(chunk)
        
        # Extract URL
        project["url"] = self._extract_url(chunk)
        
        # Extract description (remaining text)
        project["description"] = self._extract_description(chunk, project)
        
        # Classify project type
        project["type"] = self._classify_project_type(chunk)
        
        # Calculate confidence
        project["confidence"] = self._calculate_confidence(project)
        
        return project
    
    def _extract_title(self, chunk: str) -> str:
        """Extract project title from chunk."""
        lines = chunk.split('\n')
        first_line = lines[0].strip()
        
        # Remove bullet markers
        title = self.bullet_regex.sub('', first_line).strip()
        
        # Extract title before colon or dash
        title_match = re.match(r'^(.+?)\s*[-:]', title)
        if title_match:
            title = title_match.group(1).strip()
        
        # Limit title length
        if len(title) > 80:
            title = title[:77] + "..."
        
        # If title is too short, use first few words
        if len(title) < 3 and len(first_line.split()) > 1:
            words = first_line.split()[:7]
            title = ' '.join(words)
        
        return title
    
    def _parse_dates(self, chunk: str) -> Dict[str, Any]:
        """Parse dates from chunk with inversion detection."""
        date_info = {
            "start_date": None,
            "end_date": None,
            "current": False
        }
        
        # Check for current markers
        if self.current_regex.search(chunk):
            date_info["current"] = True
        
        # Try each date pattern
        for pattern in self.date_patterns:
            match = pattern.search(chunk)
            if match:
                date_info.update(self._normalize_date_match(match))
                self.metrics["dates_parsed"] += 1
                break
        
        return date_info
    
    def _normalize_date_match(self, match: re.Match) -> Dict[str, Any]:
        """Normalize a date match to start/end dates."""
        groups = match.groups()
        
        if len(groups) >= 2:
            start_str = groups[0] if groups[0] else ""
            end_str = groups[1] if groups[1] else ""
            
            # Check for current markers in end date
            current_markers = self.rules.get("current_markers", [])
            is_current = any(marker in end_str.lower() for marker in current_markers)
            
            if is_current:
                return {
                    "start_date": self._normalize_date_string(start_str),
                    "end_date": None,
                    "current": True
                }
            else:
                start_date = self._normalize_date_string(start_str)
                end_date = self._normalize_date_string(end_str)
                
                # Check for date inversion
                if start_date and end_date and start_date > end_date:
                    self.logger.debug(f"PROJ_PARSER: date inversion detected | {start_date} > {end_date}")
                    start_date, end_date = end_date, start_date  # Swap
                    self.metrics["dates_fixed_inversions"] += 1
                
                return {
                    "start_date": start_date,
                    "end_date": end_date,
                    "current": False
                }
        
        return {"start_date": None, "end_date": None, "current": False}
    
    def _normalize_date_string(self, date_str: str) -> Optional[str]:
        """Normalize a date string to YYYY-MM format."""
        if not date_str or not date_str.strip():
            return None
        
        date_str = date_str.strip()
        
        # Pattern: YYYY-MM or YYYY/MM
        if re.match(r'^\d{4}[-/.]\d{1,2}$', date_str):
            year, month = re.split(r'[-/.]', date_str)
            return f"{year}-{month.zfill(2)}"
        
        # Pattern: MM/YYYY
        if re.match(r'^\d{1,2}/\d{4}$', date_str):
            month, year = date_str.split('/')
            return f"{year}-{month.zfill(2)}"
        
        # Pattern: YYYY only
        if re.match(r'^\d{4}$', date_str):
            return f"{date_str}-01"  # Default to January
        
        return None
    
    def _extract_role(self, chunk: str) -> str:
        """Extract role from chunk."""
        for pattern in self.role_patterns:
            match = pattern.search(chunk)
            if match:
                role = match.group(1).strip()
                # Clean up role
                role = re.sub(r'[,.-]$', '', role)
                if len(role) <= 50:  # Reasonable role length
                    return role
        
        return ""
    
    def _extract_organization(self, chunk: str) -> str:
        """Extract organization from chunk."""
        for pattern in self.org_patterns:
            match = pattern.search(chunk)
            if match:
                org = match.group(1).strip()
                # Clean up organization name
                org = re.sub(r'[,.-]$', '', org)
                if len(org) <= 100:  # Reasonable org name length
                    return org
        
        return ""
    
    def _extract_tech_stack(self, chunk: str) -> List[str]:
        """Extract technology stack from chunk."""
        chunk_lower = chunk.lower()
        found_techs = set()
        
        # Simple token matching
        for tech in self.tech_whitelist:
            # Word boundary matching to avoid false positives
            if re.search(f"\\b{re.escape(tech)}\\b", chunk_lower):
                found_techs.add(tech.title())
        
        # Sort for consistency
        tech_list = sorted(list(found_techs))
        
        if tech_list:
            self.metrics["tech_stacks_detected"] += 1
        
        return tech_list
    
    def _extract_url(self, chunk: str) -> str:
        """Extract URL from chunk."""
        for pattern in self.url_patterns:
            match = pattern.search(chunk)
            if match:
                url = match.group(0)
                self.metrics["urls_extracted"] += 1
                return url
        
        return ""
    
    def _extract_description(self, chunk: str, project: Dict[str, Any]) -> str:
        """Extract description by removing already extracted elements."""
        description = chunk
        
        # Remove bullet markers
        description = self.bullet_regex.sub('', description)
        
        # Remove title (first line or title part)
        lines = description.split('\n')
        if lines and project.get("title"):
            title = project["title"]
            if title in lines[0]:
                # Remove the title part from first line
                first_line_clean = lines[0].replace(title, "").strip()
                first_line_clean = re.sub(r'^[-:]+', '', first_line_clean).strip()
                lines[0] = first_line_clean
        
        # Remove URLs
        if project.get("url"):
            description = description.replace(project["url"], "")
        
        # Remove dates (approximately)
        for pattern in self.date_patterns:
            description = pattern.sub('', description)
        
        # Remove role and organization (approximately)
        if project.get("role"):
            description = description.replace(project["role"], "")
        if project.get("organization"):
            description = description.replace(project["organization"], "")
        
        # Clean up description
        description = re.sub(r'\s+', ' ', description)  # Normalize whitespace
        description = re.sub(r'^[-:;,\s]+', '', description)  # Remove leading punctuation
        description = re.sub(r'[-:;,\s]+$', '', description)  # Remove trailing punctuation
        description = description.strip()
        
        # Limit description length
        if len(description) > 500:
            description = description[:497] + "..."
        
        return description
    
    def _classify_project_type(self, chunk: str) -> str:
        """Classify project as academic, professional, or personal."""
        chunk_lower = chunk.lower()
        
        type_markers = self.rules.get("type_markers", {})
        
        # Count markers for each type
        academic_score = sum(1 for marker in type_markers.get("academic", []) if marker in chunk_lower)
        professional_score = sum(1 for marker in type_markers.get("professional", []) if marker in chunk_lower)
        personal_score = sum(1 for marker in type_markers.get("personal", []) if marker in chunk_lower)
        
        # Determine type based on highest score
        if academic_score > professional_score and academic_score > personal_score:
            return "academic"
        elif professional_score > personal_score:
            return "professional"
        else:
            return "personal"  # Default
    
    def _calculate_confidence(self, project: Dict[str, Any]) -> float:
        """Calculate confidence score for a project."""
        scoring = self.rules.get("confidence_scoring", {})
        
        confidence = scoring.get("base_score", 0.6)
        
        # Bonus for each present field
        if project.get("title") and len(project["title"]) >= 3:
            confidence += scoring.get("title_bonus", 0.15)
        
        if project.get("start_date") or project.get("end_date"):
            confidence += scoring.get("date_bonus", 0.10)
        
        if project.get("tech_stack"):
            confidence += scoring.get("tech_bonus", 0.05)
        
        if project.get("description") and len(project["description"]) >= 10:
            confidence += scoring.get("description_bonus", 0.05)
        
        if project.get("url"):
            confidence += scoring.get("url_bonus", 0.05)
        
        if project.get("role"):
            confidence += scoring.get("role_bonus", 0.05)
        
        if project.get("organization"):
            confidence += scoring.get("org_bonus", 0.05)
        
        # Cap confidence
        max_score = scoring.get("max_score", 0.95)
        return min(confidence, max_score)
    
    def _is_viable_project(self, project: Dict[str, Any]) -> bool:
        """Check if project meets minimum viability criteria."""
        scoring = self.rules.get("confidence_scoring", {})
        min_score = scoring.get("min_viable_score", 0.65)
        
        # Must meet minimum confidence
        if project.get("confidence", 0) < min_score:
            return False
        
        # Must have at least title or URL
        if not project.get("title") and not project.get("url"):
            return False
        
        # Title must be meaningful if present
        title = project.get("title", "")
        if title and len(title.strip()) < 3:
            return False
        
        return True
    
    def _deduplicate_projects(self, projects: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove duplicate projects based on title similarity and description overlap."""
        if len(projects) <= 1:
            return projects
        
        dedup_config = self.rules.get("deduplication", {})
        title_threshold = dedup_config.get("title_similarity_threshold", 0.8)
        desc_threshold = dedup_config.get("description_overlap_threshold", 0.7)
        
        deduplicated = []
        processed_indices = set()
        
        for i, project1 in enumerate(projects):
            if i in processed_indices:
                continue
            
            # Find similar projects
            similar_projects = [project1]
            similar_indices = {i}
            
            for j, project2 in enumerate(projects[i+1:], i+1):
                if j in processed_indices:
                    continue
                
                if self._are_projects_similar(project1, project2, title_threshold, desc_threshold):
                    similar_projects.append(project2)
                    similar_indices.add(j)
            
            # Merge similar projects
            if len(similar_projects) > 1:
                merged_project = self._merge_projects(similar_projects, dedup_config)
                deduplicated.append(merged_project)
            else:
                deduplicated.append(project1)
            
            processed_indices.update(similar_indices)
        
        return deduplicated
    
    def _are_projects_similar(self, proj1: Dict[str, Any], proj2: Dict[str, Any], 
                             title_threshold: float, desc_threshold: float) -> bool:
        """Check if two projects are similar enough to be duplicates."""
        # Compare titles
        title1 = self._normalize_title_for_comparison(proj1.get("title", ""))
        title2 = self._normalize_title_for_comparison(proj2.get("title", ""))
        
        if title1 and title2:
            title_similarity = SequenceMatcher(None, title1, title2).ratio()
            if title_similarity >= title_threshold:
                return True
        
        # Compare descriptions
        desc1 = proj1.get("description", "")
        desc2 = proj2.get("description", "")
        
        if desc1 and desc2 and len(desc1) > 20 and len(desc2) > 20:
            desc_similarity = self._calculate_description_overlap(desc1, desc2)
            if desc_similarity >= desc_threshold:
                return True
        
        return False
    
    def _normalize_title_for_comparison(self, title: str) -> str:
        """Normalize title for comparison (lowercase, no punctuation)."""
        if not title:
            return ""
        
        # Convert to lowercase and remove punctuation
        normalized = re.sub(r'[^a-z0-9\s]', '', title.lower())
        # Normalize whitespace
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        
        return normalized
    
    def _calculate_description_overlap(self, desc1: str, desc2: str) -> float:
        """Calculate overlap between two descriptions based on common words."""
        words1 = set(re.findall(r'\b\w+\b', desc1.lower()))
        words2 = set(re.findall(r'\b\w+\b', desc2.lower()))
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1 & words2
        union = words1 | words2
        
        return len(intersection) / len(union) if union else 0.0
    
    def _merge_projects(self, projects: List[Dict[str, Any]], dedup_config: Dict) -> Dict[str, Any]:
        """Merge similar projects into one, keeping the best information."""
        if not projects:
            return {}
        
        # Choose base project (highest confidence)
        base_project = max(projects, key=lambda p: p.get("confidence", 0))
        merged = base_project.copy()
        
        # Merge tech stacks if enabled
        if dedup_config.get("merge_tech_stacks", True):
            all_techs = set()
            for project in projects:
                all_techs.update(project.get("tech_stack", []))
            merged["tech_stack"] = sorted(list(all_techs))
        
        # Collect sources
        all_sources = []
        for project in projects:
            source = project.get("source", "")
            if source and source not in all_sources:
                all_sources.append(source)
        merged["sources"] = all_sources
        
        # Use the longest/most detailed description
        best_desc = ""
        for project in projects:
            desc = project.get("description", "")
            if len(desc) > len(best_desc):
                best_desc = desc
        if best_desc:
            merged["description"] = best_desc
        
        return merged
    
# Utility functions for backward compatibility
def parse_projects_from_lines(lines: List[str]) -> List[Dict[str, Any]]:
    """Parse projects from lines using the default parser."""
    parser = ProjectParser()
    return parser.parse_section_lines(lines)


def extract_project_dates(text: str) -> Dict[str, Any]:
    """Extract dates from project text."""
    parser = ProjectParser()
    return parser._parse_dates(text)


def extract_tech_stack(text: str) -> List[str]:
    """Extract technology stack from project text."""
    parser = ProjectParser()
    return parser._extract_tech_stack(text)


