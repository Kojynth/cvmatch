# Quick Operating Notes

- Read `AGENTS.md` first.
- This repo is not greenfield. Preserve working flows and migrate incrementally.
- Keep `mass_apply` in scope even if parts of its source are missing in this
  clone. Do not remove it.
- Keep UI/workers thin. New logic goes to `app/domain`, `app/infra`, or
  `app/integrations`.
- Never break:
  - profile JSON round-trip
  - CV JSON contracts
  - history/export consistency
  - deterministic generation fallback
  - PII-safe logging
- High-risk files:
  - `app/workers/llm_worker.py`
  - `app/workers/qwen_manager.py`
  - `app/workers/bulk_apply_worker.py`
  - `app/workers/bulk_generation_worker.py`
  - `app/workers/job_fetch_worker.py`
  - `app/utils/profile_json.py`
  - `app/utils/cv_postprocessing.py`
  - `app/utils/mass_apply/*`
  - `app/utils/ats/*`
  - `app/models/database.py`
  - `app/views/panels/mass_application_panel.py`
  - `app/views/panels/bulk_apply_review_dialog.py`
  - `app/views/profile_details_editor.py`
- Required validation:
  - `python -m py_compile <touched files>`
  - targeted pytest scope
  - explicit code review
  - explicit security review
- Pytest temp artifacts now live under `runtime/pytest_tmp/`.
- Prefer wrappers and shims over large moves.
- No destructive git commands. No secrets or user data in Git.
