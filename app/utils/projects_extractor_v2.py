"""
Projects Extractor V2 - Enhanced project extraction with no-progress guard.

This version implements:
- Explicit slice acceptance (lines[start:end]) from boundaries
- No-progress guard with prev_candidate_count tracking
- Limited passes (1 default, 2 with feature flag)
- Returns lines_processed>0 when non-empty slice inspected
"""

import re
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from ..logging.safe_logger import get_safe_logger
from ..config import DEFAULT_PII_CONFIG, get_feature_flag

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


@dataclass
class ProjectExtractionMetrics:
    """Métriques pour l'extraction de projets V2."""
    lines_received: int = 0
    lines_processed: int = 0
    passes_executed: int = 0
    candidates_initial: int = 0
    candidates_final: int = 0
    no_progress_breaks: int = 0
    empty_slice_skips: int = 0
    projects_extracted: int = 0


class ProjectsExtractorV2:
    """
    Enhanced Projects Extractor V2 with no-progress guard.
    
    Key improvements:
    - Accepts explicit slice from section boundaries
    - No-progress guard prevents infinite loops
    - Configurable pass limits via feature flags
    - Deterministic progress tracking
    """
    
    def __init__(self, use_feature_flags: bool = True):
        """Initialize extractor with feature flag support."""
        self.use_feature_flags = use_feature_flags
        self.metrics = ProjectExtractionMetrics()
        
        # Project detection patterns
        self.project_patterns = [
            # Titles with common project indicators
            r'(?i)\b(projet|project|développement|development|création|creation|réalisation|implementation)\s+[:\-]?\s*(.{3,60})',
            # Direct project naming
            r'(?i)^[\s\-\•]*(.{10,80})\s*[\-\–]\s*(développé|created|built|implemented|designed)',
            # Project with context
            r'(?i)\b(application|site|système|system|plateforme|platform|outil|tool)\s+(.{5,50})',
            # GitHub/portfolio style
            r'(?i)\bhttps?://(?:github\.com|gitlab\.com)/[^\s]+',
            # Tech stack indicators
            r'(?i)\b(stack|technologies?|langages?|languages?)\s*[:\-]\s*(.{10,100})',
        ]
        
        # Anti-patterns (things that are NOT projects)
        self.anti_patterns = [
            r'(?i)\b(formation|course|école|school|université|university|diplôme|degree)',
            r'(?i)\b(entreprise|company|société|corporation|inc\.|ltd\.)',
            r'(?i)\b(stage|internship|emploi|job|poste|position)',
            r'(?i)^(janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)',
            r'(?i)^(january|february|march|april|may|june|july|august|september|october|november|december)',
        ]
    
    def extract_projects(self, lines_slice: List[str], start_idx: int = 0, end_idx: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Extract projects from explicit slice with no-progress guard.
        
        Args:
            lines_slice: Explicit slice of lines to process
            start_idx: Start index in original document (for context)
            end_idx: End index in original document (for context)
            
        Returns:
            List of extracted project dictionaries
        """
        # Initialize metrics
        self.metrics = ProjectExtractionMetrics()
        self.metrics.lines_received = len(lines_slice)
        
        if end_idx is None:
            end_idx = start_idx + len(lines_slice)
        
        logger.info(f"PROJECTS_V2: extract_start | slice_size={len(lines_slice)} range=({start_idx}-{end_idx})")
        
        # Handle empty slice
        if not lines_slice:
            logger.info("PROJECTS_V2: empty_slice | skipping extraction")
            self.metrics.empty_slice_skips = 1
            return []
        
        # Determine pass limits from feature flags
        max_passes = self._get_max_passes()
        
        # Extract projects with no-progress guard
        projects = self._extract_with_no_progress_guard(lines_slice, max_passes)
        
        # Update final metrics
        self.metrics.lines_processed = len([line for line in lines_slice if line.strip()])
        self.metrics.projects_extracted = len(projects)
        
        # Log final metrics
        logger.info(f"PROJECTS_V2: extract_complete | "
                   f"processed={self.metrics.lines_processed}/{self.metrics.lines_received} "
                   f"passes={self.metrics.passes_executed}/{max_passes} "
                   f"projects={self.metrics.projects_extracted} "
                   f"no_progress_breaks={self.metrics.no_progress_breaks}")
        
        return projects
    
    def _get_max_passes(self) -> int:
        """Get maximum number of passes from feature flags."""
        if not self.use_feature_flags:
            return 1  # Conservative default
        
        # Check feature flag for extra pass
        if get_feature_flag("proj_v2_extra_pass", default=False):
            return 2
        else:
            return 1
    
    def _extract_with_no_progress_guard(self, lines_slice: List[str], max_passes: int) -> List[Dict[str, Any]]:
        """
        Extract projects with no-progress guard to prevent infinite loops.
        
        Args:
            lines_slice: Lines to process
            max_passes: Maximum number of passes allowed
            
        Returns:
            List of extracted projects
        """
        candidates = []
        prev_candidate_count = -1  # Initialize to -1 to detect first iteration
        
        for pass_num in range(1, max_passes + 1):
            logger.debug(f"PROJECTS_V2: pass_{pass_num} | prev_candidates={prev_candidate_count}")
            
            # Extract candidates for this pass
            pass_candidates = self._extract_candidates_single_pass(lines_slice, pass_num)
            
            # Update metrics
            self.metrics.passes_executed = pass_num
            if pass_num == 1:
                self.metrics.candidates_initial = len(pass_candidates)
            
            # No-progress guard: break if no change in candidate count
            current_count = len(pass_candidates)
            if current_count == prev_candidate_count:
                logger.info(f"PROJECTS_V2: no_progress_detected | pass_{pass_num} count={current_count} (unchanged)")
                self.metrics.no_progress_breaks += 1
                break
            
            # Update candidates and continue
            candidates = pass_candidates
            prev_candidate_count = current_count
            
            logger.debug(f"PROJECTS_V2: pass_{pass_num}_complete | candidates={current_count}")
        
        # Finalize and validate candidates
        self.metrics.candidates_final = len(candidates)
        projects = self._finalize_projects(candidates)
        
        return projects
    
    def _extract_candidates_single_pass(self, lines_slice: List[str], pass_num: int) -> List[Dict[str, Any]]:
        """
        Extract project candidates in a single pass.
        
        Args:
            lines_slice: Lines to process
            pass_num: Current pass number (for logging)
            
        Returns:
            List of project candidates
        """
        candidates = []
        
        for i, line in enumerate(lines_slice):
            line = line.strip()
            if not line:
                continue
            
            # Check anti-patterns first
            if self._matches_anti_patterns(line):
                continue
            
            # Extract project from line
            project = self._extract_project_from_line(line, i)
            if project:
                candidates.append(project)
        
        logger.debug(f"PROJECTS_V2: pass_{pass_num} | extracted={len(candidates)} candidates")
        return candidates
    
    def _matches_anti_patterns(self, line: str) -> bool:
        """Check if line matches anti-patterns (not a project)."""
        for pattern in self.anti_patterns:
            if re.search(pattern, line):
                return True
        return False
    
    def _extract_project_from_line(self, line: str, line_idx: int) -> Optional[Dict[str, Any]]:
        """
        Extract a single project from a line.
        
        Args:
            line: Line to analyze
            line_idx: Line index for reference
            
        Returns:
            Project dictionary or None
        """
        project = None
        
        # Try each project pattern
        for pattern in self.project_patterns:
            match = re.search(pattern, line)
            if match:
                project = self._create_project_from_match(match, line, line_idx)
                break
        
        # If no pattern match, try heuristic extraction
        if not project:
            project = self._extract_project_heuristic(line, line_idx)
        
        return project
    
    def _create_project_from_match(self, match: re.Match, line: str, line_idx: int) -> Dict[str, Any]:
        """Create project dictionary from regex match."""
        groups = match.groups()
        
        # Extract title (usually the most significant group)
        title = self._clean_project_title(groups[-1] if groups else line[:50])
        
        # Basic project structure
        project = {
            "title": title,
            "description": line,
            "line_index": line_idx,
            "extraction_method": "pattern",
            "confidence": 0.8
        }
        
        # Try to extract additional fields
        project.update(self._extract_additional_fields(line))
        
        return project
    
    def _extract_project_heuristic(self, line: str, line_idx: int) -> Optional[Dict[str, Any]]:
        """
        Heuristic project extraction for lines without pattern matches.
        
        Args:
            line: Line to analyze
            line_idx: Line index
            
        Returns:
            Project dictionary or None
        """
        # Minimum length check
        if len(line.strip()) < 10:
            return None
        
        # Check for project-like indicators
        project_score = self._calculate_project_score(line)
        
        if project_score >= 0.5:  # Threshold for heuristic acceptance
            title = self._extract_heuristic_title(line)
            
            return {
                "title": title,
                "description": line,
                "line_index": line_idx,
                "extraction_method": "heuristic",
                "confidence": project_score
            }
        
        return None
    
    def _calculate_project_score(self, line: str) -> float:
        """Calculate project likelihood score for a line."""
        score = 0.0
        line_lower = line.lower()
        
        # Tech keywords
        tech_keywords = [
            'web', 'mobile', 'api', 'database', 'frontend', 'backend', 
            'react', 'vue', 'angular', 'python', 'java', 'javascript',
            'app', 'application', 'système', 'plateforme', 'site'
        ]
        
        for keyword in tech_keywords:
            if keyword in line_lower:
                score += 0.2
        
        # Project-specific verbs
        project_verbs = [
            'développé', 'créé', 'conçu', 'implémenté', 'réalisé',
            'developed', 'created', 'designed', 'implemented', 'built'
        ]
        
        for verb in project_verbs:
            if verb in line_lower:
                score += 0.3
        
        # Structure indicators
        if re.search(r'[\-\–\:]', line):  # Separation indicators
            score += 0.1
        
        if re.search(r'\bhttps?://', line):  # URLs
            score += 0.3
        
        return min(1.0, score)
    
    def _extract_heuristic_title(self, line: str) -> str:
        """Extract title using heuristics."""
        # Try to find title before separator
        separators = [' - ', ' – ', ' : ', ' | ']
        
        for sep in separators:
            if sep in line:
                parts = line.split(sep, 1)
                if len(parts[0]) > 3:
                    return self._clean_project_title(parts[0])
        
        # Fallback: use first significant part
        words = line.split()
        if len(words) >= 2:
            return self._clean_project_title(' '.join(words[:5]))
        
        return self._clean_project_title(line[:50])
    
    def _extract_additional_fields(self, line: str) -> Dict[str, Any]:
        """Extract additional project fields from line."""
        fields = {}
        
        # Extract URLs
        url_match = re.search(r'https?://[^\s]+', line)
        if url_match:
            fields['url'] = url_match.group()
        
        # Extract technologies (basic pattern)
        tech_pattern = r'(?i)\b(?:avec|using|built with)\s+([^,.]+)'
        tech_match = re.search(tech_pattern, line)
        if tech_match:
            fields['technologies'] = [tech.strip() for tech in tech_match.group(1).split()]
        
        return fields
    
    def _clean_project_title(self, title: str) -> str:
        """Clean and normalize project title."""
        if not title:
            return "Untitled Project"
        
        # Remove common prefixes
        prefixes = ['projet ', 'project ', 'développement ', 'development ']
        title_lower = title.lower()
        
        for prefix in prefixes:
            if title_lower.startswith(prefix):
                title = title[len(prefix):]
                break
        
        # Clean and trim
        title = re.sub(r'[^\w\s\-\.,!?]', '', title).strip()
        title = re.sub(r'\s+', ' ', title)  # Normalize whitespace
        
        # Capitalize first letter
        if title:
            title = title[0].upper() + title[1:]
        
        return title[:100]  # Limit length
    
    def _finalize_projects(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Finalize and deduplicate project candidates.
        
        Args:
            candidates: Raw project candidates
            
        Returns:
            Finalized project list
        """
        if not candidates:
            return []
        
        # Remove duplicates based on title similarity
        unique_projects = []
        seen_titles = set()
        
        for project in candidates:
            title_key = self._normalize_title_for_dedup(project.get('title', ''))
            
            if title_key and title_key not in seen_titles:
                seen_titles.add(title_key)
                unique_projects.append(project)
        
        # Sort by confidence (highest first)
        unique_projects.sort(key=lambda p: p.get('confidence', 0), reverse=True)
        
        logger.debug(f"PROJECTS_V2: finalized | {len(candidates)} candidates → {len(unique_projects)} unique")
        
        return unique_projects
    
    def _normalize_title_for_dedup(self, title: str) -> str:
        """Normalize title for deduplication."""
        if not title:
            return ""
        
        # Normalize to lowercase, remove special chars
        normalized = re.sub(r'[^\w\s]', '', title.lower())
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        
        return normalized
    
    def get_metrics(self) -> ProjectExtractionMetrics:
        """Get extraction metrics."""
        return self.metrics


# Convenience function for easy usage
def extract_projects_v2(lines_slice: List[str], start_idx: int = 0, end_idx: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Convenience function for project extraction V2.
    
    Args:
        lines_slice: Explicit slice of lines to process  
        start_idx: Start index in original document
        end_idx: End index in original document
        
    Returns:
        List of extracted projects
    """
    extractor = ProjectsExtractorV2()
    return extractor.extract_projects(lines_slice, start_idx, end_idx)