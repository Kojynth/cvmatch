"""
Pattern Registry System for CV Extraction Quality Guardrails.

Centralized registry of extraction patterns with metadata for overfitting control,
diversity monitoring, and quality enforcement across all CV sections.
"""

import json
from dataclasses import dataclass, asdict
from typing import Dict, List, Any, Optional, Set
from pathlib import Path
from datetime import datetime
from ..logging.safe_logger import get_safe_logger
from ..config import DEFAULT_PII_CONFIG

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


@dataclass
class PatternDef:
    """Definition of an extraction pattern with quality controls."""
    id: str                    # Unique pattern ID (e.g., "exp.title_company_inline.v1")
    section: str               # Section: "exp" | "edu" | "certs" | "lang" | "soft" | "proj"
    weight: float = 1.0        # Initial scoring weight for pattern
    enabled: bool = True       # Whether pattern is active
    max_share: float = 0.6     # Max percentage of section candidates this pattern can claim
    min_evidence: int = 1      # Minimum evidence requirements for pattern activation
    notes: str = ""            # Description/usage notes
    
    def __post_init__(self):
        """Validate pattern definition."""
        if not self.id or not self.section:
            raise ValueError(f"Pattern must have valid id and section")
        
        if not (0.0 <= self.weight <= 5.0):
            raise ValueError(f"Pattern weight must be in [0.0, 5.0], got {self.weight}")
        
        if not (0.1 <= self.max_share <= 1.0):
            raise ValueError(f"Pattern max_share must be in [0.1, 1.0], got {self.max_share}")


@dataclass 
class PatternUsage:
    """Tracking pattern usage during extraction."""
    pattern_id: str
    items_extracted: int = 0
    total_candidates: int = 0
    confidence_scores: List[float] = None
    
    def __post_init__(self):
        if self.confidence_scores is None:
            self.confidence_scores = []
    
    @property
    def usage_rate(self) -> float:
        """Percentage of candidates extracted by this pattern."""
        return self.items_extracted / max(self.total_candidates, 1)
    
    @property
    def avg_confidence(self) -> float:
        """Average confidence of extracted items."""
        return sum(self.confidence_scores) / len(self.confidence_scores) if self.confidence_scores else 0.0


class PatternRegistry:
    """Central registry for extraction patterns with quality controls."""
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize pattern registry with default or custom patterns."""
        self.patterns: Dict[str, PatternDef] = {}
        self.usage_tracking: Dict[str, PatternUsage] = {}
        self.logger = get_safe_logger(f"{__name__}.PatternRegistry", cfg=DEFAULT_PII_CONFIG)
        
        # Load default patterns
        self._load_default_patterns()
        
        # Load custom config if provided
        if config_path and Path(config_path).exists():
            self._load_config(config_path)
        
        self.logger.info(f"PATTERN_REGISTRY: initialized | patterns={len(self.patterns)} | "
                        f"sections={len(self.get_sections())}")
    
    def _load_default_patterns(self):
        """Load the default set of extraction patterns."""
        
        # EXP Patterns - ordered by reliability
        exp_patterns = [
            PatternDef(
                id="exp.date_title_company.v1",
                section="exp", 
                weight=1.2,
                max_share=0.60,
                min_evidence=2,  # Date + (title OR company)
                notes="Most reliable: date line followed by title/company"
            ),
            PatternDef(
                id="exp.bullet_company_role_dates.v1", 
                section="exp",
                weight=1.1,
                max_share=0.60,
                min_evidence=2,  # Bullet + company/role
                notes="Structured bullet points with clear role/company/dates"
            ),
            PatternDef(
                id="exp.title_company_inline.v1",
                section="exp",
                weight=1.0, 
                max_share=0.50,  # Lower max due to noise susceptibility
                min_evidence=2,  # Title + company or employment keywords
                notes="Inline format - susceptible to false positives, needs guards"
            ),
            PatternDef(
                id="exp.internship_keywords.v1",
                section="exp",
                weight=0.9,
                max_share=0.40,
                min_evidence=1,  # Internship keyword
                notes="Internship-specific extraction with relaxed requirements"
            )
        ]
        
        # EDU Patterns
        edu_patterns = [
            PatternDef(
                id="edu.degree_school_line.v1",
                section="edu",
                weight=1.1,
                max_share=0.60,
                min_evidence=2,  # Degree + school
                notes="Clear degree and school on same/adjacent lines"
            ),
            PatternDef(
                id="edu.school_degree_line.v1", 
                section="edu",
                weight=1.0,
                max_share=0.60,
                min_evidence=2,  # School + degree
                notes="School name followed by degree information"
            ),
            PatternDef(
                id="edu.period_school_block.v1",
                section="edu", 
                weight=0.9,
                max_share=0.50,
                min_evidence=2,  # Period + school
                notes="Time period with school block identification"
            )
        ]
        
        # CERTS Patterns
        cert_patterns = [
            PatternDef(
                id="cert.test_vendor_line.v1",
                section="certs",
                weight=1.0,
                max_share=0.80,
                min_evidence=1,  # Test name OR vendor
                notes="Standard certification tests (TOEFL, IELTS, etc.)"
            ),
            PatternDef(
                id="cert.vendor_code.v1",
                section="certs", 
                weight=0.9,
                max_share=0.60,
                min_evidence=1,  # Vendor + code/ID
                notes="Professional certifications with vendor codes"
            )
        ]
        
        # LANG Patterns
        lang_patterns = [
            PatternDef(
                id="lang.list_inline.v1",
                section="lang",
                weight=1.0,
                max_share=0.80,
                min_evidence=1,  # Language name
                notes="Comma/bullet-separated language lists"
            ),
            PatternDef(
                id="lang.table_level.v1",
                section="lang",
                weight=1.1,
                max_share=0.70, 
                min_evidence=2,  # Language + level
                notes="Structured table format with proficiency levels"
            ),
            PatternDef(
                id="lang.nationality_guard.v1",
                section="lang",
                weight=0.0,  # Negative filter
                max_share=0.1,  # Phase 5: Fix invalid max_share (was 0.0)
                enabled=True,
                notes="Guard pattern: exclude nationality/citizenship contexts"
            )
        ]
        
        # SOFT SKILLS Patterns  
        soft_patterns = [
            PatternDef(
                id="soft.header_list_delims.v1",
                section="soft",
                weight=1.1,
                max_share=0.80,
                min_evidence=1,  # In soft skills section
                notes="Multi-delimiter parsing within soft skills sections"
            ),
            PatternDef(
                id="soft.bullets_canon.v1",
                section="soft", 
                weight=1.0,
                max_share=0.60,
                min_evidence=1,  # Bullet format
                notes="Bullet point format with canonical taxonomy mapping"
            )
        ]
        
        # PROJECTS Patterns
        proj_patterns = [
            PatternDef(
                id="proj.header_bullets.v1",
                section="proj",
                weight=1.0,
                max_share=0.80,
                min_evidence=1,  # Project header
                notes="Header followed by bullet-structured project entries"  
            ),
            PatternDef(
                id="proj.dates_tech_desc.v1",
                section="proj",
                weight=1.1, 
                max_share=0.70,
                min_evidence=2,  # Dates + (tech OR desc)
                notes="Rich metadata extraction with dates and technology stack"
            )
        ]
        
        # Register all patterns
        all_patterns = exp_patterns + edu_patterns + cert_patterns + lang_patterns + soft_patterns + proj_patterns
        
        for pattern in all_patterns:
            self.register_pattern(pattern)
    
    def register_pattern(self, pattern: PatternDef):
        """Register a new extraction pattern."""
        if pattern.id in self.patterns:
            self.logger.warning(f"PATTERN_REGISTRY: pattern '{pattern.id}' already exists, overwriting")
        
        self.patterns[pattern.id] = pattern
        self.usage_tracking[pattern.id] = PatternUsage(pattern_id=pattern.id)
        
        self.logger.debug(f"PATTERN_REGISTRY: registered | id={pattern.id} section={pattern.section} "
                         f"weight={pattern.weight} max_share={pattern.max_share}")
    
    def get_patterns_for_section(self, section: str, enabled_only: bool = True) -> List[PatternDef]:
        """Get all patterns for a specific section."""
        section_patterns = []
        
        for pattern in self.patterns.values():
            if pattern.section == section:
                if not enabled_only or pattern.enabled:
                    section_patterns.append(pattern)
        
        # Sort by weight (descending) for priority
        return sorted(section_patterns, key=lambda p: p.weight, reverse=True)
    
    def get_pattern(self, pattern_id: str) -> Optional[PatternDef]:
        """Get specific pattern by ID."""
        return self.patterns.get(pattern_id)
    
    def get_sections(self) -> Set[str]:
        """Get all registered sections."""
        return {p.section for p in self.patterns.values()}
    
    def update_pattern_weight(self, pattern_id: str, new_weight: float, reason: str = ""):
        """Update pattern weight for overfitting control."""
        if pattern_id not in self.patterns:
            self.logger.warning(f"PATTERN_REGISTRY: cannot update unknown pattern '{pattern_id}'")
            return False
        
        old_weight = self.patterns[pattern_id].weight
        self.patterns[pattern_id].weight = max(0.0, min(5.0, new_weight))  # Clamp to valid range
        
        self.logger.info(f"PATTERN_REGISTRY: weight updated | pattern={pattern_id} "
                        f"weight={old_weight:.2f}→{new_weight:.2f} reason='{reason}'")
        return True
    
    def update_pattern_max_share(self, pattern_id: str, new_max_share: float, reason: str = ""):
        """Update pattern max_share for overfitting control."""
        if pattern_id not in self.patterns:
            self.logger.warning(f"PATTERN_REGISTRY: cannot update unknown pattern '{pattern_id}'")
            return False
        
        old_max_share = self.patterns[pattern_id].max_share
        self.patterns[pattern_id].max_share = max(0.1, min(1.0, new_max_share))  # Clamp to valid range
        
        self.logger.info(f"PATTERN_REGISTRY: max_share updated | pattern={pattern_id} "
                        f"max_share={old_max_share:.2f}→{new_max_share:.2f} reason='{reason}'")
        return True
    
    def record_pattern_usage(self, pattern_id: str, items_extracted: int, 
                           total_candidates: int, confidence_scores: List[float]):
        """Record pattern usage for monitoring."""
        if pattern_id not in self.usage_tracking:
            self.usage_tracking[pattern_id] = PatternUsage(pattern_id=pattern_id)
        
        usage = self.usage_tracking[pattern_id]
        usage.items_extracted = items_extracted
        usage.total_candidates = total_candidates
        usage.confidence_scores = confidence_scores.copy()
        
        self.logger.debug(f"PATTERN_REGISTRY: usage recorded | pattern={pattern_id} "
                         f"extracted={items_extracted}/{total_candidates} "
                         f"rate={usage.usage_rate:.2f} avg_conf={usage.avg_confidence:.2f}")
    
    def get_usage_stats(self, section: str = None) -> Dict[str, Any]:
        """Get usage statistics for patterns."""
        stats = {
            "total_patterns": len(self.patterns),
            "enabled_patterns": sum(1 for p in self.patterns.values() if p.enabled),
            "sections": list(self.get_sections()),
            "usage_by_pattern": {},
            "usage_by_section": {}
        }
        
        # Per-pattern stats
        for pattern_id, usage in self.usage_tracking.items():
            if usage.total_candidates > 0:
                stats["usage_by_pattern"][pattern_id] = {
                    "items_extracted": usage.items_extracted,
                    "total_candidates": usage.total_candidates,
                    "usage_rate": usage.usage_rate,
                    "avg_confidence": usage.avg_confidence
                }
        
        # Per-section aggregated stats
        for section_name in self.get_sections():
            if section and section != section_name:
                continue
                
            section_patterns = self.get_patterns_for_section(section_name)
            section_usage = {
                "pattern_count": len(section_patterns),
                "total_extracted": 0,
                "total_candidates": 0,
                "patterns": []
            }
            
            for pattern in section_patterns:
                usage = self.usage_tracking.get(pattern.id)
                if usage and usage.total_candidates > 0:
                    section_usage["total_extracted"] += usage.items_extracted
                    section_usage["total_candidates"] += usage.total_candidates
                    section_usage["patterns"].append({
                        "pattern_id": pattern.id,
                        "usage_rate": usage.usage_rate,
                        "items_extracted": usage.items_extracted
                    })
            
            stats["usage_by_section"][section_name] = section_usage
        
        return stats
    
    def reset_usage_tracking(self):
        """Reset all usage tracking data."""
        for pattern_id in self.usage_tracking:
            self.usage_tracking[pattern_id] = PatternUsage(pattern_id=pattern_id)
        
        self.logger.info("PATTERN_REGISTRY: usage tracking reset")
    
    def export_patterns(self, filepath: str):
        """Export pattern definitions to JSON file."""
        try:
            export_data = {
                "metadata": {
                    "export_timestamp": str(datetime.now()),
                    "total_patterns": len(self.patterns),
                    "sections": list(self.get_sections())
                },
                "patterns": {pid: asdict(pattern) for pid, pattern in self.patterns.items()}
            }
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f"PATTERN_REGISTRY: patterns exported | filepath={filepath} "
                           f"patterns={len(self.patterns)}")
            
        except Exception as e:
            self.logger.error(f"PATTERN_REGISTRY: export failed | filepath={filepath} | error={e}")
    
    def _load_config(self, config_path: str):
        """Load patterns from configuration file."""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            patterns_data = config_data.get("patterns", {})
            
            for pattern_id, pattern_config in patterns_data.items():
                if pattern_id in self.patterns:
                    # Update existing pattern with config overrides
                    pattern = self.patterns[pattern_id]
                    if "weight" in pattern_config:
                        pattern.weight = pattern_config["weight"]
                    if "max_share" in pattern_config:
                        pattern.max_share = pattern_config["max_share"] 
                    if "enabled" in pattern_config:
                        pattern.enabled = pattern_config["enabled"]
                        
                    self.logger.debug(f"PATTERN_REGISTRY: pattern updated from config | "
                                    f"id={pattern_id} weight={pattern.weight} max_share={pattern.max_share}")
            
            self.logger.info(f"PATTERN_REGISTRY: config loaded | file={config_path} "
                           f"patterns_updated={len(patterns_data)}")
                           
        except Exception as e:
            self.logger.error(f"PATTERN_REGISTRY: config load failed | file={config_path} | error={e}")


# Global registry instance
_global_registry: Optional[PatternRegistry] = None


def get_pattern_registry(config_path: Optional[str] = None) -> PatternRegistry:
    """Get the global pattern registry instance."""
    global _global_registry
    
    if _global_registry is None:
        _global_registry = PatternRegistry(config_path)
    
    return _global_registry


def reset_pattern_registry():
    """Reset the global pattern registry (primarily for testing)."""
    global _global_registry
    _global_registry = None


# Utility functions for backward compatibility
def get_patterns_for_section(section: str, enabled_only: bool = True) -> List[PatternDef]:
    """Get patterns for section using global registry."""
    registry = get_pattern_registry()
    return registry.get_patterns_for_section(section, enabled_only)


def record_pattern_usage(pattern_id: str, items_extracted: int, 
                        total_candidates: int, confidence_scores: List[float]):
    """Record pattern usage using global registry."""
    registry = get_pattern_registry()
    registry.record_pattern_usage(pattern_id, items_extracted, total_candidates, confidence_scores)