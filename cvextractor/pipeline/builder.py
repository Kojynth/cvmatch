"""Factory helpers to assemble the modular extraction pipeline."""

from __future__ import annotations

from typing import Dict, Sequence

from cvextractor.modules.base_extractor import BaseExtractor
from cvextractor.modules.certifications import CertificationsExtractor
from cvextractor.modules.contact import ContactInfoExtractor
from cvextractor.modules.headline import HeadlineExtractor
from cvextractor.modules.interests import InterestsExtractor
from cvextractor.modules.languages import LanguagesExtractor
from cvextractor.modules.personal_info import PersonalInfoExtractor
from cvextractor.modules.projects import ProjectsExtractor
from cvextractor.modules.skills import SkillsExtractor
from cvextractor.modules.experience import ExperienceExtractor
from cvextractor.modules.education import EducationExtractor
from cvextractor.pipeline.pipeline import ExtractionPipeline, FallbackCallable
from cvextractor.shared.config import load_all_sections
from cvextractor.shared.post_processors import apply_post_processors


def build_personal_data_modules() -> Sequence[BaseExtractor]:
    """Instantiate the low-risk modular extractors."""
    config: Dict[str, Dict] = load_all_sections()
    return (
        PersonalInfoExtractor(config.get("personal_info")),
        ContactInfoExtractor(config.get("contact")),
        HeadlineExtractor(config.get("headline")),
        InterestsExtractor(config.get("interests")),
        LanguagesExtractor(config.get("languages")),
        SkillsExtractor(config.get("skills")),
        CertificationsExtractor(config.get("certifications")),
        ProjectsExtractor(config.get("projects")),
        ExperienceExtractor(config.get("experience")),
        EducationExtractor(config.get("education")),
    )


def create_pipeline_with_personal_data(
    fallback: FallbackCallable,
    *,
    enabled: bool = False,
    fallback_on_error: bool = True,
) -> ExtractionPipeline:
    """Create a pipeline that covers the initial set of migrated modules."""
    modules = build_personal_data_modules()
    return ExtractionPipeline(
        modules=modules,
        fallback=fallback,
        enabled=enabled,
        fallback_on_error=fallback_on_error,
        post_processors=(apply_post_processors,),
    )
