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
  - `app/utils/cv_quality_audit.py`
  - `app/utils/mass_apply/*`
  - `app/utils/ats/*`
  - `app/models/database.py`
  - `app/controllers/export_manager.py`
  - `app/views/panels/mass_application_panel.py`
  - `app/views/panels/bulk_apply_review_dialog.py`
  - `app/views/profile_details_editor.py`
  - `app/views/generic_cv_export_dialog.py`
  - `app/workers/generic_cv_export_worker.py`
- Profile-domain extraction status:
  - `app/domain/profile/date_support.py` now owns deterministic date-support
    metadata derivation.
  - `app/domain/profile/section_mappers.py` now owns
    `experiences`/`education` mapping.
  - `app/domain/profile/personal_info.py` now owns personal-info extraction and
    link normalization/merge helpers.
  - `app/domain/profile/skill_language_mappers.py` now owns
    `skills`/`soft_skills`/`languages` mapping.
  - `app/domain/profile/artifact_mappers.py` now owns
    `projects`/`certifications`/`publications`/`volunteering`/`awards`/
    `references`/`interests` mapping.
  - `app/utils/profile_json.py` remains the compatibility facade and canonical
    round-trip entrypoint.
- Required validation:
  - `python -m py_compile <touched files>`
  - targeted pytest scope
  - explicit code review
  - explicit security review
- CV generation quality reminders:
  - keep ATS-first, one-language output
  - keep reverse chronology, consistent dates, and explicit durations when
    reliable
  - keep 2-4 concise bullets per role when bullets are available
  - prefer `action + what + impact`, strong verbs, no first-person pronouns,
    no filler or keyword stuffing
  - use offer keywords pertinently by section and company context
  - controlled inferred impact is allowed when implicit in the profile, but do
    not invent new hard facts, technologies, projects, certifications, or exact
    metrics
  - `CVMATCH_CV_EVIDENCE_MODE=strict_factual|inferred_impact` controls this
    boundary; default runtime behavior is `inferred_impact`
- Generic standalone CV export:
  - `app/views/generic_cv_export_dialog.py` and
    `app/workers/generic_cv_export_worker.py` are now a real path from profile
    editor to PDF export.
  - This path must keep explicit model selection, safe logging, deterministic
    fallback, and the same minimum postprocess/quality gate as the main CV
    pipeline.
- Pytest temp artifacts now live under `runtime/pytest_tmp/`.
- Prefer wrappers and shims over large moves.
- No destructive git commands. No secrets or user data in Git.
