"""Skills and languages mapping helpers."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List

from ...config import DEFAULT_PII_CONFIG
from ...logging.safe_logger import get_safe_logger
from .base_mapper import format_label, load_mapping_rules


class SkillsMapper:
    """Encapsulates skill, language, and engagement mapping rules."""

    def __init__(self) -> None:
        self.logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)

        category_rules = load_mapping_rules("skill_categories.json").get(
            "categories", {}
        )
        self.default_category = format_label(
            category_rules.get("other"), fallback="❔ Autres"
        )
        self.category_patterns: List[tuple[List[re.Pattern[str]], str]] = []
        for entry in category_rules.values():
            patterns = entry.get("patterns", [])
            if not patterns:
                continue
            label = format_label(entry, fallback=self.default_category)
            compiled = [re.compile(pattern, re.IGNORECASE) for pattern in patterns]
            self.category_patterns.append((compiled, label))

        levels_rules = load_mapping_rules("skill_levels.json")
        self.default_level = format_label(
            levels_rules.get("default"), fallback="🟡 Intermédiaire"
        )
        level_entries = []
        for entry in levels_rules.get("levels", {}).values():
            patterns = entry.get("patterns", [])
            compiled = [re.compile(pattern, re.IGNORECASE) for pattern in patterns]
            priority = entry.get("priority", 0)
            label = format_label(entry, fallback=self.default_level)
            level_entries.append((priority, compiled, label))
        self.level_patterns: List[tuple[int, List[re.Pattern[str]], str]] = sorted(
            level_entries, key=lambda item: item[0], reverse=True
        )

        engagement_rules = load_mapping_rules("engagement_levels.json")
        self.default_engagement = format_label(
            engagement_rules.get("default"), fallback="🤝 Intéressé"
        )
        self.engagement_patterns: List[tuple[List[re.Pattern[str]], str]] = []
        for entry in engagement_rules.get("levels", {}).values():
            patterns = entry.get("patterns", [])
            compiled = [re.compile(pattern, re.IGNORECASE) for pattern in patterns]
            label = format_label(entry, fallback=self.default_engagement)
            self.engagement_patterns.append((compiled, label))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def map_skills(self, skills_data: Any) -> List[Dict[str, Any]]:
        """Normalize skills provided as list or legacy dict format."""
        data_type = type(skills_data).__name__
        self.logger.debug("SKILLS_MAPPER: input type=%s", data_type)

        if isinstance(skills_data, list):
            mapped = [self.map_single_skill(item) for item in skills_data]
            self.logger.info("SKILLS_MAPPER: list → %s items", len(mapped))
            return mapped

        if isinstance(skills_data, dict):
            mapped_skills: List[Dict[str, Any]] = []
            for category, values in skills_data.items():
                values_iterable: Iterable[Any]
                if isinstance(values, list):
                    values_iterable = values
                else:
                    values_iterable = [values]
                for value in values_iterable:
                    mapped_skill = self.map_single_skill(value)
                    if not mapped_skill.get("category"):
                        mapped_skill["category"] = self.map_skill_category(
                            mapped_skill.get("name", "")
                        )
                    mapped_skills.append(mapped_skill)
            self.logger.info("SKILLS_MAPPER: dict → %s items", len(mapped_skills))
            return mapped_skills

        self.logger.warning("SKILLS_MAPPER: unsupported input type %s", data_type)
        return []

    def map_single_skill(self, skill_data: Any) -> Dict[str, Any]:
        """Normalize a single skill entry."""
        if isinstance(skill_data, str):
            skill_data = {"name": skill_data}

        mapped: Dict[str, Any] = dict(skill_data)
        name = mapped.get("name", "")
        mapped["name"] = name

        if not mapped.get("category"):
            mapped["category"] = self.map_skill_category(name)

        if not mapped.get("level"):
            context = f"{mapped.get('description', '')} {name}".strip()
            mapped["level"] = self.map_skill_level(context)

        mapped.setdefault("description", "")
        mapped.setdefault("years_experience", 0)
        return mapped

    def map_skill_category(self, skill_name: str) -> str:
        lower = (skill_name or "").lower()
        for patterns, label in self.category_patterns:
            if any(pattern.search(lower) for pattern in patterns):
                return label
        return self.default_category

    def map_skill_level(self, context: str) -> str:
        lower = (context or "").lower()
        for _, patterns, label in self.level_patterns:
            if any(pattern.search(lower) for pattern in patterns):
                return label
        return self.default_level

    def map_engagement(self, interest_name: str) -> str:
        lower = (interest_name or "").lower()
        for patterns, label in self.engagement_patterns:
            if any(pattern.search(lower) for pattern in patterns):
                return label
        return self.default_engagement


__all__ = ["SkillsMapper"]
