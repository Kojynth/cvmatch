"""
Generic CV Export Worker
========================

QThread that runs a single LLM pass to format a profile as a standalone
professional CV (no specific job offer), then emits the resulting cv_json.

Post-processing guarantees:
- Evidence policy (CVMATCH_CV_EVIDENCE_MODE) is honoured.
- Output always goes through coerce_generated_cv_payload + sanitize_cv_json_output,
  matching the quality and structural guarantees of the main pipeline.

Usage::

    worker = GenericCVExportWorker(profile_json, language_code="fr")
    worker.progress_updated.connect(on_progress)
    worker.generation_finished.connect(on_cv_json_ready)
    worker.error_occurred.connect(on_error)
    worker.start()
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict

from PySide6.QtCore import QThread, Signal

try:
    from ..config import DEFAULT_PII_CONFIG
    from ..logging.safe_logger import get_safe_logger

    logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)
except ImportError:
    import logging

    logger = logging.getLogger(__name__)


class GenericCVExportWorker(QThread):
    """Single-pass LLM worker for generic (offer-less) CV generation."""

    progress_updated = Signal(int, str)
    generation_finished = Signal(dict)
    error_occurred = Signal(str)

    def __init__(
        self,
        profile_json: Dict[str, Any],
        language_code: str = "fr",
        model_id: str = "",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._profile_json = profile_json
        self._language_code = language_code
        self._model_id = str(model_id or "").strip()

    # ------------------------------------------------------------------
    # QThread entry point
    # ------------------------------------------------------------------

    def run(self) -> None:
        try:
            self._emit_progress(5, "Chargement du modèle LLM...")
            qwen_manager = self._get_qwen_manager()

            if self.isInterruptionRequested():
                return

            self._emit_progress(15, "Construction du prompt...")
            from ..utils.prompt_factory import build_generic_cv_messages
            from ..utils.multilang_cv_support import get_cv_culture_hint

            profile_block = json.dumps(
                self._profile_json, ensure_ascii=False, indent=2
            )
            evidence_policy_block = self._build_evidence_policy_block()
            culture_hint = get_cv_culture_hint(self._language_code)
            messages = build_generic_cv_messages(
                language_code=self._language_code,
                profile_block=profile_block,
                evidence_policy_block=evidence_policy_block,
                culture_hint=culture_hint,
            )

            if self.isInterruptionRequested():
                return

            self._emit_progress(25, "Génération du CV par le LLM...")

            def _progress_cb(msg: str) -> None:
                self._emit_progress(50, str(msg))

            raw = qwen_manager.generate_structured_json(
                messages["system"],
                messages["user"],
                progress_callback=_progress_cb,
                generation_overrides=self._build_generation_overrides(),
                role="generator",
            )

            if self.isInterruptionRequested():
                return

            self._emit_progress(80, "Post-traitement du CV...")
            raw_json = self._parse_json_response(raw)
            cv_json = self._postprocess(raw_json)

            if not cv_json:
                self.error_occurred.emit(
                    "Le modèle n'a pas retourné de JSON valide. "
                    "Vérifiez que le modèle est correctement chargé et réessayez."
                )
                return

            self._emit_progress(100, "Génération terminée.")
            self.generation_finished.emit(cv_json)

        except Exception as exc:
            logger.exception("GenericCVExportWorker error: %s", exc)
            self.error_occurred.emit(
                f"Erreur lors de la génération : {exc}"
            )

    # ------------------------------------------------------------------
    # Post-processing — mirrors the main pipeline quality guarantees
    # ------------------------------------------------------------------

    def _postprocess(self, raw_json: Dict[str, Any]) -> Dict[str, Any]:
        """Apply the canonical CV post-processing pipeline to the LLM output.

        Runs coerce_generated_cv_payload (structural merge + deterministic
        fallback) followed by sanitize_cv_json_output (placeholder/marker
        removal), matching what the main generation pipeline guarantees.
        """
        from ..utils.cv_postprocessing import (
            coerce_generated_cv_payload,
            sanitize_cv_json_output,
        )

        coerced = coerce_generated_cv_payload(
            payload=raw_json or {},
            profile_json=self._profile_json,
            fallback_generator=self._minimal_cv_fallback,
            job_title="",
            company="",
            profile_name=self._get_personal("full_name"),
            profile_email=self._get_personal("email"),
            profile_phone=self._get_personal("phone"),
            profile_linkedin=self._get_personal("linkedin_url"),
            language_code=self._language_code,
        )
        sanitize_cv_json_output(coerced, language_code=self._language_code)
        # Ensure the top-level language field is always set so cv_json_to_cv_data
        # and TemplatePreviewWindow can render the CV in the correct locale.
        if not str(coerced.get("language") or "").strip():
            coerced["language"] = self._language_code
        quality_audit = self._audit_quality(coerced)
        if not quality_audit.get("sufficient", True):
            logger.warning(
                "GenericCVExportWorker quality fallback: score=%s penalty=%s",
                quality_audit.get("score"),
                quality_audit.get("penalty"),
            )
            fallback = self._minimal_cv_fallback(
                self._profile_json,
                "quality_insufficient",
            )
            if isinstance(fallback, dict) and not str(fallback.get("language") or "").strip():
                fallback["language"] = self._language_code
            # Compute durations on the fallback so it satisfies the same quality gate
            # that caused the main CV to be rejected (duration_missing flag).
            # The fallback generator does not call coerce_generated_cv_payload, so
            # _compute_experience_durations must be run explicitly here.
            try:
                from ..utils.cv_postprocessing import _compute_experience_durations
                _compute_experience_durations(fallback, language_code=self._language_code)
            except Exception:
                pass
            sanitize_cv_json_output(fallback, language_code=self._language_code)
            return fallback
        return coerced

    def _minimal_cv_fallback(
        self, profile_json: Dict[str, Any], reason: str
    ) -> Dict[str, Any]:
        """Deterministic structural base used by coerce_generated_cv_payload.

        Returns the minimum valid cv_json skeleton populated from personal_info
        so that the merge always produces a complete, exportable structure.
        """
        from ..utils.cv_fallback_generator import generate_fallback_cv_json_simple

        return generate_fallback_cv_json_simple(
            profile_json=profile_json if isinstance(profile_json, dict) else {},
            profile_name=self._get_personal("full_name"),
            profile_email=self._get_personal("email"),
            profile_phone=self._get_personal("phone"),
            profile_linkedin=self._get_personal("linkedin_url"),
            language_code=self._language_code,
            reason=reason,
        )

    # ------------------------------------------------------------------
    # Evidence policy — mirrors _resolve_cv_evidence_mode / _build_cv_evidence_policy_block
    # ------------------------------------------------------------------

    def _resolve_evidence_mode(self) -> str:
        """Read CVMATCH_CV_EVIDENCE_MODE from env/config, defaulting to inferred_impact."""
        raw = os.getenv("CVMATCH_CV_EVIDENCE_MODE", "")
        if not raw:
            try:
                from ..utils.model_config_manager import model_config_manager

                config = model_config_manager.get_current_config()
                raw = str(
                    (getattr(config, "custom_parameters", {}) or {}).get(
                        "cv_evidence_mode"
                    )
                    or ""
                )
            except Exception:
                raw = ""
        mode = raw.strip().lower().replace("-", "_")
        if mode in {"strict", "strict_factual"}:
            return "strict_factual"
        return "inferred_impact"

    def _build_evidence_policy_block(self) -> str:
        """Build the EVIDENCE_POLICY prompt block matching the main pipeline."""
        mode = self._resolve_evidence_mode()
        if mode == "strict_factual":
            guidance = (
                "- Stay strictly factual: use only facts that are explicit in PROFILE_JSON.\n"
                "- Do not infer new outcomes, responsibilities, metrics, technologies, "
                "project names, or certifications.\n"
                "- Never create new experience, project, education, or certification records."
            )
        else:
            guidance = (
                "- Stay grounded in PROFILE_JSON facts and chronology.\n"
                "- You may infer a qualitative impact or implied operational outcome when it is "
                "directly supported by the described tasks, context, and duration.\n"
                "- Never invent exact metrics, new technologies, employers, project names, "
                "certifications, or responsibilities absent from PROFILE_JSON.\n"
                "- Never create new experience, project, education, or certification records."
            )
        return (
            "\n\nEVIDENCE_POLICY (highest-priority factual boundary):\n"
            f"{guidance}"
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_qwen_manager(self):
        from ..workers.qwen_manager import QwenManager

        manager = QwenManager()
        if self._model_id:
            try:
                manager.apply_model_profile(
                    self._model_id,
                    reason="generic_cv_export",
                )
            except Exception as exc:
                logger.warning(
                    "GenericCVExportWorker could not switch model to %s: %s",
                    self._model_id,
                    exc,
                )
        return manager

    def _get_personal(self, field: str) -> str:
        personal = self._profile_json.get("personal_info", {}) if isinstance(self._profile_json, dict) else {}
        return str(personal.get(field) or "")

    def _audit_quality(self, cv_json: Dict[str, Any]) -> Dict[str, Any]:
        from ..utils.cv_quality_audit import build_cv_quality_audit

        return build_cv_quality_audit(
            cv_json,
            target_language=self._language_code,
        )

    def _emit_progress(self, pct: int, msg: str) -> None:
        self.progress_updated.emit(pct, msg)

    def _build_generation_overrides(self) -> Dict[str, Any]:
        """Match the main non-strict generator retry settings for JSON stability."""
        raw = str(os.getenv("CVMATCH_JSON_NON_STRICT_DETERMINISTIC", "1") or "").strip()
        deterministic = raw.lower() not in {"0", "false", "no", "off"}
        if not deterministic:
            return {}
        return {
            "temperature": 0.0,
            "do_sample": False,
            "top_p": 0.9,
            "top_k": 40,
            "repetition_penalty": 1.05,
            "max_new_tokens": 1800,
        }

    def _parse_json_response(self, text: str) -> Dict[str, Any]:
        """Extract a JSON dict from raw LLM output."""
        if not text:
            return {}
        cleaned = text.strip()
        try:
            return json.loads(cleaned)
        except Exception:
            pass
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = cleaned[start : end + 1]
            try:
                return json.loads(candidate)
            except Exception:
                pass
        try:
            from ..utils.json_strict import attempt_json_repair

            repaired = attempt_json_repair(cleaned)
            if repaired:
                return json.loads(repaired)
        except Exception:
            pass
        logger.warning("GenericCVExportWorker: could not parse JSON from LLM output")
        return {}
