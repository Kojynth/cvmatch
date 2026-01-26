from .metrics_mixin import ParserMetricsMixin
"""
Enhanced soft skills parser with taxonomy mapping and section-aware extraction.

Provides robust parsing of soft skills from dedicated sections with:
- Multi-delimiter splitting (commas, semicolons, pipes, bullets)
- Canonical taxonomy mapping for consistent categorization
- Confidence scoring based on match quality and context
- Deduplication and false positive filtering
- PII-safe logging with metrics only
"""

import re
import json
from typing import List, Dict, Any, Optional, Set, Tuple
from pathlib import Path
from difflib import SequenceMatcher
from ..logging.safe_logger import get_safe_logger
from ..config import DEFAULT_PII_CONFIG
from ..utils.pii import validate_no_pii_leakage

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


class SoftSkillsParser(ParserMetricsMixin):
    """Enhanced parser for soft skills with taxonomy mapping and confidence scoring."""
    METRICS_COPY = True
    
    def __init__(self, rules_file: Optional[str] = None):
        """
        Initialize the soft skills parser with enhanced rules.
        
        Args:
            rules_file: Path to soft skills rules file (optional)
        """
        self.rules = self._load_rules(rules_file)
        self.logger = get_safe_logger(f"{__name__}.SoftSkillsParser", cfg=DEFAULT_PII_CONFIG)
        
        # Build optimized lookup structures
        self._build_taxonomy_lookup()
        self._compile_regex_patterns()
        
        # Metrics tracking
        self.metrics = {
            "lines_processed": 0,
            "tokens_extracted": 0,
            "canonicalized": 0,
            "filtered_false_positives": 0,
            "duplicates_removed": 0,
            "section_context_count": 0,
            "inline_context_count": 0
        }
    
    def _load_rules(self, rules_file: Optional[str] = None) -> Dict[str, Any]:
        """Load enhanced soft skills rules from JSON file."""
        if rules_file is None:
            rules_file = Path(__file__).parent.parent / "rules" / "soft_skills.json"
        
        try:
            with open(rules_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"SOFT_PARSER: failed to load rules from {rules_file} | {e}")
            # Return minimal fallback rules
            return {
                "taxonomy": {"communication": {"canonical": "Communication", "synonyms": ["communication"]}},
                "delimiters_regex": "\\s*[•·●\\-–—;,/|]\\s*",
                "confidence_weights": {"exact_match": 0.95},
                "block_phrases": []
            }
    
    def _build_taxonomy_lookup(self):
        """Build optimized taxonomy lookup structures."""
        self.synonym_to_canonical = {}
        self.canonical_skills = set()
        
        taxonomy = self.rules.get("taxonomy", {})
        
        for category, skill_info in taxonomy.items():
            canonical = skill_info.get("canonical", category.title())
            self.canonical_skills.add(canonical)
            
            synonyms = skill_info.get("synonyms", [])
            for synonym in synonyms:
                synonym_key = synonym.lower().strip()
                if synonym_key:
                    self.synonym_to_canonical[synonym_key] = canonical
                    
        self.logger.debug(f"SOFT_PARSER: built taxonomy lookup | "
                         f"canonical_skills={len(self.canonical_skills)} "
                         f"synonyms={len(self.synonym_to_canonical)}")
    
    def _compile_regex_patterns(self):
        """Compile regex patterns for performance."""
        delimiters_pattern = self.rules.get("delimiters_regex", "\\s*[•·●\\-–—;,/|]\\s*")
        self.delimiters_regex = re.compile(delimiters_pattern, re.IGNORECASE)
        
        # False positive filters
        fp_filters = self.rules.get("false_positive_filters", {})
        skip_patterns = fp_filters.get("skip_if_contains", [])
        
        self.false_positive_patterns = []
        for pattern in skip_patterns:
            try:
                self.false_positive_patterns.append(re.compile(pattern, re.IGNORECASE))
            except re.error as e:
                self.logger.warning(f"SOFT_PARSER: invalid regex pattern '{pattern}' | {e}")
    
    def parse_section_lines(self, lines: List[str], context: str = "section") -> List[Dict[str, Any]]:
        """
        Parse soft skills from a list of lines within a section.
        
        Args:
            lines: List of text lines from the soft skills section
            context: Context type ("section" or "inline")
            
        Returns:
            List of parsed soft skills with canonical names and confidence scores
        """
        if not lines:
            return []
        
        self.logger.info(f"SOFT_PARSER: starting parsing | lines={len(lines)} context={context}")
        
        all_skills = []
        
        for line_idx, line in enumerate(lines):
            if not line or len(line.strip()) < 2:
                continue
            
            self.metrics["lines_processed"] += 1
            
            # Skip lines that are clearly not soft skills
            if self._is_false_positive(line):
                self.metrics["filtered_false_positives"] += 1
                continue
            
            # Extract skills from this line
            line_skills = self._extract_skills_from_line(line, context, line_idx)
            all_skills.extend(line_skills)
        
        # Deduplicate skills
        if all_skills:
            deduplicated = self._deduplicate_skills(all_skills)
            self.metrics["duplicates_removed"] = len(all_skills) - len(deduplicated)
        else:
            deduplicated = []
        
        # Update context metrics
        if context == "section":
            self.metrics["section_context_count"] += len(deduplicated)
        else:
            self.metrics["inline_context_count"] += len(deduplicated)
        
        self.logger.info(f"SOFT_PARSER: completed | extracted={len(deduplicated)} "
                        f"duplicates_removed={self.metrics['duplicates_removed']}")
        
        return deduplicated
    
    def _extract_skills_from_line(self, line: str, context: str, line_idx: int) -> List[Dict[str, Any]]:
        """Extract and canonicalize soft skills from a single line."""
        line_clean = line.strip()
        
        # Skip block phrases (section headers)
        block_phrases = self.rules.get("block_phrases", [])
        if any(phrase.lower() in line_clean.lower() for phrase in block_phrases):
            return []
        
        # Split line by delimiters
        tokens = self._split_by_delimiters(line_clean)
        
        skills = []
        for token in tokens:
            token = token.strip()
            if not token or len(token) < 3:
                continue
            
            self.metrics["tokens_extracted"] += 1
            
            # Try to canonicalize this token
            canonical_result = self._canonicalize_skill(token)
            if canonical_result:
                skill_dict = {
                    **canonical_result,
                    "context": context,
                    "source_line": line_idx,
                    "evidence": token
                }
                skills.append(skill_dict)
                self.metrics["canonicalized"] += 1
        
        return skills
    
    def _split_by_delimiters(self, text: str) -> List[str]:
        """Split text by various delimiters (commas, pipes, bullets, etc.)."""
        # Use regex to split by multiple delimiters
        tokens = self.delimiters_regex.split(text)
        
        # Clean and filter tokens
        cleaned_tokens = []
        for token in tokens:
            token = token.strip()
            if token and len(token) >= 2:
                # Remove leading/trailing punctuation
                token = re.sub(r'^[\s\-•–—\*\+\>\|\[\]()]+', '', token)
                token = re.sub(r'[\s\-•–—\*\+\>\|\[\]()]+$', '', token)
                
                if token and len(token) >= 2:
                    cleaned_tokens.append(token)
        
        return cleaned_tokens
    
    def _canonicalize_skill(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Canonicalize a skill token to its taxonomy entry.
        
        Args:
            token: Raw skill token
            
        Returns:
            Dictionary with canonical info or None if not found
        """
        token_lower = token.lower().strip()
        
        # Direct lookup in synonyms
        if token_lower in self.synonym_to_canonical:
            canonical = self.synonym_to_canonical[token_lower]
            confidence = self._calculate_confidence("exact_match", canonical, token)
            
            return {
                "name": canonical,
                "canonical_category": self._get_category_for_canonical(canonical),
                "confidence": confidence,
                "match_type": "exact"
            }
        
        # Partial matching for compound phrases
        best_match = self._find_best_partial_match(token_lower)
        if best_match:
            canonical, similarity = best_match
            confidence = self._calculate_confidence("partial_match", canonical, token) * similarity
            
            return {
                "name": canonical,
                "canonical_category": self._get_category_for_canonical(canonical),
                "confidence": confidence,
                "match_type": "partial"
            }
        
        return None
    
    def _find_best_partial_match(self, token: str) -> Optional[Tuple[str, float]]:
        """Find the best partial match for a token in synonyms."""
        best_canonical = None
        best_similarity = 0.0
        min_similarity = 0.7  # Threshold for partial matches
        
        for synonym, canonical in self.synonym_to_canonical.items():
            if len(synonym) < 4 or len(token) < 4:
                continue  # Skip short tokens for partial matching
            
            # Check if one contains the other
            if synonym in token or token in synonym:
                similarity = min(len(synonym), len(token)) / max(len(synonym), len(token))
            else:
                # Use sequence matching for similarity
                similarity = SequenceMatcher(None, synonym, token).ratio()
            
            if similarity >= min_similarity and similarity > best_similarity:
                best_similarity = similarity
                best_canonical = canonical
        
        if best_canonical and best_similarity >= min_similarity:
            return best_canonical, best_similarity
        
        return None
    
    def _get_category_for_canonical(self, canonical: str) -> str:
        """Get the taxonomy category for a canonical skill name."""
        taxonomy = self.rules.get("taxonomy", {})
        
        for category, skill_info in taxonomy.items():
            if skill_info.get("canonical") == canonical:
                return category
        
        return "other"
    
    def _calculate_confidence(self, match_type: str, canonical: str, evidence: str) -> float:
        """Calculate confidence score based on match type and quality."""
        weights = self.rules.get("confidence_weights", {})
        
        base_confidence = weights.get(match_type, 0.8)
        
        # Bonus for common/important skills
        high_value_skills = {
            "Communication", "Teamwork", "Leadership", "Problem Solving",
            "Time Management", "Adaptability", "Initiative"
        }
        
        if canonical in high_value_skills:
            base_confidence += 0.05
        
        # Penalty for very short evidence
        if len(evidence) < 5:
            base_confidence -= 0.1
        
        # Bonus for evidence containing multiple words
        if len(evidence.split()) > 1:
            base_confidence += 0.05
        
        return max(0.0, min(1.0, base_confidence))
    
    def _is_false_positive(self, line: str) -> bool:
        """Check if a line should be filtered as a false positive."""
        line_lower = line.lower()
        
        # Check against compiled regex patterns
        for pattern in self.false_positive_patterns:
            if pattern.search(line_lower):
                return True
        
        # Check length constraints
        fp_filters = self.rules.get("false_positive_filters", {})
        min_length = fp_filters.get("min_token_length", 3)
        max_length = fp_filters.get("max_token_length", 50)
        
        if len(line.strip()) < min_length or len(line.strip()) > max_length:
            return True
        
        # Filter obvious non-skills
        non_skill_patterns = [
            r'^\d+[\.\)]\s*',  # Numbered lists
            r'^[A-Z\s]+:$',    # Section headers
            r'^\s*[-•*]\s*$',  # Empty bullets
            r'voir\s+cv|see\s+resume|curriculum\s+vitae'  # CV references
        ]
        
        for pattern in non_skill_patterns:
            if re.match(pattern, line_lower):
                return True
        
        return False
    
    def _deduplicate_skills(self, skills: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove duplicate skills, keeping the highest confidence entry."""
        if not skills:
            return []
        
        # Group by canonical name
        skill_groups = {}
        for skill in skills:
            canonical = skill["name"]
            if canonical not in skill_groups:
                skill_groups[canonical] = []
            skill_groups[canonical].append(skill)
        
        deduplicated = []
        for canonical, group in skill_groups.items():
            if len(group) == 1:
                deduplicated.append(group[0])
            else:
                # Merge duplicates, keeping the highest confidence
                best_skill = max(group, key=lambda s: s["confidence"])
                
                # Merge evidence from all sources
                all_evidence = []
                all_sources = []
                for skill in group:
                    evidence = skill.get("evidence", "")
                    if evidence and evidence not in all_evidence:
                        all_evidence.append(evidence)
                    
                    source = skill.get("source_line", -1)
                    if source >= 0 and source not in all_sources:
                        all_sources.append(source)
                
                merged_skill = best_skill.copy()
                merged_skill["evidence"] = "; ".join(all_evidence) if len(all_evidence) > 1 else all_evidence[0] if all_evidence else best_skill.get("evidence", "")
                merged_skill["source_lines"] = all_sources
                
                deduplicated.append(merged_skill)
        
        return deduplicated
    
# Utility functions for backward compatibility
def parse_soft_skills_from_lines(lines: List[str], context: str = "section") -> List[Dict[str, Any]]:
    """Parse soft skills from lines using the default parser."""
    parser = SoftSkillsParser()
    return parser.parse_section_lines(lines, context)


def canonicalize_soft_skill(token: str) -> Optional[Dict[str, Any]]:
    """Canonicalize a single soft skill token."""
    parser = SoftSkillsParser()
    return parser._canonicalize_skill(token)


def split_soft_skills_line(line: str) -> List[str]:
    """Split a line into soft skill tokens."""
    parser = SoftSkillsParser()
    return parser._split_by_delimiters(line)

