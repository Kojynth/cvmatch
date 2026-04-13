from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest

from app.controllers.main_window.mass_applications import MassApplicationsCoordinator


class _ExecResult:
    def __init__(self, rows) -> None:
        self._rows = rows

    def all(self):
        return self._rows


class _Session:
    def __init__(self, rows) -> None:
        self.rows = rows
        self.statement = None

    def exec(self, statement):
        self.statement = statement
        return _ExecResult(self.rows)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_load_results_is_scoped_to_requested_profile(monkeypatch) -> None:
    rows = [
        SimpleNamespace(
            id=1,
            profile_id=7,
            dedup_key="abc",
            source_name="greenhouse",
            source_tier="api_public",
            job_title="Cloud Engineer",
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
            runtime_source_url=None,
            runtime_apply_url=None,
            match_score=0.9,
            scan_date=datetime(2026, 4, 7, 12, 0, 0),
        ),
    ]
    session = _Session(rows)
    monkeypatch.setattr(
        "app.controllers.main_window.mass_applications.get_session",
        lambda: session,
    )

    coordinator = MassApplicationsCoordinator(profile=SimpleNamespace(id=7))
    result = coordinator.load_results(profile_id=7)

    assert [item["id"] for item in result] == [1]
    query = str(session.statement)
    assert "jobscanresult.profile_id = :profile_id_1" in query
    assert "jobscanresult.profile_id = :profile_id_2" not in query


def test_start_bulk_generation_refuses_while_apply_batch_is_live() -> None:
    coordinator = MassApplicationsCoordinator(profile=SimpleNamespace(id=7))
    coordinator._bulk_apply_worker = SimpleNamespace(
        isRunning=lambda: True,
        isFinished=lambda: False,
    )

    with pytest.raises(RuntimeError, match="candidature en masse"):
        coordinator.start_bulk_generation([1, 2])


def test_start_bulk_apply_refuses_while_generation_batch_is_live() -> None:
    coordinator = MassApplicationsCoordinator(profile=SimpleNamespace(id=7))
    coordinator._bulk_worker = SimpleNamespace(
        isRunning=lambda: True,
        isFinished=lambda: False,
    )

    with pytest.raises(RuntimeError, match="generation en masse"):
        coordinator.start_bulk_apply([1, 2])
