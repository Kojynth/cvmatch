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

## Post-Fix Coherence Rule (Mandatory)
After fixing a bug, perform an explicit coherence pass across all coupled layers touched by the fix (registry entries, selectors, routing and fallback logic, memory or size heuristics, strict JSON parsing paths, and stage orchestration). Do not stop at the local patch: verify that identifiers, thresholds, and assumptions stay aligned end-to-end, then run at least one targeted functional check reproducing the original failure path and confirming it does not reappear.

## Model Addition Coherence Rule (Mandatory)
When adding a new model to the selectable list, treat it as a cross-layer change and update all impacted contracts in one pass: registry profile (`config/model_registry.yaml`) with consistent `model_id`, `loader`, `quantization`, `min_vram_gb`, `min_ram_gb`, `quality_stars`, and dropdown tag policy; hardware tier defaults and fallbacks; writer-quality routing preferences; runtime estimation maps (size, RAM, and time) used by model manager and memory planning; and stage/fallback assumptions that depend on model-size pattern matching. Before enabling the model in UI selection, verify backend compatibility with the current loading path (for example `AutoModelForCausalLM` plus tokenizer path); if architecture is not compatible, do not expose it as selectable until a dedicated loader path is implemented. Validate with at least one targeted end-to-end check proving the model appears in selectors and resolves coherently through routing and validation logic.

## History Preview Photo Consistency Rule (Mandatory)
For CVs opened from history, keep profile photo rendering consistent across preview and PDF export paths. If `photo_base64` is available, do not blindly prioritize legacy `raw_html` that lacks an embedded profile photo; prefer a template-rendered HTML path (or equivalent safe regeneration) so the preview and exported PDF both display the same profile image. Any change touching history data mapping, preview HTML selection, or export entrypoints must include a targeted regression check on the exact flow: History -> open CV -> Exporter en PDF preview.

## Offer Term Routing Precision Rule (Mandatory)
When adjusting offer-term routing logic (`app/utils/cv_offer_term_routing.py`) or skill recovery (`app/utils/cv_skill_recovery.py`), avoid over-routing concise skill compounds to `experience` only because they start with an action-like token. Keep noun compounds such as `test automation` in `skills` unless strong experience-object evidence is present. Handle ambiguous tokens with context-sensitive rules: uppercase `IT` must remain a technical term (skills context) and must not be auto-classified as a language alias for Italian. Any routing change must include targeted regression checks for at least: `test automation`, `IT`, `it`, and one explicit experience phrase (for example `manage team`).

## Education Adaptation Non-Injection Rule (Mandatory)
In CV offer adaptation (`app/utils/cv_postprocessing.py`), keep education enrichment generation-led and do not reintroduce deterministic synthetic bullets in `education.details` from `missing_education_terms`. Missing education terms may guide model generation, but postprocessing must not force appended sentences such as generic "aligned with ..." phrases. If adaptation behavior changes, update and keep regression tests aligned with this invariant.

## Rules-Only Minimal Edit Rule (Mandatory)
When the user asks to add rules only, or to modify existing rules without rewriting the file, apply strict minimal edits: append only the requested rule(s) or update only the explicitly requested rule block(s). Do not overwrite, reorder, delete, or rephrase unrelated sections of `AGENTS.md`.
