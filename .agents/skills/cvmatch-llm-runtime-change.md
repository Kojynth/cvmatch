# Skill: cvmatch-llm-runtime-change

Use when touching model loading, retries, stage subprocesses, or memory policy.

Checklist:
1. Preserve deterministic fallback JSON.
2. Preserve subprocess compatibility and env handling.
3. Validate stage-specific memory overrides.
4. Run targeted `tests/pipeline` or `tests/contracts` scopes plus compile checks.
