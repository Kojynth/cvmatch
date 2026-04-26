# Skill: cvmatch-public-repo-hygiene

Use before opening a PR from this public repository.

Checklist:
1. Run repo hygiene and PII checks.
2. Confirm no runtime artifacts or local backups are staged.
3. Confirm operational memory docs stay aligned with versioned source:
   `AGENTS.md`, `CLAUDE.md`, and any relevant `.agents/*` subagent/skill docs
   touched by the change.
4. Confirm `.gitignore` keeps `tests/` and `tests/**` ignored and does not add
   negated test exceptions such as `!tests/...` or `!scripts/tests/...`.
5. Confirm the changed-path test command is documented.
6. If render/export behavior changed, confirm the PR description or notes call
   out the updated one-page/render contract and any manual PDF validation gap.
7. If WebEngine PDF export changed, confirm the notes say whether the visible
   preview remains stable during export and cite the hidden-export-view
   regression test.
