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
  `Poste vise: {job_title} | {company}` / `Target role: {job_title} | {company}`,
  not an employer-looking label
- print/PDF contract = single canonical print block, A4 margins, no forced
  `body` A4 height, no `overflow: hidden`, and `break-inside: avoid` on
  structured experience/project/education blocks
- one-page render must keep structured sections (summary, skills, experience,
  featured project, certifications) instead of flattening content into a blob
- final rendered sentences must stay whole: no `...` / `…` truncation in the
  one-page HTML/PDF path; select better sentences instead of clipping them
- when a grounding-safe positioning sentence exists, keep it as the closing
  sentence of the rendered summary
- company-description prose is weak context only; rendered experience details
  should prefer the strongest offer-aligned action/impact sentences

If the execution environment does not support native sub-agent spawning, invoke
these definitions manually: copy the target sub-agent prompt, preserve its file
scope and guard-fous, then run only the targeted checks listed in the file.
