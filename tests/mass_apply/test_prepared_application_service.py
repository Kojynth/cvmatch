from __future__ import annotations

import sys
from types import SimpleNamespace

from app.utils.mass_apply.prepared_application_service import _generate_application


class _Signal:
    def __init__(self) -> None:
        self._callbacks = []

    def connect(self, callback) -> None:
        self._callbacks.append(callback)

    def emit(self, *args) -> None:
        for callback in list(self._callbacks):
            callback(*args)


def test_generate_application_prefers_runtime_offer_url(monkeypatch) -> None:
    captured = {}

    class _FakeWorker:
        def __init__(self, *, offer_data, **kwargs) -> None:
            captured["offer_url"] = offer_data["offer_url"]
            self.generation_finished = _Signal()
            self.error_occurred = _Signal()
            self.finished = _Signal()

        def start(self) -> None:
            self.generation_finished.emit({"application_id": 42})
            self.finished.emit()

    class _FakeLoop:
        def exec(self) -> None:
            return None

        def quit(self) -> None:
            return None

    monkeypatch.setattr(
        "app.utils.mass_apply.prepared_application_service.ProfileWorkerData.from_profile",
        lambda profile: {"profile": True},
    )
    monkeypatch.setattr(
        "app.utils.mass_apply.prepared_application_service.QEventLoop",
        _FakeLoop,
    )
    monkeypatch.setitem(
        sys.modules,
        "app.workers.llm_worker",
        SimpleNamespace(CVGenerationWorker=_FakeWorker),
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

    result = _generate_application(
        SimpleNamespace(preferred_template="modern"),
        row,
        "modern",
        selected_model_id=None,
    )

    assert result["application_id"] == 42
    assert captured["offer_url"] == row.runtime_apply_url
