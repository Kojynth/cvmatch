from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from PySide6.QtCore import QThread, Signal

from app.config.feature_flags import ENABLE_CV_PIPELINE
from cvextractor.pipeline import create_pipeline_with_personal_data
from cvextractor.pipeline.context import ExtractionContext


@dataclass
class ExtractionParams:
    """Lightweight configuration holder kept for API compatibility."""

    model_name: str = "rule_based"
    max_tokens: int = 512
    temperature: float = 0.1
    extract_detailed_skills: bool = True
    extract_soft_skills: bool = True
    extract_achievements: bool = True
    extract_linkedin_info: bool = True
    extract_references: bool = True
    language: str = "fr"
    include_confidence_scores: bool = False
    enable_contact_protection: bool = True
    require_spaced_at_for_role_company: bool = True
    strict_domain_checking: bool = True
    exp_fallback_window_size: int = 30
    enable_duplicate_detection: bool = True


def _empty_pipeline_fallback(*args, **kwargs) -> Dict[str, Any]:
    return {}


class CVExtractorWorker:
    """Thin wrapper around the modular pipeline (legacy worker replacement)."""

    def __init__(self) -> None:
        self._use_pipeline = bool(ENABLE_CV_PIPELINE)

    @property
    def use_cv_pipeline(self) -> bool:
        return self._use_pipeline

    def extract_from_lines(
        self,
        lines: Sequence[str],
        sections: Optional[Mapping[str, Any]] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        pipeline = create_pipeline_with_personal_data(
            fallback=_empty_pipeline_fallback,
            enabled=True,
            fallback_on_error=False,
        )

        context = ExtractionContext(
            lines=list(lines or []),
            sections=sections or {},
            metadata=metadata or {},
        )

        result = pipeline.run(context)
        payload = dict(result.payload)

        modules = [asdict(module) for module in result.modules]
        errors = [asdict(error) for error in result.errors]

        return {
            "payload": payload,
            "used_legacy": False,
            "used_pipeline": True,
            "modules": modules,
            "errors": errors,
            "legacy_payload": None,
        }


class CVExtractor(QThread):
    """Qt-compatible worker that delegates to the modular pipeline."""

    progress_updated = Signal(int, str)
    section_extracted = Signal(str, dict)
    extraction_completed = Signal(dict)
    extraction_failed = Signal(str)

    ml_stage = Signal(str)
    ml_log = Signal(str)

    def __init__(
        self,
        cv_path: str,
        params: Optional[ExtractionParams] = None,
        debug_opts: Optional[Any] = None,
        raw_text: Optional[str] = None,
    ) -> None:
        super().__init__()
        self.cv_path = Path(cv_path)
        self.params = params or ExtractionParams()
        self.debug_opts = debug_opts
        self.raw_text = raw_text or ""
        self.results: Dict[str, Any] = {}
        self._worker = CVExtractorWorker()

    def run(self) -> None:  # pragma: no cover - Qt thread
        try:
            text = self._load_cv_text()
            lines = text.splitlines()
        except Exception as exc:  # pragma: no cover - filesystem issues
            message = f"Lecture impossible: {exc}"
            self.extraction_failed.emit(message)
            return

        try:
            self.progress_updated.emit(5, "Initialisation du pipeline modulaire…")
            result = self._worker.extract_from_lines(lines)
            self.results = result["payload"]
        except Exception as exc:  # pragma: no cover - pipeline errors
            self.extraction_failed.emit(str(exc))
            return

        try:
            from app.utils.profile_json import build_profile_json_from_source, has_profile_json_content
            from app.utils.json_strict import JsonStrictError

            profile_json = build_profile_json_from_source(
                payload=self.results,
                raw_text=text,
                source="cv",
            )
            if has_profile_json_content(profile_json):
                self.results["profile_json"] = profile_json
        except JsonStrictError as exc:
            self.extraction_failed.emit(str(exc))
            return
        except Exception as exc:
            self.extraction_failed.emit(str(exc))
            return

        for section, payload in self.results.items():
            if isinstance(payload, dict):
                self.section_extracted.emit(section, payload)
            else:
                self.section_extracted.emit(section, {"items": payload})

        self.progress_updated.emit(100, "Extraction terminée")
        self.extraction_completed.emit(self.results)

    def _load_cv_text(self) -> str:
        if self.raw_text:
            return self.raw_text

        extension = self.cv_path.suffix.lower()
        parser_error: Optional[Exception] = None
        try:
            from app.utils.parsers import DocumentParser

            parser = DocumentParser()
            if extension in parser.supported_formats:
                try:
                    return parser.parse_document(str(self.cv_path))
                except ImportError:
                    raise
                except Exception as exc:
                    parser_error = exc
        except ImportError:
            raise
        except Exception as exc:
            parser_error = exc

        # Fallback for plain text files with unknown extensions.
        try:
            return self.cv_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            for encoding in ("utf-8-sig", "cp1252", "latin-1"):
                try:
                    return self.cv_path.read_text(encoding=encoding)
                except UnicodeDecodeError:
                    continue
        except Exception:
            if parser_error is not None:
                raise parser_error
            raise
        try:
            return self.cv_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            if parser_error is not None:
                raise parser_error
            raise


__all__ = [
    "ExtractionParams",
    "CVExtractor",
    "CVExtractorWorker",
]
