# Skill: cvmatch-llm-runtime-change

Use when touching model loading, retries, stage subprocesses, or memory policy.

Checklist:
1. Preserve deterministic fallback JSON.
2. Preserve subprocess compatibility and env handling.
3. Validate stage-specific memory overrides.
4. If output quality/rendering is affected, preserve the fit-to-page one-page
   contract: prioritized content, measured height, controlled compression,
   no CSS clipping, explicit clickable contacts, explicit target subtitle,
   structured sections instead of a generic blob, no renderer-side
   ellipsis/clamp truncation, a short natural positioning sentence when
   grounded, and experience selection that prefers action/impact evidence over
   company-description text.
5. If offer extraction/targeting is affected, prioritize requirement-heavy
   offer sections over company marketing/benefits text, keep pure offer-only
   vocabulary in the positioning sentence unless profile evidence supports a
   coherent implicit inference elsewhere, and prefer explicit QA/automation
   tool names when the profile contains them.
6. Run targeted `tests/pipeline` or `tests/contracts` scopes plus compile checks.
