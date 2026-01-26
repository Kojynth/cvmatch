"""
Main integration module for enhanced CV extraction pipeline.
Ties together all components: boundary guards, tri-signal validation, org rebinding,
certification routing, education extraction, pattern diversity monitoring, and unified reporting.
"""

import time
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path

from ..config import EXPERIENCE_CONF
from ..logging.safe_logger import get_safe_logger, DEFAULT_PII_CONFIG
from .boundary_guards import boundary_guards, tri_signal_validator
from .org_sieve import org_sieve
from .certification_router import CertificationRouter
from .education_extractor_enhanced import education_extractor
from .experience_extractor_enhanced import enhanced_experience_extractor
from .overfitting_monitor import overfitting_monitor
from .unified_reporter import unified_reporter
from .cli_config import CLIConfigManager, ExtractionFlags
from .extraction_logger import get_extraction_logger

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


class EnhancedExtractionPipeline:
    """Main pipeline orchestrating enhanced CV extraction with all gates and validation."""
    
    def __init__(self, flags: Optional[ExtractionFlags] = None):
        self.flags = flags or ExtractionFlags()
        self.cli_manager = CLIConfigManager()
        
        # Apply configuration from flags
        self.config = self.cli_manager.apply_flags_to_config(self.flags)
        
        # Initialize components with config
        self.cert_router = CertificationRouter()
        self.extraction_logger = get_extraction_logger()
        
        # Statistics and metrics
        self.pipeline_stats = {
            'total_documents_processed': 0,
            'successful_extractions': 0,
            'failed_extractions': 0,
            'average_processing_time': 0.0,
            'total_processing_time': 0.0
        }
        
    def extract_cv_enhanced(self, cv_path: str, 
                           text_lines: Optional[List[str]] = None,
                           entities: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        Main enhanced extraction method with full pipeline.
        
        Args:
            cv_path: Path to CV file
            text_lines: Pre-extracted text lines (optional)
            entities: Pre-extracted NER entities (optional)
            
        Returns:
            Complete extraction results with all metrics
        """
        start_time = time.time()
        doc_id = Path(cv_path).stem
        
        try:
            # Start extraction session logging
            extraction_log_path = self.extraction_logger.start_extraction_session(doc_id, cv_path)
            extraction_id = unified_reporter.start_extraction_session(doc_id)
            
            # Configure redirection des logs détaillés de tous les modules
            enhanced_loggers = [
                "app.utils.enhanced_extraction_pipeline",
                "app.utils.experience_extractor_enhanced",
                "app.utils.education_extractor_enhanced", 
                "app.utils.certification_router",
                "app.utils.boundary_guards",
                "app.utils.org_sieve",
                "app.utils.overfitting_monitor",
                "app.utils.unified_reporter"
            ]
            self.extraction_logger.setup_multiple_loggers_redirection(enhanced_loggers)
            
            logger.info(f"ENHANCED_PIPELINE: starting_extraction | doc_id={doc_id} "
                       f"offline={self.flags.offline} pattern_diversity_enforce={self.flags.pattern_diversity_enforce}")
            
            # Step 1: Document loading and preprocessing (if not provided)
            if text_lines is None:
                text_lines, entities = self._load_and_preprocess_document(cv_path)
                
            self.extraction_logger.log_document_analysis(
                doc_type=Path(cv_path).suffix[1:].upper(),
                pages=1,  # Simplified
                text_length=sum(len(line) for line in text_lines)
            )
            
            # Step 2: Section segmentation with boundary quality assessment
            sections_result = self._segment_sections_with_boundaries(text_lines)
            
            unified_reporter.update_section_metrics(
                sections_result['sections_detected'],
                sections_result['sections_mapped'], 
                sections_result['boundary_quality_score']
            )
            
            # Step 3: Pre-merge certification detection (run early as required)
            self.extraction_logger.log_progress(20, "Pre-merge certification detection")
            cert_result = self.cert_router.run_pre_merge_detection(text_lines, entities)
            
            unified_reporter.update_certification_metrics(cert_result)
            
            self.extraction_logger.log_info(f"Pre-merge certifications detected: {cert_result['pre_merge_count']}")
            
            # Step 4: Enhanced experience extraction with all gates
            self.extraction_logger.log_progress(40, "Enhanced experience extraction")
            exp_result = self._extract_experiences_with_full_gates(
                text_lines, sections_result, entities, cert_result['stop_tags']
            )
            
            # Step 5: Enhanced education extraction with two-pass system
            self.extraction_logger.log_progress(60, "Enhanced education extraction")
            edu_result = self._extract_education_with_deduplication(
                text_lines, sections_result, cert_result['detected_certifications']
            )
            
            # Step 6: Extract other sections (skills, languages, projects)
            self.extraction_logger.log_progress(80, "Other sections extraction")
            other_sections = self._extract_other_sections(text_lines, sections_result)
            
            # Step 7: Final quality assessment and pattern diversity validation
            self.extraction_logger.log_progress(90, "Quality assessment and validation")
            final_validation = self._perform_final_validation(exp_result, edu_result, other_sections)
            
            # Step 8: Compile final results
            extraction_results = self._compile_final_results(
                exp_result, edu_result, other_sections, cert_result, final_validation
            )
            
            # Step 9: Update unified reporting
            self._update_unified_reporting(exp_result, edu_result, final_validation)
            
            # Finalize metrics
            final_metrics = unified_reporter.finalize_extraction_session()
            processing_time = time.time() - start_time
            
            # Update pipeline statistics
            self._update_pipeline_stats(processing_time, success=True)
            
            # Log completion
            self.extraction_logger.end_extraction_session(True, processing_time)
            
            logger.info(f"ENHANCED_PIPELINE: extraction_completed | doc_id={doc_id} "
                       f"processing_time={processing_time:.2f}s "
                       f"experiences={len(extraction_results['experiences'])} "
                       f"pattern_diversity={final_validation['pattern_diversity']:.3f}")
            
            # Add final metrics to results
            extraction_results['final_metrics'] = final_metrics
            extraction_results['extraction_log_path'] = extraction_log_path
            extraction_results['processing_time'] = processing_time
            
            return extraction_results
            
        except Exception as e:
            processing_time = time.time() - start_time
            self._update_pipeline_stats(processing_time, success=False)
            
            logger.error(f"ENHANCED_PIPELINE: extraction_failed | doc_id={doc_id} error={str(e)}")
            self.extraction_logger.end_extraction_session(False, processing_time)
            
            return {
                'success': False,
                'error': str(e),
                'processing_time': processing_time,
                'doc_id': doc_id
            }
            
    def _load_and_preprocess_document(self, cv_path: str) -> Tuple[List[str], List[Dict[str, Any]]]:
        """Load and preprocess document (simplified version)."""
        # This would integrate with existing document loaders
        # For now, return mock data structure
        
        try:
            with open(cv_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # Simple line splitting
            text_lines = [line.strip() for line in content.split('\n')]
            
            # Mock entities (in real implementation, would use NER)
            entities = []
            
            logger.debug(f"DOCUMENT_LOADING: loaded | lines={len(text_lines)}")
            
            return text_lines, entities
            
        except Exception as e:
            logger.error(f"DOCUMENT_LOADING: failed | path={cv_path} error={e}")
            raise
            
    def _segment_sections_with_boundaries(self, text_lines: List[str]) -> Dict[str, Any]:
        """Segment text into sections with boundary quality assessment."""
        
        # Mock section detection (would integrate with existing segmenter)
        sections = {
            'personal_info': (0, 5),
            'experience': (6, 20),
            'education': (21, 30),
            'skills': (31, 35),
            'languages': (36, 40)
        }
        
        # Calculate boundary quality score
        boundary_quality_score = 0.75  # Mock score
        
        # Check for header conflicts across sections
        header_conflicts = 0
        for section_name, (start, end) in sections.items():
            for i in range(start, min(end, len(text_lines))):
                has_conflict, _, _ = boundary_guards.check_header_conflict_killradius(text_lines, i)
                if has_conflict:
                    header_conflicts += 1
                    
        # Adjust boundary quality based on conflicts
        if header_conflicts > 0:
            boundary_quality_score *= (1.0 - min(header_conflicts * 0.1, 0.3))
            
        self.extraction_logger.log_info(f"Section segmentation: {len(sections)} sections detected, "
                                      f"boundary quality: {boundary_quality_score:.3f}")
        
        return {
            'sections': sections,
            'sections_detected': len(sections),
            'sections_mapped': len(sections),
            'boundary_quality_score': boundary_quality_score,
            'header_conflicts': header_conflicts
        }
        
    def _extract_experiences_with_full_gates(self, text_lines: List[str], 
                                           sections_result: Dict[str, Any],
                                           entities: List[Dict[str, Any]],
                                           cert_stop_tags: set) -> Dict[str, Any]:
        """Extract experiences with full enhanced pipeline."""
        
        experience_bounds = sections_result['sections'].get('experience')
        
        # Mock date hits for fallback
        date_hits = []
        for i, line in enumerate(text_lines):
            if any(year in line for year in ['2020', '2021', '2022', '2023', '2024']):
                date_hits.append({
                    'line_idx': i,
                    'date_text': line,
                    'confidence': 0.8
                })
        
        # Use enhanced experience extractor
        result = enhanced_experience_extractor.extract_experiences_with_gates(
            text_lines,
            section_bounds=experience_bounds,
            entities=entities,
            date_hits=date_hits
        )
        
        self.extraction_logger.log_section_result(
            'experiences',
            result['experiences'],
            confidence=result.get('pattern_diversity', 0.0)
        )
        
        return result
        
    def _extract_education_with_deduplication(self, text_lines: List[str],
                                            sections_result: Dict[str, Any],
                                            certifications: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Extract education with enhanced two-pass system."""
        
        education_bounds = sections_result['sections'].get('education')
        
        result = education_extractor.extract_education_two_pass(
            text_lines,
            section_bounds=education_bounds,
            entities=[]
        )
        
        # Filter out certification duplicates
        result['items'] = education_extractor.filter_credential_duplicates(
            result['items'], certifications
        )
        
        self.extraction_logger.log_section_result(
            'education',
            result['items'],
            confidence=result['metrics'].get('keep_rate_pass1', 0.0)
        )
        
        return result
        
    def _extract_other_sections(self, text_lines: List[str], 
                               sections_result: Dict[str, Any]) -> Dict[str, Any]:
        """Extract skills, languages, and projects."""
        
        # Mock extraction for other sections
        other_sections = {
            'skills': [],
            'languages': [],
            'projects': []
        }
        
        # Simple keyword-based extraction for skills
        skills_bounds = sections_result['sections'].get('skills', (0, len(text_lines)))
        skills_keywords = ['Python', 'JavaScript', 'React', 'Docker', 'AWS', 'SQL']
        
        for i in range(skills_bounds[0], min(skills_bounds[1], len(text_lines))):
            line = text_lines[i]
            for skill in skills_keywords:
                if skill.lower() in line.lower():
                    other_sections['skills'].append({
                        'name': skill,
                        'line_idx': i,
                        'confidence': 0.7
                    })
                    
        # Mock languages
        lang_bounds = sections_result['sections'].get('languages', (0, len(text_lines)))
        languages = ['Français', 'Anglais', 'Espagnol', 'Allemand']
        
        for i in range(lang_bounds[0], min(lang_bounds[1], len(text_lines))):
            line = text_lines[i]
            for lang in languages:
                if lang.lower() in line.lower():
                    other_sections['languages'].append({
                        'language': lang,
                        'level': 'B2',  # Mock level
                        'line_idx': i,
                        'confidence': 0.6
                    })
        
        self.extraction_logger.log_section_result('skills', other_sections['skills'])
        self.extraction_logger.log_section_result('languages', other_sections['languages'])
        self.extraction_logger.log_section_result('projects', other_sections['projects'])
        
        return other_sections
        
    def _perform_final_validation(self, exp_result: Dict[str, Any], 
                                 edu_result: Dict[str, Any],
                                 other_sections: Dict[str, Any]) -> Dict[str, Any]:
        """Perform final quality assessment and pattern diversity validation."""
        
        # Calculate final pattern diversity
        all_items = (
            exp_result.get('experiences', []) + 
            edu_result.get('items', []) +
            other_sections.get('skills', []) +
            other_sections.get('languages', [])
        )
        
        from .experience_filters import calculate_pattern_diversity
        extraction_data = {
            'experiences': exp_result.get('experiences', []),
            'education': edu_result.get('items', []),
            'skills': other_sections.get('skills', [])
        }
        
        pattern_diversity = calculate_pattern_diversity(extraction_data)
        
        # Apply overfitting monitoring
        overfitting_metrics = {
            'pattern_diversity': pattern_diversity,
            'total_items': len(all_items),
            'extraction_complexity': min(len(all_items) / 20.0, 1.0)
        }
        
        # Record overfitting metrics
        overfitting_monitor.record_extraction(
            extraction_data, 
            extraction_time_ms=1000,  # Mock time
            cv_metadata={'cv_id': 'current_extraction'}
        )
        
        # Pattern diversity enforcement (if enabled)
        enforcement_result = overfitting_monitor.enforce_pattern_diversity_gate(
            pattern_diversity, 
            date_hit_count=len(exp_result.get('experiences', []))
        )
        
        if enforcement_result['action'] == 'hard_block':
            unified_reporter.add_pattern_diversity_alert(enforcement_result['message'])
            
        validation_result = {
            'pattern_diversity': pattern_diversity,
            'overfitting_metrics': overfitting_metrics,
            'enforcement_result': enforcement_result,
            'total_items_extracted': len(all_items),
            'validation_passed': enforcement_result['action'] != 'hard_block'
        }
        
        self.extraction_logger.log_info(f"Final validation: pattern diversity {pattern_diversity:.3f}, "
                                      f"total items {len(all_items)}, "
                                      f"enforcement action: {enforcement_result['action']}")
        
        return validation_result
        
    def _compile_final_results(self, exp_result: Dict[str, Any],
                              edu_result: Dict[str, Any], 
                              other_sections: Dict[str, Any],
                              cert_result: Dict[str, Any],
                              validation: Dict[str, Any]) -> Dict[str, Any]:
        """Compile final extraction results in structured format."""
        
        final_results = {
            'success': True,
            'extraction_method': exp_result.get('method', 'enhanced_pipeline'),
            
            # Main sections
            'experiences': exp_result.get('experiences', []),
            'education': edu_result.get('items', []),
            'certifications': cert_result.get('detected_certifications', []),
            'skills': other_sections.get('skills', []),
            'languages': other_sections.get('languages', []),
            'projects': other_sections.get('projects', []),
            
            # Quality metrics
            'pattern_diversity': validation['pattern_diversity'],
            'extraction_quality': {
                'boundary_quality': 0.75,  # From sections_result
                'tri_signal_success_rate': exp_result.get('gate_stats', {}).get('tri_signal_success_rate', 0.0),
                'org_rebind_success_rate': exp_result.get('rebind_stats', {}).get('success_rate', 0.0),
                'education_keep_rate': edu_result.get('metrics', {}).get('keep_rate_pass1', 0.0)
            },
            
            # Gate statistics
            'gate_statistics': {
                'header_conflicts': exp_result.get('gate_stats', {}).get('header_conflicts', 0),
                'tri_signal_passes': exp_result.get('gate_stats', {}).get('tri_signal_passes', 0),
                'tri_signal_failures': exp_result.get('gate_stats', {}).get('tri_signal_failures', 0),
                'experiences_demoted': len(exp_result.get('demotions', [])),
                'certification_stop_tags': len(cert_result.get('stop_tags', set()))
            },
            
            # Validation results
            'validation': validation,
            
            # Configuration used
            'extraction_config': {
                'flags': self.flags.__dict__ if self.flags else {},
                'pattern_diversity_enforce': self.flags.pattern_diversity_enforce if self.flags else False,
                'tri_signal_window': self.config.get('tri_signal_window', 3),
                'header_conflict_killradius': self.config.get('header_conflict_killradius_lines', 8)
            }
        }
        
        return final_results
        
    def _update_unified_reporting(self, exp_result: Dict[str, Any],
                                 edu_result: Dict[str, Any], 
                                 validation: Dict[str, Any]):
        """Update unified reporting with all extraction metrics."""
        
        # Update experience metrics
        unified_reporter.update_experience_metrics(
            exp_result.get('gate_stats', {}),
            validation['pattern_diversity'],
            exp_result.get('demotions', [])
        )
        
        # Update education metrics
        unified_reporter.update_education_metrics(edu_result)
        
        # Add alerts if needed
        if validation['enforcement_result']['action'] != 'allow':
            unified_reporter.add_pattern_diversity_alert(
                validation['enforcement_result']['message']
            )
            
    def _update_pipeline_stats(self, processing_time: float, success: bool):
        """Update pipeline-level statistics."""
        self.pipeline_stats['total_documents_processed'] += 1
        self.pipeline_stats['total_processing_time'] += processing_time
        
        if success:
            self.pipeline_stats['successful_extractions'] += 1
        else:
            self.pipeline_stats['failed_extractions'] += 1
            
        # Update average processing time
        if self.pipeline_stats['total_documents_processed'] > 0:
            self.pipeline_stats['average_processing_time'] = (
                self.pipeline_stats['total_processing_time'] / 
                self.pipeline_stats['total_documents_processed']
            )
            
    def get_pipeline_stats(self) -> Dict[str, Any]:
        """Get comprehensive pipeline statistics."""
        stats = self.pipeline_stats.copy()
        
        # Add success rate
        if stats['total_documents_processed'] > 0:
            stats['success_rate'] = stats['successful_extractions'] / stats['total_documents_processed']
        else:
            stats['success_rate'] = 0.0
            
        # Add component statistics
        stats['component_stats'] = {
            'org_sieve': org_sieve.get_rebind_stats(),
            'enhanced_experience_extractor': enhanced_experience_extractor.get_extraction_stats(),
            'overfitting_monitor_health': overfitting_monitor.get_health_report()
        }
        
        return stats
        
    def export_pipeline_report(self, output_path: str):
        """Export comprehensive pipeline report."""
        report_data = {
            'pipeline_stats': self.get_pipeline_stats(),
            'configuration': {
                'flags': self.flags.__dict__ if self.flags else {},
                'config': self.config
            },
            'component_health': {
                'overfitting_monitor': overfitting_monitor.get_health_report()
            }
        }
        
        unified_reporter.export_detailed_report(output_path)
        logger.info(f"ENHANCED_PIPELINE: report_exported | path={output_path}")


# Global pipeline instance
enhanced_pipeline = EnhancedExtractionPipeline()


def create_pipeline_with_flags(flags: ExtractionFlags) -> EnhancedExtractionPipeline:
    """Create pipeline instance with specific flags."""
    return EnhancedExtractionPipeline(flags)
