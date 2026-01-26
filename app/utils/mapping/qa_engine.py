"""Post-mapping quality assurance helpers."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from ...config import DEFAULT_PII_CONFIG
from ...logging.safe_logger import get_safe_logger
from ..certification_router import create_certification_router
from ..experience_filters import ExperienceQualityAssessor


class QAEngine:
    """Encapsulates post-mapping demotion and certification cleanup logic."""

    def __init__(
        self,
        assessor: ExperienceQualityAssessor | None = None,
        cert_router: Any | None = None,
    ) -> None:
        self.logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)
        self.assessor = assessor or ExperienceQualityAssessor()
        self.cert_router = cert_router or create_certification_router()

    def apply_post_mapping_qa(
        self, mapped_data: Dict[str, Any], original_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Apply demotion/promotions and return the enriched mapping."""
        self.logger.info("QA_POST_MAPPING: start")

        experiences: List[Dict[str, Any]] = list(mapped_data.get("experiences") or [])
        education: List[Dict[str, Any]] = list(mapped_data.get("education") or [])
        certifications: List[Dict[str, Any]] = list(
            mapped_data.get("certifications") or []
        )

        demoted_experiences: List[Dict[str, Any]] = []
        promoted_certifications: List[Dict[str, Any]] = []
        remaining_experiences: List[Dict[str, Any]] = []

        for exp in experiences:
            context = {
                "text_lines": original_data.get("text_lines", []),
                "ner_entities": original_data.get("ner_entities", []),
            }
            assessment = self.assessor.assess_experience_quality(exp, context) or {}

            if assessment.get("should_demote"):
                demoted_exp = {
                    "school": exp.get("company", ""),
                    "degree": exp.get("title", "Formation"),
                    "start_date": exp.get("start_date", ""),
                    "end_date": exp.get("end_date", ""),
                    "location": exp.get("location", ""),
                    "description": exp.get("description", []),
                    "source": "cv_demoted_from_experience",
                    "confidence": assessment.get("quality_score", 0),
                }

                if not demoted_exp["degree"] and (
                    demoted_exp["start_date"] or demoted_exp["end_date"]
                ):
                    period = f"{demoted_exp['start_date']} - {demoted_exp['end_date']}".strip(
                        " -"
                    )
                    demoted_exp["period_note"] = period

                education.append(demoted_exp)
                demoted_experiences.append(
                    {
                        "original": exp,
                        "demoted_to": demoted_exp,
                        "reasons": assessment.get("reasons", []),
                    }
                )
                self.logger.info(
                    "QA_DEMOTE: experience_to_education | title='%s' company='%s' reasons=%s",
                    exp.get("title", ""),
                    exp.get("company", ""),
                    assessment.get("reasons", []),
                )
            else:
                remaining_experiences.append(exp)

        cleaned_education, extracted_certs = self._clean_education_certifications(
            education
        )
        certifications.extend(extracted_certs)
        promoted_certifications.extend(extracted_certs)

        mapped_data["experiences"] = remaining_experiences
        mapped_data["education"] = cleaned_education
        mapped_data["certifications"] = certifications

        self.logger.info(
            "QA_POST_MAPPING: summary | demoted_experiences=%s promoted_certifications=%s final_experiences=%s final_education=%s final_certifications=%s",
            len(demoted_experiences),
            len(promoted_certifications),
            len(remaining_experiences),
            len(cleaned_education),
            len(certifications),
        )

        for demo in demoted_experiences:
            self.logger.debug(
                "QA_DEMOTED: %s @ %s → education",
                demo["original"].get("title", "NO_TITLE"),
                demo["original"].get("company", "NO_COMPANY"),
            )

        for cert in promoted_certifications:
            self.logger.debug(
                "QA_PROMOTED: %s → certifications",
                cert.get("name", "NO_NAME"),
            )

        self.logger.info("QA_POST_MAPPING: complete")
        return mapped_data

    def _clean_education_certifications(
        self, education: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Delegate certification clean-up to the router."""
        return self.cert_router.clean_education_certifications(education)


__all__ = ["QAEngine"]
