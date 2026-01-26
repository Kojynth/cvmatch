"""
Enhanced CV Extractor that integrates the new robust extraction pipeline
with the existing CVExtractor interface for backward compatibility.
"""

import time
from pathlib import Path
from typing import Optional, Dict, Any, List
import sys

# Add the app modules to path if needed
if 'app' not in sys.modules:
    sys.path.insert(0, str(Path(__file__).parent.parent))

from ..logging.safe_logger import get_safe_logger, DEFAULT_PII_CONFIG
from .enhanced_extraction_pipeline import EnhancedExtractionPipeline
from .cli_config import ExtractionFlags
from .unified_reporter import unified_reporter

# Try to import existing types, fallback to basic types if not available
try:
    from ...cvextractor.core.types import ExtractionResult, ExtractionMetrics
    from ...cvextractor.core.config import ExtractionConfig
except ImportError:
    # Define basic types if cvextractor module not available
    class ExtractionResult:
        def __init__(self):
            self.source_file = ""
            self.detected_language = "unknown"
            self.experiences = []
            self.education = []
            self.skills = []
            self.languages = []
            self.certifications = []
            self.projects = []
            self.personal_info = {}
            self.contact_info = {}
            self.other_sections = []
            self.metrics = None
    
    class ExtractionMetrics:
        def __init__(self, **kwargs):
            self.total_pages = kwargs.get('total_pages', 0)
            self.processing_time = kwargs.get('processing_time', 0.0)
            self.sections_detected = kwargs.get('sections_detected', 0)
            self.fields_extracted = kwargs.get('fields_extracted', 0)
            self.fields_with_high_confidence = kwargs.get('fields_with_high_confidence', 0)
            self.completion_rate = kwargs.get('completion_rate', 0.0)
            self.warnings = kwargs.get('warnings', [])
    
    class ExtractionConfig:
        def __init__(self):
            self.email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
            self.phone_patterns = [r'\b\d{2}[\s\-]?\d{2}[\s\-]?\d{2}[\s\-]?\d{2}[\s\-]?\d{2}\b']

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


class EnhancedCVExtractor:
    """Enhanced CV Extractor with robust gates and anti-overfitting measures."""
    
    def __init__(self, config: Optional[ExtractionConfig] = None, 
                 extraction_flags: Optional[ExtractionFlags] = None):
        """
        Initialize enhanced CV extractor.
        
        Args:
            config: Legacy extraction configuration for compatibility
            extraction_flags: Enhanced extraction flags for modular pipeline
        """
        self.config = config or ExtractionConfig()
        self.extraction_flags = extraction_flags or ExtractionFlags()
        
        # Initialize enhanced pipeline
        self.enhanced_pipeline = EnhancedExtractionPipeline(self.extraction_flags)
        
        logger.info("ENHANCED_CV_EXTRACTOR: initialized | "
                   f"pattern_diversity_enforce={self.extraction_flags.pattern_diversity_enforce} "
                   f"offline={self.extraction_flags.offline}")
        
    def extract(self, cv_path: str) -> ExtractionResult:
        """
        Extract CV information using enhanced pipeline with backward compatibility.
        
        Args:
            cv_path: Path to CV file
            
        Returns:
            ExtractionResult: Compatible with legacy interface but enhanced internally
        """
        start_time = time.time()
        cv_path = Path(cv_path)
        
        logger.info(f"ENHANCED_CV_EXTRACTOR: starting_extraction | file={cv_path.name}")
        
        try:
            # Use enhanced pipeline for extraction
            enhanced_result = self.enhanced_pipeline.extract_cv_enhanced(str(cv_path))
            
            if not enhanced_result.get('success', True):
                # Handle extraction failure
                error_msg = enhanced_result.get('error', 'Unknown extraction error')
                logger.error(f"ENHANCED_CV_EXTRACTOR: extraction_failed | error={error_msg}")
                
                return self._create_error_result(str(cv_path), error_msg, time.time() - start_time)
            
            # Convert enhanced results to legacy format
            legacy_result = self._convert_to_legacy_format(enhanced_result, str(cv_path))
            
            processing_time = time.time() - start_time
            logger.info(f"ENHANCED_CV_EXTRACTOR: extraction_completed | "
                       f"processing_time={processing_time:.2f}s "
                       f"experiences={len(legacy_result.experiences)} "
                       f"education={len(legacy_result.education)} "
                       f"pattern_diversity={enhanced_result.get('pattern_diversity', 0.0):.3f}")
            
            return legacy_result
            
        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(f"ENHANCED_CV_EXTRACTOR: unexpected_error | error={str(e)}")
            
            return self._create_error_result(str(cv_path), str(e), processing_time)
    
    def extract_enhanced(self, cv_path: str) -> Dict[str, Any]:
        """
        Extract CV using enhanced pipeline and return full enhanced results.
        
        Args:
            cv_path: Path to CV file
            
        Returns:
            Dict with complete enhanced extraction results and metrics
        """
        return self.enhanced_pipeline.extract_cv_enhanced(cv_path)
    
    def _convert_to_legacy_format(self, enhanced_result: Dict[str, Any], 
                                 source_file: str) -> ExtractionResult:
        """Convert enhanced pipeline results to legacy ExtractionResult format."""
        
        result = ExtractionResult()
        result.source_file = source_file
        result.detected_language = "fr"  # Default, could be enhanced
        
        # Convert experiences
        result.experiences = self._convert_experiences_to_legacy(
            enhanced_result.get('experiences', [])
        )
        
        # Convert education
        result.education = self._convert_education_to_legacy(
            enhanced_result.get('education', [])
        )
        
        # Convert skills
        result.skills = self._convert_skills_to_legacy(
            enhanced_result.get('skills', [])
        )
        
        # Convert languages
        result.languages = self._convert_languages_to_legacy(
            enhanced_result.get('languages', [])
        )
        
        # Convert certifications
        result.certifications = self._convert_certifications_to_legacy(
            enhanced_result.get('certifications', [])
        )
        
        # Convert projects
        result.projects = self._convert_projects_to_legacy(
            enhanced_result.get('projects', [])
        )
        
        # Create enhanced metrics
        result.metrics = self._create_enhanced_metrics(enhanced_result)
        
        return result
    
    def _convert_experiences_to_legacy(self, experiences: List[Dict[str, Any]]) -> List[Any]:
        """Convert enhanced experience format to legacy format."""
        legacy_experiences = []
        
        for exp in experiences:
            # Create legacy experience object
            legacy_exp = {
                'title': exp.get('title', ''),
                'company': exp.get('company', ''),
                'start_date': exp.get('start_date', ''),
                'end_date': exp.get('end_date', ''),
                'description': exp.get('description', ''),
                'location': exp.get('location', ''),
                'confidence': exp.get('confidence', 0.5),
                'extraction_method': exp.get('extraction_method', 'enhanced'),
                
                # Enhanced fields
                'tri_signal_validation': exp.get('tri_signal_validation', {}),
                'org_rebind': exp.get('org_rebind', {}),
                'quality_assessment': exp.get('quality_assessment', {})
            }
            
            legacy_experiences.append(legacy_exp)
        
        return legacy_experiences
    
    def _convert_education_to_legacy(self, education_items: List[Dict[str, Any]]) -> List[Any]:
        """Convert enhanced education format to legacy format."""
        legacy_education = []
        
        for edu in education_items:
            legacy_edu = {
                'degree': edu.get('degree', ''),
                'institution': edu.get('institution', ''),
                'start_date': edu.get('start_date', ''),
                'end_date': edu.get('end_date', ''),
                'location': edu.get('location', ''),
                'confidence': edu.get('confidence', 0.5),
                
                # Enhanced fields
                'extraction_pass': edu.get('extraction_pass', 1),
                'dedup_key': edu.get('dedup_key', ''),
                'org_confidence': edu.get('org_confidence', 0.0)
            }
            
            legacy_education.append(legacy_edu)
        
        return legacy_education
    
    def _convert_skills_to_legacy(self, skills: List[Dict[str, Any]]) -> List[Any]:
        """Convert skills to legacy format."""
        return [
            {
                'name': skill.get('name', ''),
                'confidence': skill.get('confidence', 0.5),
                'category': skill.get('category', 'technical')
            }
            for skill in skills
        ]
    
    def _convert_languages_to_legacy(self, languages: List[Dict[str, Any]]) -> List[Any]:
        """Convert languages to legacy format."""
        return [
            {
                'language': lang.get('language', ''),
                'level': lang.get('level', ''),
                'confidence': lang.get('confidence', 0.5),
                'source': lang.get('source', 'extracted')
            }
            for lang in languages
        ]
    
    def _convert_certifications_to_legacy(self, certifications: List[Dict[str, Any]]) -> List[Any]:
        """Convert certifications to legacy format."""
        return [
            {
                'name': cert.get('name', ''),
                'issuer': cert.get('issuer', ''),
                'date': cert.get('date', ''),
                'level': cert.get('level', ''),
                'score': cert.get('score', ''),
                'confidence': 0.8,  # Certifications have high confidence due to canonical matching
                'stage': cert.get('stage', 'final')
            }
            for cert in certifications
        ]
    
    def _convert_projects_to_legacy(self, projects: List[Dict[str, Any]]) -> List[Any]:
        """Convert projects to legacy format."""
        return [
            {
                'name': project.get('name', ''),
                'description': project.get('description', ''),
                'technologies': project.get('technologies', []),
                'date': project.get('date', ''),
                'confidence': project.get('confidence', 0.5)
            }
            for project in projects
        ]
    
    def _create_enhanced_metrics(self, enhanced_result: Dict[str, Any]) -> ExtractionMetrics:
        """Create enhanced metrics from pipeline results."""
        
        final_metrics = enhanced_result.get('final_metrics')
        extraction_quality = enhanced_result.get('extraction_quality', {})
        gate_stats = enhanced_result.get('gate_statistics', {})
        
        # Count extracted fields
        fields_extracted = (
            len(enhanced_result.get('experiences', [])) +
            len(enhanced_result.get('education', [])) +
            len(enhanced_result.get('skills', [])) +
            len(enhanced_result.get('languages', [])) +
            len(enhanced_result.get('certifications', []))
        )
        
        # Count high confidence fields (confidence >= 0.8)
        high_conf_count = 0
        for section_items in [
            enhanced_result.get('experiences', []),
            enhanced_result.get('education', []),
            enhanced_result.get('certifications', [])  # Certs typically high confidence
        ]:
            high_conf_count += sum(1 for item in section_items 
                                 if item.get('confidence', 0.0) >= 0.8)
        
        # Calculate completion rate based on expected sections
        expected_sections = 5  # experiences, education, skills, languages, certifications
        actual_sections = sum(1 for section in [
            enhanced_result.get('experiences'),
            enhanced_result.get('education'), 
            enhanced_result.get('skills'),
            enhanced_result.get('languages'),
            enhanced_result.get('certifications')
        ] if section and len(section) > 0)
        
        completion_rate = actual_sections / expected_sections
        
        # Create warnings based on quality issues
        warnings = []
        
        if enhanced_result.get('pattern_diversity', 0.0) < 0.30:
            warnings.append(f"Low pattern diversity: {enhanced_result.get('pattern_diversity', 0.0):.3f}")
        
        if gate_stats.get('experiences_demoted', 0) > 0:
            warnings.append(f"Experiences demoted: {gate_stats.get('experiences_demoted', 0)}")
        
        if gate_stats.get('header_conflicts', 0) > 0:
            warnings.append(f"Header conflicts detected: {gate_stats.get('header_conflicts', 0)}")
        
        validation_result = enhanced_result.get('validation', {})
        if not validation_result.get('validation_passed', True):
            warnings.append("Pattern diversity enforcement triggered")
        
        return ExtractionMetrics(
            total_pages=1,  # Simplified
            processing_time=enhanced_result.get('processing_time', 0.0),
            sections_detected=final_metrics.sections_detected if final_metrics else len(enhanced_result.get('experiences', [])),
            fields_extracted=fields_extracted,
            fields_with_high_confidence=high_conf_count,
            completion_rate=completion_rate,
            warnings=warnings
        )
    
    def _create_error_result(self, source_file: str, error_message: str, 
                           processing_time: float) -> ExtractionResult:
        """Create an error result for failed extractions."""
        
        result = ExtractionResult()
        result.source_file = source_file
        result.detected_language = "unknown"
        result.experiences = []
        result.education = []
        result.skills = []
        result.languages = []
        result.certifications = []
        result.projects = []
        
        result.metrics = ExtractionMetrics(
            total_pages=0,
            processing_time=processing_time,
            sections_detected=0,
            fields_extracted=0,
            fields_with_high_confidence=0,
            completion_rate=0.0,
            warnings=[f"Extraction failed: {error_message}"]
        )
        
        return result
    
    def get_pipeline_stats(self) -> Dict[str, Any]:
        """Get comprehensive pipeline statistics."""
        return self.enhanced_pipeline.get_pipeline_stats()
    
    def export_pipeline_report(self, output_path: str):
        """Export comprehensive pipeline report."""
        return self.enhanced_pipeline.export_pipeline_report(output_path)


# Factory functions for backward compatibility
def create_enhanced_extractor(pattern_diversity_enforce: bool = False,
                            offline: bool = True,
                            tri_signal_window: int = 3,
                            exp_gate_min: float = 0.55) -> EnhancedCVExtractor:
    """
    Create enhanced CV extractor with specific configuration.
    
    Args:
        pattern_diversity_enforce: Enable pattern diversity enforcement
        offline: Run in offline mode
        tri_signal_window: Tri-signal validation window
        exp_gate_min: Experience acceptance gate minimum
        
    Returns:
        Configured EnhancedCVExtractor instance
    """
    flags = ExtractionFlags(
        pattern_diversity_enforce=pattern_diversity_enforce,
        offline=offline,
        tri_signal_window=tri_signal_window,
        exp_gate_min=exp_gate_min
    )
    
    return EnhancedCVExtractor(extraction_flags=flags)


def create_legacy_compatible_extractor() -> EnhancedCVExtractor:
    """
    Create extractor with conservative settings for legacy compatibility.
    
    Returns:
        EnhancedCVExtractor with conservative configuration
    """
    flags = ExtractionFlags(
        pattern_diversity_enforce=False,  # Disabled for compatibility
        offline=True,
        tri_signal_window=5,  # Larger window for more lenient matching
        exp_gate_min=0.45,    # Lower threshold
        min_desc_tokens=3     # Lower requirement
    )
    
    return EnhancedCVExtractor(extraction_flags=flags)
