# Skill: cvmatch-contract-checklist

Use when a change touches schemas, DB models, profile mapping, generation,
history, export, or `mass_apply` payloads.

Checklist:
1. Identify all affected contracts.
2. Verify propagation across UI, JSON, DB, generation, export, history.
3. Run `tests/contracts`.
4. Record skipped scope explicitly.
