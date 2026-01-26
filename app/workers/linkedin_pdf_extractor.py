"""Worker for LinkedIn PDF extraction (re-uses CV pipeline)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QThread, Signal

from cvextractor import extract as extract_cv

from ..logging.safe_logger import get_safe_logger
from ..config import DEFAULT_PII_CONFIG

LOGGER = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


class LinkedInPdfExtractor(QThread):
    """Extract LinkedIn data from an exported PDF profile."""

    progress_updated = Signal(int, str)
    extraction_completed = Signal(dict)
    extraction_failed = Signal(str)

    def __init__(self, pdf_path: str, *, include_provenance: bool = False) -> None:
        super().__init__()
        self._pdf_path = Path(pdf_path)
        self._include_provenance = include_provenance

    def run(self) -> None:  # noqa: D401 - Qt thread entry point
        try:
            if not self._pdf_path.exists():
                raise FileNotFoundError(f"LinkedIn PDF introuvable: {self._pdf_path}")

            self.progress_updated.emit(5, "Lecture du PDF LinkedIn…")
            extraction_result = extract_cv(str(self._pdf_path))
            self.progress_updated.emit(60, "Analyse des sections LinkedIn…")

            linkedin_payload = extraction_result.to_dict(include_provenance=self._include_provenance)
            linkedin_payload['source'] = 'linkedin_pdf'
            linkedin_payload['source_file'] = str(self._pdf_path)

            raw_text = ""
            try:
                from ..utils.parsers import DocumentParser

                raw_text = DocumentParser().parse_document(str(self._pdf_path))
            except Exception as exc:
                LOGGER.warning("Profile JSON source text unavailable: %s", exc)

            from ..utils.profile_json import build_profile_json_from_source, has_profile_json_content
            from ..utils.json_strict import JsonStrictError

            try:
                profile_json = build_profile_json_from_source(
                    payload=linkedin_payload,
                    raw_text=raw_text,
                    source="linkedin",
                )
                if has_profile_json_content(profile_json):
                    linkedin_payload["profile_json"] = profile_json
            except JsonStrictError as exc:
                LOGGER.error("Profile JSON extraction failed: %s", exc)
                raise
            except Exception as exc:
                LOGGER.error("Profile JSON extraction failed: %s", exc)
                raise

            self.progress_updated.emit(100, "Extraction LinkedIn PDF terminee")
            self.extraction_completed.emit(linkedin_payload)
        except Exception as exc:  # pylint: disable=broad-except
            LOGGER.error("Extraction LinkedIn PDF échouée | path=%s err=%s", self._pdf_path, exc)
            self.extraction_failed.emit(str(exc))


__all__ = ["LinkedInPdfExtractor"]
