from __future__ import annotations

import sys
from types import SimpleNamespace

from app.workers.bulk_generation_worker import BulkGenerationWorker


class _Signal:
    def __init__(self) -> None:
        self._callbacks = []

    def connect(self, callback) -> None:
        self._callbacks.append(callback)

    def emit(self, *args) -> None:
        for callback in list(self._callbacks):
            callback(*args)


def test_generate_one_prefers_runtime_offer_url(monkeypatch) -> None:
    captured = {}

    class _FakeWorker:
        def __init__(self, *, offer_data, **kwargs) -> None:
            captured["offer_url"] = offer_data["offer_url"]
            self.generation_finished = _Signal()
            self.error_occurred = _Signal()
            self.finished = _Signal()

        def start(self) -> None:
            self.generation_finished.emit({"application_id": 77})
            self.finished.emit()

    class _FakeLoop:
        def exec(self) -> None:
            return None

        def quit(self) -> None:
            return None

    monkeypatch.setattr(
        "app.workers.worker_data.ProfileWorkerData.from_profile",
        lambda profile: SimpleNamespace(model_version="base"),
    )
    monkeypatch.setattr(
        "app.workers.bulk_generation_worker.QEventLoop",
        _FakeLoop,
    )
    monkeypatch.setitem(
        sys.modules,
        "app.workers.llm_worker",
        SimpleNamespace(CVGenerationWorker=_FakeWorker),
    )
    monkeypatch.setattr(
        "app.utils.mass_apply.ensure_selected_model",
        lambda *args, **kwargs: None,
    )

    worker = BulkGenerationWorker(
        profile=SimpleNamespace(),
        scan_result_ids=[],
        template="modern",
    )
    row = SimpleNamespace(
        job_title="Cloud Engineer",
        company="Example",
        description_html="<p>Offer</p>",
        source_url="https://boards.greenhouse.io/example/jobs/123",
        apply_url="https://boards.greenhouse.io/example/jobs/123",
        runtime_source_url="https://boards.greenhouse.io/example/jobs/123?src=feed",
        runtime_apply_url="https://boards.greenhouse.io/example/jobs/123?gh_jid=123#apply",
        location="Paris",
        remote_type="hybrid",
        salary_min=60000,
        salary_max=80000,
        salary_currency="EUR",
        source_name="greenhouse",
        application_id=None,
    )

    success, application_id = worker._generate_one(row)

    assert success is True
    assert application_id == 77
    assert captured["offer_url"] == row.runtime_apply_url


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
        "app.workers.bulk_generation_worker.get_session",
        lambda: _SessionContext(),
    )

    worker = BulkGenerationWorker(
        profile=SimpleNamespace(id=7),
        scan_result_ids=[],
        template="modern",
    )

    assert worker._load_scan_result(1) is None
    assert worker._load_scan_result(2) is None
