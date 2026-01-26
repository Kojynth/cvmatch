"""
Soft Skills and Interests Extractors
====================================

Consolidates soft skills and interests extraction with strict context awareness
to prevent extraction from arbitrary text. Only extracts from appropriate 
sections and contexts.
"""

import re
from typing import List, Dict, Set, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from ..logging.safe_logger import get_safe_logger
from ..config import DEFAULT_PII_CONFIG, get_feature_flag

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


class ExtractionContext(Enum):
    """Context where extraction is taking place."""
    SOFT_SKILLS_SECTION = "soft_skills_section"
    INTERESTS_SECTION = "interests_section" 
    SKILLS_SECTION = "skills_section"
    BULLET_LIST = "bullet_list"
    NARRATIVE_TEXT = "narrative_text"
    UNKNOWN = "unknown"


@dataclass
class ExtractionResult:
    """Result of soft skills or interests extraction."""
    items: List[str]
    confidence: float
    context: ExtractionContext
    rejected_items: List[Tuple[str, str]] = None  # (item, reason)
    
    def __post_init__(self):
        if self.rejected_items is None:
            self.rejected_items = []


class SoftSkillsExtractor:
    """Extracts soft skills with strict context awareness."""
    
    def __init__(self):
        self.compile_patterns()
        self.load_vocabularies()
        
    def compile_patterns(self):
        """Compile regex patterns for soft skills detection."""
        # Soft skills section headers
        self.header_patterns = [
            re.compile(r'\b(?:soft\s*skills|compétences\s*(?:comportementales|transversales|personnelles))\b', re.IGNORECASE),
            re.compile(r'\b(?:qualités|savoir-être|aptitudes\s*personnelles)\b', re.IGNORECASE),
            re.compile(r'\b(?:personal\s*skills|interpersonal\s*skills)\b', re.IGNORECASE),
        ]
        
        # Negative patterns (avoid these contexts)
        self.negative_patterns = [
            re.compile(r'\b(?:\d{4}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b'),  # Dates
            re.compile(r'(?:expérience|experience|projet|project|formation|education)', re.IGNORECASE),
            re.compile(r'(?:entreprise|company|société|organization)', re.IGNORECASE),
            re.compile(r'(?:université|university|école|school|institut)', re.IGNORECASE),
        ]
        
        # Bullet point patterns
        self.bullet_pattern = re.compile(r'^[\s]*[-•▪▫◦‣⁃]\s*(.+)', re.MULTILINE)
        
        # Long sentence pattern (avoid narrative)
        self.long_sentence_pattern = re.compile(r'^.{100,}[.!?]', re.IGNORECASE)
        
    def load_vocabularies(self):
        """Load soft skills vocabularies."""
        # Core soft skills vocabulary (English and French)
        self.soft_skills_vocab = {
            # Communication
            'communication', 'présentation', 'écoute', 'listening', 'speaking', 'writing',
            'négociation', 'negotiation', 'persuasion', 'diplomatie', 'diplomacy',
            
            # Leadership
            'leadership', 'management', 'encadrement', 'delegation', 'délégation',
            'mentoring', 'coaching', 'motivation', 'inspiration',
            
            # Teamwork
            'travail d\'équipe', 'teamwork', 'collaboration', 'coopération', 'cooperation',
            'esprit d\'équipe', 'team spirit', 'networking', 'réseautage',
            
            # Problem-solving
            'résolution de problèmes', 'problem solving', 'analyse', 'analysis', 
            'pensée critique', 'critical thinking', 'créativité', 'creativity',
            'innovation', 'adaptabilité', 'adaptability', 'flexibilité', 'flexibility',
            
            # Personal qualities
            'autonomie', 'autonomy', 'initiative', 'proactivité', 'proactivity',
            'rigueur', 'précision', 'precision', 'organisation', 'organization',
            'gestion du temps', 'time management', 'ponctualité', 'punctuality',
            'fiabilité', 'reliability', 'persévérance', 'perseverance',
            
            # Emotional intelligence
            'empathie', 'empathy', 'intelligence émotionnelle', 'emotional intelligence',
            'gestion du stress', 'stress management', 'patience', 'tolerance',
            'bienveillance', 'kindness', 'respect', 'intégrité', 'integrity'
        }
        
        # Expand with common variations
        expanded_vocab = set()
        for skill in self.soft_skills_vocab:
            expanded_vocab.add(skill)
            expanded_vocab.add(skill.replace(' ', '-'))  # "time management" -> "time-management" 
            
        self.soft_skills_vocab = expanded_vocab
    
    def detect_context(self, text: str, line_index: int, all_lines: List[str]) -> ExtractionContext:
        """Detect the context of extraction."""
        # Check for soft skills header in surrounding lines
        start_idx = max(0, line_index - 3)
        end_idx = min(len(all_lines), line_index + 3)
        context_text = ' '.join(all_lines[start_idx:end_idx]).lower()
        
        for pattern in self.header_patterns:
            if pattern.search(context_text):
                return ExtractionContext.SOFT_SKILLS_SECTION
                
        # Check if it's a bullet list
        if self.bullet_pattern.match(text):
            return ExtractionContext.BULLET_LIST
            
        # Check for negative contexts
        for pattern in self.negative_patterns:
            if pattern.search(text):
                return ExtractionContext.NARRATIVE_TEXT
                
        return ExtractionContext.UNKNOWN
    
    def is_valid_soft_skill(self, candidate: str) -> Tuple[bool, str]:
        """Validate if candidate is a valid soft skill."""
        candidate_lower = candidate.lower().strip()
        
        # Too short or too long
        if len(candidate_lower) < 3:
            return False, "too_short"
        if len(candidate_lower) > 50:
            return False, "too_long"
            
        # Contains numbers (likely not a soft skill)
        if re.search(r'\d', candidate_lower):
            return False, "contains_numbers"
            
        # Contains colons (likely a section header or technical detail)
        if ':' in candidate_lower:
            return False, "contains_colon"
            
        # Check against vocabulary
        # Direct match
        if candidate_lower in self.soft_skills_vocab:
            return True, "vocabulary_match"
            
        # Partial match for compound skills
        words = candidate_lower.split()
        if len(words) > 1:
            for skill in self.soft_skills_vocab:
                if skill in candidate_lower or candidate_lower in skill:
                    return True, "partial_vocabulary_match"
                    
        # Check for common soft skill patterns
        soft_skill_patterns = [
            r'(?:capacité|ability|aptitude)\s+(?:à|to|de|for)',
            r'(?:esprit|spirit|sens)\s+(?:de|of|du)',
            r'(?:gestion|management)\s+(?:de|of|du)',
            r'(?:compétence|skill)\s+(?:en|in)',
        ]
        
        for pattern in soft_skill_patterns:
            if re.search(pattern, candidate_lower):
                return True, "pattern_match"
                
        return False, "no_match"
    
    def extract_from_line(self, line: str) -> List[str]:
        """Extract soft skills from a single line."""
        candidates = []
        
        # Extract from bullet points
        bullet_match = self.bullet_pattern.match(line)
        if bullet_match:
            content = bullet_match.group(1).strip()
            candidates.append(content)
        else:
            # Extract from comma-separated items
            parts = [part.strip() for part in line.split(',')]
            candidates.extend(parts)
            
        return candidates
    
    def extract(self, text: str, all_lines: List[str] = None, line_index: int = 0) -> ExtractionResult:
        """Extract soft skills from text with context awareness."""
        if not text or not text.strip():
            return ExtractionResult([], 0.0, ExtractionContext.UNKNOWN)
        
        # Determine context
        context = self.detect_context(text, line_index, all_lines or [text])
        
        # Apply strict filtering based on feature flag
        strict_mode = get_feature_flag('soft_interests.strict_fallback', True)
        
        if strict_mode and context in [ExtractionContext.NARRATIVE_TEXT, ExtractionContext.UNKNOWN]:
            logger.debug(f"SOFT_SKILLS: strict mode rejected extraction from context {context.value}")
            return ExtractionResult([], 0.0, context)
        
        # Extract candidates
        candidates = self.extract_from_line(text)
        
        # Validate candidates
        valid_skills = []
        rejected = []
        
        for candidate in candidates:
            is_valid, reason = self.is_valid_soft_skill(candidate)
            if is_valid:
                valid_skills.append(candidate.strip())
            else:
                rejected.append((candidate, reason))
        
        # Calculate confidence based on context and validation
        confidence = 0.0
        if valid_skills:
            base_confidence = {
                ExtractionContext.SOFT_SKILLS_SECTION: 0.9,
                ExtractionContext.BULLET_LIST: 0.7,
                ExtractionContext.SKILLS_SECTION: 0.8,
                ExtractionContext.NARRATIVE_TEXT: 0.3,
                ExtractionContext.UNKNOWN: 0.4,
            }.get(context, 0.4)
            
            # Boost confidence if many skills validated
            validation_boost = min(0.2, len(valid_skills) * 0.05)
            confidence = min(1.0, base_confidence + validation_boost)
        
        logger.debug(f"SOFT_SKILLS: extracted {len(valid_skills)} skills from context {context.value} with confidence {confidence:.2f}")
        
        return ExtractionResult(valid_skills, confidence, context, rejected)


class InterestsExtractor:
    """Extracts interests with strict context awareness."""
    
    def __init__(self):
        self.compile_patterns()
        self.load_vocabularies()
        
    def compile_patterns(self):
        """Compile regex patterns for interests detection."""
        # Interest section headers
        self.header_patterns = [
            re.compile(r'\b(?:interests|intérêts|centres?\s*d\'intérêt|hobbies|loisirs)\b', re.IGNORECASE),
            re.compile(r'\b(?:passions?|activités?\s*personnelles|temps\s*libre)\b', re.IGNORECASE),
            re.compile(r'\b(?:outside\s*work|personal\s*interests|recreational)\b', re.IGNORECASE),
        ]
        
        # Negative patterns
        self.negative_patterns = [
            re.compile(r'\b(?:\d{4}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b'),  # Dates  
            re.compile(r'(?:expérience|experience|formation|education|projet|project)', re.IGNORECASE),
            re.compile(r'(?:compétence|skill|technologie|technology)', re.IGNORECASE),
        ]
        
        # Bullet point patterns
        self.bullet_pattern = re.compile(r'^[\s]*[-•▪▫◦‣⁃]\s*(.+)', re.MULTILINE)
        
        # List markers
        self.list_markers = re.compile(r'^[\s]*(?:\d+\.|[a-z]\)|\*|\-|\+)', re.MULTILINE)
    
    def load_vocabularies(self):
        """Load interests vocabulary with thematic categorization."""
        # Thematic categorization for interest bucketing
        self.interest_categories = {
            'sports': {
                'sport', 'football', 'basketball', 'tennis', 'running', 'cycling', 'swimming',
                'yoga', 'fitness', 'musculation', 'randonnée', 'hiking', 'escalade', 'climbing',
                'ski', 'snowboard', 'surf', 'plongée', 'diving', 'marathon', 'triathlon',
                'boxe', 'boxing', 'judo', 'karaté', 'karate', 'rugby', 'volleyball', 'handball'
            },
            
            'arts': {
                'lecture', 'reading', 'écriture', 'writing', 'peinture', 'painting', 'dessin', 'drawing',
                'photographie', 'photography', 'musique', 'music', 'chant', 'singing', 'danse', 'dancing',
                'théâtre', 'theater', 'cinéma', 'cinema', 'films', 'movies', 'sculpture', 'poésie', 'poetry',
                'littérature', 'literature', 'art', 'artistique', 'créatif', 'creative', 'design'
            },
            
            'tech': {
                'technologie', 'technology', 'informatique', 'computing', 'programmation', 'programming',
                'développement', 'development', 'jeux vidéo', 'gaming', 'robotique', 'robotics',
                'intelligence artificielle', 'artificial intelligence', 'blockchain', 'crypto',
                'innovation', 'numérique', 'digital', 'électronique', 'electronics', 'gadgets'
            },
            
            'community': {
                'bénévolat', 'volunteering', 'associatif', 'charity', 'humanitaire', 'humanitarian',
                'environnement', 'environment', 'écologie', 'ecology', 'durabilité', 'sustainability',
                'politique', 'politics', 'social', 'communauté', 'community', 'engagement',
                'solidarité', 'solidarity', 'aide', 'helping', 'mentoring', 'enseignement', 'teaching'
            },
            
            'travel': {
                'voyage', 'travel', 'découverte', 'exploration', 'culture', 'langues', 'languages',
                'international', 'étranger', 'foreign', 'pays', 'countries', 'aventure', 'adventure',
                'backpacking', 'road trip', 'tourisme', 'tourism'
            }
        }
        
        # Flatten for backward compatibility
        self.interests_vocab = set()
        for category_interests in self.interest_categories.values():
            self.interests_vocab.update(category_interests)
    
    def categorize_interests(self, interests: List[str]) -> Dict[str, List[str]]:
        """
        Categorize interests into thematic buckets.
        
        Args:
            interests: List of interest strings
            
        Returns:
            Dict mapping category names to categorized interests
        """
        categorized = {category: [] for category in self.interest_categories.keys()}
        uncategorized = []
        
        for interest in interests:
            interest_normalized = self._normalize_interest(interest)
            category_found = False
            
            # Find matching category
            for category, vocab in self.interest_categories.items():
                if self._interest_matches_category(interest_normalized, vocab):
                    categorized[category].append(interest)
                    category_found = True
                    break
            
            if not category_found:
                uncategorized.append(interest)
        
        # Add uncategorized items to the most appropriate category or create "other"
        if uncategorized:
            if len(uncategorized) <= 2:
                # Add to largest existing category
                largest_category = max(categorized.keys(), 
                                     key=lambda k: len(categorized[k]))
                categorized[largest_category].extend(uncategorized)
            else:
                categorized['other'] = uncategorized
        
        # Remove empty categories
        return {k: v for k, v in categorized.items() if v}
    
    def cap_interests(self, categorized_interests: Dict[str, List[str]], 
                     max_categories: int = 4, max_per_category: int = 5) -> Dict[str, List[str]]:
        """
        Cap the number of interest categories and items per category.
        
        Args:
            categorized_interests: Dict of categorized interests
            max_categories: Maximum number of categories to keep
            max_per_category: Maximum items per category
            
        Returns:
            Capped interests dict
        """
        # Sort categories by count (keep most populous)
        sorted_categories = sorted(
            categorized_interests.items(),
            key=lambda x: len(x[1]),
            reverse=True
        )
        
        capped = {}
        for category, interests in sorted_categories[:max_categories]:
            # Normalize and deduplicate interests within category
            normalized_interests = []
            seen_normalized = set()
            
            for interest in interests:
                normalized = self._normalize_interest(interest)
                if normalized not in seen_normalized:
                    normalized_interests.append(interest)
                    seen_normalized.add(normalized)
            
            # Cap per category
            capped[category] = normalized_interests[:max_per_category]
        
        return capped
    
    def _normalize_interest(self, interest: str) -> str:
        """
        Normalize interest for comparison (lowercase, singular, emoji-stripped).
        
        Args:
            interest: Interest string to normalize
            
        Returns:
            Normalized interest string
        """
        if not interest:
            return ""
        
        # Convert to lowercase
        normalized = interest.lower().strip()
        
        # Remove common emoji and symbols
        emoji_pattern = re.compile(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF\u2600-\u26FF\u2700-\u27BF]')
        normalized = emoji_pattern.sub('', normalized)
        
        # Handle common plural forms
        plural_patterns = [
            (r's$', ''),           # sports -> sport
            (r'ies$', 'y'),        # hobbies -> hobby
            (r'ves$', 'f'),        # leaves -> leaf
            (r'es$', ''),          # games -> game (careful with this one)
        ]
        
        for pattern, replacement in plural_patterns:
            if re.search(pattern, normalized) and len(normalized) > 4:  # Don't singularize very short words
                normalized = re.sub(pattern, replacement, normalized)
                break
        
        # Remove extra whitespace
        normalized = ' '.join(normalized.split())
        
        return normalized
    
    def _interest_matches_category(self, interest_normalized: str, category_vocab: set) -> bool:
        """
        Check if normalized interest matches a category vocabulary.
        
        Args:
            interest_normalized: Normalized interest string
            category_vocab: Set of category vocabulary
            
        Returns:
            True if interest matches category
        """
        # Exact match
        if interest_normalized in category_vocab:
            return True
        
        # Partial match (interest contains vocabulary word)
        words = interest_normalized.split()
        for vocab_word in category_vocab:
            # Check if vocabulary word is in interest
            if vocab_word in interest_normalized:
                return True
            # Check if any word from interest is in vocabulary word
            if any(word in vocab_word for word in words if len(word) > 3):
                return True
        
        return False
    
    def detect_context(self, text: str, line_index: int, all_lines: List[str]) -> ExtractionContext:
        """Detect the context of extraction."""
        # Check for interests header in surrounding lines
        start_idx = max(0, line_index - 3)
        end_idx = min(len(all_lines), line_index + 3)
        context_text = ' '.join(all_lines[start_idx:end_idx]).lower()
        
        for pattern in self.header_patterns:
            if pattern.search(context_text):
                return ExtractionContext.INTERESTS_SECTION
                
        # Check if it's a bullet/list format
        if self.bullet_pattern.match(text) or self.list_markers.match(text):
            return ExtractionContext.BULLET_LIST
            
        # Check for negative contexts
        for pattern in self.negative_patterns:
            if pattern.search(text):
                return ExtractionContext.NARRATIVE_TEXT
                
        return ExtractionContext.UNKNOWN
    
    def is_valid_interest(self, candidate: str) -> Tuple[bool, str]:
        """Validate if candidate is a valid interest."""
        candidate_lower = candidate.lower().strip()
        
        # Length constraints
        if len(candidate_lower) < 3:
            return False, "too_short"
        if len(candidate_lower) > 40:
            return False, "too_long"
            
        # Single generic nouns (too vague)
        if len(candidate.split()) == 1 and candidate_lower in ['sport', 'music', 'reading', 'travel']:
            return False, "too_generic"
            
        # Contains dates or years
        if re.search(r'\b(?:\d{4}|\d{1,2}/\d{1,2})\b', candidate_lower):
            return False, "contains_dates"
            
        # Contains colons (likely section headers)
        if ':' in candidate:
            return False, "contains_colon"
            
        # Direct vocabulary match
        if candidate_lower in self.interests_vocab:
            return True, "vocabulary_match"
            
        # Partial match for compound interests
        words = candidate_lower.split()
        if len(words) > 1:
            for interest in self.interests_vocab:
                if interest in candidate_lower or any(word in interest for word in words):
                    return True, "partial_vocabulary_match"
        
        # Check for interest-like patterns
        interest_patterns = [
            r'(?:pratique|practice|playing|jouer)\s+(?:du|de|la|le|\w+)',
            r'(?:collection|collecting)\s+(?:de|of)',
            r'(?:apprentissage|learning)\s+(?:du|de|la|des)',
        ]
        
        for pattern in interest_patterns:
            if re.search(pattern, candidate_lower):
                return True, "pattern_match"
                
        # If it contains multiple words and no negative indicators, likely valid
        if len(words) >= 2 and len(words) <= 4:
            return True, "multi_word_interest"
            
        return False, "no_match"
    
    def extract_from_line(self, line: str) -> List[str]:
        """Extract interests from a single line."""
        candidates = []
        
        # Extract from bullet points
        bullet_match = self.bullet_pattern.match(line)
        if bullet_match:
            content = bullet_match.group(1).strip()
            candidates.append(content)
        else:
            # Extract from comma/semicolon separated items
            separators = [',', ';', '•', '▪']
            parts = [line]
            
            for sep in separators:
                new_parts = []
                for part in parts:
                    new_parts.extend([p.strip() for p in part.split(sep)])
                parts = new_parts
                
            candidates.extend([p for p in parts if p])
            
        return candidates
    
    def extract(self, text: str, all_lines: List[str] = None, line_index: int = 0) -> ExtractionResult:
        """Extract interests from text with context awareness."""
        if not text or not text.strip():
            return ExtractionResult([], 0.0, ExtractionContext.UNKNOWN)
        
        # Determine context
        context = self.detect_context(text, line_index, all_lines or [text])
        
        # Apply strict filtering
        strict_mode = get_feature_flag('soft_interests.strict_fallback', True)
        
        if strict_mode and context not in [ExtractionContext.INTERESTS_SECTION, ExtractionContext.BULLET_LIST]:
            logger.debug(f"INTERESTS: strict mode rejected extraction from context {context.value}")
            return ExtractionResult([], 0.0, context)
        
        # Extract candidates
        candidates = self.extract_from_line(text)
        
        # Validate candidates
        valid_interests = []
        rejected = []
        
        for candidate in candidates:
            is_valid, reason = self.is_valid_interest(candidate)
            if is_valid:
                valid_interests.append(candidate.strip())
            else:
                rejected.append((candidate, reason))
        
        # Calculate confidence
        confidence = 0.0
        if valid_interests:
            base_confidence = {
                ExtractionContext.INTERESTS_SECTION: 0.9,
                ExtractionContext.BULLET_LIST: 0.7,
                ExtractionContext.SKILLS_SECTION: 0.6,
                ExtractionContext.NARRATIVE_TEXT: 0.2,
                ExtractionContext.UNKNOWN: 0.3,
            }.get(context, 0.3)
            
            # Boost confidence for multiple validated interests
            validation_boost = min(0.2, len(valid_interests) * 0.05)
            confidence = min(1.0, base_confidence + validation_boost)
        
        logger.debug(f"INTERESTS: extracted {len(valid_interests)} interests from context {context.value} with confidence {confidence:.2f}")
        
        return ExtractionResult(valid_interests, confidence, context, rejected)


# Global extractor instances
_soft_skills_extractor = None
_interests_extractor = None


def get_soft_skills_extractor() -> SoftSkillsExtractor:
    """Get global soft skills extractor instance."""
    global _soft_skills_extractor
    if _soft_skills_extractor is None:
        _soft_skills_extractor = SoftSkillsExtractor()
    return _soft_skills_extractor


def get_interests_extractor() -> InterestsExtractor:
    """Get global interests extractor instance."""
    global _interests_extractor
    if _interests_extractor is None:
        _interests_extractor = InterestsExtractor()
    return _interests_extractor


def extract_soft_skills_contextual(text: str, all_lines: List[str] = None, line_index: int = 0) -> ExtractionResult:
    """Extract soft skills with full context awareness."""
    extractor = get_soft_skills_extractor()
    return extractor.extract(text, all_lines, line_index)


def extract_interests_contextual(text: str, all_lines: List[str] = None, line_index: int = 0) -> ExtractionResult:
    """Extract interests with full context awareness."""
    extractor = get_interests_extractor()
    return extractor.extract(text, all_lines, line_index)