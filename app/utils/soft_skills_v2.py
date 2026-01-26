"""
Soft Skills V2 - Conservative extraction with strict validation guardrails.

This implementation provides:
- Conservative guardrails against over-extraction
- Strict validation and confidence thresholds
- False positive filtering with statistical validation
- Quality-based filtering and deduplication
- Integration with existing soft skills infrastructure
"""

import re
from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass
from pathlib import Path
import json
from collections import Counter

from ..logging.safe_logger import get_safe_logger
from ..config import DEFAULT_PII_CONFIG, get_feature_flag
from .soft_skills_fallback import SOFT_SKILLS_LEXICON, SoftSkillsExtractionResult

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


@dataclass
class SoftSkillsV2Metrics:
    """Conservative metrics for soft skills extraction V2."""
    candidates_found: int = 0
    candidates_validated: int = 0
    candidates_rejected: int = 0
    false_positives_filtered: int = 0
    duplicates_removed: int = 0
    confidence_threshold_applied: float = 0.0
    extraction_method: str = ""
    quality_score_avg: float = 0.0
    validation_failures: List[str] = None
    
    def __post_init__(self):
        if self.validation_failures is None:
            self.validation_failures = []


class SoftSkillsV2:
    """
    Conservative soft skills extractor with strict validation guardrails.
    
    Key features:
    - Conservative thresholds to prevent over-extraction
    - Multi-stage validation pipeline
    - False positive detection using context analysis
    - Quality scoring and statistical validation
    - Configurable guardrails via feature flags
    """
    
    def __init__(self):
        self.logger = get_safe_logger(f"{__name__}.SoftSkillsV2", cfg=DEFAULT_PII_CONFIG)
        self.metrics = SoftSkillsV2Metrics()
        
        # Conservative configuration - strict thresholds
        self.config = {
            'min_confidence_threshold': 0.75,  # High threshold
            'max_skills_per_extraction': 12,   # Conservative limit
            'min_skill_length': 4,             # Minimum character length
            'max_skill_length': 50,            # Maximum character length
            'context_validation_required': True,
            'statistical_validation_enabled': True,
            'false_positive_filters_enabled': True
        }
        
        # Load enhanced lexicon
        self.skills_lexicon = self._load_enhanced_lexicon()
        
        # Conservative validation patterns
        self.validation_patterns = {
            'valid_contexts': [
                r'(?:compétences?|skills?|qualités?|atouts?)\s*[:.]',
                r'(?:soft\s+skills?|savoir[- ]être|interpersonnel)',
                r'(?:aptitudes?|capacités?|talents?)\s*[:.]',
            ],
            'invalid_contexts': [
                r'(?:techniques?|technical|hard\s+skills?)',
                r'(?:outils?|tools?|logiciels?|software)',
                r'(?:langages?|languages?|programmation)',
                r'(?:diplômes?|formations?|certifications?)',
                r'(?:expériences?|postes?|emplois?)',
            ],
            'noise_patterns': [
                r'^\d+[\s\.]',  # Numbers at start
                r'^[A-Z]{2,}$',  # All caps abbreviations
                r'^\w{1,2}$',   # Very short tokens
                r'[^\w\s\'-]',  # Non-standard characters
            ]
        }
        
        # Statistical validation thresholds
        self.statistical_thresholds = {
            'max_extraction_rate': 0.15,  # Max 15% of tokens can be skills
            'min_token_frequency': 0.02,  # Min 2% frequency in corpus
            'diversity_threshold': 0.6,   # At least 60% unique skills
        }
        
    def extract_soft_skills(self, lines: List[str], context: Optional[Dict[str, Any]] = None) -> SoftSkillsExtractionResult:
        """
        Extract soft skills with conservative guardrails.
        
        Args:
            lines: Lines of text to extract from
            context: Additional context for validation
            
        Returns:
            Conservative extraction result with validation metrics
        """
        self.metrics = SoftSkillsV2Metrics()
        
        if not lines:
            logger.info("SOFT_SKILLS_V2: empty_input | returning empty result")
            return SoftSkillsExtractionResult(
                skills=[], 
                confidence=0.0, 
                extraction_method="empty_input"
            )
        
        logger.info(f"SOFT_SKILLS_V2: extract_start | lines={len(lines)}")
        
        # Stage 1: Initial candidate extraction
        candidates = self._extract_candidates(lines)
        self.metrics.candidates_found = len(candidates)
        
        # Stage 2: Context validation
        validated_candidates = self._validate_context(candidates, lines)
        
        # Stage 3: False positive filtering
        filtered_candidates = self._filter_false_positives(validated_candidates)
        
        # Stage 4: Quality scoring and ranking
        scored_candidates = self._score_and_rank(filtered_candidates)
        
        # Stage 5: Statistical validation and final filtering
        final_skills = self._apply_statistical_validation(scored_candidates, lines)
        
        # Stage 6: Conservative guardrails enforcement
        conservative_skills = self._apply_conservative_guardrails(final_skills)
        
        # Calculate final metrics
        confidence = self._calculate_conservative_confidence(conservative_skills, lines)
        
        self.metrics.candidates_validated = len(conservative_skills)
        self.metrics.candidates_rejected = self.metrics.candidates_found - self.metrics.candidates_validated
        self.metrics.confidence_threshold_applied = self.config['min_confidence_threshold']
        self.metrics.extraction_method = "conservative_v2"
        
        logger.info(f"SOFT_SKILLS_V2: extract_complete | "
                   f"found={self.metrics.candidates_found} "
                   f"validated={self.metrics.candidates_validated} "
                   f"rejected={self.metrics.candidates_rejected} "
                   f"confidence={confidence:.3f}")
        
        return SoftSkillsExtractionResult(
            skills=conservative_skills,
            confidence=confidence,
            extraction_method="conservative_v2_guardrails",
            raw_text=' '.join(lines),
            normalized_count=len(conservative_skills)
        )
    
    def _load_enhanced_lexicon(self) -> Set[str]:
        """Load enhanced soft skills lexicon with conservative filtering."""
        # Start with existing lexicon
        base_lexicon = set(SOFT_SKILLS_LEXICON)
        
        # Apply conservative filtering - remove ambiguous terms
        ambiguous_terms = {
            'management',  # Could be technical project management
            'development', # Could be software development
            'design',      # Could be technical design
            'analysis',    # Could be data analysis
            'research',    # Could be technical research
        }
        
        conservative_lexicon = base_lexicon - ambiguous_terms
        
        # Add high-confidence soft skills
        conservative_additions = {
            'empathie', 'bienveillance', 'patience', 'persévérance',
            'adaptabilité', 'flexibilité', 'créativité', 'innovation',
            'collaboration', 'teamwork', 'esprit d\'équipe',
            'communication interpersonnelle', 'écoute active',
            'résolution de conflits', 'médiation', 'négociation',
            'leadership naturel', 'influence positive', 'inspiration',
            'communication', 'interpersonnelle', 'leadership', 'esprit',
            'équipe', 'adaptabilité', 'créativité', 'empathie', 'écoute',
            'résolution', 'conflits', 'bienveillance', 'résilience',
        }
        
        conservative_lexicon.update(conservative_additions)
        
        logger.debug(f"SOFT_SKILLS_V2: lexicon loaded | terms={len(conservative_lexicon)}")
        return conservative_lexicon
    
    def _extract_candidates(self, lines: List[str]) -> List[Dict[str, Any]]:
        """Extract initial soft skill candidates from lines."""
        candidates = []
        
        for line_idx, line in enumerate(lines):
            line = line.strip()
            if not line or len(line) < 5:
                continue
            
            # Check if line is in valid context
            if not self._is_valid_context_line(line):
                continue
            
            # Extract tokens from line
            tokens = self._extract_tokens_from_line(line)
            
            for token in tokens:
                if self._is_potential_soft_skill(token):
                    candidates.append({
                        'skill': token,
                        'line_idx': line_idx,
                        'original_line': line,
                        'raw_token': token,
                        'confidence': 0.5  # Initial confidence
                    })
        
        logger.debug(f"SOFT_SKILLS_V2: candidates_extracted | count={len(candidates)}")
        return candidates
    
    def _is_valid_context_line(self, line: str) -> bool:
        """Check if line contains valid soft skills context."""
        line_lower = line.lower()
        
        # Check for valid context patterns
        valid_context_found = False
        for pattern in self.validation_patterns['valid_contexts']:
            if re.search(pattern, line_lower):
                valid_context_found = True
                break
        
        # If no explicit valid context, check for bullet/list patterns
        if not valid_context_found:
            bullet_patterns = [
                r'^\s*[-•*▪▫]\s+',  # Bullet points
                r'^\s*\d+[\.\)]\s+',  # Numbered lists
                r'^\s*[a-z]\)\s+',    # Letter lists
            ]
            for pattern in bullet_patterns:
                if re.search(pattern, line):
                    valid_context_found = True
                    break
        
        # Check for invalid contexts (exclusion)
        if valid_context_found:
            for pattern in self.validation_patterns['invalid_contexts']:
                if re.search(pattern, line_lower):
                    logger.debug(f"SOFT_SKILLS_V2: invalid_context_detected | line='{line[:30]}...'")
                    return False
        
        return valid_context_found
    
    def _extract_tokens_from_line(self, line: str) -> List[str]:
        """Extract potential skill tokens from line."""
        # Clean line
        cleaned = re.sub(r'^\s*[-•*▪▫\d+\.\)\]]\s*', '', line)  # Remove bullets/numbers
        cleaned = re.sub(r'[^\w\s\'-àâäçéèêëïîôùûüÿ]', ' ', cleaned)  # Keep only letters, spaces, hyphens, accents
        
        # Split on multiple delimiters
        primary_tokens = re.split(r'[,;|/\n]+', cleaned)
        
        # Further split long phrases and extract meaningful chunks
        all_tokens = []
        for token in primary_tokens:
            token = token.strip()
            if not token:
                continue
                
            # Split long phrases into sub-phrases
            words = token.split()
            if len(words) <= 3:  # Keep short phrases intact
                all_tokens.append(token)
            else:
                # Extract 1-3 word combinations from longer phrases
                for i in range(len(words)):
                    # Single words
                    if len(words[i]) >= 4:  # Avoid very short words
                        all_tokens.append(words[i])
                    
                    # Two-word combinations
                    if i < len(words) - 1:
                        two_word = f"{words[i]} {words[i+1]}"
                        all_tokens.append(two_word)
                    
                    # Three-word combinations  
                    if i < len(words) - 2:
                        three_word = f"{words[i]} {words[i+1]} {words[i+2]}"
                        all_tokens.append(three_word)
        
        # Clean and validate tokens
        clean_tokens = []
        for token in all_tokens:
            token = token.strip().lower()
            if (self.config['min_skill_length'] <= len(token) <= self.config['max_skill_length'] 
                and not self._is_noise_token(token)):
                clean_tokens.append(token)
        
        return clean_tokens
    
    def _is_noise_token(self, token: str) -> bool:
        """Check if token is noise/invalid."""
        for pattern in self.validation_patterns['noise_patterns']:
            if re.search(pattern, token):
                return True
        
        # Additional noise checks
        if token.isdigit():
            return True
        
        if len(set(token)) <= 2:  # Too repetitive
            return True
        
        return False
    
    def _is_potential_soft_skill(self, token: str) -> bool:
        """Check if token could be a soft skill."""
        token_lower = token.lower()
        
        # Exact match in lexicon
        if token_lower in self.skills_lexicon:
            return True
        
        # Fuzzy matching for slight variations
        from difflib import SequenceMatcher
        for skill in self.skills_lexicon:
            if SequenceMatcher(None, token_lower, skill).ratio() > 0.75:  # More lenient threshold
                return True
        
        # Partial matching for compound skills
        for skill in self.skills_lexicon:
            if token_lower in skill or skill in token_lower:
                return True
        
        return False
    
    def _validate_context(self, candidates: List[Dict[str, Any]], lines: List[str]) -> List[Dict[str, Any]]:
        """Validate candidates using broader context analysis."""
        if not self.config['context_validation_required']:
            return candidates
        
        validated = []
        
        for candidate in candidates:
            line_idx = candidate['line_idx']
            skill = candidate['skill']
            
            # Analyze surrounding context (±2 lines)
            context_lines = []
            for i in range(max(0, line_idx - 2), min(len(lines), line_idx + 3)):
                if i < len(lines):
                    context_lines.append(lines[i])
            
            context_text = ' '.join(context_lines).lower()
            
            # Context validation scoring
            context_score = self._calculate_context_score(skill, context_text)
            
            if context_score >= 0.6:  # Conservative threshold
                candidate['context_score'] = context_score
                candidate['confidence'] = min(candidate['confidence'] + context_score * 0.3, 1.0)
                validated.append(candidate)
            else:
                self.metrics.validation_failures.append(f"low_context_score_{skill}")
        
        logger.debug(f"SOFT_SKILLS_V2: context_validation | {len(validated)}/{len(candidates)} passed")
        return validated
    
    def _calculate_context_score(self, skill: str, context: str) -> float:
        """Calculate context relevance score for a skill."""
        score = 0.0
        
        # Positive context indicators
        positive_indicators = [
            'compétences', 'skills', 'qualités', 'atouts', 'soft skills',
            'savoir être', 'interpersonnel', 'relationnel', 'humain'
        ]
        
        for indicator in positive_indicators:
            if indicator in context:
                score += 0.2
        
        # Negative context indicators
        negative_indicators = [
            'technique', 'technical', 'programming', 'software', 'code',
            'langage', 'language', 'framework', 'library', 'database'
        ]
        
        for indicator in negative_indicators:
            if indicator in context:
                score -= 0.3
        
        return max(0.0, min(1.0, score))
    
    def _filter_false_positives(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter out false positives using pattern analysis."""
        if not self.config['false_positive_filters_enabled']:
            return candidates
        
        filtered = []
        
        # Common false positive patterns in French CVs
        false_positive_patterns = [
            r'\b(?:janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)\b',  # Months
            r'\b(?:lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)\b',  # Days
            r'\b(?:paris|lyon|marseille|toulouse|nice|nantes|strasbourg|montpellier|bordeaux)\b',  # Cities
            r'\b\d+\s*(?:ans?|years?|mois|months?)\b',  # Age/duration
            r'\b(?:master|licence|bac|phd|doctorat)\b',  # Degrees
            r'\b(?:stage|internship|cdd|cdi|freelance)\b',  # Contract types
        ]
        
        for candidate in candidates:
            skill = candidate['skill'].lower()
            is_false_positive = False
            
            for pattern in false_positive_patterns:
                if re.search(pattern, skill):
                    is_false_positive = True
                    self.metrics.false_positives_filtered += 1
                    self.metrics.validation_failures.append(f"false_positive_pattern_{skill}")
                    break
            
            if not is_false_positive:
                filtered.append(candidate)
        
        logger.debug(f"SOFT_SKILLS_V2: false_positive_filtering | "
                    f"{len(filtered)}/{len(candidates)} passed, "
                    f"{self.metrics.false_positives_filtered} filtered")
        
        return filtered
    
    def _score_and_rank(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Score and rank candidates by quality."""
        for candidate in candidates:
            skill = candidate['skill']
            
            # Base quality score
            quality_score = 0.5
            
            # Length bonus (optimal length skills get higher score)
            length = len(skill)
            if 8 <= length <= 25:  # Optimal length range
                quality_score += 0.2
            elif length < 4 or length > 40:  # Too short or too long
                quality_score -= 0.2
            
            # Lexicon match bonus
            if skill.lower() in self.skills_lexicon:
                quality_score += 0.3
            
            # Multi-word bonus (compound soft skills often more specific)
            if len(skill.split()) >= 2:
                quality_score += 0.1
            
            # French accent handling bonus
            if any(c in skill for c in 'àâäçéèêëïîôùûüÿ'):
                quality_score += 0.05
            
            candidate['quality_score'] = min(1.0, quality_score)
            candidate['confidence'] = min(candidate.get('confidence', 0.5) + quality_score * 0.2, 1.0)
        
        # Sort by quality score (highest first)
        scored_candidates = sorted(candidates, key=lambda x: x['quality_score'], reverse=True)
        
        # Calculate average quality score
        if scored_candidates:
            self.metrics.quality_score_avg = sum(c['quality_score'] for c in scored_candidates) / len(scored_candidates)
        
        return scored_candidates
    
    def _apply_statistical_validation(self, candidates: List[Dict[str, Any]], lines: List[str]) -> List[str]:
        """Apply statistical validation to prevent over-extraction."""
        if not self.config['statistical_validation_enabled']:
            return [c['skill'] for c in candidates]
        
        total_tokens = sum(len(line.split()) for line in lines)
        max_allowed_skills = int(total_tokens * self.statistical_thresholds['max_extraction_rate'])
        
        # Limit by extraction rate
        limited_candidates = candidates[:min(len(candidates), max_allowed_skills)]
        
        # Apply diversity threshold
        skills = [c['skill'] for c in limited_candidates]
        unique_skills = list(dict.fromkeys(skills))  # Preserve order, remove duplicates
        
        diversity_ratio = len(unique_skills) / len(skills) if skills else 1.0
        if diversity_ratio < self.statistical_thresholds['diversity_threshold']:
            # Keep only most confident unique skills
            seen = set()
            diverse_skills = []
            for candidate in limited_candidates:
                skill = candidate['skill']
                if skill not in seen:
                    diverse_skills.append(skill)
                    seen.add(skill)
                else:
                    self.metrics.duplicates_removed += 1
            unique_skills = diverse_skills
        
        self.metrics.duplicates_removed = len(skills) - len(unique_skills)
        
        logger.debug(f"SOFT_SKILLS_V2: statistical_validation | "
                    f"extraction_rate={len(unique_skills)/total_tokens:.3f} "
                    f"diversity={diversity_ratio:.3f}")
        
        return unique_skills
    
    def _apply_conservative_guardrails(self, skills: List[str]) -> List[str]:
        """Apply final conservative guardrails."""
        # Limit maximum number of skills
        max_skills = self.config['max_skills_per_extraction']
        
        # Apply feature flag override if available
        if get_feature_flag("soft_skills_v2_max_limit", default=None) is not None:
            max_skills = get_feature_flag("soft_skills_v2_max_limit", default=max_skills)
        
        if len(skills) > max_skills:
            skills = skills[:max_skills]
            logger.info(f"SOFT_SKILLS_V2: guardrail_applied | limited to {max_skills} skills")
        
        # Remove very short skills in final pass
        quality_filtered = [skill for skill in skills if len(skill.strip()) >= self.config['min_skill_length']]
        
        return quality_filtered
    
    def _calculate_conservative_confidence(self, skills: List[str], lines: List[str]) -> float:
        """Calculate conservative confidence score."""
        if not skills:
            return 0.0
        
        base_confidence = 0.5
        
        # Bonus for reasonable number of skills
        skill_count = len(skills)
        if 3 <= skill_count <= 8:  # Sweet spot
            base_confidence += 0.2
        elif skill_count > 12:  # Too many, reduce confidence
            base_confidence -= 0.3
        
        # Bonus for clear context
        has_clear_context = any(
            re.search(pattern, ' '.join(lines).lower())
            for pattern in self.validation_patterns['valid_contexts']
        )
        
        if has_clear_context:
            base_confidence += 0.2
        
        # Quality score bonus
        base_confidence += self.metrics.quality_score_avg * 0.1
        
        # Conservative adjustment - never too confident
        conservative_confidence = min(base_confidence, 0.85)  # Cap at 85%
        
        # Apply minimum threshold
        if conservative_confidence < self.config['min_confidence_threshold']:
            return 0.0  # Reject extraction
        
        return conservative_confidence
    
    def get_metrics(self) -> SoftSkillsV2Metrics:
        """Get extraction metrics."""
        return self.metrics


# Convenience function for easy integration
def extract_soft_skills_v2(lines: List[str], context: Optional[Dict[str, Any]] = None) -> SoftSkillsExtractionResult:
    """
    Conservative soft skills extraction V2.
    
    Args:
        lines: Lines of text to extract from
        context: Additional context for validation
        
    Returns:
        Conservative extraction result
    """
    extractor = SoftSkillsV2()
    return extractor.extract_soft_skills(lines, context)