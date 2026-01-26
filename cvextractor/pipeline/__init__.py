"""Scaffolding for the modular CV extraction pipeline."""

from .builder import build_personal_data_modules, create_pipeline_with_personal_data
from .context import ExtractionContext
from .pipeline import ExtractionPipeline
from .result import ModuleError, ModuleReport, PipelineResult

__all__ = [
    "build_personal_data_modules",
    "create_pipeline_with_personal_data",
    "ExtractionContext",
    "ExtractionPipeline",
    "ModuleError",
    "ModuleReport",
    "PipelineResult",
]
