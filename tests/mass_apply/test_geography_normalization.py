from __future__ import annotations

from app.utils.mass_apply.geography_normalization import (
    build_location_queries_for_source,
    format_geography_expansion_preview,
    normalize_geography_queries,
)


def test_normalize_geography_queries_expands_country_and_aliases() -> None:
    plan = normalize_geography_queries(["France", "Suisse", "USA"])

    assert plan.normalized_inputs == ["France", "Switzerland", "United States"]
    assert "Paris" in plan.search_queries
    assert "Suisse" in plan.search_queries
    assert "United States" in plan.search_queries
    assert plan.has_expansion is True


def test_build_location_queries_for_source_is_source_aware() -> None:
    plan = normalize_geography_queries(["France", "Japan", "UE"])

    adzuna_queries = build_location_queries_for_source(plan.expansions, "adzuna")
    remoteok_queries = build_location_queries_for_source(plan.expansions, "remoteok")

    assert "France" in adzuna_queries
    assert "Tokyo" in adzuna_queries
    assert remoteok_queries == []


def test_format_geography_expansion_preview_renders_details() -> None:
    preview = format_geography_expansion_preview(
        normalize_geography_queries(["France"]),
        max_targets=1,
    )

    assert "France" in preview
    assert "Paris" in preview
    assert "Total variantes geographiques" in preview
