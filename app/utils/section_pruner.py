"""
Section Pruner: Prevents empty or low-quality sections from being persisted.

This module implements intelligent section pruning to avoid saving sections
that are empty, contain only formatting artifacts, or have insufficient content.
"""

from typing import Dict, Any, List, Optional
from ..config import DEFAULT_PII_CONFIG
from ..logging.safe_logger import get_safe_logger

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


class SectionPruner:
    """Intelligent section pruning to prevent empty sections from being persisted."""
    
    def __init__(self):
        self.logger = get_safe_logger(f"{__name__}.SectionPruner", cfg=DEFAULT_PII_CONFIG)
        
        # Minimum content thresholds
        self.min_thresholds = {
            'experiences': 1,      # At least 1 experience
            'education': 1,        # At least 1 education entry
            'skills': 3,           # At least 3 skills  
            'languages': 1,        # At least 1 language
            'certifications': 1,   # At least 1 certification
            'interests': 2,        # At least 2 interests
            'volunteering': 1,     # At least 1 volunteering entry
            'awards': 1,           # At least 1 award
            'projects': 1,         # At least 1 project
            'publications': 1,     # At least 1 publication
        }
        
        # Quality score thresholds (0.0-1.0)
        self.quality_thresholds = {
            'experiences': 0.3,    # Low threshold - experiences are critical
            'education': 0.3,      # Low threshold - education is critical  
            'skills': 0.4,         # Medium threshold
            'languages': 0.5,      # Medium threshold
            'certifications': 0.6, # High threshold - prevent false positives
            'interests': 0.4,      # Medium threshold
            'volunteering': 0.5,   # Medium threshold
            'awards': 0.5,         # Medium threshold
            'projects': 0.4,       # Medium threshold
            'publications': 0.6,   # High threshold - prevent false positives
        }
    
    def should_persist_section(self, section_name: str, section_data: Any, 
                              metrics: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Determine if a section should be persisted based on content quality and quantity.
        
        Args:
            section_name: Name of the section (e.g., 'experiences', 'skills')
            section_data: The section data (list, dict, or other)
            metrics: Additional metrics from extraction process
            
        Returns:
            Dict with 'should_persist', 'reason', 'content_count', 'quality_score'
        """
        result = {
            'should_persist': False,
            'reason': 'unknown',
            'content_count': 0,
            'quality_score': 0.0,
            'section_name': section_name
        }
        
        # Handle None or empty data
        if section_data is None:
            result['reason'] = 'data_is_none'
            return result
        
        # Count actual content items
        content_count = self._count_content_items(section_data)
        result['content_count'] = content_count
        
        if content_count == 0:
            result['reason'] = 'no_content_items'
            return result
        
        # Check minimum threshold
        min_threshold = self.min_thresholds.get(section_name, 1)
        if content_count < min_threshold:
            result['reason'] = f'below_min_threshold_{min_threshold}'
            return result
        
        # Calculate quality score
        quality_score = self._calculate_quality_score(section_name, section_data, metrics)
        result['quality_score'] = quality_score
        
        # Check quality threshold
        quality_threshold = self.quality_thresholds.get(section_name, 0.5)
        if quality_score < quality_threshold:
            result['reason'] = f'below_quality_threshold_{quality_threshold:.1f}'
            return result
        
        # Section passes all checks
        result['should_persist'] = True
        result['reason'] = 'quality_checks_passed'
        
        self.logger.info(f"SECTION_PERSIST: {section_name} | count={content_count} "
                        f"quality={quality_score:.3f} threshold={quality_threshold}")
        
        return result
    
    def prune_extraction_result(self, extraction_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prune an entire extraction result, removing sections that shouldn't be persisted.
        
        Args:
            extraction_result: Complete extraction result dictionary
            
        Returns:
            Pruned extraction result with only valid sections
        """
        if not extraction_result:
            return {}
        
        pruned_result = {}
        pruning_stats = {
            'original_sections': 0,
            'kept_sections': 0,
            'pruned_sections': 0,
            'pruned_section_names': []
        }
        
        # Get metrics if available
        metrics = extraction_result.get('extraction_metrics', {})
        
        for section_name, section_data in extraction_result.items():
            pruning_stats['original_sections'] += 1
            
            # Skip metadata sections
            if section_name in ['extraction_metrics', 'processing_info', 'metadata']:
                pruned_result[section_name] = section_data
                pruning_stats['kept_sections'] += 1
                continue
            
            # Check if section should be persisted
            persistence_check = self.should_persist_section(
                section_name, section_data, metrics.get(section_name, {})
            )
            
            if persistence_check['should_persist']:
                pruned_result[section_name] = section_data
                pruning_stats['kept_sections'] += 1
            else:
                pruning_stats['pruned_sections'] += 1
                pruning_stats['pruned_section_names'].append(section_name)
                
                self.logger.info(f"SECTION_PRUNED: {section_name} | reason={persistence_check['reason']} "
                               f"count={persistence_check['content_count']} "
                               f"quality={persistence_check['quality_score']:.3f}")
        
        # Log pruning summary
        self.logger.info(f"PRUNING_SUMMARY: original={pruning_stats['original_sections']} "
                        f"kept={pruning_stats['kept_sections']} "
                        f"pruned={pruning_stats['pruned_sections']} "
                        f"pruned_sections={pruning_stats['pruned_section_names']}")
        
        # Add pruning stats to result
        if 'extraction_metrics' not in pruned_result:
            pruned_result['extraction_metrics'] = {}
        pruned_result['extraction_metrics']['pruning_stats'] = pruning_stats
        
        return pruned_result
    
    def _count_content_items(self, section_data: Any) -> int:
        """Count actual content items in section data."""
        if section_data is None:
            return 0
        
        if isinstance(section_data, list):
            # Filter out empty/invalid items
            valid_items = []
            for item in section_data:
                if item is None:
                    continue
                    
                if isinstance(item, dict):
                    # Check if dict has meaningful content
                    if self._has_meaningful_content(item):
                        valid_items.append(item)
                elif isinstance(item, str):
                    # Check if string has meaningful content
                    if item.strip() and len(item.strip()) > 2:
                        valid_items.append(item)
                else:
                    # Other types are considered valid if not None
                    valid_items.append(item)
            
            return len(valid_items)
        
        elif isinstance(section_data, dict):
            # For dict sections, check if it has meaningful content
            if self._has_meaningful_content(section_data):
                return 1
            return 0
        
        elif isinstance(section_data, str):
            # For string sections
            if section_data.strip() and len(section_data.strip()) > 2:
                return 1
            return 0
        
        else:
            # Other types are considered as 1 item if not None
            return 1 if section_data else 0
    
    def _has_meaningful_content(self, item: Dict[str, Any]) -> bool:
        """Check if a dictionary item has meaningful content."""
        if not item:
            return False
        
        # Check for meaningful text fields
        text_fields = ['name', 'title', 'company', 'description', 'school', 
                      'degree', 'skill', 'language', 'certification']
        
        for field in text_fields:
            value = item.get(field, '')
            if isinstance(value, str) and value.strip() and len(value.strip()) > 2:
                return True
        
        # Check for non-empty lists
        list_fields = ['responsibilities', 'achievements', 'skills', 'keywords']
        for field in list_fields:
            value = item.get(field, [])
            if isinstance(value, list) and len(value) > 0:
                return True
        
        return False
    
    def _calculate_quality_score(self, section_name: str, section_data: Any, 
                                metrics: Dict[str, Any] = None) -> float:
        """Calculate quality score for section data."""
        if not section_data:
            return 0.0
        
        base_score = 0.5  # Starting score
        
        # Use extraction metrics if available
        if metrics:
            # Check confidence scores
            confidence = metrics.get('avg_confidence', 0.0)
            base_score = max(base_score, confidence)
            
            # Check validation success rate
            validation_rate = metrics.get('validation_success_rate', 0.0)
            base_score = (base_score + validation_rate) / 2
            
            # Check pattern diversity
            pattern_diversity = metrics.get('pattern_diversity', 0.0)
            if pattern_diversity > 0:
                base_score += pattern_diversity * 0.1
        
        # Section-specific quality adjustments
        if isinstance(section_data, list):
            item_count = len(section_data)
            
            # Bonus for multiple items (shows consistency)
            if item_count > 1:
                base_score += min(item_count * 0.05, 0.2)
            
            # Check item quality for specific sections
            if section_name == 'experiences':
                base_score = self._assess_experiences_quality(section_data, base_score)
            elif section_name == 'skills':
                base_score = self._assess_skills_quality(section_data, base_score)
            elif section_name == 'certifications':
                base_score = self._assess_certifications_quality(section_data, base_score)
        
        return min(base_score, 1.0)
    
    def _assess_experiences_quality(self, experiences: List[Dict[str, Any]], base_score: float) -> float:
        """Assess quality of experiences section."""
        if not experiences:
            return 0.0
        
        quality_score = base_score
        
        for exp in experiences:
            if not isinstance(exp, dict):
                continue
                
            # Check for essential fields
            if exp.get('title') and exp.get('company'):
                quality_score += 0.1
            
            # Check for date information
            if exp.get('start_date') or exp.get('date'):
                quality_score += 0.05
            
            # Check for description/responsibilities
            if exp.get('description') or exp.get('responsibilities'):
                quality_score += 0.1
        
        return min(quality_score, 1.0)
    
    def _assess_skills_quality(self, skills: List[Any], base_score: float) -> float:
        """Assess quality of skills section."""
        if not skills:
            return 0.0
        
        # Skills are generally lower confidence, so we're more lenient
        return min(base_score + 0.1, 0.8)
    
    def _assess_certifications_quality(self, certifications: List[Dict[str, Any]], base_score: float) -> float:
        """Assess quality of certifications section."""
        if not certifications:
            return 0.0
        
        quality_score = base_score
        
        # Certifications need high confidence to avoid false positives
        canonical_count = 0
        for cert in certifications:
            if isinstance(cert, dict):
                # Check if it's a recognized/canonical certification
                confidence = cert.get('confidence', 0.0)
                if confidence > 0.8:
                    canonical_count += 1
        
        # Boost score for canonical certifications
        if canonical_count > 0:
            quality_score += canonical_count * 0.15
        
        return min(quality_score, 1.0)


def get_section_pruner() -> SectionPruner:
    """Get a singleton instance of SectionPruner."""
    if not hasattr(get_section_pruner, '_instance'):
        get_section_pruner._instance = SectionPruner()
    return get_section_pruner._instance