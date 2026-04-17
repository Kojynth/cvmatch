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

If the execution environment does not support native sub-agent spawning, invoke
these definitions manually: copy the target sub-agent prompt, preserve its file
scope and guard-fous, then run only the targeted checks listed in the file.
