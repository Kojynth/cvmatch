# Repository Operating Rules

## Scope
This repository is a public desktop Python project for local CV extraction,
profile management, CV and cover-letter generation, export rendering, history,
and `mass_apply` automation. The project is offline-first, privacy-sensitive,
and must stay usable on heterogeneous Windows/Linux machines.

## Operating Discipline
- Always diagnose and analyze before editing: reproduce the symptom when
  possible, inspect the relevant code path, identify the contract at risk, and
  keep the change scoped to that diagnosis.
- If the request, data source, or expected behavior is unclear and repository
  context cannot resolve it safely, ask a concise clarifying question before
  changing code. If the ambiguity can be resolved from local context with a
  low-risk assumption, state the assumption and proceed.

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
- **Sourcing principle (MANDATORY)**: every generated sentence, bullet, skill
  label, or positioning phrase must be sourced from **either the profile JSON
  or the job offer data**. The product's goal is explicitly to *reformulate
  profile skills in the vocabulary of the offer* — not to verbatim-copy the
  profile, not to invent content. Cross-domain offer keywords are legitimate
  when surfaced in positioning text (e.g. "Atouts pertinents pour
  {Company}"). Ex-nihilo content (facts, tools, metrics absent from BOTH
  sources) is forbidden.
- Do not introduce invented facts. Do not create new experiences,
  certifications, employers, dates, achievements, or exact metrics that are not
  grounded in the source profile.
- Controlled inferred enrichment is allowed only when it stays implicit and
  coherent with existing profile evidence, role context, and reliable dates or
  durations. This may strengthen phrasing, surface qualitative impact, or
  highlight already-evidenced tools/contexts, but it must not introduce new
  employers, roles, projects, technologies, degrees, certifications, or exact
  unsupported metrics.
- **Specific-formulation ownership (MANDATORY)**: deterministic code,
  renderers, postprocessors, validators, fallback builders, and coding-agent
  helper logic must stay profession-agnostic, company-agnostic,
  profile-agnostic, and language-agnostic. They may provide neutral structure,
  filters, guards, validation, source collection, and prompt instructions, but
  must not hardcode reader-facing role/company/profile-specific prose or fixed
  profession/sector contribution formulas. Specific formulations for CVs and
  cover letters must be induced by the LLM from the profile JSON plus the job
  offer in the selected output language. If a specific phrase seems needed,
  move that requirement into prompt guidance and source-backed generation
  rules, or let the LLM produce it; deterministic fallback should use only
  neutral cross-role wording.
- When designing or tightening a filter/guard (grounding gate, low-signal
  detector, supported-skill predicate), ask: *would this reject a legitimate
  offer-sourced reformulation of profile content?* If yes, the filter is too
  tight. Permissive on sourced content; strict on fragment bullets, clipped
  phrases, and ex-nihilo content.
- Keep deterministic minimum-schema recovery active for invalid or empty LLM
  outputs.
- Preserve round-trip integrity across:
  UI -> profile JSON -> DB -> generated CV JSON -> render/export/history.
- Preserve history preview/export parity, especially profile photo behaviour.
- **Preview/export immutability (MANDATORY)**: exporting a PDF must not mutate,
  reload, rescale, or otherwise visibly change the preview currently shown to
  the user. WebEngine PDF export must print from a dedicated hidden
  `QWebEngineView` loaded with the same final HTML, then clean it up after
  success or error. Do not run print-fit JavaScript, `setHtml`, or
  `printToPdf` against the visible `cv_web_view` / `letter_web_view` unless a
  hidden export view cannot be created and the fallback is explicit. Regression
  coverage lives in `tests/contracts/test_template_preview_pdf_export_contract.py`.
- `personal_info.links` stays the source of truth and maps to `contact.links`.
- Use canonical profile keys first and legacy aliases only as explicit fallback.
- **One-page output (MANDATORY)**: the generated CV must always render to
  exactly one A4 page. This is a core product feature (reformat any profile,
  regardless of length, to one page). The product must achieve this through
  a **fit-to-page compiler**, not destructive clipping:
  1. prioritized content allocation;
  2. HTML render;
  3. measured rendered height;
  4. controlled compression tiers;
  5. final PDF export.
  `ONE_PAGE_PRINT_CSS` in `app/views/template_preview_window.py` is the
  canonical print contract: one `@media print` block, A4 margins, no forced
  `height: 297mm` on `body`, no `overflow: hidden`, and `break-inside: avoid`
  on experience/project/education blocks. `_enforce_single_page_budget` in
  `app/utils/cv_postprocessing.py` remains the content-budget backstop for
  excessive bullet density. Direct WeasyPrint exports must also apply
  `PDF_ONE_PAGE_FIT_CSS` in `app/controllers/export_manager.py`; keep it
  aligned with the same no-crop/no-overflow contract so exported PDFs do not
  bypass the preview fit-to-page path. Do NOT reintroduce CSS clipping,
  duplicate print blocks, or silent crop-to-page behavior. Any PR touching that
  CSS, the export templates, or the postprocess trimming logic must ship with a
  regression test that pins both the print-fit invariant and the per-role /
  total-bullet budget. Regression tests live in
  `tests/test_one_page_invariant.py`.
- **Header render contract (MANDATORY)**: CV contact methods must render as
  explicit, accessible links when actionable (`mailto:`, `tel:`, LinkedIn,
  GitHub, portfolio URL). Placeholder labels such as `Lien 1` / `Link 1`
  are forbidden in final HTML. The target subtitle must make the recruitment
  intent explicit (for example `Poste visé: {job_title} | {company}` /
  `Target role: {job_title} | {company}`) instead of looking like an employer
  label. Regression coverage must pin clickable contacts and smart link labels.
- **Content allocation contract (MANDATORY)**: final one-page rendering must
  actively exploit the CV JSON instead of flattening it to a few generic
  sections. The default one-page layout must prioritize:
  - a summary built LAST from the blocks actually retained in the CV, so it
    avoids repeating the same signals already visible in rendered experiences;
  - up to 4 summary sentences grouped into compact paragraphs when needed:
    profile/value proposition, strongest aligned experience, natural company
    targeting sentence, then most recent experience or remaining complement;
  - a natural positioning sentence always present when company/offer signal is
    available and grounded; keep `{company}` visible, but phrase it as a
    natural relevance statement for the `{job_title}` instead of a keyword
    dump like `Profil pertinent pour {Company} grâce à A, B, C`;
  - up to 10 compact, credible skill/tool chips when the layout can support
    them (not a keyword dump); skill grouping and ordering must be driven by
    `{job_title}` plus requirement-heavy offer evidence for any profession or
    sector, never by a hardcoded company/profile/tech-only taxonomy; the
    renderer must not invent profession-specific grouped skill categories,
    because specific category labels belong in the LLM-generated CV JSON;
    final display must deduplicate repeated tools across flat and comparative
    labels, prefer compact source-backed groups over raw chips when that
    improves readability, and avoid losing named profile evidence such as
    tools, data stores, methods, delivery systems, or frameworks;
  - rendered experience order stays reverse-chronological; relevance ranking
    may change detail budgets, not the visible role order;
  - hard skill/tool chips may come from explicit user-profile evidence:
    `skills`, projects, education/formations, certifications, and experience
    evidence. Narrative experience/project/education text may create chips
    only when the extracted label is skill-shaped, source-backed, and ranked
    as aligned to the offer; avoid raw sentence fragments;
  - asymmetric experience density: the most aligned experience keeps the
    richest detail budget, the most recent role may keep a secondary budget,
    and lower-priority roles compress first;
  - 2 to 4 concrete impacts per experience, prioritizing the strongest
    action-led and quantified evidence when available; dense source evidence
    should be rewritten by the LLM into new coherent bullets rather than
    dropped, copied verbatim, or mechanically concatenated; these rewrites
    must preserve high-signal keywords, named tools, and role vocabulary that
    carry offer/profile alignment, integrated naturally rather than as a
    keyword list;
  - one featured project when available;
  - compact interests/hobbies when present in the source profile, unless the
    measured fit-to-page pass has no remaining safe space after preserving
    higher-priority content;
  - a compact certifications block when available;
  - soft skills only as a compact supporting signal, never as filler; when
    behaviour evidence can be integrated into experience bullets, avoid a
    separate generic soft-skill section.
  The renderer may hide lower-priority sections under measured compression,
  but it must not collapse useful structured content into a vague
  `additional relevant details` blob, and it must not truncate rendered
  sentences with `...` / `…`. When content does not fit, select or reorder
  whole grounded sentences; do not crop mid-sentence. The renderer is not a
  prose generator: it must not fabricate fused bullets by joining source
  fragments with semicolons. Rich bullets belong in the LLM generation/final
  rewrite stage and must remain sourced.
- **Positioning-sentence word-sourcing hierarchy (MANDATORY)**: when a
  generator selects a small set of keywords to surface in a positioning
  sentence (for example a natural summary tail such as `Profil pertinent pour
  {Company} grâce à ...`; same rule applies to any future positioning
  phrase), words MUST be chosen in this tiered order:
  1. **Generation** — offer keyword that ALSO matches a profile skill
     (profile concept rendered in offer vocabulary; this IS the product
     goal).
  2. **Offer** — skill-shaped offer keyword absent from the profile
     (cross-domain positioning), provided it passes the skill-ish filter
     (multi-word compound, acronym, CamelCase, lexicon match, or technical
     suffix — NOT a verb, preposition, adverb, article, or generic field
     noun like "technology"/"solution"/"approach").
  3. **Profile** — top profile skill verbatim (fallback when offer yields
     fewer qualifying candidates than `max_terms`).
  Hard-reject tokens: verbs (`designed`, `integrate`), prepositions
  (`into`, `with`), adverbs (`seamlessly`, `easily`), articles, generic
  field nouns, marketing fluff. Prefer emitting NO sentence over one with
  junk tokens. Reference implementation: `collect_targeted_offer_terms` +
  `_skillish_score` in `app/utils/cv_summary_adaptation.py`. Regression
  tests live in `tests/test_positioning_hierarchy.py`. Reference incident:
  Mistral AI run 2026-04-20 emitted
  `"Atouts pertinents pour Mistral AI : technology, designed, integrate.
  Atouts pertinents pour Mistral AI : seamlessly, into, cloud."` — five
  junk tokens and one legitimate skill — because the selector used
  length/stopword filters only (no skill-shape check, no profile ranking,
  no deduplication against an existing positioning sentence).
- **Positioning render contract (MANDATORY)**: when a positioning sentence is
  present, final rendering must preserve it visibly inside the final summary
  instead of stripping it from HTML/PDF output. The sentence should read
  naturally, echo the target company/offer, and remain grounded in
  profile-backed or offer-backed terms selected by the hierarchy above.
  Existing positioning text may be preserved only if it remains competitive
  against the renderer's recomputed candidate terms; if the stored sentence is
  weaker, noisier, or less aligned than the recomputed offer/profile mix, the
  renderer must normalize casing/accents and rebuild it.
- **Offer-only term placement contract (MANDATORY)**: pure offer-only terms
  (supported by the offer but not directly evidenced in the profile) may
  appear only inside the natural positioning sentence of the profile block.
  They must NOT be rendered as proven hard skills, experience bullets, or
  project facts unless profile evidence or a coherent implicit inference
  supports them. Implicit inference is allowed when the profile already shows
  adjacent evidence (for example Python + model benchmarking + AI project
  context), but must remain phrased as positioning or transferable relevance,
  not as a fabricated past responsibility.
- **Photo invariant (MANDATORY)**: the profile photo must appear in the
  rendered CV regardless of template choice, user HTML edits, or history
  reopen — photo presence is a product invariant. When a user edits the
  raw HTML in the template editor, do NOT discard the edits to regenerate
  from template; instead **inject** the `<img>` tag non-destructively into
  the saved HTML. Reference implementation: `ensure_photo_in_raw_html` in
  `app/utils/cv_html_photo_inject.py`, wired into
  `app/views/template_preview_window.py::generate_dynamic_html`.
  Regression tests live in `tests/test_photo_invariant.py`. Reference
  incident: Mistral AI 2026-04-21 shipped a CV with no photo because
  `raw_html_is_user_edited=True` disabled the bypass that was the only
  re-injection path. Fix: inject, don't bypass.
- **Positioning keywords prefer multi-word phrases (MANDATORY)**: the
  positioning sentence must surface multi-word skill phrases (`REST API`,
  `test automation`, `model inference`) over bare single tokens. Single
  tokens are only legitimate as acronyms (SQL, REST, API, ML) or proper
  nouns (Docker, Python, Kubernetes). Bare verbs (`believe`, `build`,
  `work`), pronouns (`us`, `we`, `you`), and generic task nouns (`tasks`,
  `things`, `items`) are HARD-rejected by `_POSITIONING_HARD_BLOCKLIST`
  in `app/utils/cv_summary_adaptation.py`. Multi-word compounds get a
  `+2` score bonus in `_skillish_score`, plus `+1` when any phrase
  token overlaps profile lemmas. Regression tests live in
  `tests/test_positioning_keywords_r2.py`. Reference incident: Mistral
  AI 2026-04-21 emitted `"Atouts pertinents pour Mistral Ai: api,
  believe, tasks."` — three bare tokens, none a skill — because the
  blocklist lacked common verbs/task-nouns and the scorer weighted
  multi-word compounds at only `+1`.
- **Clip-repair-at-source (MANDATORY)**: every code path that polishes or
  re-extracts a bullet from the profile must route through
  `_polish_experience_fragment` in `app/utils/cv_postprocessing.py`, and
  that function must strip trailing `…` / `...` / dangling connectors on
  entry (before any further processing). The pipeline orchestrator's
  alignment-retry loop must also run a final
  `_repair_clipped_bullets` + `_dedup_fuzzy_highlights` pass before
  returning success, so no clipped-twin survives retries. Regression
  tests live in `tests/test_bullet_dedup_regression_r1.py`. Reference
  incident: Mistral AI 2026-04-21 re-shipped a clipped bullet
  `"Ingénieur QA en alternance - Concevoir, exécuter et suivre des…"`
  next to its full-length twin because `_polish_experience_fragment`
  didn't strip the ellipsis on entry, so clipped fragments re-entered
  merge paths where fuzzy dedup couldn't match them.
- **Experience render-selection contract (MANDATORY)**: final CV rendering
  must protect the most aligned experience first, then compress lower-priority
  roles. The anchor role may keep a richer sentence budget than the others
  when multiple roles compete for space, but all rendered details must still
  favor strong action verbs and explicit impact when available.
  Profile-derived experience descriptions must remain available as a rich
  internal candidate pool before offer-alignment scoring. Do not cap source
  extraction to the first 4-6 sentences before ranking, because late sentences
  often contain the strongest proof (named tools, QA deliverables, automation
  benchmarks, quantified impact, AI/innovation work). Display budgets apply
  after scoring/compaction, not during source-candidate extraction.
  Rendered role order itself must remain reverse-chronological; use relevance
  to allocate detail, not to reshuffle chronology.
  Company-description prose is supporting context only: it may inform weak
  sector inference or tie-breaking, but it must not outrank action/impact
  evidence and should usually be omitted from the rendered bullet list.
- **Experience tense guidance contract (MANDATORY)**: experience detail
  editing / "Visualiser les détails" must explicitly tell the user which
  tense to use from the role dates: current roles use present-tense action
  verbs; ended roles use past-tense action verbs. This guidance is editorial
  support, not permission to invent metrics or rewrite source facts. Do not
  maintain renderer-side language-wide verb replacement lists; tense issues
  should be surfaced to the user unless a safe, language-aware rewriter exists.
- **Featured-skills ranking contract (MANDATORY)**: compact hard skill/tool
  chips must be ranked against the target offer and may be sourced from
  explicit profile evidence: `skills`, projects, education/formations,
  certifications, and experience text. Experience/project/education evidence
  may create a chip only when the extracted label is compact, skill-shaped,
  source-backed, and offer-aligned; never render raw narrative fragments as
  chips. When a vague comparative skill is backed by explicit tool names in
  source evidence, prefer a compact comparative label such as
  `Benchmark Playwright / Cypress / Selenium` over a vague wording or an
  invented direct-usage claim. For strongly targeted offers, prefer compact
  grouped chips over flat keyword lists when this improves proof and
  hierarchy, but derive group labels from `{job_title}` and requirement-heavy
  offer evidence for the current profession/sector during generation, not in
  renderer-side fallback code. Soft skills must not compete with hard skill
  chips; render them only when not already proved inside experience bullets.
  Do not backfill
  low-scoring/noisy skill candidates just to reach a visual chip quota: a
  shorter credible skill list is better than ten weak chips.
- **Offer-ranked skill theme contract (MANDATORY)**: source-backed thematic
  fallback categories such as `QA & tests`, `API & data`, `Automation`,
  `AI & software quality`, `Data & BI`, or future profession-specific groups
  are quality helpers, not global priorities. They may appear when the profile
  supports them, but their visible order and survival must be driven by the
  target offer score, not by the mere presence of a profile keyword. A QA
  profile applying to a QA role should still surface `QA & tests` first; the
  same profile applying to another role must let better offer-aligned blocks
  outrank QA. When themed blocks miss profile-backed skills that are strongly
  aligned with the offer, add a generic role-aligned block rather than forcing
  those skills into a wrong profession taxonomy. Keep the default skill-block
  budget at 4; allow 5 only when the target offer exists, at least two
  experience/project sources are offer-aligned, and the fifth block has a
  positive offer score. This exception must remain compatible with the
  one-page fit-to-page contract.
- **Company-description filter contract (MANDATORY)**: renderer-side guards
  that suppress employer-description prose must stay narrow. Reject true
  intros such as `Company: filiale...` or `Employer - Groupe...`, but do not
  drop action/impact bullets just because they contain an early colon or dash
  (for example `Data platform: reduced latency...`).
- **Sector/industry signal contract (MANDATORY)**: sector or industry context
  may be inferred softly from employer/context text and used only as a minor
  ranking or wording bonus. It must never be a hard gate, never override
  stronger offer-skill/profile evidence, and never justify invented content.
- **Offer keyword extraction contract (MANDATORY)**: offer-keyword extraction
  must prioritize requirement-heavy sections first (`Role summary`, `What you
  will do`, `About you`, `Ideal if`, responsibilities, stack/tools, required
  skills). Marketing, culture, benefits, remote-policy, and hiring-process
  sections are low-priority context only. They may inform sector/company tone
  lightly, but must not dominate extracted keywords or downstream alignment.
- **Explicit tool naming contract (MANDATORY)**: when the profile or offer
  evidences concrete named tools, software, platforms, systems, suites, or
  frameworks, generated summary/skills/highlights should prefer naming those
  concrete products explicitly over vague wording like "outils", "logiciels",
  "plateformes", "frameworks", "outils d'automatisation", or
  "outils de facturation" whenever space allows.
- **Vague tooling phrase contract (MANDATORY)**: generic tooling categories
  (`automation tools`, `CRM software`, `outils de facturation`, etc.) are
  acceptable only when no concrete named product is available in the source.
  If named products exist in the profile or offer, the generator must prefer
  those names and treat the vague category as fallback context only.
- **Named-tool detection contract (MANDATORY)**: capitalization alone is not
  enough to classify a fragment as a tool. Tool detection must favor
  tool-shaped tokens (acronyms, product names, symbolic tokens like
  `llama.cpp`, `C#`, `dbt`, `open-webui`) and scan only tool-relevant fields;
  names, locations, company labels, and headings must not consume the
  `PROFILE_TOOL_HINTS` budget.
- **Source-file encoding invariant (MANDATORY)**: every tracked source file
  (`.py`, `.md`, `.txt`, `.bat`, `.sh`, `.json`, `.yaml`, `.html`, `.css`,
  `.ini`, `.toml`) MUST be saved as **UTF-8 without BOM**. Any edit that
  produces mojibake signatures (`Ã©`, `Ã¨`, `Ãª`, `Ã `, `Ã§`, `Ã´`, `Ã»`,
  `Ã®`, `â€™`, `â€œ`, `â€"`, `â€¦`, `Â«`, `Â»`, or `ðŸ`-prefixed broken
  emojis) must be rejected and redone with correct encoding. When
  reading/writing files from Python, always pass `encoding='utf-8'`
  explicitly. On Windows, when content contains CRLF and non-ASCII
  characters, use `Path.write_bytes(content.encode('utf-8'))` instead of
  `Path.write_text(...)` to avoid `\r\n → \r\r\n` doubling. JSON dumps
  that ship Unicode text must use `ensure_ascii=False` (the one exception
  is `profile_json.py`'s SHA-256 fingerprint, which must stay
  deterministic ASCII). Never commit code or docs containing mojibake —
  if a scan surfaces `Ã©`/`â€™`/`ðŸ` in production files, treat it as a
  bug, not a style preference. Reference audit: 2026-04-22 found 7 files
  still affected (`app/views/panels/job_application_panel.py`,
  `app/utils/universal_gpu_adapter.py`, `app/workers/llm_worker.py`,
  `app/workers/qwen_manager.py`, `tests/pipeline/test_export_manager_quality.py`,
  `docs/STRUCTURE.md`, `scripts/cleanup_reset.bat`) despite the
  2026-03-01 byte-level fix. Legitimate fix-maps in `app/utils/text_norm.py`,
  `app/views/text_cleaner.py`, `app/utils/ui_text.py`, and archived
  `scripts/archive/legacy_tools/*` are exempt — those contain the
  patterns by design as replacement keys.

## Additional CV Contracts
- **Final experience dedup contract (MANDATORY)**: every final CV payload path
  must run cross-entry experience dedup before one-page budgeting/export. Use
  `_dedup_experience_sections_in_place` / `_dedup_experience_entries` in
  `app/utils/cv_postprocessing.py`. Dedup may merge retries that differ only
  by wording or date formatting (`09/2021` vs `2021-09`), but it must NOT
  merge two genuinely distinct stints sharing the same company/title when
  their normalized periods conflict. Regression coverage lives in
  `tests/test_retry_loop_experience_dedup.py`,
  `tests/test_experience_dedup_regression.py`, and
  `tests/contracts/test_cv_postprocessing_contract.py`.
- **Targeted-summary candidate contract (MANDATORY)**: the positioning
  sentence must surface profile-backed aligned skills/talents first when such
  signal exists. `missing_summary_terms` alone is not a sufficient candidate
  pool: the selector must also consider aligned skill/talent terms already
  grounded in the profile, so cross-domain offer-only terms do not evict
  better profile-backed keywords. Profile soft skills may appear only as a
  separate supported fallback signal, never as hard skill chips or generic
  filler. Regression coverage
  lives in `tests/contracts/test_cv_postprocessing_contract.py` and
  `tests/utils/test_cv_summary_adaptation.py`.

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
- Local Windows caveat: broad `python -m black ...` currently hangs in this
  workspace. Do not run broad black formatting/checks until investigated;
  prefer `py_compile`, `git diff --check`, and targeted pytest validation
  unless the user explicitly asks for formatting.
- Imports: `python -m isort --check-only .`
- Types: `python -m mypy app cvextractor`
- Contracts: `python -m pytest tests/contracts -q`
- Mass apply: `python -m pytest tests/mass_apply -q`
- Always compile touched Python files and run the smallest relevant functional
  suite before concluding.
- Git ignore policy for tests: keep `tests/` and `tests/**` ignored in
  `.gitignore`. Do not add negated exceptions for test trees (`!tests/...`,
  `!scripts/tests/...`) and do not stage newly-created test files unless the
  user explicitly overrides this rule for a specific change.

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
- Preserve required reader-facing sections when source data exists: summary,
  contact, skills, experience/projects, education, and compact hobbies or
  interests. Do not drop projects/interests by default just because a CV is
  one page; use prioritized fit-to-page compression first.
- Keep each role to 2-4 concise bullet points whenever the source profile
  supports bullet rendering; prefer short action-led bullets over dense
  narrative paragraphs.
- Role-critical skills shown in the skill section should be proved somewhere
  visible when the profile contains that evidence. For example, API/data,
  automation, delivery, or domain tools should be retained in experience or
  project bullets instead of appearing only as isolated chips.
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
