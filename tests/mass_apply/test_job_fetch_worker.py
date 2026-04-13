from __future__ import annotations

from types import SimpleNamespace

from app.utils.job_sources.base import JobSearchQuery
from app.utils.mass_apply.geography_normalization import normalize_geography_queries
from app.utils.mass_apply.keyword_search import normalize_keyword_queries
from app.workers.job_fetch_worker import JobFetchWorker, _row_to_dict


def test_build_query_variants_crosses_keywords_locations_and_levels() -> None:
    worker = JobFetchWorker.__new__(JobFetchWorker)
    worker._query = JobSearchQuery(
        keywords="",
        location="",
        experience_level=None,
        max_results=48,
    )
    worker._keyword_queries = ["data engineer", "ml engineer"]
    worker._location_queries = ["Paris", "London"]
    worker._experience_levels = ["mid", "senior"]

    variants = worker._build_query_variants()

    assert variants[0].keywords == "data engineer"
    assert variants[-1].keywords == "ml engineer"
    assert len(variants) == 8
    assert all(variant.max_results == 6 for variant in variants)


def test_row_to_dict_prefers_runtime_urls_for_navigation() -> None:
    row = SimpleNamespace(
        id=1,
        profile_id=3,
        dedup_key="abc",
        source_name="greenhouse",
        source_tier="api_public",
        job_title="Platform Engineer",
        company="Example",
        location="Paris",
        remote_type="hybrid",
        job_type="full_time",
        salary_min=60000,
        salary_max=80000,
        salary_currency="EUR",
        experience_level="senior",
        tags=["python"],
        source_url="https://boards.greenhouse.io/example/jobs/123",
        apply_url="https://boards.greenhouse.io/example/jobs/123",
        runtime_source_url="https://boards.greenhouse.io/example/jobs/123?gh_jid=123",
        runtime_apply_url="https://boards.greenhouse.io/example/jobs/123?gh_jid=123#apply",
        match_score=0.82,
        scan_date=None,
    )

    payload = _row_to_dict(row)

    assert payload["source_url"] == row.runtime_source_url
    assert payload["apply_url"] == row.runtime_apply_url


def test_source_keyword_queries_for_global_feed_prefer_base_queries() -> None:
    geography = normalize_geography_queries(["France", "Japan"])
    profile = SimpleNamespace(
        learned_preferences={"target_roles": ["Machine Learning Engineer"]},
        extracted_skills=[{"skill": "Python"}],
        extracted_soft_skills=[],
        extracted_experiences=[],
    )
    worker = JobFetchWorker.__new__(JobFetchWorker)
    worker._query = JobSearchQuery(keywords="", location="", max_results=50)
    worker._keyword_queries = normalize_keyword_queries(
        [],
        profile=profile,
        geography_expansions=geography.expansions,
    )

    remoteok_queries = worker._source_keyword_queries(SimpleNamespace(name="remoteok"))
    adzuna_queries = worker._source_keyword_queries(SimpleNamespace(name="adzuna"))

    assert any("Machine Learning Engineer" in query for query in remoteok_queries)
    assert not any("Ingenieur machine learning" in query for query in remoteok_queries)
    assert any("Ingenieur machine learning" in query for query in adzuna_queries)
