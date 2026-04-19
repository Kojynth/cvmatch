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

from copy import deepcopy
import json
import os
import re
from typing import Any, Dict, List

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
        self._qwen_manager = None

    # ------------------------------------------------------------------
    # QThread entry point
    # ------------------------------------------------------------------

    def run(self) -> None:
        try:
            self._emit_progress(5, "Chargement du modèle LLM...")
            qwen_manager = self._get_qwen_manager()
            self._qwen_manager = qwen_manager

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

            raw_json = self._generate_cv_payload(
                qwen_manager,
                messages,
                progress_callback=_progress_cb,
            )

            if self.isInterruptionRequested():
                return

            self._emit_progress(80, "Post-traitement du CV...")
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
        coerced = self._repair_language_if_needed(
            coerced,
            stage="generic_postprocess",
        )
        coerced = self._enrich_experience_from_profile_descriptions(
            coerced,
            stage="generic_postprocess",
        )
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
                preserve_foreign_text=True,
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
            rich_fallback = deepcopy(fallback)
            fallback = self._repair_language_if_needed(
                fallback,
                stage="generic_quality_fallback",
            )
            fallback = self._enrich_experience_from_profile_descriptions(
                fallback,
                stage="generic_quality_fallback",
            )
            fallback_audit = self._audit_language(fallback)
            rich_audit = self._audit_language(rich_fallback)
            rich_sections = set(rich_audit.get("mixed_language_sections") or [])
            fallback_sections = set(fallback_audit.get("mixed_language_sections") or [])
            if fallback_audit.get("language_ok", True) or len(fallback_sections) < len(rich_sections):
                return fallback

            pruned_fallback = self._minimal_cv_fallback(
                self._profile_json,
                "quality_insufficient_pruned",
                preserve_foreign_text=False,
            )
            if isinstance(pruned_fallback, dict) and not str(pruned_fallback.get("language") or "").strip():
                pruned_fallback["language"] = self._language_code
            try:
                from ..utils.cv_postprocessing import _compute_experience_durations

                _compute_experience_durations(
                    pruned_fallback,
                    language_code=self._language_code,
                )
            except Exception:
                pass
            sanitize_cv_json_output(pruned_fallback, language_code=self._language_code)
            return pruned_fallback
        return coerced

    def _minimal_cv_fallback(
        self,
        profile_json: Dict[str, Any],
        reason: str,
        *,
        preserve_foreign_text: bool = False,
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
            preserve_foreign_text=preserve_foreign_text,
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
        refresh_config = getattr(manager, "refresh_selected_model_config", None)
        if callable(refresh_config):
            try:
                refresh_config()
            except Exception as exc:
                logger.warning(
                    "GenericCVExportWorker could not refresh selected model config: %s",
                    exc,
                )
        if self._model_id:
            try:
                select_model = getattr(manager, "select_model_profile", None)
                if callable(select_model):
                    select_model(
                        self._model_id,
                        reason="generic_cv_export",
                    )
                else:
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

    def _audit_language(self, cv_json: Dict[str, Any]) -> Dict[str, Any]:
        from ..utils.cv_language_audit import audit_cv_language_consistency

        audit = audit_cv_language_consistency(
            cv_json,
            target_language=self._language_code,
        )
        title_issues = self._collect_language_title_issues(cv_json)
        skill_issues = self._collect_language_skill_issues(cv_json)
        extra_issues = [*title_issues, *skill_issues]
        if extra_issues:
            mixed_sections = list(audit.get("mixed_language_sections") or [])
            for issue in extra_issues:
                if issue not in mixed_sections:
                    mixed_sections.append(issue)
            audit["mixed_language_sections"] = mixed_sections
            audit["language_ok"] = False
            audit["language_penalty"] = max(
                float(audit.get("language_penalty") or 0.0),
                20.0,
            )
        return audit

    def _collect_language_title_issues(self, cv_json: Dict[str, Any]) -> list[str]:
        payload = cv_json if isinstance(cv_json, dict) else {}
        issues: list[str] = []

        for idx, entry in enumerate(payload.get("experience") or [], start=1):
            if not isinstance(entry, dict):
                continue
            title = str(entry.get("title") or "").strip()
            if title and self._title_looks_mismatched(title):
                issues.append(f"experience_{idx}.title")

        for idx, entry in enumerate(payload.get("education") or [], start=1):
            if not isinstance(entry, dict):
                continue
            degree = str(entry.get("degree") or "").strip()
            if degree and self._title_looks_mismatched(degree):
                issues.append(f"education_{idx}.degree")

        return issues

    def _collect_language_skill_issues(self, cv_json: Dict[str, Any]) -> list[str]:
        payload = cv_json if isinstance(cv_json, dict) else {}
        issues: list[str] = []

        for block_index, block in enumerate(payload.get("skills") or [], start=1):
            if not isinstance(block, dict):
                continue
            for item_index, item in enumerate(block.get("items") or [], start=1):
                if self._text_looks_mismatched(str(item or "").strip()):
                    issues.append(f"skills_{block_index}.item_{item_index}")

        return issues

    def _title_looks_mismatched(self, text: str) -> bool:
        import re
        import unicodedata

        raw = str(text or "").strip()
        if not raw:
            return False

        normalized = (
            unicodedata.normalize("NFKD", raw)
            .encode("ascii", "ignore")
            .decode("ascii")
            .lower()
        )
        tokens = set(re.findall(r"[a-z]+", normalized))
        if not tokens:
            return False

        fr_markers = {
            "alternant",
            "ingenieur",
            "qualite",
            "stagiaire",
            "stage",
            "charge",
            "responsable",
            "developpeur",
            "chef",
            "produit",
            "commercial",
            "technicien",
            "assurance",
        }
        en_markers = {
            "engineer",
            "apprentice",
            "developer",
            "manager",
            "specialist",
            "analyst",
            "lead",
            "product",
            "quality",
            "business",
            "designer",
            "operations",
            "sales",
            "intern",
        }

        target = "en" if str(self._language_code or "").strip().lower().startswith("en") else "fr"
        if target == "en":
            return bool(tokens & fr_markers)
        return bool(tokens & en_markers)

    def _text_looks_mismatched(self, text: str) -> bool:
        from ..utils.language_policy import detect_language_from_text_default

        raw = str(text or "").strip()
        if not raw:
            return False
        if self._title_looks_mismatched(raw):
            return True

        words = [token for token in re.findall(r"[A-Za-zÀ-ÿ]+", raw) if token]
        if not words:
            return False
        technical_short = {
            "sql",
            "python",
            "java",
            "c",
            "c++",
            "api",
            "qa",
            "aws",
            "azure",
            "gcp",
            "tableau",
            "powerbi",
            "looker",
            "excel",
            "jira",
            "gherkin",
            "scrum",
        }
        lowered_words = [word.lower() for word in words]
        if len(lowered_words) == 1 and lowered_words[0] in technical_short:
            return False

        target = "en" if str(self._language_code or "").strip().lower().startswith("en") else "fr"
        detected = detect_language_from_text_default(raw)
        if detected != target and (
            len(lowered_words) >= 3
            or any(ord(ch) > 127 for ch in raw)
        ):
            return True
        return False

    def _emit_progress(self, pct: int, msg: str) -> None:
        self.progress_updated.emit(pct, msg)

    def _enrich_experience_from_profile_descriptions(
        self,
        cv_json: Dict[str, Any],
        *,
        stage: str,
    ) -> Dict[str, Any]:
        payload = deepcopy(cv_json) if isinstance(cv_json, dict) else {}
        experiences = payload.get("experience")
        if not isinstance(experiences, list) or not experiences:
            return payload
        if self._qwen_manager is None or not callable(
            getattr(self._qwen_manager, "generate_structured_json", None)
        ):
            return payload

        try:
            from ..utils.cv_postprocessing import (
                _best_profile_match,
                _extract_profile_experiences,
            )
            from ..utils.cv_postprocessing import clean_narrative_text
            from ..utils.language_policy import text_matches_target_language
        except Exception:
            return payload

        profile_experiences = _extract_profile_experiences(
            self._profile_json if isinstance(self._profile_json, dict) else {}
        )
        if not profile_experiences:
            return payload

        candidates: List[Dict[str, Any]] = []
        for index, entry in enumerate(experiences):
            if not isinstance(entry, dict):
                continue
            if not self._experience_needs_targeted_rewrite(entry):
                continue
            matched_profile = _best_profile_match(entry, profile_experiences)
            if not isinstance(matched_profile, dict):
                continue

            source_description = clean_narrative_text(
                matched_profile.get("description") or ""
            )
            if not source_description or len(source_description.split()) < 8:
                continue

            translated_highlights = [
                str(item).strip()
                for item in (entry.get("highlights") or [])
                if isinstance(item, str)
                and str(item).strip()
                and text_matches_target_language(
                    str(item).strip(),
                    self._language_code,
                )
            ]
            translated_summary = str(entry.get("summary") or "").strip()
            if translated_summary and not text_matches_target_language(
                translated_summary,
                self._language_code,
            ):
                translated_summary = ""
            is_current = self._entry_is_current(entry)

            candidates.append(
                {
                    "index": index,
                    "title": str(entry.get("title") or "").strip(),
                    "company": str(entry.get("company") or "").strip(),
                    "start_date": str(entry.get("start_date") or "").strip(),
                    "end_date": str(entry.get("end_date") or "").strip(),
                    "location": str(entry.get("location") or "").strip(),
                    "is_current": is_current,
                    "target_tense": "present" if is_current else "past",
                    "current_summary": translated_summary,
                    "current_highlights": translated_highlights,
                    "source_title": str(matched_profile.get("title") or "").strip(),
                    "source_company": str(matched_profile.get("company") or "").strip(),
                    "source_description": source_description,
                }
            )

        if not candidates:
            return payload

        rewritten = self._rewrite_experience_entries_from_profile(candidates)
        items = rewritten.get("items") if isinstance(rewritten, dict) else None
        if not isinstance(items, list):
            return payload

        updated = False
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                index = int(item.get("index"))
            except Exception:
                continue
            if index < 0 or index >= len(experiences):
                continue
            target_entry = experiences[index]
            if not isinstance(target_entry, dict):
                continue

            summary = str(item.get("summary") or "").strip()
            highlights = [
                str(value).strip()
                for value in (item.get("highlights") or [])
                if isinstance(value, str) and str(value).strip()
            ]
            try:
                from ..utils.language_policy import text_matches_target_language
            except Exception:
                text_matches_target_language = None

            if not summary and not highlights:
                continue

            if summary and (
                text_matches_target_language is None
                or text_matches_target_language(summary, self._language_code)
            ):
                target_entry["summary"] = summary
                updated = True
            filtered_highlights = [
                value
                for value in highlights
                if text_matches_target_language is None
                or text_matches_target_language(value, self._language_code)
            ]
            if filtered_highlights:
                target_entry["highlights"] = filtered_highlights[:4]
                updated = True

        if updated:
            logger.info(
                "GenericCVExportWorker experience rewrite applied: stage=%s count=%s",
                stage,
                len(candidates),
            )
        payload["experience"] = experiences
        return payload

    def _experience_needs_targeted_rewrite(self, entry: Dict[str, Any]) -> bool:
        try:
            from ..utils.language_policy import text_matches_target_language
        except Exception:
            return False

        is_current = self._entry_is_current(entry)
        summary = str(entry.get("summary") or "").strip()
        highlights = [
            str(value).strip()
            for value in (entry.get("highlights") or [])
            if isinstance(value, str) and str(value).strip()
        ]
        translated_highlights = [
            value
            for value in highlights
            if text_matches_target_language(value, self._language_code)
        ]
        company_name = str(entry.get("company") or "").strip()
        summary_in_target_language = bool(summary) and text_matches_target_language(
            summary,
            self._language_code,
        )
        if summary and self._experience_text_needs_rewrite(
            summary,
            company=company_name,
            is_summary=True,
            is_current=is_current,
        ):
            return True
        if any(
            self._experience_text_needs_rewrite(
                value,
                company=company_name,
                is_summary=False,
                is_current=is_current,
            )
            for value in translated_highlights
        ):
            return True
        if (
            translated_highlights
            and summary_in_target_language
            and not self._is_generic_experience_summary(summary)
        ):
            return False
        if not summary:
            return True
        if not summary_in_target_language:
            return True
        return self._is_generic_experience_summary(summary) or len(translated_highlights) < 2

    def _experience_text_needs_rewrite(
        self,
        text: str,
        *,
        company: str,
        is_summary: bool,
        is_current: bool,
    ) -> bool:
        raw = str(text or "").strip()
        if not raw:
            return False

        lowered = raw.lower()
        word_count = len(re.findall(r"\b\w+\b", raw, flags=re.UNICODE))
        if word_count == 0:
            return False

        if raw.endswith(":"):
            return True
        if not is_summary and raw[:1].islower() and word_count >= 4:
            return True
        if word_count > (24 if is_summary else 20):
            return True

        if any(
            marker in lowered
            for marker in (
                "mes missions",
                "my responsibilities",
                "responsibilities included",
                "i worked",
                "i supported",
                "j'interviens",
                "j'assure",
                "j'ai",
            )
        ):
            return True

        try:
            from ..utils.cv_fallback_generator import (
                _contains_first_person_reference,
                _looks_like_company_description,
            )
        except Exception:
            _contains_first_person_reference = None
            _looks_like_company_description = None

        if (
            _contains_first_person_reference is not None
            and _contains_first_person_reference(
                raw,
                language_code=self._language_code,
            )
        ):
            return True

        if (
            _looks_like_company_description is not None
            and _looks_like_company_description(raw, company)
        ):
            return True

        try:
            from ..utils.cv_postprocessing import _starts_with_action_phrase
        except Exception:
            _starts_with_action_phrase = None

        if (
            not is_summary
            and _starts_with_action_phrase is not None
            and word_count >= 4
            and not _starts_with_action_phrase(raw, language_code=self._language_code)
        ):
            return True

        if self._text_has_tense_mismatch(raw, is_current=is_current):
            return True

        return False

    def _entry_is_current(self, entry: Dict[str, Any]) -> bool:
        try:
            from ..utils.profile_json import derive_date_support_fields
        except Exception:
            derive_date_support_fields = None

        if derive_date_support_fields is not None:
            try:
                support = derive_date_support_fields(
                    entry.get("start_date") or "",
                    entry.get("end_date") or "",
                )
                return bool(support.get("is_current"))
            except Exception:
                pass

        try:
            from ..rules.date_normalize import normalize_present_token
        except Exception:
            normalize_present_token = None

        end_value = str(entry.get("end_date") or "").strip()
        if normalize_present_token is not None and end_value:
            normalized = str(normalize_present_token(end_value) or "").strip().upper()
            return normalized == "PRESENT"
        return False

    def _text_has_tense_mismatch(self, text: str, *, is_current: bool) -> bool:
        raw = str(text or "").strip()
        if not raw:
            return False

        language = "en" if str(self._language_code or "").strip().lower().startswith("en") else "fr"
        first_token_match = re.match(r"[A-Za-zÀ-ÿ']+", raw)
        if not first_token_match:
            return False
        first_token = first_token_match.group(0).lower()

        if language == "fr":
            if not is_current and re.fullmatch(r"[a-zà-ÿ]+(?:er|ir|re)", first_token):
                return True
            present_heads = {
                "accompagne",
                "ameliore",
                "analyse",
                "assure",
                "automatise",
                "collabore",
                "concoit",
                "consolide",
                "contribue",
                "coordonne",
                "cree",
                "definit",
                "deploie",
                "developpe",
                "documente",
                "execute",
                "fiabilise",
                "gere",
                "identifie",
                "implemente",
                "mene",
                "optimise",
                "pilote",
                "prepare",
                "qualifie",
                "realise",
                "redige",
                "renforce",
                "revoit",
                "structure",
                "suit",
                "teste",
                "valide",
            }
            if not is_current and first_token in present_heads:
                return True
        else:
            base_heads = {
                "analyze",
                "automate",
                "build",
                "coordinate",
                "create",
                "define",
                "deliver",
                "design",
                "develop",
                "document",
                "drive",
                "execute",
                "implement",
                "improve",
                "lead",
                "manage",
                "optimize",
                "prepare",
                "qualify",
                "reduce",
                "review",
                "streamline",
                "structure",
                "support",
                "test",
                "track",
                "validate",
            }
            if not is_current and first_token in base_heads:
                return True
            if is_current and first_token.endswith("ed"):
                return True

        return False

    @staticmethod
    def _is_generic_experience_summary(text: str) -> bool:
        normalized = re.sub(r"\s+", " ", str(text or "").strip().lower())
        if not normalized:
            return True
        return normalized in {
            "delivered key contributions in this role.",
            "contributions principales realisees sur ce poste.",
        } or normalized.startswith("delivered key contributions as ")

    def _rewrite_experience_entries_from_profile(
        self,
        candidates: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        qwen_manager = self._qwen_manager
        if (
            qwen_manager is None
            or not callable(getattr(qwen_manager, "generate_structured_json", None))
            or not candidates
        ):
            return {}

        messages = self._build_experience_rewrite_messages(candidates)
        try:
            raw = qwen_manager.generate_structured_json(
                messages["system"],
                messages["user"],
                generation_overrides={
                    **self._build_generation_overrides(),
                    "max_new_tokens": 1200,
                },
                role="generator",
            )
        except Exception as exc:
            logger.warning(
                "GenericCVExportWorker experience rewrite unavailable: %s",
                exc,
            )
            return {}
        return self._parse_json_response(raw)

    def _build_experience_rewrite_messages(
        self,
        candidates: List[Dict[str, Any]],
    ) -> Dict[str, str]:
        candidate_block = json.dumps(candidates, ensure_ascii=False, indent=2)
        system_prompt = (
            "You are a CV experience rewriter. Return JSON only. "
            "For each candidate item, rewrite SOURCE_DESCRIPTION into LANGUAGE using concise recruiter wording. "
            "Preserve facts exactly. Do not invent metrics, tools, employers, scope, or achievements. "
            "Keep proper nouns, company names, product names, and locations unchanged."
        )
        user_prompt = f"""
LANGUAGE: {self._language_code}

EXPERIENCES_TO_REWRITE:
{candidate_block}

OUTPUT RULES:
- Return JSON only with the shape: {{"items": [{{"index": 0, "summary": "...", "highlights": ["...", "..."]}}]}}
- Keep the same index values.
- Respect TARGET_TENSE for each item:
  * if TARGET_TENSE is "present", use present tense;
  * if TARGET_TENSE is "past", use past tense.
- summary: exactly 1 compact sentence, factual, recruiter-facing, not generic.
- highlights: 2 to 4 short ATS-safe lines when SOURCE_DESCRIPTION supports them.
- Translate SOURCE_DESCRIPTION fully into LANGUAGE when needed.
- Do not leave French text when LANGUAGE is English.
- Do not use placeholders such as "Delivered key contributions in this role."
- Do not copy SOURCE_DESCRIPTION verbatim; rewrite it into concise CV wording.
- Remove company boilerplate, first-person phrasing, and weak lead-ins such as "Mes missions couvrent".
- Each highlight must follow: action verb + concrete task + grounded effect or operational outcome when the source supports it.
- When SOURCE_DESCRIPTION implies an outcome but gives no exact metric, you may express a qualitative impact in LANGUAGE (for example: clearer reporting, smoother releases, reduced manual work, stronger test coverage) without inventing numbers.
- Reject noun-fragment bullets such as "Validation fonctionnelle..." or "Conception, execution et suivi..."; rewrite them into verb-led recruiter bullets.
- For former roles, do not keep infinitive-only bullets or present-tense openings such as "Concevoir...", "Pilote...", "Build...", or "Lead...".
- Use strong action verbs and one idea per highlight.
- Start each highlight with a clear action verb in LANGUAGE.
- If CURRENT_SUMMARY or CURRENT_HIGHLIGHTS are already strong and in LANGUAGE, you may keep them.
""".strip()
        return {"system": system_prompt, "user": user_prompt}

    def _repair_language_if_needed(
        self,
        cv_json: Dict[str, Any],
        *,
        stage: str,
    ) -> Dict[str, Any]:
        payload = dict(cv_json or {}) if isinstance(cv_json, dict) else {}
        if not payload:
            return payload

        language_audit = self._audit_language(payload)
        if language_audit.get("language_ok", True):
            return payload

        logger.warning(
            "GenericCVExportWorker language mismatch: stage=%s target=%s sections=%s",
            stage,
            self._language_code,
            language_audit.get("mixed_language_sections"),
        )

        repaired = self._rewrite_cv_language_payload(
            payload,
            mixed_sections=language_audit.get("mixed_language_sections") or [],
        )
        if not isinstance(repaired, dict) or not repaired:
            return payload

        try:
            from ..utils.cv_postprocessing import (
                _compute_experience_durations,
                sanitize_cv_json_output,
            )

            if not str(repaired.get("language") or "").strip():
                repaired["language"] = self._language_code
            _compute_experience_durations(repaired, language_code=self._language_code)
            sanitize_cv_json_output(repaired, language_code=self._language_code)
        except Exception as exc:
            logger.warning(
                "GenericCVExportWorker language repair postprocess failed: %s",
                exc,
            )

        repaired_audit = self._audit_language(repaired)
        if repaired_audit.get("language_ok", True):
            return repaired

        original_sections = set(language_audit.get("mixed_language_sections") or [])
        repaired_sections = set(repaired_audit.get("mixed_language_sections") or [])
        if repaired_sections and len(repaired_sections) < len(original_sections):
            logger.info(
                "GenericCVExportWorker accepted partial language repair: stage=%s before=%s after=%s",
                stage,
                sorted(original_sections),
                sorted(repaired_sections),
            )
            return repaired

        logger.warning(
            "GenericCVExportWorker language repair still mixed: stage=%s sections=%s",
            stage,
            repaired_audit.get("mixed_language_sections"),
        )
        return payload

    def _rewrite_cv_language_payload(
        self,
        cv_json: Dict[str, Any],
        *,
        mixed_sections: list[str],
    ) -> Dict[str, Any]:
        qwen_manager = self._qwen_manager
        if qwen_manager is None:
            return {}

        messages = self._build_language_repair_messages(
            cv_json,
            mixed_sections=mixed_sections,
        )
        try:
            from ..schemas.cv_schema import CVJSON
            from ..utils.json_strict import JsonStrictError, generate_json_with_schema

            payload = generate_json_with_schema(
                role="generator",
                schema_model=CVJSON,
                messages=messages,
                qwen_manager=qwen_manager,
                retries=1,
            )
            if isinstance(payload, dict):
                return payload
        except JsonStrictError as exc:
            logger.warning(
                "GenericCVExportWorker language repair strict JSON failed: %s",
                exc,
            )
        except Exception as exc:
            logger.warning(
                "GenericCVExportWorker language repair unavailable, retrying non-strict: %s",
                exc,
            )

        raw = qwen_manager.generate_structured_json(
            messages["system"],
            messages["user"],
            generation_overrides=self._build_generation_overrides(),
            role="generator",
        )
        return self._parse_json_response(raw)

    def _build_language_repair_messages(
        self,
        cv_json: Dict[str, Any],
        *,
        mixed_sections: list[str],
    ) -> Dict[str, str]:
        profile_block = json.dumps(
            self._profile_json if isinstance(self._profile_json, dict) else {},
            ensure_ascii=False,
            indent=2,
        )
        cv_block = json.dumps(
            cv_json if isinstance(cv_json, dict) else {},
            ensure_ascii=False,
            indent=2,
        )
        sections_text = ", ".join(
            str(item).strip() for item in mixed_sections if str(item).strip()
        )
        system_prompt = (
            "You are a CV JSON editor. Return JSON only that matches the CVJSON schema. "
            "Rewrite CURRENT_CV_JSON so every natural-language field is in LANGUAGE only. "
            "Preserve chronology, contact facts, companies, dates, durations, and evidence. "
            "Use PROFILE_JSON only to verify or clarify existing facts; never add new facts. "
            "Translate source-language role titles, degree names, summaries, highlights, skill items, certification names, "
            "and project descriptions "
            "when the meaning is clear. Keep proper nouns, official company names, product names, URLs, and acronyms unchanged. "
            "Do not leave mixed French/English text."
        )
        user_prompt = f"""
LANGUAGE: {self._language_code}
MIXED_SECTIONS: {sections_text or "unknown"}

PROFILE_JSON (source of truth):
{profile_block}

CURRENT_CV_JSON (rewrite in LANGUAGE, preserve facts):
{cv_block}

OUTPUT RULES:
- Return JSON only.
- Keep the exact CVJSON structure.
- Keep target_job_title and target_company unchanged.
- Translate every visible human-language field fully into LANGUAGE, including titles, summaries, highlights, skill items, education labels, and certification names when possible.
- If a phrase cannot be translated confidently without inventing facts, rewrite it conservatively in LANGUAGE.
- Do not invent metrics, achievements, technologies, employers, projects, schools, or certifications.
- Do not use placeholders or bracketed notes.
""".strip()
        return {"system": system_prompt, "user": user_prompt}

    def _generate_cv_payload(
        self,
        qwen_manager,
        messages: Dict[str, str],
        progress_callback=None,
    ) -> Dict[str, Any]:
        try:
            from ..schemas.cv_schema import CVJSON
            from ..utils.json_strict import JsonStrictError, generate_json_with_schema

            payload = generate_json_with_schema(
                role="generator",
                schema_model=CVJSON,
                messages=messages,
                qwen_manager=qwen_manager,
                retries=2,
                progress_callback=progress_callback,
            )
            if isinstance(payload, dict):
                return payload
        except JsonStrictError as exc:
            logger.warning(
                "GenericCVExportWorker strict CVJSON failed, retrying non-strict: %s",
                exc,
            )
        except Exception as exc:
            logger.warning(
                "GenericCVExportWorker strict CVJSON unavailable, retrying non-strict: %s",
                exc,
            )

        raw = qwen_manager.generate_structured_json(
            messages["system"],
            messages["user"],
            progress_callback=progress_callback,
            generation_overrides=self._build_generation_overrides(),
            role="generator",
        )
        return self._parse_json_response(raw)

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
