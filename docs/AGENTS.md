# Repository Guidelines

## Project Structure & Module Organization
The PySide6 client lives in `app/` with controllers, views, widgets, workers, and shared utils. Extraction pipelines live in `cvextractor/`, powering both the GUI and automation flows. Regression suites sit in `tests/`, while `development/tests/` hosts exploratory cases and fixtures, and `development/dev_tools/` covers diagnostics. Benchmarking and maintenance scripts live in `tools/` and `scripts/` (notably `enhanced_cli.py`, installer wrappers, PII cleaners), with reference docs in `docs/`, assets in `resources/`, and environment templates in `config/`.

## Build, Test, and Development Commands
`poetry install` (add `--with ai` for transformer extras) prepares dependencies. Launch the GUI with `poetry run cvmatch`; automation flows use `poetry run cvmatch-cli` or `poetry run python scripts/enhanced_cli.py`. Platform helpers `cvmatch.bat` and `./cvmatch.sh` wrap those entrypoints; hydrate model caches once per workstation via `installer_AI.bat` or `./installer_AI.sh`. Run `poetry run pre-commit run --all-files` to execute Black, isort, Flake8, and safety hooks.

## Coding Style & Naming Conventions
Format with Black (88 columns, 4-space indentation) via `poetry run black app cvextractor tests`. Keep modules, functions, and signals in `snake_case`, classes in `PascalCase`, constants in `UPPER_SNAKE`, and mirror Qt object names with their Python attributes. Normalise imports through `poetry run isort .` and keep mypy clean with `poetry run mypy`, adding annotations for public APIs.

## Testing Guidelines
Run `poetry run pytest` before every PR. Tag long flows with `@pytest.mark.slow` and skip them during quick passes via `pytest -m "not slow"`. Prototype work can live in `development/tests/`, reusing data from its `fixtures/` directory after anonymising CV samples. Generate coverage with `pytest --cov=app --cov=cvextractor --cov-report=term-missing` and share HTML output in `reports/coverage/` when reviewers need artefacts.

## Commit & Pull Request Guidelines
Write imperative commit subjects (`tighten diploma parsing`) and reuse the emoji severity pattern from history when flagging hotfixes (e.g., `🔒 CRITICAL: ...`). Reference tickets in footers (`Refs #123`), separate behavioural, UI, and tooling changes, and list validation commands in the PR body. Attach screenshots for UI work and mention cache or model steps reviewers must replicate.

## Security & Data Handling
Use the safe logging wrappers (`app.utils.safe_log.get_safe_logger` or `cvextractor.utils.log_safety.create_safe_logger_wrapper`) instead of bare `logging` when handling profile content. Reference users by internal IDs or hashed tokens rather than names/emails in artefacts, metrics, or filenames. Keep secrets in env files under `config/`, scrub data with `python scripts/clean_pii_logs_emergency.py` or the masking switches in `scripts/enhanced_cli.py`, and leave caches (`.hf_cache/`, `cache/`, `logs/`) untracked so each contributor refreshes them locally.

