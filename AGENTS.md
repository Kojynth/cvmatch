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
- Do not introduce invented facts. Do not create new experiences,
  certifications, employers, dates, achievements, or exact metrics that are not
  grounded in the source profile.
- Controlled inferred enrichment is allowed only when it stays implicit and
  coherent with existing profile evidence, role context, and reliable dates or
  durations. This may strengthen phrasing, surface qualitative impact, or
  highlight already-evidenced tools/contexts, but it must not introduce new
  employers, roles, projects, technologies, degrees, certifications, or exact
  unsupported metrics.
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

## CV Generation Quality Requirements
- Apply CV quality constraints regardless of the original job-offer language.
  Language-specific heuristics may vary, but structural and adaptation rules
  remain mandatory for French, English, Japanese, Chinese, and other supported
  output languages.
- Keep the final CV in one consistent output language unless the user
  explicitly requests bilingual content.
- Keep ATS-compatible structure: simple sections, parseable headings, no noisy
  pseudo-bullets, and no decorative formatting assumptions in generated text.
- Keep experiences and projects in reverse chronological order and use one
  consistent date format across the full CV.
- Include an explicit duration for each role or project when reliable dates
  allow it.
- Keep each role to 2-4 concise bullet points whenever the source profile
  supports bullet rendering; prefer short action-led bullets over dense
  narrative paragraphs.
- Use strong action verbs, avoid first-person pronouns, keep punctuation and
  tense consistent, and prefer `action + what + result/impact` phrasing when
  facts support it.
- Use target-offer keywords and company context pertinently: route them to the
  right sections, prefer grounded evidence over lexical stuffing, and do not
  pass a CV as high quality if the match is only terminological.
- When metrics are explicitly available, keep them. When they are only
  implicit, qualitative impact may be inferred, but exact numbers must not be
  fabricated.
- If the generated CV is lexically aligned but fails quality checks
  (grammar/clarity, dates, ATS readability, bullet density, tense, pronouns, or
  evidence quality), treat it as insufficient and retry or reject it.

## Change Propagation Rules
- Schema or DB changes must update:
  `app/schemas`, `app/models`, profile mapping, generation, postprocessing,
  history, export, and tests in the same change.
- Model additions must update:
  model registry, runtime routing, memory heuristics, selectors, and tests.
- Stage memory policy changes must preserve explicit host overrides and compare
  normalized numeric values.

## Development Leniency
- Prefer lenient, additive behaviour over restrictive defaults. When fixing or
  extending logic, keep accepting inputs that already worked and only narrow
  the contract when a concrete bug requires it.
- New filters, thresholds, or allowlists must ship with a regression test that
  pins legitimate inputs that must still pass. Commit 697ffd5 is the reference
  incident: a "tightening" on short tokens and single-term summaries silently
  removed valid enrichment and let duplicate bullets slip through. Tightenings
  without a proof of the legitimate inputs they preserve are not accepted.
- When two behaviours are possible, pick the one that keeps the existing
  generated CV as similar as possible to the previous version for the same
  profile + offer pair. Surprise for the user is a bigger cost than a narrower
  edge-case fix.
- Never remove or disable an existing code path to avoid debugging it. If a
  branch is truly obsolete, delete it in a dedicated change with justification.

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
