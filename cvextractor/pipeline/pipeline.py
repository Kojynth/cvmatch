"""Orchestrator for the modular CV extraction pipeline."""

from __future__ import annotations

import inspect
from typing import Any, Callable, Dict, Iterable, List, Sequence, Tuple

from app.logging.safe_logger import get_safe_logger

from cvextractor.modules.base_extractor import BaseExtractor
from cvextractor.pipeline.context import ExtractionContext
from cvextractor.pipeline.result import ModuleError, ModuleReport, PipelineResult

FallbackCallable = Callable[..., Dict[str, object]]
PostProcessor = Callable[
    [Dict[str, object], ExtractionContext],
    Tuple[Dict[str, object], List[Dict[str, Any]]],
]


class ExtractionPipeline:
    """Pipeline skeleton with legacy fallback support."""

    def __init__(
        self,
        modules: Sequence[BaseExtractor],
        fallback: FallbackCallable,
        *,
        enabled: bool = False,
        fallback_on_error: bool = True,
        post_processors: Sequence[PostProcessor] | None = None,
    ) -> None:
        self._modules = list(modules)
        self._fallback = fallback
        self.enabled = enabled
        self.fallback_on_error = fallback_on_error
        self._post_processors = list(post_processors or [])
        self.logger = get_safe_logger("cvextractor.pipeline")

    @property
    def modules(self) -> Sequence[BaseExtractor]:
        return tuple(self._modules)

    def with_modules(self, modules: Iterable[BaseExtractor]) -> "ExtractionPipeline":
        """Return a copy of the pipeline with a new module sequence."""
        clone = ExtractionPipeline(
            modules=list(modules),
            fallback=self._fallback,
            enabled=self.enabled,
            fallback_on_error=self.fallback_on_error,
        )
        return clone

    def run(
        self, context: ExtractionContext, *, force_legacy: bool | None = None
    ) -> PipelineResult:
        """Execute the pipeline for the provided context."""
        use_legacy = (
            force_legacy
            if force_legacy is not None
            else not (self.enabled and self._modules)
        )
        if use_legacy:
            payload = self._invoke_fallback(context)
            return PipelineResult.legacy(payload)

        payload: Dict[str, object] = {}
        module_reports: List[ModuleReport] = []
        errors: List[ModuleError] = []
        post_processor_reports: List[Dict[str, Any]] = []

        for module in self._modules:
            module_name = module.__class__.__name__
            try:
                run_result = module.run(context)
                module_reports.append(
                    ModuleReport(
                        name=module_name,
                        section=module.section,
                        status="ok",
                        diagnostics=run_result.diagnostics,
                    )
                )
                if run_result.payload is not None:
                    payload[module.section] = run_result.payload
            except (
                Exception
            ) as exc:  # pragma: no cover - defensive, tested via unit tests
                message = f"{exc.__class__.__name__}: {exc}"
                errors.append(
                    ModuleError(
                        name=module_name,
                        section=getattr(module, "section", module_name),
                        message=message,
                    )
                )
                module_reports.append(
                    ModuleReport(
                        name=module_name,
                        section=getattr(module, "section", module_name),
                        status="error",
                    )
                )
                self.logger.exception(
                    "pipeline.module_failure",
                    extra={
                        "module_name": module_name,
                        "section": getattr(module, "section", module_name),
                    },
                )
                if self.fallback_on_error:
                    legacy_payload = self._invoke_fallback(context)
                    result = PipelineResult.legacy(legacy_payload)
                    result.errors.extend(errors)
                    result.modules.extend(module_reports)
                    return result

        if self._post_processors:
            processed_payload = dict(payload)
            for processor in self._post_processors:
                processor_name = getattr(processor, "__name__", repr(processor))
                try:
                    processed_payload, reports = processor(processed_payload, context)
                except Exception as exc:  # pragma: no cover - defensive path
                    self.logger.exception(
                        "pipeline.post_processor_failed",
                        extra={"processor": processor_name},
                    )
                    if self.fallback_on_error:
                        legacy_payload = self._invoke_fallback(context)
                        diagnostics = {
                            "post_processors": post_processor_reports
                            + [
                                {
                                    "name": processor_name,
                                    "status": "error",
                                    "message": f"{exc.__class__.__name__}: {exc}",
                                }
                            ]
                        }
                        result = PipelineResult.legacy(
                            legacy_payload, diagnostics=diagnostics
                        )
                        result.errors.extend(errors)
                        result.modules.extend(module_reports)
                        return result
                    continue

                if reports:
                    for report in reports:
                        post_processor_reports.append(
                            {
                                "name": processor_name,
                                **report,
                                "status": "ok",
                            }
                        )
            payload = processed_payload

        diagnostics: Dict[str, Any] = {}
        if post_processor_reports:
            diagnostics["post_processors"] = post_processor_reports

        return PipelineResult(
            payload=payload,
            used_legacy=False,
            modules=module_reports,
            errors=errors,
            diagnostics=diagnostics,
        )

    def _invoke_fallback(self, context: ExtractionContext) -> Dict[str, object]:
        """Call the legacy extraction entry point."""
        try:
            signature = inspect.signature(self._fallback)
        except (TypeError, ValueError):
            signature = None

        if signature and len(signature.parameters) == 1:
            return self._fallback(context)

        return self._fallback(context.lines, context.sections, context.metadata)
