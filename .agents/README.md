# Agentic Operations

This directory contains repository-local definitions for:
- `subagents/`: reusable specialist roles
- `skills/`: repeatable task checklists
- `hooks/`: hook policy and expected scripts
- `mcp/`: external tool usage rules

These files are documentation and invocation support. They do not replace the
root `AGENTS.md`; they operationalize it.

Recommended invocation order:
- `subagents/contract-guardian.md` first for any cross-layer contract change.
- `subagents/llm-runtime-worker.md` only for runtime/model-stage work.
- `subagents/mass-apply-worker.md` only for job sources, secrets, review, or
  bulk apply flows.

Current render/export contracts to preserve across agent runs:
- one-page CVs use measured fit-to-page compression, not CSS clipping
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
  featured project, certifications) instead of flattening content into a blob
- final rendered sentences must stay whole: no `...` / `…` truncation in the
  one-page HTML/PDF path; select better sentences instead of clipping them
- when a grounding-safe positioning sentence exists, keep it visible in the
  rendered summary, but do not preserve a stale/noisy stored sentence when a
  recomputed candidate is clearly better aligned
- build the rendered summary after retained blocks are selected so it does not
  repeat the same signals already visible in rendered experience bullets
- protect the most aligned experience first; lower-priority roles compress
  before the anchor role loses detail
- dense experience evidence should be fused into 2-4 coherent bullets instead
  of being dropped or expanded into too many bullets
- keep rendered experience order reverse-chronological; use relevance only to
  allocate detail, not to reshuffle the visible role order
- "Visualiser les détails" / profile detail editing must show tense guidance:
  present-tense action verbs for current roles, past-tense action verbs for
  ended roles, based on role dates; do not add renderer-side language-wide
  verb replacement lists
- compact skill chips may extend to roughly 10 visible items when the row-wrap
  stays clean; do not artificially collapse to 3-5 if the layout remains readable
- compact grouped skill chips are preferred for strongly targeted offers when
  they make the proof hierarchy clearer than flat keyword chips
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

If the execution environment does not support native sub-agent spawning, invoke
these definitions manually: copy the target sub-agent prompt, preserve its file
scope and guard-fous, then run only the targeted checks listed in the file.
