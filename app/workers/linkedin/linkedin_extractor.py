"""Future LinkedIn extraction orchestrator."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from .linkedin_logger import LinkedInLogger
from .linkedin_parser import LinkedInParser, SelectorConfig
from .linkedin_scraper import LinkedInScraper, ScraperConfig


@dataclass(slots=True)
class LinkedInExtractionParams:
    """Configuration contract for the refactored extractor."""

    profile_url: str
    include_recommendations: bool = False
    locale: str = "fr_FR"
    scrape_timeout: int = 30


class LinkedInExtractor:
    """Orchestrates scraper + parser + logger for LinkedIn."""

    def __init__(
        self,
        params: LinkedInExtractionParams,
        *,
        scraper: Optional[LinkedInScraper] = None,
        parser: Optional[LinkedInParser] = None,
        logger: Optional[LinkedInLogger] = None,
    ) -> None:
        self.params = params
        self._scraper = scraper or LinkedInScraper(
            ScraperConfig(
                profile_url=params.profile_url,
                timeout_seconds=params.scrape_timeout,
            )
        )
        if parser is None:
            selectors_dir = Path(__file__).resolve().parent / "config"
            selector_config = SelectorConfig.from_files(
                selectors_dir / "selectors.json",
                selectors_dir / "field_mappings.json",
            )
            parser = LinkedInParser(selector_config)
        self._parser = parser
        self._logger = logger or LinkedInLogger()

    def extract(self) -> Dict[str, Any]:
        html = self._scraper.fetch_html()
        parsed = self._parser.parse(html)
        if not self.params.include_recommendations:
            parsed.pop("recommendations", None)
        self._logger.log_summary(parsed.get("profile", {}))
        return parsed

    def cancel(self) -> None:
        """Allow UI to cancel the scraping thread."""

        if self._scraper and hasattr(self._scraper, "cancel"):
            self._scraper.cancel()


__all__ = [
    "LinkedInExtractor",
    "LinkedInExtractionParams",
]
