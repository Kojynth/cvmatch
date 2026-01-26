"""
Enhanced language normalization module for context-aware language extraction.

Provides canonicalization, level mapping, CEFR ranking, and context detection
to improve language extraction accuracy while filtering nationality contexts.
"""

import re
import json
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
from ..logging.safe_logger import get_safe_logger
from ..config import DEFAULT_PII_CONFIG
from ..utils.pii import validate_no_pii_leakage

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


class LanguageNormalizer:
    """Advanced language normalizer with nationality filtering and canonicalization."""
    
    def __init__(self, rules_file: Optional[str] = None):
        """
        Initialize the language normalizer with enhanced rules.
        
        Args:
            rules_file: Path to language rules file (optional)
        """
        self.rules = self._load_rules(rules_file)
        self.logger = get_safe_logger(f"{__name__}.LanguageNormalizer", cfg=DEFAULT_PII_CONFIG)
        
        # Build quick lookup maps for performance
        self._build_lookup_maps()
        
        # Metrics tracking
        self.metrics = {
            "canonicalized": 0,
            "nationality_blocked": 0,
            "context_detected": 0,
            "levels_mapped": 0,
            "duplicates_merged": 0
        }
    
    def _load_rules(self, rules_file: Optional[str] = None) -> Dict[str, Any]:
        """Load enhanced language rules from JSON file."""
        if rules_file is None:
            rules_file = Path(__file__).parent.parent / "rules" / "languages.json"
        
        try:
            with open(rules_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"LANG_NORM: failed to load rules from {rules_file} | {e}")
            # Return minimal fallback rules
            return {
                "canonical_map": {"english": "English", "français": "French"},
                "level_synonyms": {"fluent": "C1", "basic": "A1"},
                "blocklist_context": {"nationality": []},
                "allowlist_signals": []
            }
    
    def _build_lookup_maps(self):
        """Build optimized lookup maps for fast pattern matching."""
        self.canonical_patterns = {}
        self.level_patterns = {}
        self.nationality_patterns = []
        self.allowlist_patterns = []
        
        # Build canonical language patterns
        canonical_map = self.rules.get("canonical_map", {})
        for patterns, canonical in canonical_map.items():
            # Split patterns by | and create regex for each
            for pattern in patterns.split('|'):
                if pattern.strip():
                    self.canonical_patterns[pattern.strip().lower()] = canonical
        
        # Build level synonym patterns  
        level_synonyms = self.rules.get("level_synonyms", {})
        for patterns, level in level_synonyms.items():
            compiled_pattern = re.compile(f"\\b({patterns})\\b", re.IGNORECASE)
            self.level_patterns[compiled_pattern] = level
        
        # Build nationality blocklist patterns
        blocklist = self.rules.get("blocklist_context", {}).get("nationality", [])
        for pattern in blocklist:
            try:
                self.nationality_patterns.append(re.compile(pattern, re.IGNORECASE))
            except re.error as e:
                self.logger.warning(f"LANG_NORM: invalid nationality pattern '{pattern}' | {e}")
        
        # Build allowlist signal patterns
        allowlist = self.rules.get("allowlist_signals", [])
        for pattern in allowlist:
            try:
                self.allowlist_patterns.append(re.compile(pattern, re.IGNORECASE))
            except re.error as e:
                self.logger.warning(f"LANG_NORM: invalid allowlist pattern '{pattern}' | {e}")
        
        # Phase 3.1: Build certification to language mapping
        self.certification_patterns = {}
        certification_map = self.rules.get("certification_to_language", {})
        for cert_patterns, language in certification_map.items():
            for cert_pattern in cert_patterns.split('|'):
                if cert_pattern.strip():
                    # Use word boundaries for exact matches
                    compiled_pattern = re.compile(rf'\b{re.escape(cert_pattern.strip())}\b', re.IGNORECASE)
                    self.certification_patterns[compiled_pattern] = language
    
    def canonicalize_language(self, name: str) -> Optional[str]:
        """
        Canonicalize language name using enhanced mapping.
        
        Args:
            name: Raw language name to canonicalize
            
        Returns:
            Canonical language name or None if not found
        """
        if not name or len(name.strip()) < 2:
            return None
        
        normalized_name = name.strip().lower()
        safe_name = validate_no_pii_leakage(name, DEFAULT_PII_CONFIG.HASH_SALT)
        
        # Direct lookup first (most common case)
        if normalized_name in self.canonical_patterns:
            canonical = self.canonical_patterns[normalized_name]
            self.metrics["canonicalized"] += 1
            self.logger.debug(f"LANG_NORM: direct match | '{safe_name[:20]}...' -> '{canonical}'")
            return canonical
        
        # Phase 3.1: Partial matching for compound names like "anglais courant" with enhanced filtering
        for pattern, canonical in self.canonical_patterns.items():
            if pattern in normalized_name or normalized_name in pattern:
                # Phase 3.1: Stricter filtering to avoid short code matches
                if (len(pattern) >= 4 and len(normalized_name) >= 4 and 
                    # Extra check: avoid matching very short patterns inside words
                    not (len(pattern) <= 3 and pattern in normalized_name and len(normalized_name) > len(pattern) * 2)):
                    self.metrics["canonicalized"] += 1
                    self.logger.debug(f"LANG_NORM: partial match | '{safe_name[:20]}...' -> '{canonical}' via '{pattern}'")
                    return canonical
        
        return None
    
    def extract_language_from_certification(self, text: str) -> List[Tuple[str, str]]:
        """
        Phase 3.1: Extrait les langues à partir des certifications (TOEFL→English, DELF→French, etc.)
        
        Args:
            text: Texte à analyser
            
        Returns:
            List of (language, certification) tuples
        """
        extracted_languages = []
        
        for pattern, language in self.certification_patterns.items():
            matches = pattern.finditer(text)
            for match in matches:
                certification = match.group(0)
                extracted_languages.append((language, certification))
                self.logger.debug(f"LANG_CERT: found '{certification}' -> '{language}'")
        
        return extracted_languages
    
    def map_level_from_text(self, text: str) -> Optional[str]:
        """
        Extract and map language level from text using enhanced synonyms.
        
        Args:
            text: Text to analyze for level indicators
            
        Returns:
            CEFR level (A1-C2) or None if no level found
        """
        if not text:
            return None
        
        safe_text = validate_no_pii_leakage(text, DEFAULT_PII_CONFIG.HASH_SALT)
        
        # Check explicit CEFR levels first
        cefr_pattern = self.rules.get("cefr_regex", "")
        if cefr_pattern:
            match = re.search(cefr_pattern, text, re.IGNORECASE)
            if match:
                level = match.group(1).upper()
                self.metrics["levels_mapped"] += 1
                self.logger.debug(f"LANG_NORM: explicit CEFR | '{safe_text[:30]}...' -> {level}")
                return level
        
        # Check level synonyms
        for pattern, level in self.level_patterns.items():
            if pattern.search(text):
                self.metrics["levels_mapped"] += 1
                self.logger.debug(f"LANG_NORM: synonym match | '{safe_text[:30]}...' -> {level}")
                return level
        
        return None
    
    def cefr_rank(self, level: Optional[str]) -> int:
        """
        Get numeric rank for CEFR level for comparison.
        
        Args:
            level: CEFR level string
            
        Returns:
            Numeric rank (0 for None, 1-6 for A1-C2)
        """
        if not level:
            return 0
        
        hierarchy = self.rules.get("cefr_hierarchy", {})
        return hierarchy.get(level.upper(), 0)
    
    def detect_context(self, line: str, context_lines: List[str], line_idx: int = -1) -> str:
        """
        Detect the context type for language extraction.
        
        Args:
            line: Current line to analyze
            context_lines: Surrounding lines for context
            line_idx: Index of current line in context
            
        Returns:
            Context type: 'nationality', 'languages_section', 'proficiency_signal', 'generic'
        """
        if not line:
            return 'generic'
        
        safe_line = validate_no_pii_leakage(line, DEFAULT_PII_CONFIG.HASH_SALT)
        
        # Check for nationality context first (highest priority block)
        for pattern in self.nationality_patterns:
            if pattern.search(line):
                self.metrics["nationality_blocked"] += 1
                self.logger.debug(f"LANG_NORM: nationality blocked | '{safe_line[:30]}...'")
                return 'nationality'
        
        # Check broader context for nationality indicators
        if context_lines and line_idx >= 0:
            context_window = max(0, line_idx - 2), min(len(context_lines), line_idx + 3)
            context_text = " ".join(context_lines[context_window[0]:context_window[1]]).lower()
            
            for pattern in self.nationality_patterns:
                if pattern.search(context_text):
                    self.metrics["nationality_blocked"] += 1
                    self.logger.debug(f"LANG_NORM: nationality blocked by context | '{safe_line[:30]}...'")
                    return 'nationality'
        
        # Check for languages section headers
        language_headers = self.rules.get("context_headers", {}).get("languages", [])
        if context_lines and line_idx >= 0:
            # Look for headers in ±2 lines around current position
            search_start = max(0, line_idx - 2)
            search_end = min(len(context_lines), line_idx + 3)
            
            for i in range(search_start, search_end):
                if i < len(context_lines):
                    header_line = context_lines[i].lower().strip()
                    
                    # Check if line is a section header
                    if any(header in header_line for header in language_headers):
                        # Verify it's actually a header (short line, maybe with colons/dashes)
                        if len(header_line) < 50 and (
                            header_line.endswith(':') or 
                            header_line.endswith('-') or
                            len(header_line.split()) <= 3
                        ):
                            self.metrics["context_detected"] += 1
                            self.logger.debug(f"LANG_NORM: languages section | '{safe_line[:30]}...' near header '{header_line[:20]}...'")
                            return 'languages_section'
        
        # Check for proficiency signals in the text
        for pattern in self.allowlist_patterns:
            if pattern.search(line):
                self.metrics["context_detected"] += 1
                self.logger.debug(f"LANG_NORM: proficiency signal | '{safe_line[:30]}...'")
                return 'proficiency_signal'
        
        return 'generic'
    
    def has_proficiency_signals(self, text: str) -> bool:
        """
        Check if text contains language proficiency indicators.
        
        Args:
            text: Text to check for proficiency signals
            
        Returns:
            True if proficiency signals detected
        """
        if not text:
            return False
        
        # Check allowlist patterns
        for pattern in self.allowlist_patterns:
            if pattern.search(text):
                return True
        
        # Check for explicit CEFR levels
        cefr_pattern = self.rules.get("cefr_regex", "")
        if cefr_pattern and re.search(cefr_pattern, text, re.IGNORECASE):
            return True
        
        return False
    
    def get_source_priority(self, context: str, has_level: bool = False) -> int:
        """
        Get priority score for source context.
        
        Args:
            context: Context type from detect_context()
            has_level: Whether explicit level was found
            
        Returns:
            Priority score (higher = better)
        """
        source_priority = self.rules.get("source_priority", {})
        
        if has_level:
            return source_priority.get("explicit_level", 3)
        elif context == "languages_section":
            return source_priority.get("languages_section", 2)
        elif context == "proficiency_signal":
            return source_priority.get("proficiency_signal", 1)
        else:
            return source_priority.get("generic_context", 0)
    
    def merge_duplicate_languages(self, languages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Merge duplicate language entries, keeping the strongest evidence.
        
        Args:
            languages: List of language extraction results
            
        Returns:
            Deduplicated list with merged sources and best evidence
        """
        if not languages:
            return []
        
        # Group by canonical language name
        language_groups = {}
        for lang in languages:
            canonical = self.canonicalize_language(lang.get("language", "")) or lang.get("language", "Unknown")
            
            if canonical not in language_groups:
                language_groups[canonical] = []
            language_groups[canonical].append(lang)
        
        merged_languages = []
        total_duplicates = 0
        
        for canonical, group in language_groups.items():
            if len(group) == 1:
                # No duplicates, keep as-is but ensure canonical name
                lang = group[0].copy()
                lang["language"] = canonical
                merged_languages.append(lang)
            else:
                # Merge duplicates
                total_duplicates += len(group) - 1
                merged = self._merge_language_group(canonical, group)
                merged_languages.append(merged)
                
                self.logger.info(f"LANG_NORM: merged {len(group)} entries for '{canonical}' "
                               f"-> level='{merged.get('level', 'None')}' "
                               f"sources={len(merged.get('sources', []))}")
        
        self.metrics["duplicates_merged"] += total_duplicates
        
        return merged_languages
    
    def _merge_language_group(self, canonical: str, group: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Merge a group of language entries for the same language."""
        # Sort by priority: (cefr_rank, source_priority, confidence)
        def sort_key(lang):
            level = lang.get("level")
            context = lang.get("context", "generic")
            confidence = lang.get("confidence", 0.0)
            has_level = level is not None and level != ""
            
            return (
                self.cefr_rank(level),
                self.get_source_priority(context, has_level),
                confidence
            )
        
        sorted_group = sorted(group, key=sort_key, reverse=True)
        best_lang = sorted_group[0]
        
        # Create merged result
        merged = {
            "language": canonical,
            "level": best_lang.get("level"),
            "evidence": best_lang.get("evidence", ""),
            "context": best_lang.get("context", "generic"),
            "confidence": best_lang.get("confidence", 0.0),
            "sources": []
        }
        
        # Collect all sources and evidence
        all_evidence = []
        for lang in group:
            source = lang.get("source", "unknown")
            if source not in merged["sources"]:
                merged["sources"].append(source)
            
            evidence = lang.get("evidence", "")
            if evidence and evidence not in all_evidence:
                all_evidence.append(evidence)
        
        # Merge evidence text
        if len(all_evidence) > 1:
            merged["evidence"] = "; ".join(all_evidence)
        
        return merged
    
    def get_metrics(self) -> Dict[str, int]:
        """Get normalization metrics for monitoring."""
        return self.metrics.copy()
    
    def reset_metrics(self):
        """Reset metrics counters."""
        for key in self.metrics:
            self.metrics[key] = 0


# Utility functions for backward compatibility
def canonicalize_language(name: str) -> Optional[str]:
    """Canonicalize a language name using the default normalizer."""
    normalizer = LanguageNormalizer()
    return normalizer.canonicalize_language(name)


def map_level_from_text(text: str) -> Optional[str]:
    """Map language level from text using the default normalizer."""
    normalizer = LanguageNormalizer()
    return normalizer.map_level_from_text(text)


def cefr_rank(level: Optional[str]) -> int:
    """Get CEFR level numeric rank using the default normalizer."""
    normalizer = LanguageNormalizer()
    return normalizer.cefr_rank(level)


def detect_language_context(line: str, context_lines: List[str], line_idx: int = -1) -> str:
    """Detect language extraction context using the default normalizer."""
    normalizer = LanguageNormalizer()
    return normalizer.detect_context(line, context_lines, line_idx)


def merge_duplicate_languages(languages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Merge duplicate language entries using the default normalizer."""
    normalizer = LanguageNormalizer()
    return normalizer.merge_duplicate_languages(languages)