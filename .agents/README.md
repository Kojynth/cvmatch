# Agentic Operations

This directory contains repository-local definitions for:
- `subagents/`: reusable specialist roles
- `skills/`: repeatable task checklists
- `hooks/`: hook policy and expected scripts
- `mcp/`: external tool usage rules

These files are documentation and invocation support. They do not replace the
root `AGENTS.md`; they operationalize it.

Shared operating discipline:
- Diagnose and analyze before editing: reproduce or inspect the symptom, find
  the impacted contract, then patch the smallest relevant path.
- Ask a concise clarifying question when task scope, source data, or expected
  behavior is unclear and a wrong assumption could affect behavior, security,
  or CV contracts. If local context resolves it safely, state the assumption
  and proceed.

Recommended invocation order:
- `subagents/contract-guardian.md` first for any cross-layer contract change.
- `subagents/llm-runtime-worker.md` only for runtime/model-stage work.
- `subagents/mass-apply-worker.md` only for job sources, secrets, review, or
  bulk apply flows.

Current render/export contracts to preserve across agent runs:
- one-page CVs use measured fit-to-page compression, not CSS clipping
- WebEngine PDF export must not mutate the visible preview. Print from a
  dedicated hidden `QWebEngineView` loaded with the same final HTML, then clean
  it up after success/error; do not call `setHtml`, print-fit JS, or
  `printToPdf` on the visible preview view except as an explicit fallback.
- final header contact methods are explicit links; placeholder link labels are forbidden
- target subtitle semantics are explicit candidature semantics:
  `Poste visé: {job_title} | {company}` / `Target role: {job_title} | {company}`,
  not an employer-looking label
- print/PDF contract = single canonical print block, A4 margins, no forced
  `body` A4 height, no `overflow: hidden`, and `break-inside: avoid` on
  structured experience/project/education blocks
- direct WeasyPrint exports must apply the `PDF_ONE_PAGE_FIT_CSS` fallback in
  `app/controllers/export_manager.py`; preview fit CSS alone does not protect
  final PDFs
- one-page render must keep structured sections (summary, skills, experience,
  featured project, certifications, and compact interests/hobbies when present)
  instead of flattening content into a blob
- final rendered sentences must stay whole: no `...` / `…` truncation in the
  one-page HTML/PDF path; select better sentences instead of clipping them
- when a grounding-safe positioning sentence exists, keep it visible in the
  rendered summary with `{company}` visible in a natural `{job_title}`
  relevance statement; do not preserve a stale/noisy stored sentence or a
  formulaic keyword dump when a recomputed candidate is clearly better aligned
- build the rendered summary after retained blocks are selected so it does not
  repeat the same signals already visible in rendered experience bullets
- protect the most aligned experience first; lower-priority roles compress
  before the anchor role loses detail
- dense experience evidence should be rewritten by the LLM into 2-4 new
  coherent bullets instead of being dropped, copied verbatim, expanded into too
  many bullets, or mechanically joined by the renderer with semicolons; keep
  high-signal keywords, named tools, and role vocabulary inside the rewritten
  bullets when they carry offer/profile alignment

Git hygiene rule for tests:
- Keep `tests/` and `tests/**` ignored in `.gitignore`.
- Do not add negated exceptions for test paths (`!tests/...`,
  `!scripts/tests/...`) and do not stage newly-created test files unless the
  user explicitly overrides this rule for that specific change.
- keep rendered experience order reverse-chronological; use relevance only to
  allocate detail, not to reshuffle the visible role order
- "Visualiser les détails" / profile detail editing must show tense guidance:
  present-tense action verbs for current roles, past-tense action verbs for
  ended roles, based on role dates; do not add renderer-side language-wide
  verb replacement lists
- compact skill chips may extend to roughly 10 visible items when the row-wrap
  stays clean; do not artificially collapse to 3-5 if the layout remains readable
- compact grouped skill chips are preferred for strongly targeted offers when
  they make the proof hierarchy clearer than flat keyword chips, but grouping
  must be driven by `{job_title}` and requirement-heavy offer evidence for any
  profession/sector, not by a hardcoded company/profile/tech-only taxonomy;
  renderer fallback code must not invent those grouped categories
- featured skill chips come from the profile `skills` pool first; use
  experience/project evidence to reprioritize or compactly rewrite labels, but
  do not mint extra chips directly from narrative bullets
- do not backfill weak/noisy skill chips just to reach a visual max; fewer
  credible chips are better than filler, except when the profile only exposes
  a small compact skill pool that already fits the visible budget
- hide the generic soft-skill section when those behaviours are already
  integrated into experience bullets
- when a comparative skill is grounded by named tools, prefer a compact label
  such as `Benchmark Playwright / Cypress / Selenium`
- company-description prose is weak context only; rendered experience details
  should prefer the strongest offer-aligned action/impact sentences
- keep company-description filters narrow enough not to drop action bullets
  that use an early colon or dash
- pure offer-only terms belong in the natural positioning sentence only; do
  not present them elsewhere as proven facts unless profile evidence supports
  a coherent implicit inference
- offer-keyword extraction must prioritize requirement-heavy sections over
  company marketing / benefits / remote / hiring-process text
- named tools/software/platforms from the profile or offer should replace
  vague tooling categories whenever the source contains those concrete names
- skill display must deduplicate repeated tools across flat chips and grouped
  comparative labels; role-critical tools shown as skills should also remain
  visible in experience/project proof when the source profile contains that
  evidence

If the execution environment does not support native sub-agent spawning, invoke
these definitions manually: copy the target sub-agent prompt, preserve its file
scope and guard-fous, then run only the targeted checks listed in the file.
