"""Compatibility parser mapper exposing deterministic helpers for tests.

This module intentionally provides a lightweight implementation that mirrors
legacy behaviour expected by the enhanced extraction test-suite. It does not
attempt to replicate every optimisation from the historical monolith, but the
surface API (RoutingThresholds, RoutingDecision, ParserMapper) matches the
previous contract so other modules can keep importing from
``app.utils.parser_mapper``.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Tuple, Set


@dataclass
class RoutingThresholds:
    """Threshold configuration for routing decisions."""

    min_role_conf: float = 0.55
    min_company_conf: float = 0.55
    min_education_conf: float = 0.60
    min_skill_conf: float = 0.45
    allow_cross_column: bool = False
    bullet_indicators: Set[str] = field(default_factory=lambda: {'•', '-', '*'})

    # Legacy keyword argument aliases (kept for compatibility)
    role_confidence_min: Optional[float] = None
    company_confidence_min: Optional[float] = None
    education_confidence_min: Optional[float] = None
    skills_confidence_min: Optional[float] = None

    def __post_init__(self) -> None:
        if self.role_confidence_min is not None:
            self.min_role_conf = self.role_confidence_min
        else:
            self.role_confidence_min = self.min_role_conf

        if self.company_confidence_min is not None:
            self.min_company_conf = self.company_confidence_min
        else:
            self.company_confidence_min = self.min_company_conf

        if self.education_confidence_min is not None:
            self.min_education_conf = self.education_confidence_min
        else:
            self.education_confidence_min = self.min_education_conf

        if self.skills_confidence_min is not None:
            self.min_skill_conf = self.skills_confidence_min
        else:
            self.skills_confidence_min = self.min_skill_conf

        if not self.bullet_indicators:
            self.bullet_indicators = {'•', '-', '*'}


@dataclass
class RoutingDecision:
    """Result returned by :meth:`ParserMapper.route_content`."""

    target_section: str
    confidence: float
    routing_reasons: List[str]
    scores: Dict[str, float] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    language_detected: Optional[str] = None
    is_uncertain: bool = False


class ParserMapper:
    """Deterministic content router used by the enhanced extraction tests."""

    ROLE_KEYWORDS = {
        'en': ['engineer', 'developer', 'manager', 'director', 'consultant', 'analyst'],
        'fr': ['développeur', 'ingénieur', 'responsable', 'chef de projet'],
        'es': ['ingeniero', 'desarrollador', 'gerente'],
    }

    COMPANY_SUFFIXES = ['inc', 'corp', 'co', 'ltd', 'llc', 'gmbh', 'sa', 'sas', 'sarl']
    COMPANY_TOKENS = ['company', 'corporation', 'enterprise', 'société', 'université', 'group']

    EDUCATION_TOKENS = ['university', 'université', 'licence', 'master', 'bachelor', 'degree', 'diploma']
    SKILL_TOKENS = ['python', 'excel', 'sql', 'communication', 'leadership', 'agile']

    DATE_PATTERN = re.compile(r"\b(\d{4})\b")

    def __init__(self, thresholds: RoutingThresholds | None = None) -> None:
        self.thresholds = thresholds or RoutingThresholds()

    # ------------------------------------------------------------------
    # Confidence helpers (public for compatibility with legacy tests)
    # ------------------------------------------------------------------
    def _calculate_role_confidence(self, text: str, context: Optional[Dict[str, Any]] = None) -> float:
        text_lower = (text or '').lower()
        score = 0.0

        for keywords in self.ROLE_KEYWORDS.values():
            if any(keyword in text_lower for keyword in keywords):
                score += 0.3
                break

        if re.search(r'\b(senior|junior|lead|manager|director)\b', text_lower):
            score += 0.25

        words = text_lower.split()
        if 1 <= len(words) <= 6:
            score += 0.2

        if any(text_lower.endswith(suffix) for suffix in ('er', 'or', 'ist', 'eur')):
            score += 0.15

        return min(1.0, score)

    def _calculate_company_confidence(self, text: str, context: Optional[Dict[str, Any]] = None) -> float:
        text_lower = (text or '').lower()
        score = 0.0

        if any(suffix in text_lower for suffix in self.COMPANY_SUFFIXES):
            score += 0.4

        if any(token in text_lower for token in self.COMPANY_TOKENS):
            score += 0.3

        words = text_lower.split()
        if 1 <= len(words) <= 6:
            score += 0.2

        if any(char.isdigit() for char in text_lower):
            score += 0.1

        return min(1.0, score)

    def _calculate_education_confidence(self, text: str) -> float:
        text_lower = text.lower()
        score = 0.0
        if any(token in text_lower for token in self.EDUCATION_TOKENS):
            score += 0.6
        if 'univers' in text_lower:
            score += 0.2
        return min(1.0, score)

    def _calculate_skill_confidence(self, text: str) -> float:
        text_lower = text.lower()
        hits = sum(1 for token in self.SKILL_TOKENS if token in text_lower)
        return min(1.0, 0.3 * hits)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _detect_language(self, text: str) -> str:
        if not text:
            return 'en'
        lowered = text.lower()
        normalized = unicodedata.normalize('NFKD', text)
        accent_marks = sum(1 for ch in normalized if unicodedata.category(ch) == 'Mn')

        if any(marker in lowered for marker in ['développeur', 'ingénieur', 'chez', 'france']) or accent_marks >= 2:
            return 'fr'
        if any(marker in lowered for marker in ['empresa', 'universidad', 'ingeniero']):
            return 'es'
        if any(marker in lowered for marker in ['unternehmen', 'gmbh', 'universität']):
            return 'de'
        return 'en'

    def _extract_features(self, text: str, context: Dict[str, Any]) -> Dict[str, Any]:
        role_conf = self._calculate_role_confidence(text, context)
        company_conf = self._calculate_company_confidence(text, context)
        education_conf = self._calculate_education_confidence(text)
        skill_conf = self._calculate_skill_confidence(text)
        language = self._detect_language(text)
        has_date = bool(self.DATE_PATTERN.search(text))

        return {
            'text': text,
            'role_confidence': role_conf,
            'company_confidence': company_conf,
            'education_confidence': education_conf,
            'skill_confidence': skill_conf,
            'language_detected': language,
            'has_date': has_date,
        }

    def _calculate_routing_scores(self, features: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, float]:
        scores = {
            'experience': (
                features['role_confidence'] * 0.6
                + features['company_confidence'] * 0.3
                + (0.1 if features['has_date'] else 0.0)
            ),
            'education': features['education_confidence'],
            'skills': features['skill_confidence'],
            'languages': 0.4 if features['language_detected'] != 'en' else 0.2,
        }

        return scores

    def _generate_reason_codes(self, features: Dict[str, Any], scores: Dict[str, float], best_section: str) -> List[str]:
        reasons: List[str] = []
        if features['role_confidence'] >= self.thresholds.min_role_conf:
            reasons.append('role_match')
        if features['company_confidence'] >= self.thresholds.min_company_conf:
            reasons.append('company_match')
        if best_section == 'education' and features['education_confidence'] >= self.thresholds.min_education_conf:
            reasons.append('education_keyword')
        if best_section == 'languages' and features['language_detected'] != 'en':
            reasons.append(f"language_{features['language_detected']}")
        return reasons or ['low_signal']

    def _generate_warnings(self, confidence: float) -> List[str]:
        return ['low_confidence'] if confidence < 0.5 else []

    def _has_uncertainty_flags(self, scores: Dict[str, float]) -> bool:
        ordered = sorted(scores.values(), reverse=True)
        if len(ordered) < 2:
            return False
        return abs(ordered[0] - ordered[1]) < 0.1

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def route_content(
        self,
        content: str,
        context: Optional[Dict[str, Any]] = None,
        thresholds: Optional[RoutingThresholds] = None,
    ) -> 'RoutingDecision':
        ctx = dict(context or {})
        active_thresholds = thresholds or self.thresholds

        features = self._extract_features(content, ctx)
        scores = self._calculate_routing_scores(features, ctx)

        # Contamination guard: promote education keywords even in experience context
        section_context = ctx.get('section_context')
        if section_context == 'experience' and features['education_confidence'] >= active_thresholds.min_education_conf:
            scores['education'] = max(scores['education'], features['education_confidence'] + 0.2)

        best_section, best_score = max(scores.items(), key=lambda item: item[1])

        # Enforce minima
        if best_section == 'experience' and best_score < active_thresholds.min_role_conf:
            best_section = 'skills'
            best_score = scores['skills']

        confidence = min(1.0, best_score)
        reasons = self._generate_reason_codes(features, scores, best_section)
        warnings = self._generate_warnings(confidence)
        uncertain = self._has_uncertainty_flags(scores)

        # Contamination reason
        if section_context == 'experience' and best_section == 'education':
            reasons.append('contamination_prevented')

        decision = RoutingDecision(
            target_section=best_section,
            confidence=confidence,
            routing_reasons=reasons,
            scores=scores,
            warnings=warnings,
            language_detected=features['language_detected'],
            is_uncertain=uncertain,
        )
        return decision


# Legacy alias used by older imports
RoutingResult = RoutingDecision
RoutingThresholdsCompat = RoutingThresholds
RoutingDecisionCompat = RoutingDecision


@dataclass
class RoutingContext:
    """Lightweight routing context used to keep deterministic behaviour in tests."""

    boundaries: List[Tuple[int, int, str]]
    protected_tokens: Set[str] = field(default_factory=set)
    direction: str = "LTR"
    max_vgap_lines: int = 2

    def section_for_line(self, line_index: int) -> Optional[str]:
        for start, end, section in self.boundaries:
            if start <= line_index <= end:
                return section
        return None


class DeterministicParser:
    """Simple parser wrapper exposing helpers expected by diagnostic tests."""

    def __init__(
        self,
        *,
        mapper: Optional[ParserMapper] = None,
        context: Optional[RoutingContext] = None,
    ) -> None:
        self.mapper = mapper or ParserMapper()
        self.context = context or RoutingContext(boundaries=[])

    # ------------------------------------------------------------------
    # Public helpers mirrored from the historical parser implementation
    # ------------------------------------------------------------------
    def route_content(self, text: str, line_index: int, history: List[str]) -> Dict[str, Any]:
        """Route a line of text to the most probable section."""
        from app.utils.experience_filters import looks_like_email, looks_like_url_or_domain

        protected = False
        lowered = (text or "").lower()
        if (
            looks_like_email(text)
            or looks_like_url_or_domain(text)
            or re.search(r"\b[\w.+-]+@[\w.-]+\.[a-z]{2,}\b", lowered)
            or any(keyword in lowered for keyword in ("phone", "tel:", "contact"))
        ):
            protected = True
        if not protected and self.context.protected_tokens:
            protected = any(token.lower() in lowered for token in self.context.protected_tokens)

        if protected:
            return {
                "section": "personal_info",
                "confidence": 0.95,
                "protected": True,
                "reasons": ["protected_token"],
            }

        section_context = self.context.section_for_line(line_index)
        decision = self.mapper.route_content(
            text,
            context={
                "section_context": section_context,
                "history": history,
                "line_index": line_index,
            },
        )
        return {
            "section": decision.target_section,
            "confidence": decision.confidence,
            "protected": False,
            "reasons": decision.routing_reasons,
            "warnings": decision.warnings,
            "scores": decision.scores,
        }

    def _extract_title_company_safe(self, text: str) -> Dict[str, Any]:
        """Best effort extraction of title/company tuples with contamination guards."""
        from app.utils.experience_filters import looks_like_email, looks_like_url_or_domain, looks_like_email_localpart

        candidate = (text or "").strip()
        if not candidate:
            return {"valid": False}

        separators = ["@", "-", " - ", "|", "•", "–"]
        title: Optional[str] = None
        company: Optional[str] = None

        for separator in separators:
            if separator in candidate:
                parts = [part.strip(" -–|").strip() for part in candidate.split(separator, 1)]
                if len(parts) == 2:
                    title, company = parts
                    break

        if title is None or company is None:
            return {"valid": False}

        if (
            looks_like_email(title)
            or looks_like_email(company)
            or looks_like_url_or_domain(company)
            or looks_like_email_localpart(title)
        ):
            return {"valid": False}

        if len(title) < 3 or len(company) < 3:
            return {"valid": False}

        return {
            "valid": True,
            "title": title,
            "company": company,
        }

    def _detect_section_header(self, text: str) -> Dict[str, Any]:
        """Detect multilingual section headers."""
        normalized = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii")
        lowered = normalized.lower()

        section_map = {
            "experience": "experiences",
            "experiences": "experiences",
            "work experience": "experiences",
            "experience professionnelle": "experiences",
            "experience professionnelle": "experiences",
            "expérience professionnelle": "experiences",
            "experiencia": "experiences",
            "experiencia profesional": "experiences",
            "experience professionnelle": "experiences",
            "formation": "education",
            "education": "education",
            "educacion": "education",
            "formacion": "education",
            "compétences": "skills",
            "competences": "skills",
            "skills": "skills",
            "habilidades": "skills",
            "languages": "languages",
            "langues": "languages",
            "idiomas": "languages",
        }

        matched_section = None
        for key, section in section_map.items():
            if key in lowered:
                matched_section = section
                break

        return {
            "detected": matched_section is not None,
            "section": matched_section,
            "header": text,
        }


def create_parser(
    *,
    boundaries: Optional[List[Tuple[int, int, str]]] = None,
    protected_tokens: Optional[Set[str]] = None,
    direction: str = "LTR",
    max_vgap_lines: int = 2,
) -> DeterministicParser:
    """Factory mirroring the historical deterministic parser helper."""
    context = RoutingContext(
        boundaries=list(boundaries or []),
        protected_tokens=set(protected_tokens or set()),
        direction=direction,
        max_vgap_lines=max_vgap_lines,
    )
    return DeterministicParser(context=context)
