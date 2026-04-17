# Hook Policy

- `python-compile`: compile touched Python files
- `repo-hygiene`: reject runtime artifacts, backups, and ghost source files
- `no-pii-artifacts`: block obvious real email addresses in tracked text files
- `import-boundaries`: keep views/controllers away from direct network adapters

Hooks are configured through `.pre-commit-config.yaml` and helper scripts under
`scripts/diagnostics/`.
