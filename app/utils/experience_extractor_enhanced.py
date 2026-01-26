"""
Enhanced experience extractor with tri-signal validation, pattern diversity enforcement,
and header conflict detection.
"""

import re
from typing import List, Dict, Any, Optional, Tuple, Set
from ..config import EXPERIENCE_CONF
from ..logging.safe_logger import get_safe_logger, DEFAULT_PII_CONFIG
from .boundary_guards import boundary_guards, tri_signal_validator
from .org_sieve import org_sieve
from .overfitting_monitor import overfitting_monitor
from .certification_router import CertificationRouter
from .experience_filters import calculate_pattern_diversity

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


class EnhancedExperienceExtractor:
    """Enhanced experience extractor with all new validation gates."""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or EXPERIENCE_CONF
        self.certification_router = CertificationRouter()
        
        # Statistics tracking
        self.stats = {
            'total_attempts': 0,
            'tri_signal_passes': 0,
            'tri_signal_failures': 0,
            'header_conflicts': 0,
            'pattern_diversity_blocks': 0,
            'org_rebind_attempts': 0,
            'org_rebind_successes': 0,
            'school_org_demotions': 0,
            'final_experiences': 0
        }
        
    def extract_experiences_with_gates(self, text_lines: List[str],
                                     section_bounds: Tuple[int, int] = None,
                                     entities: List[Dict[str, Any]] = None,
                                     date_hits: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Extract experiences with full gate system (section-first + fallback date-first).
        
        Args:
            text_lines: List of text lines
            section_bounds: Optional (start_line, end_line) bounds
            entities: Optional NER entities with line_idx
            date_hits: Optional detected date patterns
            
        Returns:
            Dict with extraction results, metrics, and applied gates info
        """
        logger.info("EXPERIENCE_ENHANCED: starting_extraction_with_gates")
        
        # Step 1: Run pre-merge certification detection
        cert_result = self.certification_router.run_pre_merge_detection(text_lines, entities)
        certification_stop_tags = cert_result['stop_tags']
        
        logger.info(f"CERT_PRE_MERGE: detected={cert_result['pre_merge_count']} "
                   f"stop_tags={len(certification_stop_tags)}")
        
        # Step 2: Try section-first extraction with gates
        section_result = self._extract_section_first_with_gates(
            text_lines, section_bounds, entities, certification_stop_tags
        )
        
        # Step 3: If section-first insufficient, try date-first fallback
        if len(section_result['experiences']) < 2:  # Threshold for fallback
            logger.info("EXPERIENCE_ENHANCED: triggering_date_first_fallback")
            
            fallback_result = self._extract_date_first_with_gates(
                text_lines, section_bounds, entities, date_hits, certification_stop_tags
            )
            
            # Combine results
            all_experiences = section_result['experiences'] + fallback_result['experiences']
            combined_method = 'section_first_with_date_first_fallback'
        else:
            all_experiences = section_result['experiences']
            combined_method = 'section_first_only'
            
        # Step 4: Apply organization rebinding
        rebind_result = self._apply_organization_rebinding(all_experiences, text_lines, entities)
        
        # Step 5: Apply quality assessment and demotions
        qa_result = self._apply_quality_assessment(rebind_result['experiences'], text_lines)
        
        # Step 6: Calculate final pattern diversity
        extraction_data = {'experiences': qa_result['final_experiences']}
        pattern_diversity = calculate_pattern_diversity(extraction_data)
        
        # Final statistics update
        self.stats['final_experiences'] = len(qa_result['final_experiences'])
        
        logger.info(f"EXPERIENCE_ENHANCED: extraction_complete | "
                   f"method='{combined_method}' final_count={len(qa_result['final_experiences'])} "
                   f"pattern_diversity={pattern_diversity:.3f}")
        
        return {
            'experiences': qa_result['final_experiences'],
            'method': combined_method,
            'pattern_diversity': pattern_diversity,
            'certifications_detected': cert_result['detected_certifications'],
            'rebind_stats': rebind_result['stats'],
            'demotions': qa_result['demotions'],
            'quality_issues': qa_result['quality_issues'],
            'gate_stats': self.stats.copy()
        }
        
    def _extract_section_first_with_gates(self, text_lines: List[str],
                                        section_bounds: Tuple[int, int] = None,
                                        entities: List[Dict[str, Any]] = None,
                                        stop_tags: Set[int] = None) -> Dict[str, Any]:
        """Extract experiences using section-first approach with all gates applied."""
        
        if section_bounds:
            start_line, end_line = section_bounds
            section_lines = text_lines[start_line:end_line]
            line_offset = start_line
        else:
            section_lines = text_lines
            line_offset = 0
            
        stop_tags = stop_tags or set()
        experiences = []
        
        # Group lines into experience blocks
        experience_blocks = self._group_lines_into_experience_blocks(section_lines, stop_tags)
        
        for block in experience_blocks:
            block_start_idx = block['start_idx'] + line_offset
            block_end_idx = block['end_idx'] + line_offset
            block_lines = block['lines']
            
            # Apply boundary guards
            should_terminate, termination_reasons = boundary_guards.should_terminate_window_expansion(
                text_lines, block_start_idx, block_end_idx, block_start_idx
            )
            
            if should_terminate:
                self.stats['header_conflicts'] += 1
                logger.debug(f"SECTION_FIRST: block_terminated | reasons={termination_reasons}")
                continue
                
            # Apply tri-signal validation
            tri_signal_result = tri_signal_validator.validate_tri_signal_linkage(
                text_lines, block_start_idx, entities
            )
            
            self.stats['total_attempts'] += 1
            
            if not tri_signal_result['passes']:
                self.stats['tri_signal_failures'] += 1
                logger.debug(f"SECTION_FIRST: tri_signal_failed | block_start={block_start_idx} "
                           f"signals={tri_signal_result['signal_counts']}")
                continue
                
            self.stats['tri_signal_passes'] += 1
            
            # Extract experience from valid block
            experience = self._extract_experience_from_block(
                block_lines, block_start_idx, text_lines, entities
            )
            
            if experience:
                experience['extraction_method'] = 'section_first_with_gates'
                experience['tri_signal_validation'] = tri_signal_result
                experiences.append(experience)
                
        return {'experiences': experiences}
        
    def _extract_date_first_with_gates(self, text_lines: List[str],
                                     section_bounds: Tuple[int, int] = None,
                                     entities: List[Dict[str, Any]] = None,
                                     date_hits: List[Dict[str, Any]] = None,
                                     stop_tags: Set[int] = None) -> Dict[str, Any]:
        """Extract experiences using date-first fallback with pattern diversity enforcement."""
        
        if not date_hits:
            return {'experiences': []}
            
        # Filter date hits to avoid stop tags
        filtered_date_hits = []
        stop_tags = stop_tags or set()
        
        for hit in date_hits:
            if hit.get('line_idx') not in stop_tags:
                filtered_date_hits.append(hit)
                
        date_hit_count = len(filtered_date_hits)
        logger.info(f"DATE_FIRST_FALLBACK: date_hits_available={date_hit_count}")
        
        if date_hit_count == 0:
            return {'experiences': []}
            
        # Calculate preliminary pattern diversity for enforcement
        provisional_experiences = self._create_provisional_experiences_from_dates(
            filtered_date_hits, text_lines, entities
        )
        
        extraction_data = {'experiences': provisional_experiences}
        pattern_diversity = calculate_pattern_diversity(extraction_data)
        
        # Apply pattern diversity enforcement
        enforcement_result = overfitting_monitor.enforce_pattern_diversity_gate(
            pattern_diversity, date_hit_count
        )
        
        if enforcement_result['action'] == 'hard_block':
            self.stats['pattern_diversity_blocks'] += 1
            logger.warning(f"DATE_FIRST_FALLBACK: hard_blocked | "
                         f"diversity={pattern_diversity:.3f} message='{enforcement_result['message']}'")
            
            # Only accept date-anchored tri-signal items
            return self._extract_date_anchored_tri_signal_only(
                filtered_date_hits, text_lines, entities
            )
            
        elif enforcement_result['action'] == 'cap_merges':
            max_merges = enforcement_result['max_merges_allowed']
            logger.info(f"DATE_FIRST_FALLBACK: capping_merges | max_allowed={max_merges}")
            
            # Cap the number of merges
            capped_experiences = provisional_experiences[:max_merges]
            return {'experiences': self._validate_experiences_with_gates(capped_experiences, text_lines, entities)}
        else:
            # Normal processing
            return {'experiences': self._validate_experiences_with_gates(provisional_experiences, text_lines, entities)}
            
    def _group_lines_into_experience_blocks(self, section_lines: List[str], 
                                          stop_tags: Set[int]) -> List[Dict[str, Any]]:
        """Group section lines into logical experience blocks."""
        blocks = []
        current_block = {'start_idx': 0, 'lines': [], 'end_idx': 0}
        
        for i, line in enumerate(section_lines):
            if i in stop_tags or not line.strip():
                # End current block if it has content
                if current_block['lines']:
                    current_block['end_idx'] = i
                    blocks.append(current_block)
                    current_block = {'start_idx': i + 1, 'lines': [], 'end_idx': i + 1}
            else:
                current_block['lines'].append(line)
                
        # Add final block
        if current_block['lines']:
            current_block['end_idx'] = len(section_lines)
            blocks.append(current_block)
            
        return blocks
        
    def _create_provisional_experiences_from_dates(self, date_hits: List[Dict[str, Any]],
                                                 text_lines: List[str], 
                                                 entities: List[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Create provisional experiences from date hits for pattern diversity calculation."""
        provisional = []
        
        for hit in date_hits:
            line_idx = hit.get('line_idx', 0)
            
            # Basic experience extraction
            experience = {
                'title': '',
                'company': '',
                'dates': hit.get('date_text', ''),
                'line_idx': line_idx,
                'extraction_method': 'date_first_fallback',
                'confidence': 0.5
            }
            
            # Try to extract title and company from nearby lines
            context_window = 3
            start_ctx = max(0, line_idx - context_window)
            end_ctx = min(len(text_lines), line_idx + context_window + 1)
            
            for i in range(start_ctx, end_ctx):
                if i < len(text_lines):
                    line = text_lines[i]
                    
                    # Simple pattern matching
                    title_company_match = re.search(r'(.+?)\s+[@\-–]\s+(.+)', line)
                    if title_company_match:
                        experience['title'] = title_company_match.group(1).strip()
                        experience['company'] = title_company_match.group(2).strip()
                        break
                        
            provisional.append(experience)
            
        return provisional
        
    def _extract_date_anchored_tri_signal_only(self, date_hits: List[Dict[str, Any]],
                                             text_lines: List[str],
                                             entities: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Extract only date-anchored items that pass tri-signal validation (hard block mode)."""
        valid_experiences = []
        
        for hit in date_hits:
            line_idx = hit.get('line_idx', 0)
            
            # Must pass tri-signal validation
            tri_signal_result = tri_signal_validator.validate_tri_signal_linkage(
                text_lines, line_idx, entities
            )
            
            if tri_signal_result['passes']:
                experience = self._extract_experience_from_line(
                    text_lines[line_idx], line_idx, text_lines, entities
                )
                
                if experience:
                    experience['extraction_method'] = 'date_anchored_tri_signal_only'
                    experience['tri_signal_validation'] = tri_signal_result
                    valid_experiences.append(experience)
                    
        logger.info(f"DATE_ANCHORED_TRI_SIGNAL: extracted={len(valid_experiences)} "
                   f"from_date_hits={len(date_hits)}")
                   
        return {'experiences': valid_experiences}
        
    def _validate_experiences_with_gates(self, experiences: List[Dict[str, Any]],
                                       text_lines: List[str],
                                       entities: List[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Apply all validation gates to a list of experiences."""
        validated = []
        
        for exp in experiences:
            line_idx = exp.get('line_idx', 0)
            
            # Apply tri-signal validation
            tri_signal_result = tri_signal_validator.validate_tri_signal_linkage(
                text_lines, line_idx, entities
            )
            
            self.stats['total_attempts'] += 1
            
            if tri_signal_result['passes']:
                self.stats['tri_signal_passes'] += 1
                
                # Apply minimum description token requirement
                description = exp.get('description', '')
                desc_tokens = len(description.split()) if description else 0
                min_tokens = self.config['min_desc_tokens']
                
                is_internship = 'stage' in exp.get('title', '').lower() or 'intern' in exp.get('title', '').lower()
                has_employer_and_dates = bool(exp.get('company')) and bool(exp.get('dates'))
                
                if desc_tokens >= min_tokens or (is_internship and has_employer_and_dates):
                    exp['tri_signal_validation'] = tri_signal_result
                    validated.append(exp)
                else:
                    logger.debug(f"VALIDATION: insufficient_description | line_idx={line_idx} "
                               f"desc_tokens={desc_tokens} min_required={min_tokens}")
            else:
                self.stats['tri_signal_failures'] += 1
                
        return validated
        
    def _extract_experience_from_block(self, block_lines: List[str], 
                                     block_start_idx: int,
                                     full_text_lines: List[str],
                                     entities: List[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Extract experience from a validated block of lines."""
        if not block_lines:
            return None
            
        # Combine block lines for analysis
        full_text = '\n'.join(block_lines)
        
        experience = {
            'title': '',
            'company': '', 
            'start_date': '',
            'end_date': '',
            'description': '',
            'location': '',
            'line_idx': block_start_idx,
            'block_text': full_text,
            'confidence': 0.6
        }
        
        # Extract title and company from first line
        first_line = block_lines[0] if block_lines else ''
        title_company_patterns = [
            r'(?P<title>.+?)\s+[@\-–—]\s+(?P<company>.+)',
            r'(?P<title>.+?)\s+chez\s+(?P<company>.+)',
            r'(?P<title>.+?)\s+at\s+(?P<company>.+)'
        ]
        
        for pattern in title_company_patterns:
            match = re.search(pattern, first_line, re.IGNORECASE)
            if match:
                experience['title'] = match.group('title').strip()
                experience['company'] = match.group('company').strip()
                break
                
        # If no pattern match, use heuristics
        if not experience['title'] and first_line:
            experience['title'] = first_line.strip()
            
        # Extract dates from context
        date_result = self._extract_dates_from_context(full_text, full_text_lines, block_start_idx)
        experience.update(date_result)
        
        # Extract description (remaining lines)
        if len(block_lines) > 1:
            experience['description'] = '\n'.join(block_lines[1:]).strip()
            
        return experience
        
    def _extract_experience_from_line(self, line: str, line_idx: int,
                                    full_text_lines: List[str],
                                    entities: List[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Extract experience from a single line with context."""
        if not line.strip():
            return None
            
        experience = {
            'title': '',
            'company': '',
            'start_date': '',
            'end_date': '',
            'description': '',
            'line_idx': line_idx,
            'original_line': line.strip(),
            'confidence': 0.5
        }
        
        # Pattern matching for title and company
        patterns = [
            r'(?P<title>.+?)\s+[@\-–—]\s+(?P<company>.+)',
            r'(?P<title>.+?)\s+chez\s+(?P<company>.+)',
            r'(?P<company>.+?)\s+[@\-–—]\s+(?P<title>.+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                groups = match.groupdict()
                if 'title' in groups:
                    experience['title'] = groups['title'].strip()
                if 'company' in groups:
                    experience['company'] = groups['company'].strip()
                break
                
        # Extract dates from context
        date_result = self._extract_dates_from_context(line, full_text_lines, line_idx)
        experience.update(date_result)
        
        return experience
        
    def _extract_dates_from_context(self, text: str, full_text_lines: List[str], 
                                   line_idx: int) -> Dict[str, str]:
        """Extract date information from text and surrounding context."""
        dates = {'start_date': '', 'end_date': ''}
        
        # Date patterns
        date_patterns = [
            r'(\d{4})\s*[-–—]\s*(\d{4})',
            r'(\d{4})\s*[-–—]\s*(?:present|current|aujourd\'hui|actuel)',
            r'(\d{1,2}/\d{4})\s*[-–—]\s*(\d{1,2}/\d{4})',
            r'depuis\s+(\d{4})',
            r'since\s+(\d{4})',
            r'(\d{4})'
        ]
        
        # Search in immediate text first
        for pattern in date_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                groups = match.groups()
                dates['start_date'] = groups[0]
                if len(groups) > 1:
                    dates['end_date'] = groups[1]
                break
                
        # If no dates found in immediate text, search context
        if not dates['start_date'] and full_text_lines:
            context_start = max(0, line_idx - 2)
            context_end = min(len(full_text_lines), line_idx + 3)
            context_text = ' '.join(full_text_lines[context_start:context_end])
            
            for pattern in date_patterns:
                match = re.search(pattern, context_text, re.IGNORECASE)
                if match:
                    groups = match.groups()
                    dates['start_date'] = groups[0]
                    if len(groups) > 1:
                        dates['end_date'] = groups[1]
                    break
                    
        return dates
        
    def _apply_organization_rebinding(self, experiences: List[Dict[str, Any]],
                                    text_lines: List[str],
                                    entities: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Apply organization rebinding with school detection."""
        rebind_stats = {
            'attempts': 0,
            'successes': 0,
            'school_demotions': 0
        }
        
        processed_experiences = []
        
        for exp in experiences:
            line_idx = exp.get('line_idx', 0)
            company = exp.get('company', '')
            
            # Check for school organization demotion
            demote_result = org_sieve.should_demote_for_school_org(exp, text_lines, line_idx)
            
            if demote_result['should_demote']:
                self.stats['school_org_demotions'] += 1
                rebind_stats['school_demotions'] += 1
                exp['demote_reason'] = demote_result['reason']
                exp['target_section'] = 'education'
                logger.info(f"ORG_REBIND: school_demotion | company='{company[:20]}...' "
                           f"reason={demote_result['reason']}")
                continue
                
            # Attempt rebinding if needed
            if not company or demote_result['is_school']:
                rebind_result = org_sieve.rebind_organization(exp, text_lines, line_idx, entities)
                rebind_stats['attempts'] += 1
                self.stats['org_rebind_attempts'] += 1
                
                if rebind_result['success']:
                    rebind_stats['successes'] += 1
                    self.stats['org_rebind_successes'] += 1
                    
            processed_experiences.append(exp)
            
        return {
            'experiences': processed_experiences,
            'stats': rebind_stats
        }
        
    def _apply_quality_assessment(self, experiences: List[Dict[str, Any]],
                                text_lines: List[str]) -> Dict[str, Any]:
        """Apply quality assessment and handle demotions."""
        final_experiences = []
        demotions = []
        quality_issues = []
        
        for exp in experiences:
            line_idx = exp.get('line_idx', 0)
            
            # Quality assessment
            from .experience_filters import ExperienceQualityAssessor
            assessor = ExperienceQualityAssessor()
            
            context = {
                'text_lines': text_lines
            }
            
            quality_result = assessor.assess_experience_quality(exp, context)
            
            if quality_result['should_demote']:
                demotions.append({
                    'experience': exp,
                    'target_section': quality_result['target_section'],
                    'reasons': quality_result['reasons']
                })
                logger.info(f"QA_DEMOTE: experience_demoted | line_idx={line_idx} "
                           f"reasons={quality_result['reasons']}")
            else:
                # Apply confidence penalty
                original_confidence = exp.get('confidence', 0.5)
                penalty = quality_result['confidence_penalty']
                exp['confidence'] = max(0.1, original_confidence - penalty)
                exp['quality_assessment'] = quality_result
                
                final_experiences.append(exp)
                
            if quality_result['reasons']:
                quality_issues.extend(quality_result['reasons'])
                
        return {
            'final_experiences': final_experiences,
            'demotions': demotions,
            'quality_issues': quality_issues
        }
        
    def get_extraction_stats(self) -> Dict[str, Any]:
        """Get comprehensive extraction statistics."""
        stats = self.stats.copy()
        
        # Calculate success rates
        if stats['total_attempts'] > 0:
            stats['tri_signal_success_rate'] = stats['tri_signal_passes'] / stats['total_attempts']
        else:
            stats['tri_signal_success_rate'] = 0.0
            
        if stats['org_rebind_attempts'] > 0:
            stats['org_rebind_success_rate'] = stats['org_rebind_successes'] / stats['org_rebind_attempts']
        else:
            stats['org_rebind_success_rate'] = 0.0
            
        return stats


# Global instance
enhanced_experience_extractor = EnhancedExperienceExtractor()
