# Skill: cvmatch-llm-runtime-change

Use when touching model loading, retries, stage subprocesses, or memory policy.

Checklist:
1. Preserve deterministic fallback JSON.
2. Preserve subprocess compatibility and env handling.
3. Validate stage-specific memory overrides.
4. If output quality/rendering is affected, preserve the fit-to-page one-page
   contract: prioritized content, measured height, controlled compression,
   no CSS clipping, explicit clickable contacts, explicit target subtitle,
   and structured sections instead of a generic blob.
5. Run targeted `tests/pipeline` or `tests/contracts` scopes plus compile checks.
