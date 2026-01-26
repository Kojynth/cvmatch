"""
Internship Rebind Handler
========================

Intelligent rebinding of internship experiences from school organizations
to actual employer organizations when context allows.
"""

import re
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import logging

from ..utils.log_safety import create_safe_logger_wrapper
from ..metrics.instrumentation import get_metrics_collector
from ..extraction.parser_mapper import CandidateItem


@dataclass
class InternshipCandidate:
    """Candidate internship for rebinding analysis."""

    item: CandidateItem
    original_org: str
    potential_employers: List[
        Tuple[str, float, int]
    ]  # (org_name, confidence, line_distance)
    rebind_decision: str = "pending"  # pending, rebind, route_to_education
    rebind_target: Optional[str] = None
    rebind_confidence: float = 0.0


class InternshipHandler:
    """Handles internship detection and employer rebinding."""

    def __init__(
        self,
        proximity_max_lines: int = 2,
        proximity_max_pixels: int = 150,
        min_rebind_confidence: float = 0.60,
        school_penalty_cap: float = 0.3,
        debug_mode: bool = False,
    ):
        self.proximity_max_lines = proximity_max_lines
        self.proximity_max_pixels = proximity_max_pixels
        self.min_rebind_confidence = min_rebind_confidence
        self.school_penalty_cap = school_penalty_cap
        self.debug_mode = debug_mode

        # Logger
        base_logger = logging.getLogger(__name__)
        self.logger = create_safe_logger_wrapper(base_logger)

        # Compile patterns
        self._compile_patterns()

    def _compile_patterns(self):
        """Compile regex patterns for internship and organization detection."""

        # Internship role patterns (multilingual)
        self.internship_patterns = [
            # French
            r"\bstage\b",
            r"\bstagiaire\b",
            r"\balternant\b",
            r"\balternance\b",
            r"\bapprentissage\b",
            r"\bapprenti\b",
            r"\bcontrat pro\b",
            # English
            r"\bintern\b",
            r"\binternship\b",
            r"\btrainee\b",
            r"\bwork study\b",
            r"\bcoop\b",
            r"\bco-op\b",
            r"\bplacement\b",
            # General patterns
            r"\bwork.integrated.learning\b",
            r"\bstudent.worker\b",
        ]

        # School lexemes (from parser_mapper)
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
            "formation",
        ]

        # Organization patterns for rebind candidates
        self.org_patterns = [
            # Company with legal suffix
            r"\b([A-Z][a-zA-Z\s&]{2,40})\s+(?:SARL|SAS|SASU|SA|Inc|Ltd|LLC|Corp|Group|Groupe)\b",
            # "chez/at" patterns
            r"\b(?:chez|at|pour|with|dans|in)\s+([A-Z][a-zA-Z\s&]{2,30})\b",
            # Company followed by industry indicator
            r"\b([A-Z][a-zA-Z\s&]{2,30})\s*(?:company|société|entreprise|firm|corporation)\b",
            # Department/division indicators
            r"\b(?:department|service|division|équipe)\s+([A-Z][a-zA-Z\s&]{2,30})\b",
            # Simple capitalized entities (more permissive for internships)
            r"\b([A-Z][a-zA-Z]{2,}(?:\s+[A-Z][a-zA-Z]{2,}){1,3})\b",
        ]

        # Compile all patterns
        self.internship_regex = [
            re.compile(pattern, re.IGNORECASE) for pattern in self.internship_patterns
        ]
        self.org_regex = [
            re.compile(pattern, re.IGNORECASE) for pattern in self.org_patterns
        ]

    def rebind_internships(
        self,
        candidates: List[CandidateItem],
        context_sections: List[Any],
        doc_id: str = "unknown",
    ) -> List[CandidateItem]:
        """
        Main entry point for internship rebinding.

        Args:
            candidates: Candidate items to analyze
            context_sections: Full section context for proximity analysis
            doc_id: Document ID for metrics

        Returns:
            Updated candidates with rebinding applied
        """
        metrics = get_metrics_collector(doc_id)

        self.logger.info(f"INTERNSHIP_HANDLER: starting | candidates={len(candidates)}")

        # Step 1: Identify internship candidates
        internship_candidates = self._identify_internship_candidates(candidates)

        self.logger.info(
            f"INTERNSHIP_HANDLER: identified {len(internship_candidates)} internship candidates"
        )

        # Step 2: Find potential employer organizations for each
        candidates_with_employers = self._find_potential_employers(
            internship_candidates, context_sections
        )

        # Step 3: Make rebinding decisions
        rebind_decisions = self._make_rebinding_decisions(candidates_with_employers)

        # Step 4: Apply rebinding and update candidates
        updated_candidates = self._apply_rebinding(candidates, rebind_decisions, doc_id)

        # Log metrics
        rebind_count = sum(
            1 for decision in rebind_decisions if decision.rebind_decision == "rebind"
        )
        route_to_edu_count = sum(
            1
            for decision in rebind_decisions
            if decision.rebind_decision == "route_to_education"
        )

        if rebind_decisions:
            success_rate = rebind_count / len(rebind_decisions)
            self.logger.info(
                f"INTERNSHIP_HANDLER: complete | "
                f"rebind_success={rebind_count} route_to_edu={route_to_edu_count} "
                f"success_rate={success_rate:.3f}"
            )

            # Log routing decisions for metrics
            if rebind_count > 0:
                metrics.log_routing_decision(
                    "experience",
                    "experience_rebind",
                    "internship_employer_rebind",
                    rebind_count,
                )
            if route_to_edu_count > 0:
                metrics.log_routing_decision(
                    "experience",
                    "education",
                    "internship_academic_context",
                    route_to_edu_count,
                )

        return updated_candidates

    def _identify_internship_candidates(
        self, candidates: List[CandidateItem]
    ) -> List[InternshipCandidate]:
        """Identify candidates that appear to be internships."""
        internship_candidates = []

        for candidate in candidates:
            if self._is_internship_candidate(candidate):
                # Extract current organization
                current_org = self._extract_current_organization(candidate)

                internship_candidates.append(
                    InternshipCandidate(
                        item=candidate, original_org=current_org, potential_employers=[]
                    )
                )

        return internship_candidates

    def _is_internship_candidate(self, candidate: CandidateItem) -> bool:
        """Check if candidate appears to be an internship."""
        text = candidate.text.lower()

        # Check for internship role keywords
        for pattern in self.internship_regex:
            if pattern.search(text):
                # Additional validation: check if organization contains school lexeme
                if self._contains_school_lexeme(candidate.text):
                    return True

                # Or if explicitly tagged as internship
                if (
                    "internship" in candidate.item_type.lower()
                    or "stage" in candidate.item_type.lower()
                ):
                    return True

        return False

    def _contains_school_lexeme(self, text: str) -> bool:
        """Check if text contains school-related terms."""
        text_lower = text.lower()
        return any(lexeme in text_lower for lexeme in self.school_lexemes)

    def _extract_current_organization(self, candidate: CandidateItem) -> str:
        """Extract current organization from candidate."""
        # Try to get from structured fields first
        if "organization" in candidate.fields:
            return candidate.fields["organization"]
        elif "company" in candidate.fields:
            return candidate.fields["company"]

        # Fallback to text extraction
        text = candidate.text

        for pattern in self.org_regex:
            matches = pattern.findall(text)
            if matches:
                # Return first substantial match
                for match in matches:
                    org_name = (
                        match if isinstance(match, str) else match[0] if match else ""
                    )
                    if len(org_name.strip()) >= 3:
                        return org_name.strip()

        return "UNKNOWN"

    def _find_potential_employers(
        self,
        internship_candidates: List[InternshipCandidate],
        context_sections: List[Any],
    ) -> List[InternshipCandidate]:
        """Find potential employer organizations near each internship."""

        for candidate in internship_candidates:
            # Find the section containing this internship
            source_section = self._find_source_section(candidate.item, context_sections)

            if source_section:
                # Look for nearby organizations
                potential_employers = self._scan_for_nearby_organizations(
                    candidate.item, source_section, context_sections
                )

                candidate.potential_employers = potential_employers

        return internship_candidates

    def _find_source_section(
        self, item: CandidateItem, sections: List[Any]
    ) -> Optional[Any]:
        """Find the section that contains this item."""
        item_text = item.text

        for section in sections:
            if hasattr(section, "text") and section.text:
                # Simple containment check
                if item_text.strip() in section.text or any(
                    line.strip() in section.text
                    for line in item_text.split("\n")
                    if line.strip()
                ):
                    return section

        return None

    def _scan_for_nearby_organizations(
        self, item: CandidateItem, source_section: Any, all_sections: List[Any]
    ) -> List[Tuple[str, float, int]]:
        """Scan for organizations near the internship item."""
        potential_employers = []

        # Get lines from source section
        if hasattr(source_section, "text") and source_section.text:
            lines = source_section.text.split("\n")

            # Find item position
            item_line_idx = self._find_item_line_index(item, lines)

            if item_line_idx >= 0:
                # Scan nearby lines
                scan_start = max(0, item_line_idx - self.proximity_max_lines)
                scan_end = min(len(lines), item_line_idx + self.proximity_max_lines + 1)

                for line_idx in range(scan_start, scan_end):
                    if line_idx != item_line_idx:  # Skip the item line itself
                        line = lines[line_idx]
                        orgs_in_line = self._extract_organizations_from_line(line)

                        for org_name, confidence in orgs_in_line:
                            # Filter out school organizations
                            if not self._contains_school_lexeme(org_name):
                                line_distance = abs(line_idx - item_line_idx)
                                potential_employers.append(
                                    (org_name, confidence, line_distance)
                                )

        # Sort by confidence and proximity
        potential_employers.sort(key=lambda x: (-x[1], x[2]))

        return potential_employers[:5]  # Limit to top 5 candidates

    def _find_item_line_index(self, item: CandidateItem, lines: List[str]) -> int:
        """Find the line index where the item appears."""
        item_text = item.text.strip()

        # Try exact match first
        for i, line in enumerate(lines):
            if item_text in line.strip():
                return i

        # Try partial matches (first line of item)
        first_line = item_text.split("\n")[0].strip()
        for i, line in enumerate(lines):
            if first_line in line.strip() or line.strip() in first_line:
                return i

        return -1  # Not found

    def _extract_organizations_from_line(self, line: str) -> List[Tuple[str, float]]:
        """Extract organizations from a single line with confidence scores."""
        organizations = []

        for pattern in self.org_regex:
            matches = pattern.findall(line)
            for match in matches:
                org_name = (
                    match if isinstance(match, str) else match[0] if match else ""
                )
                org_name = org_name.strip()

                if len(org_name) >= 3:
                    # Calculate confidence based on pattern strength and text features
                    confidence = self._calculate_org_confidence(org_name, line, pattern)
                    organizations.append((org_name, confidence))

        # Remove duplicates and return top candidates
        unique_orgs = {}
        for org_name, conf in organizations:
            if org_name not in unique_orgs or conf > unique_orgs[org_name]:
                unique_orgs[org_name] = conf

        return [(name, conf) for name, conf in unique_orgs.items()]

    def _calculate_org_confidence(
        self, org_name: str, line: str, pattern: re.Pattern
    ) -> float:
        """Calculate confidence score for organization match."""
        base_confidence = 0.6

        # Boost for legal entity suffixes
        legal_suffixes = [
            "SARL",
            "SAS",
            "SASU",
            "SA",
            "Inc",
            "Ltd",
            "LLC",
            "Corp",
            "Group",
            "Groupe",
        ]
        if any(suffix in org_name for suffix in legal_suffixes):
            base_confidence += 0.2

        # Boost for context indicators
        context_indicators = [
            "company",
            "société",
            "entreprise",
            "firm",
            "corporation",
            "chez",
            "at",
        ]
        if any(indicator in line.lower() for indicator in context_indicators):
            base_confidence += 0.15

        # Penalty for very short names
        if len(org_name) < 5:
            base_confidence -= 0.1

        # Penalty for all lowercase (less likely to be organization)
        if org_name.islower():
            base_confidence -= 0.15

        return max(0.0, min(1.0, base_confidence))

    def _make_rebinding_decisions(
        self, candidates: List[InternshipCandidate]
    ) -> List[InternshipCandidate]:
        """Make rebinding decisions for each internship candidate."""

        for candidate in candidates:
            if candidate.potential_employers:
                # Get best employer candidate
                best_employer = candidate.potential_employers[0]
                org_name, confidence, line_distance = best_employer

                if confidence >= self.min_rebind_confidence:
                    # Rebind to this employer
                    candidate.rebind_decision = "rebind"
                    candidate.rebind_target = org_name
                    candidate.rebind_confidence = confidence

                    self.logger.info(
                        f"INTERNSHIP_REBIND: rebinding | "
                        f"from='{candidate.original_org}' to='{org_name}' "
                        f"confidence={confidence:.3f}"
                    )
                else:
                    # Route to education
                    candidate.rebind_decision = "route_to_education"
                    self.logger.info(
                        f"INTERNSHIP_ROUTE: routing to education | "
                        f"org='{candidate.original_org}' "
                        f"best_employer_conf={confidence:.3f}"
                    )
            else:
                # No potential employers found - route to education
                candidate.rebind_decision = "route_to_education"
                self.logger.info(
                    f"INTERNSHIP_ROUTE: no employers found | "
                    f"org='{candidate.original_org}'"
                )

        return candidates

    def _apply_rebinding(
        self,
        original_candidates: List[CandidateItem],
        rebind_decisions: List[InternshipCandidate],
        doc_id: str,
    ) -> List[CandidateItem]:
        """Apply rebinding decisions to the original candidate list."""

        # Create mapping of items to decisions
        decision_map = {id(decision.item): decision for decision in rebind_decisions}

        updated_candidates = []

        for candidate in original_candidates:
            candidate_id = id(candidate)

            if candidate_id in decision_map:
                decision = decision_map[candidate_id]

                if decision.rebind_decision == "rebind":
                    # Update organization field
                    candidate.fields["organization"] = decision.rebind_target
                    candidate.fields["company"] = decision.rebind_target

                    # Update item type to indicate rebinding
                    candidate.item_type = "experience"
                    candidate.status = "ok"
                    candidate.warnings.append(
                        f"internship_rebind_to_{decision.rebind_target}"
                    )

                    # Log success
                    self.logger.debug(
                        f"REBIND_APPLIED: {decision.original_org} → {decision.rebind_target}"
                    )

                elif decision.rebind_decision == "route_to_education":
                    # Route to education
                    candidate.item_type = "education"
                    candidate.status = "ok"
                    candidate.warnings.append("internship_routed_to_education")

                    # Add work-integrated learning tag
                    if "tags" not in candidate.fields:
                        candidate.fields["tags"] = []
                    candidate.fields["tags"].append("work_integrated_learning")

            updated_candidates.append(candidate)

        return updated_candidates


# Convenience function for integration
def rebind_internships(
    candidates: List[CandidateItem],
    context_sections: List[Any],
    doc_id: str = "unknown",
    **kwargs,
) -> List[CandidateItem]:
    """
    Convenience function for internship rebinding.

    Args:
        candidates: Candidate items
        context_sections: Section context
        doc_id: Document ID
        **kwargs: Additional parameters for InternshipHandler

    Returns:
        Updated candidates with rebinding applied
    """
    handler = InternshipHandler(**kwargs)
    return handler.rebind_internships(candidates, context_sections, doc_id)


# Export main classes and functions
__all__ = ["InternshipHandler", "InternshipCandidate", "rebind_internships"]
