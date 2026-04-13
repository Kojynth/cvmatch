from __future__ import annotations

from datetime import date as real_date
from types import SimpleNamespace

from app.utils.mass_apply.offer_qualification import (
    _estimate_years_experience,
    _safe_int,
    qualify_offer,
)


def _profile(**overrides):
    payload = {
        "learned_preferences": None,
        "extracted_personal_info": None,
        "extracted_experiences": [],
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def _row(**overrides):
    payload = {
        "job_title": "Cloud Engineer",
        "company": "Example",
        "apply_url": "https://93.184.216.34/apply",
        "source_url": "https://93.184.216.34/offer",
        "salary_min": None,
        "salary_max": None,
        "salary_currency": "EUR",
        "location": "Paris, France",
        "remote_type": "hybrid",
        "experience_level": "mid",
        "description_html": "<p>Role description</p>",
        "tags": ["cloud", "kubernetes"],
        "match_score": 0.72,
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def test_salary_unknown_is_not_hard_rejected() -> None:
    result = qualify_offer(
        _row(salary_min=None, salary_max=None),
        _profile(learned_preferences={"salary_min": 65000}),
    )

    assert result.decision in {"qualified", "reviewable"}
    assert not result.hard_failures
    assert any("Salaire non communiqué" in item for item in result.unknowns)


def test_salary_below_minimum_is_hard_rejected() -> None:
    result = qualify_offer(
        _row(salary_min=60000, salary_max=65000),
        _profile(learned_preferences={"salary_min": 90000}),
    )

    assert result.decision == "rejected"
    assert any("Salaire annoncé" in item for item in result.hard_failures)


def test_estimate_years_experience_uses_current_year(monkeypatch) -> None:
    class _FakeDate(real_date):
        @classmethod
        def today(cls):
            return cls(2031, 6, 1)

    monkeypatch.setattr("app.utils.mass_apply.offer_qualification.date", _FakeDate)

    profile = _profile(
        extracted_experiences=[
            {"title": "Engineer", "start_year": 2028, "end_year": "present"}
        ]
    )

    assert _estimate_years_experience(profile) == 3


def test_safe_int_parses_salary_ranges_and_suffixes() -> None:
    assert _safe_int("60k") == 60000
    assert _safe_int("60.5k") == 60500
    assert _safe_int("1.5m") == 1500000
