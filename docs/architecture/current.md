# Current Architecture

- Desktop-first Python application with `main.py` and OS launchers.
- Canonical UI shell lives in `app/lifecycle`, `app/controllers/main_window`,
  `app/views/panels`, and `app/services`.
- Canonical extraction path is moving toward `cvextractor.pipeline`.
- Generation and post-processing still depend on large runtime modules under
  `app/workers` and `app/utils`.
- A standalone generic CV export path also exists from the profile editor:
  - `app/views/generic_cv_export_dialog.py`
  - `app/workers/generic_cv_export_worker.py`
  - It now applies explicit model selection plus the same minimum deterministic
    postprocess/quality gate as the main CV generation path.
- `app/domain/profile` now owns deterministic profile-domain helpers for:
  - date support metadata,
  - personal-info and link normalization,
  - `experiences` / `education` mapping,
  - `skills` / `soft_skills` / `languages` mapping,
  - `projects`, `certifications`, `publications`, `volunteering`, `awards`,
    `references`, and `interests` mapping.
- `app/utils/profile_json.py` is still the canonical compatibility facade and
  round-trip contract entrypoint, but much of its pure mapping logic has now
  been extracted into `app/domain/profile`.
- `mass_apply` is a real bounded context. Source recovery is now partially
  restored for:
  - `app/utils/mass_apply/*` core pure helpers,
  - `app/utils/job_sources/api_key/usajobs_client.py`,
  - `app/utils/job_sources/sitemap_html/wttj_client.py`,
  - `app/utils/ats/*` minimal automation contracts,
  - `app/workers/job_fetch_worker.py`,
  - `app/workers/bulk_generation_worker.py`,
  - `app/workers/bulk_apply_worker.py`,
  - `app/controllers/main_window/mass_applications.py`,
  - `app/views/panels/mass_application_panel.py`,
  - `app/views/panels/bulk_apply_review_dialog.py`.
- Test-runtime temp directories are pinned under `runtime/pytest_tmp/` to keep
  validation inside the workspace on Windows.
- Remaining gaps still exist in some legacy/job-source source files that remain
  only as `.pyc`.

This file is the compact operator-facing snapshot used during migration.
