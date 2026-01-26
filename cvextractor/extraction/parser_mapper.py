"""
Parser Mapper with Triad Binding
================================

Deterministic routing and field binding using explicit DATE+ROLE+ORG triad scoring.
Enforces strict thresholds and demotes contaminated fields.
"""

import re
import math
from typing import Dict, List, Any, Optional, Tuple, Set
from dataclasses import dataclass
from datetime import datetime
import logging

from ..utils.log_safety import create_safe_logger_wrapper, mask_all
from ..metrics.instrumentation import get_metrics_collector, DecisionLog


@dataclass
class TriadScore:
    """Scoring for DATE+ROLE+ORG triad."""

    date_conf: float = 0.0
    role_conf: float = 0.0
    org_conf: float = 0.0
    assoc_score: float = 0.0

    @property
    def is_valid_triad(self) -> bool:
        """Check if all components meet minimum thresholds."""
        return self.date_conf > 0 and self.role_conf > 0 and self.org_conf > 0

    @property
    def overall_score(self) -> float:
        """Calculate overall triad quality score."""
        if not self.is_valid_triad:
            return 0.0
        return (
            self.date_conf * 0.3 + self.role_conf * 0.4 + self.org_conf * 0.3
        ) * self.assoc_score


@dataclass
class CandidateItem:
    """Item candidate for parsing and routing."""

    text: str
    item_type: str = "unknown"  # experience, education, project, etc.
    fields: Dict[str, Any] = None
    triad_score: TriadScore = None
    status: str = "pending"  # ok, uncertain, rejected
    warnings: List[str] = None
    original_section: str = "unknown"

    def __post_init__(self):
        if self.fields is None:
            self.fields = {}
        if self.triad_score is None:
            self.triad_score = TriadScore()
        if self.warnings is None:
            self.warnings = []


class ParserMapper:
    """Deterministic parser with triad binding and explicit thresholds."""

    def __init__(
        self,
        min_date_conf: float = 0.60,
        min_role_token_conf: float = 0.55,
        min_org_conf: float = 0.50,
        min_assoc: float = 0.70,
        school_org_boost: float = 0.20,
        school_org_min: float = 0.70,
        debug_mode: bool = False,
    ):
        # Thresholds
        self.min_date_conf = min_date_conf
        self.min_role_token_conf = min_role_token_conf
        self.min_org_conf = min_org_conf
        self.min_assoc = min_assoc
        self.school_org_boost = school_org_boost
        self.school_org_min = school_org_min
        self.debug_mode = debug_mode

        # Logger
        base_logger = logging.getLogger(__name__)
        self.logger = create_safe_logger_wrapper(base_logger)

        # Compile patterns
        self._compile_patterns()

    def _compile_patterns(self):
        """Compile regex patterns for field detection."""

        # Date patterns (French and international)
        self.date_patterns = [
            # DD/MM/YYYY formats
            re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})\b"),
            re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{2})\b"),
            # MM/YYYY formats
            re.compile(r"\b(\d{1,2})[/.-](\d{4})\b"),
            # Year ranges
            re.compile(r"\b(\d{4})\s*[-–]\s*(\d{4})\b"),
            re.compile(
                r"\b(\d{4})\s*[-–]\s*(?:présent|present|current|en cours|à ce jour)\b",
                re.IGNORECASE,
            ),
            # Standalone years
            re.compile(r"\b(19|20)\d{2}\b"),
        ]

        # Role patterns (French/English)
        self.role_keywords = [
            # French roles
            "développeur",
            "ingénieur",
            "chef",
            "responsable",
            "manager",
            "directeur",
            "consultant",
            "analyste",
            "technicien",
            "assistant",
            "coordinateur",
            "stage",
            "stagiaire",
            "alternant",
            "apprenti",
            # English roles
            "developer",
            "engineer",
            "manager",
            "director",
            "consultant",
            "analyst",
            "technician",
            "assistant",
            "coordinator",
            "specialist",
            "intern",
            "trainee",
            "junior",
            "senior",
            "lead",
        ]

        # School lexemes for organization filtering
        self.school_lexemes = [
            "université",
            "university",
            "école",
            "school",
            "institut",
            "institute",
            "college",
            "faculté",
            "faculty",
            "campus",
            "iut",
            "bts",
            "dut",
            "lycée",
            "high school",
            "académie",
            "academy",
        ]

        # Employment verification patterns
        self.employment_verbs = [
            "développé",
            "créé",
            "géré",
            "dirigé",
            "coordonné",
            "supervisé",
            "developed",
            "created",
            "managed",
            "led",
            "coordinated",
            "supervised",
            "implemented",
            "designed",
            "built",
            "maintained",
        ]

        # Date token patterns for field contamination detection
        self.date_token_pattern = re.compile(
            r"\b(?:\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}|\d{1,2}[/.-]\d{4}|\d{4}|"
            r"janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre|"
            r"january|february|march|april|may|june|july|august|september|october|november|december)\b",
            re.IGNORECASE,
        )

    def route_and_bind(
        self,
        candidates: List[CandidateItem],
        sections_context: List[Any],
        doc_id: str = "unknown",
    ) -> List[CandidateItem]:
        """
        Main entry point for routing and binding candidates.

        Args:
            candidates: Raw candidate items
            sections_context: Full section context for validation
            doc_id: Document ID for metrics

        Returns:
            Processed candidates with routing decisions
        """
        metrics = get_metrics_collector(doc_id)

        self.logger.info(f"PARSER_MAPPER: starting | candidates={len(candidates)}")

        processed_candidates = []

        for i, candidate in enumerate(candidates):
            # Score the triad
            triad_score = self._score_triad(candidate)
            candidate.triad_score = triad_score

            # Make routing decision
            routing_decision = self._make_routing_decision(candidate, sections_context)

            # Apply field cleaning
            cleaned_candidate = self._clean_contaminated_fields(candidate)

            # Log decision
            metrics.log_decision(
                page=1,  # Simplified for now
                block_id=f"candidate_{i}",
                rule_id="triad_binding_v1",
                scores={
                    "date_conf": triad_score.date_conf,
                    "role_conf": triad_score.role_conf,
                    "org_conf": triad_score.org_conf,
                    "assoc_score": triad_score.assoc_score,
                },
                thresholds={
                    "min_date": self.min_date_conf,
                    "min_role": self.min_role_token_conf,
                    "min_org": self.min_org_conf,
                    "min_assoc": self.min_assoc,
                },
                decision=routing_decision,
                reason=self._get_routing_reason(candidate, triad_score),
            )

            processed_candidates.append(cleaned_candidate)

        # Update metrics
        accepted_count = sum(1 for c in processed_candidates if c.status == "ok")
        if candidates:
            pass_rate = accepted_count / len(candidates)
            self.logger.info(f"PARSER_MAPPER: complete | pass_rate={pass_rate:.3f}")

        return processed_candidates

    def _score_triad(self, candidate: CandidateItem) -> TriadScore:
        """Score DATE+ROLE+ORG triad for candidate."""
        text = candidate.text

        # Date confidence
        date_conf = self._score_date_evidence(text)

        # Role confidence
        role_conf = self._score_role_evidence(text)

        # Organization confidence
        org_conf = self._score_org_evidence(text)

        # Association score (how well components link together)
        assoc_score = self._score_association(text, date_conf, role_conf, org_conf)

        return TriadScore(
            date_conf=date_conf,
            role_conf=role_conf,
            org_conf=org_conf,
            assoc_score=assoc_score,
        )

    def _score_date_evidence(self, text: str) -> float:
        """Score date evidence in text."""
        max_score = 0.0

        for pattern in self.date_patterns:
            matches = pattern.findall(text)
            if matches:
                # Score based on pattern strength and validity
                for match in matches:
                    if isinstance(match, tuple):
                        # Validate date components
                        score = self._validate_date_match(match, pattern)
                        max_score = max(max_score, score)
                    else:
                        # Simple match
                        max_score = max(max_score, 0.8)

        return min(max_score, 1.0)

    def _validate_date_match(self, match: Tuple, pattern: re.Pattern) -> float:
        """Validate and score a date match."""
        try:
            if len(match) == 3:  # DD/MM/YYYY or MM/DD/YYYY
                day_or_month, month_or_day, year = match
                day_or_month, month_or_day = int(day_or_month), int(month_or_day)
                year = int(year)

                # Validate ranges
                if year < 1950 or year > 2030:
                    return 0.3  # Weak evidence

                if day_or_month <= 12 and month_or_day <= 31:
                    return 0.9  # Strong evidence
                elif day_or_month <= 31 and month_or_day <= 12:
                    return 0.8  # Good evidence (possible format ambiguity)
                else:
                    return 0.2  # Weak evidence

            elif len(match) == 2:  # MM/YYYY
                month, year = int(match[0]), int(match[1])
                if 1 <= month <= 12 and 1950 <= year <= 2030:
                    return 0.85
                else:
                    return 0.3

            else:
                return 0.6  # Default for other patterns

        except (ValueError, IndexError):
            return 0.2

    def _score_role_evidence(self, text: str) -> float:
        """Score role/title evidence in text."""
        text_lower = text.lower()
        max_score = 0.0

        # Check for explicit role keywords
        for role in self.role_keywords:
            if role in text_lower:
                # Context scoring
                if self._has_strong_role_context(text, role):
                    max_score = max(max_score, 0.9)
                else:
                    max_score = max(max_score, 0.7)

        # Check for capitalization patterns (title case)
        if self._has_title_case_pattern(text):
            max_score = max(max_score, 0.6)

        return min(max_score, 1.0)

    def _has_strong_role_context(self, text: str, role: str) -> bool:
        """Check if role has strong contextual evidence."""
        # Look for structure indicators around the role
        role_contexts = [
            r"poste\s*:?\s*" + re.escape(role),
            r"fonction\s*:?\s*" + re.escape(role),
            r"title\s*:?\s*" + re.escape(role),
            r"position\s*:?\s*" + re.escape(role),
        ]

        for context_pattern in role_contexts:
            if re.search(context_pattern, text, re.IGNORECASE):
                return True

        return False

    def _has_title_case_pattern(self, text: str) -> bool:
        """Check for title case patterns indicating roles."""
        # Look for Title Case Words that could be roles
        title_pattern = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b")
        matches = title_pattern.findall(text)

        # Filter out common non-role words
        non_roles = {"The", "And", "Or", "But", "For", "With", "From", "To"}
        role_matches = [
            m for m in matches if m not in non_roles and len(m.split()) <= 4
        ]

        return len(role_matches) > 0

    def _score_org_evidence(self, text: str) -> float:
        """Score organization evidence with school detection."""
        # Look for organization patterns
        org_patterns = [
            r"\b[A-Z][a-zA-Z\s&]{2,30}(?:\s+(?:SARL|SAS|SASU|SA|Inc|Ltd|LLC|Corp))\b",
            r"\bchez\s+([A-Z][a-zA-Z\s&]{2,30})\b",
            r"\bat\s+([A-Z][a-zA-Z\s&]{2,30})\b",
            r"\b([A-Z][a-zA-Z\s&]{2,30})\s*(?:company|société|entreprise|group|groupe)\b",
        ]

        max_score = 0.0
        contains_school_lexeme = False

        for pattern in org_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                org_name = (
                    match if isinstance(match, str) else match[0] if match else ""
                )

                # Check for school lexemes
                if self._contains_school_lexeme(org_name):
                    contains_school_lexeme = True
                    # School organizations need higher evidence
                    max_score = max(max_score, 0.5)
                else:
                    max_score = max(max_score, 0.8)

        # Apply school organization penalty/boost
        if contains_school_lexeme:
            # Boost if there's employment evidence nearby
            if self._has_employment_evidence(text):
                max_score += self.school_org_boost
            # Otherwise, require higher threshold
            return min(max_score, 1.0)

        return min(max_score, 1.0)

    def _contains_school_lexeme(self, org_name: str) -> bool:
        """Check if organization name contains school-related terms."""
        org_lower = org_name.lower()
        return any(lexeme in org_lower for lexeme in self.school_lexemes)

    def _has_employment_evidence(self, text: str) -> bool:
        """Check for employment verification evidence."""
        text_lower = text.lower()

        # Look for employment action verbs
        for verb in self.employment_verbs:
            if verb in text_lower:
                return True

        # Look for employment context patterns
        employment_patterns = [
            r"travail\w*",
            r"emploi",
            r"mission",
            r"projet",
            r"work\w*",
            r"job",
            r"employment",
            r"project",
            r"task",
        ]

        for pattern in employment_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True

        return False

    def _score_association(
        self, text: str, date_conf: float, role_conf: float, org_conf: float
    ) -> float:
        """Score how well DATE+ROLE+ORG components associate."""
        if not (date_conf > 0 and role_conf > 0 and org_conf > 0):
            return 0.0

        # Proximity scoring - components should be near each other
        lines = text.split("\n")
        component_lines = []

        for i, line in enumerate(lines):
            line_score = 0
            if any(pattern.search(line) for pattern in self.date_patterns):
                line_score += 1
            if any(role in line.lower() for role in self.role_keywords):
                line_score += 1
            if re.search(r"\b[A-Z][a-zA-Z\s&]{2,30}\b", line):
                line_score += 1

            if line_score > 0:
                component_lines.append((i, line_score))

        if len(component_lines) < 2:
            return 0.5  # Moderate association

        # Calculate proximity score
        max_proximity = 0.0
        for i in range(len(component_lines)):
            for j in range(i + 1, len(component_lines)):
                line1, score1 = component_lines[i]
                line2, score2 = component_lines[j]

                distance = abs(line1 - line2)
                proximity = max(0, 1.0 - distance / 5.0)  # Decay over 5 lines
                weight = (score1 + score2) / 6.0  # Normalize by max possible score

                max_proximity = max(max_proximity, proximity * weight)

        return min(max_proximity, 1.0)

    def _make_routing_decision(
        self, candidate: CandidateItem, sections_context: List[Any]
    ) -> str:
        """Make routing decision based on triad scores and context."""
        triad = candidate.triad_score

        # Check minimum thresholds
        date_ok = triad.date_conf >= self.min_date_conf
        role_ok = triad.role_conf >= self.min_role_token_conf

        # Organization threshold depends on school detection
        text_lower = candidate.text.lower()
        contains_school = any(lexeme in text_lower for lexeme in self.school_lexemes)

        if contains_school:
            org_ok = triad.org_conf >= self.school_org_min
        else:
            org_ok = triad.org_conf >= self.min_org_conf

        assoc_ok = triad.assoc_score >= self.min_assoc

        # Routing logic
        if date_ok and role_ok and org_ok and assoc_ok:
            # Strong triad - accept as experience
            candidate.status = "ok"
            candidate.item_type = "experience"
            return "accepted"

        elif date_ok and role_ok and not org_ok and contains_school:
            # Date+Role but school org without employment evidence
            if not self._has_employment_evidence(candidate.text):
                candidate.status = "ok"
                candidate.item_type = "education"
                candidate.warnings.append("routed_to_education_school_context")
                return "routed_to_education"

        elif date_ok and not role_ok and not org_ok:
            # Only date evidence - uncertain
            candidate.status = "uncertain"
            candidate.warnings.append("insufficient_role_org_evidence")
            return "uncertain"

        else:
            # Insufficient evidence
            candidate.status = "rejected"
            candidate.warnings.append("insufficient_triad_evidence")
            return "rejected"

    def _clean_contaminated_fields(self, candidate: CandidateItem) -> CandidateItem:
        """Clean fields contaminated with date tokens."""
        for field_name in ["title", "company", "role", "organization"]:
            if field_name in candidate.fields:
                field_value = candidate.fields[field_name]

                if isinstance(field_value, str) and self.date_token_pattern.search(
                    field_value
                ):
                    # Move contaminated content to description
                    if "description" not in candidate.fields:
                        candidate.fields["description"] = ""

                    candidate.fields["description"] += f" {field_value}".strip()
                    candidate.fields[field_name] = "UNKNOWN"
                    candidate.warnings.append(f"date_token_in_{field_name}")

                    self.logger.warning(
                        f"FIELD_CLEANING: date token found in {field_name}, moved to description"
                    )

        return candidate

    def _get_routing_reason(self, candidate: CandidateItem, triad: TriadScore) -> str:
        """Get human-readable reason for routing decision."""
        reasons = []

        if triad.date_conf < self.min_date_conf:
            reasons.append(f"date_conf={triad.date_conf:.3f}<{self.min_date_conf}")

        if triad.role_conf < self.min_role_token_conf:
            reasons.append(
                f"role_conf={triad.role_conf:.3f}<{self.min_role_token_conf}"
            )

        if triad.org_conf < self.min_org_conf:
            reasons.append(f"org_conf={triad.org_conf:.3f}<{self.min_org_conf}")

        if triad.assoc_score < self.min_assoc:
            reasons.append(f"assoc={triad.assoc_score:.3f}<{self.min_assoc}")

        if not reasons:
            return "triad_score_above_threshold"

        return "; ".join(reasons)


# Language detection for CEFR mapping
class LanguageMapper:
    """Maps language skills to CEFR levels."""

    def __init__(self):
        self.cefr_levels = ["A1", "A2", "B1", "B2", "C1", "C2"]

        # Explicit CEFR patterns
        self.explicit_cefr = re.compile(r"\b([ABC][12])\b", re.IGNORECASE)

        # Heuristic mappings
        self.heuristic_mappings = {
            "native": ("C2", 0.95),
            "fluent": ("C1", 0.85),
            "professional": ("B2", 0.80),
            "conversational": ("B1", 0.75),
            "intermediate": ("B1", 0.70),
            "basic": ("A2", 0.75),
            "beginner": ("A1", 0.80),
            # French equivalents
            "natif": ("C2", 0.95),
            "courant": ("C1", 0.85),
            "professionnel": ("B2", 0.80),
            "intermédiaire": ("B1", 0.70),
            "débutant": ("A1", 0.80),
        }

    def map_to_cefr(self, language_text: str) -> Tuple[Optional[str], float]:
        """
        Map language text to CEFR level.

        Returns:
            Tuple of (CEFR level, confidence)
        """
        text_lower = language_text.lower()

        # Check for explicit CEFR levels
        explicit_match = self.explicit_cefr.search(language_text)
        if explicit_match:
            return explicit_match.group(1).upper(), 1.0

        # Check heuristic mappings
        for term, (level, confidence) in self.heuristic_mappings.items():
            if term in text_lower:
                return level, confidence

        return None, 0.0


# Export main classes
__all__ = ["ParserMapper", "TriadScore", "CandidateItem", "LanguageMapper"]
