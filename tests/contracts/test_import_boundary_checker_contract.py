from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_boundary_checker_module():
    repo_root = Path(__file__).resolve().parents[2]
    module_path = repo_root / "scripts" / "diagnostics" / "check_import_boundaries.py"
    spec = importlib.util.spec_from_file_location(
        "check_import_boundaries_contract",
        module_path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_boundary_checker_flags_relative_view_and_controller_paths(monkeypatch) -> None:
    module = _load_boundary_checker_module()

    def fake_read_text(self, encoding="utf-8-sig"):
        normalized = self.as_posix()
        if normalized == "app/views/sample.py":
            return "import requests\n"
        if normalized == "app/controllers/sample.py":
            return "from app.integrations.job_sources import source\n"
        raise FileNotFoundError(normalized)

    monkeypatch.setattr(Path, "read_text", fake_read_text)

    view_failures = module._check_file(Path("app/views/sample.py"))
    controller_failures = module._check_file(Path("app/controllers/sample.py"))

    assert any("forbidden import `requests`" in failure for failure in view_failures)
    assert any(
        "forbidden import `app.integrations.job_sources`" in failure
        for failure in controller_failures
    )
