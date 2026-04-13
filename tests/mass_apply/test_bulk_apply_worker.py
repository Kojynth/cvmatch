from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from app.workers.bulk_apply_worker import BulkApplyWorker


def _create_temp_screenshot() -> Path:
    root = Path("runtime") / "pytest_tmp" / "artifacts"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"bulk-apply-{uuid4().hex}.png"
    path.write_bytes(b"fake-png")
    return path


def test_record_attempt_deletes_screenshot_on_commit_failure(monkeypatch) -> None:
    screenshot = _create_temp_screenshot()
    session = SimpleNamespace(
        add=lambda attempt: None,
        commit=lambda: (_ for _ in ()).throw(Exception("DB error")),
    )
    session_cm = SimpleNamespace(
        __enter__=lambda self: session,
        __exit__=lambda self, exc_type, exc, tb: False,
    )
    monkeypatch.setattr(
        "app.workers.bulk_apply_worker.get_session",
        lambda: session_cm,
    )

    worker = BulkApplyWorker(profile=SimpleNamespace(id=1), scan_result_ids=[])
    row = SimpleNamespace(
        id=1,
        profile_id=2,
        application_id=None,
        apply_url="https://jobs.example.com/apply",
        source_url=None,
    )
    ats = SimpleNamespace(platform="generic")
    report = SimpleNamespace(
        score=70, decision="human_pause", breakdown={}, blocking_reasons=[]
    )
    exec_result = SimpleNamespace(
        screenshot_path=str(screenshot),
        fields_filled=3,
        fields_skipped=1,
        error=None,
    )

    worker._record_attempt(row, ats, report, exec_result, "submitted")

    assert not screenshot.exists()


def test_record_attempt_sanitizes_persisted_apply_url(monkeypatch) -> None:
    captured = {}

    class _Session:
        def add(self, attempt):
            captured["apply_url"] = attempt.apply_url
            captured["screenshot_path"] = attempt.screenshot_path

        def commit(self):
            return None

    class _SessionContext:
        def __enter__(self):
            return _Session()

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(
        "app.workers.bulk_apply_worker.get_session",
        lambda: _SessionContext(),
    )

    worker = BulkApplyWorker(profile=SimpleNamespace(id=1), scan_result_ids=[])
    row = SimpleNamespace(
        id=2,
        profile_id=2,
        application_id=None,
        apply_url="https://jobs.example.com/apply?token=secret&prefill=email",
        source_url=None,
        runtime_apply_url="https://jobs.example.com/runtime?token=live&prefill=email",
        runtime_source_url=None,
    )
    ats = SimpleNamespace(platform="generic")
    report = SimpleNamespace(
        score=70, decision="human_pause", breakdown={}, blocking_reasons=[]
    )
    exec_result = SimpleNamespace(
        screenshot_path=None,
        fields_filled=1,
        fields_skipped=0,
        error=None,
    )

    worker._record_attempt(row, ats, report, exec_result, "submitted")

    assert captured["apply_url"] == "https://jobs.example.com/runtime"
    assert captured["screenshot_path"] is None


def test_record_attempt_deletes_review_screenshot_on_commit_failure(monkeypatch) -> None:
    screenshot = _create_temp_screenshot()
    session = SimpleNamespace(
        add=lambda attempt: None,
        commit=lambda: (_ for _ in ()).throw(Exception("DB error")),
    )
    session_cm = SimpleNamespace(
        __enter__=lambda self: session,
        __exit__=lambda self, exc_type, exc, tb: False,
    )
    monkeypatch.setattr(
        "app.workers.bulk_apply_worker.get_session",
        lambda: session_cm,
    )

    worker = BulkApplyWorker(profile=SimpleNamespace(id=1), scan_result_ids=[])
    row = SimpleNamespace(
        id=10,
        profile_id=2,
        application_id=11,
        apply_url="https://jobs.example.com/apply",
        source_url=None,
        runtime_apply_url="https://jobs.example.com/runtime?token=live",
        runtime_source_url=None,
    )
    ats = SimpleNamespace(platform="generic")
    report = SimpleNamespace(
        score=91, decision="auto_submit", breakdown={}, blocking_reasons=[]
    )
    exec_result = SimpleNamespace(
        screenshot_path=None,
        fields_filled=4,
        fields_skipped=0,
        error=None,
    )

    retained = worker._record_attempt(
        row,
        ats,
        report,
        exec_result,
        "submitted",
        review_screenshot_path=str(screenshot),
    )

    assert retained is False
    assert not screenshot.exists()


def test_record_attempt_retains_submitted_review_screenshot(monkeypatch) -> None:
    captured = {}
    screenshot = _create_temp_screenshot()

    class _Session:
        def add(self, attempt):
            captured["screenshot_path"] = attempt.screenshot_path
            captured["screenshot_stage"] = attempt.screenshot_stage

        def commit(self):
            return None

    class _SessionContext:
        def __enter__(self):
            return _Session()

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(
        "app.workers.bulk_apply_worker.get_session",
        lambda: _SessionContext(),
    )

    worker = BulkApplyWorker(profile=SimpleNamespace(id=1), scan_result_ids=[])
    row = SimpleNamespace(
        id=4,
        profile_id=2,
        application_id=12,
        apply_url="https://jobs.example.com/apply",
        source_url=None,
        runtime_apply_url="https://jobs.example.com/runtime?token=live",
        runtime_source_url=None,
    )
    ats = SimpleNamespace(platform="generic")
    report = SimpleNamespace(
        score=91, decision="auto_submit", breakdown={}, blocking_reasons=[]
    )
    exec_result = SimpleNamespace(
        screenshot_path=None,
        fields_filled=4,
        fields_skipped=0,
        error=None,
    )

    retained = worker._record_attempt(
        row,
        ats,
        report,
        exec_result,
        "submitted",
        review_screenshot_path=str(screenshot),
    )

    assert retained is True
    assert captured["screenshot_path"] == str(screenshot)
    assert captured["screenshot_stage"] == "pre_review"
    assert screenshot.exists()
    screenshot.unlink(missing_ok=True)


def test_load_scan_result_rejects_cross_profile_and_legacy_rows(monkeypatch) -> None:
    rows = {
        1: SimpleNamespace(id=1, profile_id=99),
        2: SimpleNamespace(id=2, profile_id=0),
    }

    class _Session:
        def get(self, model, scan_id):
            return rows.get(scan_id)

        def expunge(self, row):
            return None

    class _SessionContext:
        def __enter__(self):
            return _Session()

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(
        "app.workers.bulk_apply_worker.get_session",
        lambda: _SessionContext(),
    )

    worker = BulkApplyWorker(profile=SimpleNamespace(id=1), scan_result_ids=[])

    assert worker._load_scan_result(1) is None
    assert worker._load_scan_result(2) is None


def test_build_allowed_request_policy_relaxes_known_ats_hosts() -> None:
    pinned, suffixes = BulkApplyWorker._build_allowed_request_policy(
        "jobs.company.wd5.myworkdayjobs.com",
        "workday",
    )

    assert pinned == ("jobs.company.wd5.myworkdayjobs.com",)
    assert "myworkdayjobs.com" in suffixes
    assert "workdaycdn.com" in suffixes


def test_all_done_signal_accepts_four_ints() -> None:
    worker = BulkApplyWorker(profile=SimpleNamespace(id=1), scan_result_ids=[])
    emitted = []
    worker.all_done.connect(
        lambda submitted, paused, skipped, failed: emitted.append(
            (submitted, paused, skipped, failed)
        )
    )

    worker._run()

    assert emitted == [(0, 0, 0, 0)]
