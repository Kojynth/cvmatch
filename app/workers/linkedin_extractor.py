"""Qt thread wrapper around the refactored LinkedIn pipeline."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Optional

from PySide6.QtCore import QThread, Signal

from app.utils.safe_log import get_safe_logger
from .linkedin.linkedin_extractor import LinkedInExtractor as ModularLinkedInExtractor
from .linkedin.linkedin_extractor import LinkedInExtractionParams as ModularParams

logger = get_safe_logger(__name__)


@dataclass
class LinkedInExtractionParams:
    """Backwards-compatible params (subset used by modular pipeline)."""

    method: str = "crawler"
    extract_recommendations: bool = True
    delay_between_requests: float = 2.0
    use_headless_browser: bool = True
    extract_connections: bool = False
    respect_robots_txt: bool = True


class LinkedInExtractor(QThread):
    """Legacy QThread worker delegating to the modular pipeline."""

    progress_updated = Signal(int, str)
    section_extracted = Signal(str, dict)
    extraction_completed = Signal(dict)
    extraction_failed = Signal(str)

    def __init__(self, linkedin_url: str, params: Optional[LinkedInExtractionParams] = None):
        super().__init__()
        self.linkedin_url = linkedin_url
        self.params = params or LinkedInExtractionParams()
        self.results: Dict[str, object] = {}
        self._modular = None
        self._use_modular = os.getenv("LINKEDIN_REFACTOR_PIPELINE", "1").lower() in {"1", "true", "yes"}

    def run(self) -> None:
        try:
            if not self._use_modular:
                raise RuntimeError("Legacy pipeline retiré; définir LINKEDIN_REFACTOR_PIPELINE=1 est désormais obligatoire.")
            self._run_modular_pipeline()
        except Exception as exc:
            logger.error("LinkedIn extraction failed: %s", exc)
            self.extraction_failed.emit(str(exc))

    def _run_modular_pipeline(self) -> None:
        self.progress_updated.emit(10, "Initialisation pipeline LinkedIn…")
        params = ModularParams(
            profile_url=self.linkedin_url,
            include_recommendations=self.params.extract_recommendations,
            scrape_timeout=int(max(5, self.params.delay_between_requests * 10)),
        )
        self._modular = ModularLinkedInExtractor(params)
        self.progress_updated.emit(40, "Analyse du profil LinkedIn…")
        data = self._modular.extract()
        from ...utils.profile_json import build_profile_json_from_source, has_profile_json_content
        from ...utils.json_strict import JsonStrictError

        try:
            profile_json = build_profile_json_from_source(payload=data, source="linkedin")
            if has_profile_json_content(profile_json):
                data["profile_json"] = profile_json
        except JsonStrictError as exc:
            logger.error("Profile JSON extraction failed: %s", exc)
            raise
        except Exception as exc:
            logger.error("Profile JSON extraction failed: %s", exc)
            raise

        self.results.update(data)
        self.section_extracted.emit("profile", data.get("profile", {}))
        self.extraction_completed.emit(self.results)
        self.progress_updated.emit(100, "Extraction LinkedIn terminée")

    def cancel(self) -> None:
        if self._modular:
            self._modular.cancel()


__all__ = ["LinkedInExtractor", "LinkedInExtractionParams"]
