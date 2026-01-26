"""LinkedIn extraction refactor package.

This namespace will progressively replace the legacy monolithic
`app.workers.linkedin_extractor` module with smaller, testable
components (scraper, parser, logger, orchestrator).
"""

from __future__ import annotations

__all__ = [
    "linkedin_extractor",
    "linkedin_scraper",
    "linkedin_parser",
    "linkedin_logger",
]
