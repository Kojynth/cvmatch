# Repository Operating Rules

## Scope
This repository is a public desktop Python project for local CV extraction,
profile management, CV and cover-letter generation, export rendering, history,
and `mass_apply` automation. The project is offline-first, privacy-sensitive,
and must stay usable on heterogeneous Windows/Linux machines.

## Canonical Layout
- `app/`: desktop shell, domain logic, persistence adapters, integrations,
  services, views, workers.
- `cvextractor/`: canonical extraction engine and pipeline.
- `config/`: model registry and environment-facing configuration.
- `templates/`, `resources/`: rendering assets and lexicons.
- `scripts/`: install, diagnostics, maintenance, validation helpers.
- `tests/`: versioned contract and mass-apply suites.
- `development/`: exploratory and local-only work. Not production source.
- `.agents/`: operational definitions for sub-agents, skills, hooks, and MCP.

## Architecture Rules
- Keep `views/`, `controllers/`, and Qt `workers/` thin.
- New business logic belongs in `app/domain/`.
- Persistence, runtime, secrets, diagnostics, and model loading belong in
  `app/infra/`.
- Networked adapters belong in `app/integrations/`.
- `app/utils/` is compatibility glue or genuinely generic helpers only. Do not
  add new domain-sized logic there.
- `cvextractor.pipeline` is the canonical extraction path. Treat
  `cvextractor.core` as legacy or transition code.
- `mass_apply` is an official bounded context. Do not drop it because this clone
  is incomplete; preserve or restore it in source form before refactoring it.

## Invariants
- Never invent new candidate facts. Do not create new experiences,
  certifications, employers, dates, or achievements.
- Keep deterministic minimum-schema recovery active for invalid or empty LLM
  outputs.
- Preserve round-trip integrity across:
  UI -> profile JSON -> DB -> generated CV JSON -> render/export/history.
- Preserve history preview/export parity, especially profile photo behaviour.
- `personal_info.links` stays the source of truth and maps to `contact.links`.
- Use canonical profile keys first and legacy aliases only as explicit fallback.

## Safety And Privacy
- Use safe logging wrappers and redaction helpers for any profile, offer,
  generated CV, or runtime diagnostics data.
- Never commit logs, exports, screenshots, databases, caches, `.pyc`, backups,
  or user documents.
- Keep secrets out of source control. Use the local secure store helpers.
- No direct network calls from views or controllers. External calls must go
  through `app/integrations/`.
- `mass_apply` and job-source changes must keep domain allowlists, safe URL
  validation, and explicit human-review escape hatches for ambiguous cases.

## High-Risk Areas
- `app/workers/llm_worker.py`
- `app/workers/qwen_manager.py`
- `app/utils/profile_json.py`
- `app/utils/cv_postprocessing.py`
- `app/models/database.py`
- `app/views/profile_details_editor.py`
- any `mass_apply`, `job_sources`, secrets, or export-history code

## Build, Test, And Validation
- Preferred setup: `poetry install`
- GUI launch: `poetry run cvmatch` or repo launchers
- CLI: `poetry run cvmatch-cli`
- Format: `python -m black --check app cvextractor tests`
- Imports: `python -m isort --check-only .`
- Types: `python -m mypy app cvextractor`
- Contracts: `python -m pytest tests/contracts -q`
- Mass apply: `python -m pytest tests/mass_apply -q`
- Always compile touched Python files and run the smallest relevant functional
  suite before concluding.

## Change Propagation Rules
- Schema or DB changes must update:
  `app/schemas`, `app/models`, profile mapping, generation, postprocessing,
  history, export, and tests in the same change.
- Model additions must update:
  model registry, runtime routing, memory heuristics, selectors, and tests.
- Stage memory policy changes must preserve explicit host overrides and compare
  normalized numeric values.

## Migration Rules
- Prefer additive migrations, wrappers, and re-exports over big-bang moves.
- Do not remove legacy or compatibility shims until the replacement path is in
  source control and validated.
- If a module exists only as `.pyc` or local artifact, do not treat it as a
  stable source of truth. Restore or recreate tracked source first.

## Post-Edit Review
- Perform explicit code review on every diff: bugs, regressions, assumptions,
  missing tests.
- Perform explicit security review on every diff: subprocess/env handling, path
  writes, secrets, PII leakage, trust boundaries, unsafe HTML/logging.

## Agentic Operations
- `.agents/subagents/contract-guardian.md`
- `.agents/subagents/llm-runtime-worker.md`
- `.agents/subagents/mass-apply-worker.md`
- `.agents/skills/`
- `.agents/mcp/README.md`
- `.agents/hooks/README.md`

Follow those operational definitions when delegating or automating work. Use
hooks and scripts before spawning more reasoning.
