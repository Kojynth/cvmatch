# Repository Guidelines

## Project Structure & Module Organization
The PySide6 client lives in `app/` with controllers, views, widgets, workers, and shared utils. Extraction pipelines live in `cvextractor/`, powering both the GUI and automation flows. Regression suites sit in `tests/`, while `development/tests/` hosts exploratory cases and fixtures, and `development/dev_tools/` covers diagnostics. Benchmarking and maintenance scripts live in `tools/` and `scripts/` (notably `enhanced_cli.py`, installer wrappers, PII cleaners), with reference docs in `docs/`, assets in `resources/`, and environment templates in `config/`.

## Build, Test, and Development Commands
`poetry install` (add `--with ai` for transformer extras) prepares dependencies. Launch the GUI with `poetry run cvmatch`; automation flows use `poetry run cvmatch-cli` or `poetry run python scripts/enhanced_cli.py`. Platform helpers `cvmatch.bat` and `./cvmatch.sh` wrap those entrypoints; installation/bootstrap scripts in this repo are `installation_cvmatch_ai_windows.bat`, `installation_cvmatch_ai_linux.sh`, `installation_cvmatch_windows.bat`, and `installation_cvmatch_linux.sh`. Run `poetry run pre-commit run --all-files` for the repository hooks currently configured in `.pre-commit-config.yaml`.

## Coding Style & Naming Conventions
Format with Black (88 columns, 4-space indentation) via `poetry run black app cvextractor tests`. Keep modules, functions, and signals in `snake_case`, classes in `PascalCase`, constants in `UPPER_SNAKE`, and mirror Qt object names with their Python attributes. Normalise imports through `poetry run isort .` and keep mypy clean with `poetry run mypy`, adding annotations for public APIs.

## CV Adaptation Invariant (Mandatory)
When changing generation or postprocessing code, especially `app/workers/llm_worker.py` and `app/utils/cv_postprocessing.py`, preserve this invariant: keep offer adaptation creative and profile-grounded across all existing CV sections, keep deterministic minimum-schema recovery active for empty or invalid model outputs, and never introduce new factual entities. Do not create new experience or certification records; only reformulate existing profile facts.

## Sustainable File Size & Refactoring Rule (Mandatory)
When implementing new behavior, prefer creating a new module or file instead of continuously expanding large files. If a file is already large or a change adds substantial logic, extract cohesive helpers or services into dedicated modules with clear responsibilities. Keep functions focused, avoid god-objects and god-files, and refactor opportunistically so files remain maintainable over time.

## Testing Guidelines
Run `poetry run pytest` before every PR when feasible. Use the existing pytest markers configured in `pyproject.toml` (`gui`, `integration`) for targeted runs instead of undocumented markers. Prototype work can live in `development/tests/`, reusing data from its `fixtures/` directory after anonymising CV samples. If you run partial validation only, record the exact scope you skipped.

## Commit & Pull Request Guidelines
Write imperative commit subjects (`tighten diploma parsing`). Reference tickets in footers (`Refs #123`), separate behavioural, UI, and tooling changes, and list validation commands in the PR body. Attach screenshots for UI work and mention cache or model steps reviewers must replicate.

## Security & Data Handling
Use the safe logging wrappers (`app.utils.safe_log.get_safe_logger` or `cvextractor.utils.log_safety.create_safe_logger_wrapper`) instead of bare `logging` when handling profile content. Reference users by internal IDs or hashed tokens rather than names or emails in artefacts, metrics, or filenames. Keep secrets in env files under `config/`, scrub data with `python scripts/clean_pii_logs_emergency.py` or the masking switches in `scripts/enhanced_cli.py`, and leave caches (`.hf_cache/`, `cache/`, `logs/`) untracked so each contributor refreshes them locally.

## End-to-End Pipeline Rule (Mandatory)
Treat profile-to-CV generation as one contract pipeline: Profile Details UI input (`app/views/profile_details_editor.py` and profile sections) -> profile normalization, merge, and cache (`app/utils/profile_json.py`) -> DB save on `UserProfile` -> CV generation (`app/workers/llm_worker.py`) -> CV sanitization and postprocessing (`app/utils/cv_postprocessing.py`) -> rendering and export (`app/utils/cv_json_renderer.py`, `app/controllers/export_manager.py`, templates). Any field added or renamed in this chain must be propagated across every stage in the same change.

## JSON Round-Trip Rule (Mandatory)
For any schema evolution, preserve round-trip integrity: UI save -> Profile JSON export -> Profile JSON import -> persisted DB values -> regenerated CV JSON must keep equivalent semantic data. Update schema models (`app/schemas/profile_schema.py`, `app/schemas/cv_schema.py`), payload mapping, normalization, cache hydration, import/export conversion, and renderer fallback paths together.

## Contact Links Contract Rule (Mandatory)
`personal_info.links` is the profile source of truth and must map to `contact.links` in generated CV when links exist. Keep backward compatibility for legacy link payloads (`label/url`, `platform/url`, string URLs). Keep link labels deterministic (`Lien 1`, `Lien 2`, and so on) in UI-generated rows. Do not force empty `links` arrays in final CV or contact payloads when no valid link exists.

## Skills Sanitization Guardrail (Mandatory)
When adjusting skill or category sanitization in `app/utils/cv_postprocessing.py`, do not use broad substring role detection against job titles. Use token-based overlap checks and role-token heuristics only. Never drop a valid skill phrase only because one token is ambiguous, for example `lead` in `Lead Generation`.

## Cache Safety Rule (Mandatory)
When storing or restoring profile editor state, deep-copy nested JSON-like structures before caching and before restore comparisons to avoid hidden in-place mutation bugs on personal info, links, and extracted section arrays.

## Runtime Environment Rule (Mandatory)
Use `PYTORCH_ALLOC_CONF`, not `PYTORCH_CUDA_ALLOC_CONF`, in startup scripts and worker bootstrap code. Keep allocator defaults consistent between shell launchers and Python workers to avoid warning noise and divergent GPU memory behavior.

## Validation Rule (Mandatory)
Before merging cross-layer data-contract changes, run at minimum syntax validation on touched Python files and one targeted functional pass for profile save, JSON export or import, CV generation, and export rendering. If full `pytest` is not feasible locally, document the exact skipped scope in the PR.
