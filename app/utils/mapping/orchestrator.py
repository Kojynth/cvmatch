"""Mapping orchestrator coordinating modular mappers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Iterable, List

if TYPE_CHECKING:  # pragma: no cover
    from ..extraction_mapper import ExtractionMapper


def _as_list(value: Any) -> List[Any]:
    """Ensure values are wrapped in a list for uniform processing."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _dedup_list_preserve_one(items: Iterable[Any], norm_fn, logger=None) -> List[Any]:
    """Deduplicate entries while preserving the first item for each normalized key."""
    seen = set()
    result: List[Any] = []
    skipped_empty = 0

    for item in items or []:
        key = norm_fn(item) if norm_fn else str(item).strip().lower()
        if not key:
            skipped_empty += 1
            continue
        if key in seen:
            continue
        seen.add(key)
        result.append(item)

    if skipped_empty and logger:
        logger.info("DEDUP: skipped %s items with empty normalized keys", skipped_empty)

    return result


def _canon_lang(name: str) -> str:
    """Canonicalise language names to a consistent label."""
    canon_map = {
        "english": "Anglais",
        "en": "Anglais",
        "anglais": "Anglais",
        "french": "Français",
        "fr": "Français",
        "français": "Français",
        "francais": "Français",
        "spanish": "Espagnol",
        "es": "Espagnol",
        "espagnol": "Espagnol",
        "german": "Allemand",
        "de": "Allemand",
        "deutsch": "Allemand",
        "allemand": "Allemand",
        "italian": "Italien",
        "it": "Italien",
        "italien": "Italien",
        "italiano": "Italien",
        "portuguese": "Portugais",
        "pt": "Portugais",
        "portugais": "Portugais",
        "chinese": "Chinois",
        "zh": "Chinois",
        "chinois": "Chinois",
        "mandarin": "Chinois",
        "japanese": "Japonais",
        "ja": "Japonais",
        "japonais": "Japonais",
        "korean": "Coréen",
        "ko": "Coréen",
        "coréen": "Coréen",
    }
    lower = (name or "").lower()
    return canon_map.get(lower, (name or "").capitalize())


def _dedup_languages(raw_languages: Iterable[Any], logger=None) -> List[Dict[str, Any]]:
    """Deduplicate languages keeping the richest entry per canonical name."""
    raw_list = list(raw_languages or [])
    if not raw_list:
        return []

    cefr_order = {"A1": 1, "A2": 2, "B1": 3, "B2": 4, "C1": 5, "C2": 6}
    level_priorities = {
        "official": 4,
        "mapped": 3,
        "inferred": 2,
        "default": 1,
    }

    lang_groups: Dict[str, List[Dict[str, Any]]] = {}
    for lang_item in raw_list:
        if not lang_item:
            continue
        if isinstance(lang_item, dict):
            name = lang_item.get("name", "")
            level = lang_item.get("level", "")
            level_source = lang_item.get("level_source", "default")
            confidence = getattr(lang_item, "_confidence_score", 0)
        else:
            parts = str(lang_item).strip().split()
            name = parts[0] if parts else ""
            level = parts[1] if len(parts) > 1 else ""
            level_source = "default"
            confidence = 0
            lang_item = {"name": name, "level": level, "level_source": level_source}
        if not name:
            continue
        canonical = _canon_lang(name)
        lang_groups.setdefault(canonical, []).append(
            {
                "item": lang_item,
                "level": level,
                "level_source": level_source,
                "confidence": confidence,
            }
        )

    output: List[Dict[str, Any]] = []
    for canonical, entries in lang_groups.items():
        if len(entries) == 1:
            entry = entries[0]
            base = (
                entry["item"]
                if isinstance(entry["item"], dict)
                else {"name": canonical}
            )
            result = dict(base)
            result.setdefault("name", canonical)
            result.setdefault("level", entry.get("level", ""))
            result.setdefault("level_source", entry.get("level_source", "default"))
            output.append(result)
            continue

        def _priority(entry: Dict[str, Any]) -> int:
            source = entry.get("level_source", "default")
            return level_priorities.get(source, 0)

        best_entry = max(entries, key=_priority)
        removed = [e for e in entries if e is not best_entry]
        if logger:
            for rem in removed:
                logger.info(
                    "LANG_DEDUP_OVERRIDE: %s %s(%s) overridden by %s(%s)",
                    canonical,
                    rem.get("level", ""),
                    rem.get("level_source", "default"),
                    best_entry.get("level", ""),
                    best_entry.get("level_source", "default"),
                )

        base = (
            best_entry["item"]
            if isinstance(best_entry["item"], dict)
            else {"name": canonical}
        )
        result = dict(base)
        result.setdefault("name", canonical)
        result.setdefault("level", best_entry.get("level", ""))
        result.setdefault("level_source", best_entry.get("level_source", "default"))
        output.append(result)

    duplicates_removed = len(raw_list) - len(output)
    if logger:
        logger.info(
            "LANG: summary | total=%s duplicates_removed=%s unique_languages=%s",
            len(raw_list),
            duplicates_removed,
            len(output),
        )

    return output


class MappingOrchestrator:
    """Coordinate section mapping using modular helpers."""

    def __init__(self, mapper: "ExtractionMapper", logger) -> None:
        self.mapper = mapper
        self.logger = logger
        self.list_sections = [
            "experiences",
            "education",
            "skills",
            "soft_skills",
            "languages",
            "projects",
            "certifications",
            "publications",
            "volunteering",
            "interests",
            "awards",
            "references",
        ]

    def apply(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Run the extraction mapping pipeline on raw data."""
        self.logger.info("MAP: start_robust")
        out: Dict[str, Any] = {}

        personal_info = data.get("personal_info")
        out["personal_info"] = personal_info if isinstance(personal_info, dict) else {}
        self.logger.info("MAP: personal_info | fields=%s", len(out["personal_info"]))

        normalized_inputs = {key: _as_list(data.get(key)) for key in self.list_sections}
        input_counts = {key: len(values) for key, values in normalized_inputs.items()}
        self.logger.info(
            "MAP: input_counts | %s",
            " ".join(
                f"{key}={count}" for key, count in input_counts.items() if count > 0
            ),
        )

        experiences = normalized_inputs["experiences"]
        if experiences:
            self.logger.info(
                "MAP: experiences_robust_start | %s items", len(experiences)
            )
            mapped_experiences, errors = self.mapper.experience_mapper.map_experiences(
                experiences
            )
            out["experiences"] = mapped_experiences
            self.logger.info(
                "MAP: experiences_robust_done | %s mapped, %s errors",
                len(mapped_experiences),
                errors,
            )
        else:
            out["experiences"] = []

        education = normalized_inputs["education"]
        if education:
            self.logger.info("MAP: education_robust_start | %s items", len(education))
            mapped_education, errors = self.mapper.experience_mapper.map_education(
                education
            )
            out["education"] = mapped_education
            self.logger.info(
                "MAP: education_robust_done | %s mapped, %s errors",
                len(mapped_education),
                errors,
            )
        else:
            out["education"] = []

        raw_skills = normalized_inputs["skills"]
        if raw_skills:
            self.logger.info("MAP: raw_skills_sample | %s", raw_skills[:3])

        def _skills_norm(value: Any) -> str:
            if isinstance(value, dict):
                if "category" in value:
                    return str(value.get("category", "")).strip().lower()
                return str(value.get("name", "")).strip().lower()
            return str(value).strip().lower()

        out["skills"] = _dedup_list_preserve_one(
            raw_skills, norm_fn=_skills_norm, logger=self.logger
        )
        if len(raw_skills) != len(out["skills"]):
            self.logger.info(
                "MAP: skills_dedup | %s → %s (removed %s duplicates)",
                len(raw_skills),
                len(out["skills"]),
                len(raw_skills) - len(out["skills"]),
            )
        else:
            self.logger.info(
                "MAP: skills | %s items (no duplicates)", len(out["skills"])
            )

        raw_soft_skills = normalized_inputs["soft_skills"]
        out["soft_skills"] = _dedup_list_preserve_one(
            raw_soft_skills,
            norm_fn=lambda value: str(
                value.get("name", "") if isinstance(value, dict) else value
            )
            .strip()
            .lower(),
            logger=self.logger,
        )
        if len(raw_soft_skills) != len(out["soft_skills"]):
            self.logger.info(
                "MAP: soft_skills_dedup | %s → %s (removed %s duplicates)",
                len(raw_soft_skills),
                len(out["soft_skills"]),
                len(raw_soft_skills) - len(out["soft_skills"]),
            )
        else:
            self.logger.info(
                "MAP: soft_skills | %s items (no duplicates)", len(out["soft_skills"])
            )

        out["languages"] = _dedup_languages(
            normalized_inputs["languages"], logger=self.logger
        )

        passthrough_sections = [
            "projects",
            "certifications",
            "publications",
            "volunteering",
            "interests",
            "awards",
            "references",
        ]
        for section in passthrough_sections:
            raw_items = normalized_inputs[section]
            filtered_items = [item for item in raw_items if item]
            out[section] = filtered_items
            if len(raw_items) != len(filtered_items):
                self.logger.info(
                    "MAP: %s_filter | %s → %s (removed %s empty items)",
                    section,
                    len(raw_items),
                    len(filtered_items),
                    len(raw_items) - len(filtered_items),
                )
            elif filtered_items:
                self.logger.info(
                    "MAP: %s | %s items (no filtering needed)",
                    section,
                    len(filtered_items),
                )

        self.logger.info("MAP: starting_post_mapping_qa")
        out = self.mapper.qa_engine.apply_post_mapping_qa(out, data)

        output_counts = {
            section: len(out.get(section, [])) for section in self.list_sections
        }
        total_items = sum(output_counts.values()) + (1 if out["personal_info"] else 0)
        summary = " ".join(f"{k}={v}" for k, v in output_counts.items() if v > 0)
        self.logger.info(
            "MAP: output_summary_robust | total_items=%s %s", total_items, summary
        )
        self.logger.info("MAP: done_robust")
        return out


__all__ = ["MappingOrchestrator"]
