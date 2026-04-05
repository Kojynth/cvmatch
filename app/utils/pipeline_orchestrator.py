"""
Pipeline Orchestrator Module

Phase-based CV generation pipeline that replaces the monolithic CVGenerationWorker.run() method.
Each phase is a discrete unit of work with clear inputs/outputs and error handling.

Key features:
- Protocol-based phase abstraction for testability
- Central PipelineState object for data flow between phases
- Progressive phase execution with rollback support
- Structured error handling per phase
- Memory-conscious unloading between phases

Pipeline phases (in order):
1. Initialization - Load model config, determine runtime mode
2. ProfileBuild - Extract and build profile JSON
3. OfferKeywords - Extract keywords from job offer
4. DraftCV - Generate draft CV JSON
5. Critic - Review draft and provide feedback
6. FinalCV - Generate final CV with alignment retries
7. Render - Generate HTML/Markdown output
8. CoverLetter - Generate or reuse cover letter
9. Audit - Build generation audit and save
10. Cleanup - Release memory and finalize
"""

from __future__ import annotations

import copy
import os
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Protocol, Tuple

from .memory_debug import log_memory_snapshot
from .stage_subprocess_utils import is_transient_stage_memory_error

try:
    from ..config import DEFAULT_PII_CONFIG
    from ..logging.safe_logger import get_safe_logger

    logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)
except ImportError:
    import logging

    logger = logging.getLogger(__name__)


class PipelinePhaseStatus(Enum):
    """Status of a pipeline phase."""

    PENDING = auto()
    RUNNING = auto()
    COMPLETED = auto()
    SKIPPED = auto()
    FAILED = auto()


@dataclass
class PhaseResult:
    """Result of a single pipeline phase execution."""

    phase_name: str
    status: PipelinePhaseStatus
    duration_seconds: float = 0.0
    error: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineState:
    """
    Central state object that flows through the pipeline.

    Each phase reads from and writes to this state object,
    ensuring all intermediate data is accessible across phases.
    """

    # Input data (set at initialization)
    profile_data: Any = None  # ProfileWorkerData
    offer_data: Optional[Dict[str, Any]] = None
    template: str = ""
    application_id: Optional[int] = None
    user_instruction: str = ""
    cv_only_regen: bool = False
    previous_generation_audit: Dict[str, Any] = field(default_factory=dict)

    # Runtime configuration
    use_subprocess: bool = False
    skip_critic: bool = False
    vram_mode: str = "auto"
    runtime_mode: str = "unknown"
    recycle_every_runs: int = 0
    stage_routing_enabled: bool = False
    extractor_model: Optional[str] = None
    writer_model: Optional[str] = None

    # Intermediate data (populated by phases)
    language_code: str = "fr"
    profile_json: Dict[str, Any] = field(default_factory=dict)
    existing_snapshot: Dict[str, Any] = field(default_factory=dict)
    baseline_cv_json: Optional[Dict[str, Any]] = None
    offer_keywords: Dict[str, Any] = field(default_factory=dict)
    cv_json_draft: Dict[str, Any] = field(default_factory=dict)
    critic_json: Dict[str, Any] = field(default_factory=dict)
    cv_json_final: Dict[str, Any] = field(default_factory=dict)
    alignment_audit: Dict[str, Any] = field(default_factory=dict)

    # Output data
    cv_markdown: str = ""
    cv_html: str = ""
    cover_letter: str = ""
    cover_letter_review: Dict[str, Any] = field(default_factory=dict)
    generation_audit: Dict[str, Any] = field(default_factory=dict)

    # Tracking
    degraded_reasons: List[str] = field(default_factory=list)
    phase_results: List[PhaseResult] = field(default_factory=list)
    start_time: float = 0.0
    saved_application_id: Optional[int] = None

    # References (set by orchestrator)
    qwen_manager: Any = None  # QwenManager instance
    progress_callback: Optional[Callable[[str], None]] = None

    def emit_progress(self, message: str) -> None:
        """Emit a progress message if callback is set."""
        if self.progress_callback:
            try:
                self.progress_callback(message)
            except Exception:
                pass

    def add_degraded_reason(self, reason: str) -> None:
        """Add a degraded mode reason."""
        if reason and reason not in self.degraded_reasons:
            self.degraded_reasons.append(reason)

    def is_degraded(self) -> bool:
        """Check if pipeline is in degraded mode."""
        return len(self.degraded_reasons) > 0

    def get_model_name(self) -> str:
        """Get current model name for display."""
        if self.qwen_manager:
            return getattr(self.qwen_manager, "current_model_id", "IA")
        return "IA"


class PipelinePhase(Protocol):
    """Protocol for pipeline phases."""

    @property
    def name(self) -> str:
        """Phase name for logging and tracking."""
        ...

    def should_run(self, state: PipelineState) -> bool:
        """Check if this phase should run given current state."""
        ...

    def execute(self, state: PipelineState) -> PhaseResult:
        """
        Execute the phase.

        Args:
            state: Pipeline state to read from and write to

        Returns:
            PhaseResult with status and any errors/warnings
        """
        ...


# ---------------------------------------------------------------------------
# Phase Implementations
# ---------------------------------------------------------------------------


class InitializationPhase:
    """Phase 1: Load model config and determine runtime mode."""

    @property
    def name(self) -> str:
        return "initialization"

    def should_run(self, state: PipelineState) -> bool:
        return True

    def execute(self, state: PipelineState) -> PhaseResult:
        start = time.time()
        warnings: List[str] = []

        try:
            state.start_time = time.time()
            qm = state.qwen_manager

            # Load existing snapshot for cv_only_regen
            if state.cv_only_regen and state.application_id:
                # Note: _load_application_snapshot is on the worker, not here
                # The orchestrator caller should populate existing_snapshot
                if isinstance(state.existing_snapshot.get("cv_json_final"), dict):
                    state.baseline_cv_json = state.existing_snapshot.get(
                        "cv_json_final"
                    )
                elif isinstance(state.existing_snapshot.get("cv_json_draft"), dict):
                    state.baseline_cv_json = state.existing_snapshot.get(
                        "cv_json_draft"
                    )
                if not state.previous_generation_audit and isinstance(
                    state.existing_snapshot.get("generation_audit"), dict
                ):
                    state.previous_generation_audit = dict(
                        state.existing_snapshot.get("generation_audit") or {}
                    )

            logger.info(
                "Generation start: profile_id=%s template=%s",
                getattr(state.profile_data, "id", "unknown"),
                state.template,
            )

            # Load model configuration
            qm._load_selected_model_config()
            note = getattr(qm, "last_model_resolution_note", None)
            if note:
                state.emit_progress(note)
                qm.last_model_resolution_note = None

            # Determine runtime configuration
            try:
                state.vram_mode = qm._get_vram_mode()
            except Exception:
                state.vram_mode = "auto"

            try:
                state.recycle_every_runs = qm._get_recycle_every_runs()
            except Exception:
                state.recycle_every_runs = 0

            try:
                state.runtime_mode = qm._get_runtime_memory_mode()
            except Exception:
                state.runtime_mode = "unknown"

            logger.info(
                "VRAM policy: mode=%s runtime_mode=%s subprocess=%s "
                "unload_between_stages=%s skip_critic=%s recycle_every_runs=%s",
                state.vram_mode,
                state.runtime_mode,
                state.use_subprocess,
                qm._should_unload_between_stages(),
                state.skip_critic,
                state.recycle_every_runs,
            )

            model_name = state.get_model_name()

            logger.info(
                "Stage model routing: enabled=%s extractor=%s writer=%s",
                state.stage_routing_enabled,
                state.extractor_model or "-",
                state.writer_model or "-",
            )

            # Emit progress messages
            state.emit_progress(f"[MODE] {state.runtime_mode}")
            if (
                state.stage_routing_enabled
                and state.extractor_model
                and state.writer_model
                and state.extractor_model != state.writer_model
            ):
                state.emit_progress(
                    f"[MODEL] Routing actif: extractor={state.extractor_model} "
                    f"writer={state.writer_model}"
                )
            if state.runtime_mode == "LowRAM":
                state.emit_progress(
                    "[MODE] LowRAM detecte: pipeline qualite maintenue, "
                    "execution possiblement lente."
                )
            state.emit_progress(f"[MODEL] Initialisation {model_name}...")

            # Load model if not using subprocess
            if state.use_subprocess:
                state.emit_progress(
                    "[MODEL] Mode VRAM: étapes isolées en sous-processus"
                )
            elif qm._should_unload_between_stages():
                state.emit_progress("[MODEL] Mode VRAM: chargement paresseux par étape")
            else:
                try:
                    qm.set_runtime_stage("draft")
                except Exception:
                    pass
                allow_fallback = True
                try:
                    allow_fallback = bool(qm._allow_model_fallback())
                except Exception:
                    allow_fallback = True
                if allow_fallback:
                    try:
                        if bool(qm._is_selected_model_lock_enabled()):
                            allow_fallback = False
                            logger.info(
                                "Model fallback disabled for this load because selected-model lock is active."
                            )
                    except Exception:
                        pass
                qm.load_model(state.progress_callback, allow_fallback=allow_fallback)

            return PhaseResult(
                phase_name=self.name,
                status=PipelinePhaseStatus.COMPLETED,
                duration_seconds=time.time() - start,
                metadata={
                    "runtime_mode": state.runtime_mode,
                    "vram_mode": state.vram_mode,
                },
            )

        except Exception as exc:
            logger.error("Initialization phase failed: %s", exc)
            return PhaseResult(
                phase_name=self.name,
                status=PipelinePhaseStatus.FAILED,
                duration_seconds=time.time() - start,
                error=str(exc),
            )


class ProfileBuildPhase:
    """Phase 2: Build profile JSON from extracted data."""

    @property
    def name(self) -> str:
        return "profile_build"

    def should_run(self, state: PipelineState) -> bool:
        return True

    def execute(self, state: PipelineState) -> PhaseResult:
        start = time.time()

        try:
            state.emit_progress("[EXTRACTOR] Building ProfileJSON...")
            logger.info("ProfileJSON build start")

            # Note: _build_profile_json is on the worker
            # The orchestrator caller should provide this method
            # For now, we'll check if profile_json is already populated
            if not state.profile_json:
                raise RuntimeError(
                    "Profile JSON not provided - orchestrator caller must build it"
                )

            logger.info(
                "ProfileJSON build done: experiences=%s education=%s skills=%s "
                "projects=%s languages=%s",
                len(state.profile_json.get("experiences") or []),
                len(state.profile_json.get("education") or []),
                len(state.profile_json.get("skills") or []),
                len(state.profile_json.get("projects") or []),
                len(state.profile_json.get("languages") or []),
            )

            # Sync language to offer analysis
            if isinstance(state.offer_data, dict):
                analysis = state.offer_data.get("analysis")
                if (
                    isinstance(analysis, dict)
                    and analysis.get("language") != state.language_code
                ):
                    updated = dict(analysis)
                    updated["language"] = state.language_code
                    state.offer_data["analysis"] = updated
                    logger.info("Offer language set to %s", state.language_code)

            return PhaseResult(
                phase_name=self.name,
                status=PipelinePhaseStatus.COMPLETED,
                duration_seconds=time.time() - start,
                metadata={
                    "experiences_count": len(
                        state.profile_json.get("experiences") or []
                    ),
                    "skills_count": len(state.profile_json.get("skills") or []),
                },
            )

        except Exception as exc:
            logger.error("Profile build phase failed: %s", exc)
            return PhaseResult(
                phase_name=self.name,
                status=PipelinePhaseStatus.FAILED,
                duration_seconds=time.time() - start,
                error=str(exc),
            )


class OfferKeywordsPhase:
    """Phase 3: Extract keywords from job offer."""

    def __init__(
        self,
        *,
        run_subprocess: Optional[
            Callable[[str, Dict[str, Any]], Dict[str, Any]]
        ] = None,
        apply_stage_override: Optional[Callable[[str, Any], Optional[str]]] = None,
        generate_keywords: Optional[Callable[[Any], Dict[str, Any]]] = None,
        merge_keywords: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        self._run_subprocess = run_subprocess
        self._apply_stage_override = apply_stage_override
        self._generate_keywords = generate_keywords
        self._merge_keywords = merge_keywords

    @property
    def name(self) -> str:
        return "offer_keywords"

    def should_run(self, state: PipelineState) -> bool:
        offer_text = (
            state.offer_data.get("text") if isinstance(state.offer_data, dict) else ""
        )
        return bool(offer_text and len(str(offer_text).strip()) >= 50)

    def execute(self, state: PipelineState) -> PhaseResult:
        start = time.time()

        try:
            state.emit_progress("[OFFER] Extracting keywords...")
            logger.info("Offer keyword extraction start")

            if state.use_subprocess and self._run_subprocess:
                state.offer_keywords = self._run_subprocess("offer_keywords", {})
            else:
                if self._apply_stage_override:
                    self._apply_stage_override(
                        "offer_keywords", state.progress_callback
                    )
                if self._generate_keywords:
                    state.offer_keywords = self._generate_keywords(
                        state.progress_callback
                    )

            if self._merge_keywords:
                self._merge_keywords(state.offer_keywords)

            logger.info(
                "Offer keyword extraction done: keywords=%s skills=%s tools=%s "
                "lexical=%s families=%s",
                len((state.offer_keywords or {}).get("keywords") or []),
                len((state.offer_keywords or {}).get("skills") or []),
                len((state.offer_keywords or {}).get("tools") or []),
                len((state.offer_keywords or {}).get("lexical_field") or []),
                len((state.offer_keywords or {}).get("keyword_families") or {}),
            )

            return PhaseResult(
                phase_name=self.name,
                status=PipelinePhaseStatus.COMPLETED,
                duration_seconds=time.time() - start,
                metadata={
                    "keywords_count": len(
                        (state.offer_keywords or {}).get("keywords") or []
                    )
                },
            )

        except Exception as exc:
            logger.error("Offer keywords phase failed: %s", exc)
            return PhaseResult(
                phase_name=self.name,
                status=PipelinePhaseStatus.FAILED,
                duration_seconds=time.time() - start,
                error=str(exc),
            )


class DraftCVPhase:
    """Phase 4: Generate draft CV JSON."""

    def __init__(
        self,
        *,
        run_subprocess: Optional[
            Callable[[str, Dict[str, Any]], Dict[str, Any]]
        ] = None,
        apply_stage_override: Optional[Callable[[str, Any], Optional[str]]] = None,
        generate_draft: Optional[
            Callable[[Dict[str, Any], Any], Dict[str, Any]]
        ] = None,
        ensure_language_consistency: Optional[
            Callable[[Dict[str, Any], str], None]
        ] = None,
        apply_contact_fallback: Optional[
            Callable[[Dict[str, Any], Dict[str, Any]], None]
        ] = None,
        apply_target_fallback: Optional[Callable[[Dict[str, Any]], None]] = None,
        post_draft_hook: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        self._run_subprocess = run_subprocess
        self._apply_stage_override = apply_stage_override
        self._generate_draft = generate_draft
        self._ensure_language_consistency = ensure_language_consistency
        self._apply_contact_fallback = apply_contact_fallback
        self._apply_target_fallback = apply_target_fallback
        self._post_draft_hook = post_draft_hook

    @property
    def name(self) -> str:
        return "draft_cv"

    def should_run(self, state: PipelineState) -> bool:
        return True

    def execute(self, state: PipelineState) -> PhaseResult:
        start = time.time()

        try:
            state.emit_progress("[GENERATOR] Draft CVJSON...")
            logger.info("Draft CVJSON generation start")

            if state.use_subprocess and self._run_subprocess:
                state.cv_json_draft = self._run_subprocess(
                    "draft", {"profile_json": state.profile_json}
                )
            else:
                if self._apply_stage_override:
                    self._apply_stage_override("draft", state.progress_callback)
                if self._generate_draft:
                    state.cv_json_draft = self._generate_draft(
                        state.profile_json, state.progress_callback
                    )

            # Sync draft to worker attribute (needed by _postprocess_final_candidate_wrapper)
            if self._post_draft_hook:
                self._post_draft_hook(state.cv_json_draft)

            # Post-processing
            if self._ensure_language_consistency:
                self._ensure_language_consistency(state.cv_json_draft, "draft")
            if self._apply_contact_fallback:
                self._apply_contact_fallback(state.cv_json_draft, state.profile_json)
            if self._apply_target_fallback:
                self._apply_target_fallback(state.cv_json_draft)

            logger.info("Draft CVJSON generation done")

            # Unload model if needed
            if (
                not state.use_subprocess
                and state.qwen_manager
                and state.qwen_manager._should_unload_between_stages()
            ):
                state.emit_progress("[VRAM] Déchargement modèle après draft...")
                state.qwen_manager.unload_model(reason="after draft")

            return PhaseResult(
                phase_name=self.name,
                status=PipelinePhaseStatus.COMPLETED,
                duration_seconds=time.time() - start,
            )

        except Exception as exc:
            logger.error("Draft CV phase failed: %s", exc)
            return PhaseResult(
                phase_name=self.name,
                status=PipelinePhaseStatus.FAILED,
                duration_seconds=time.time() - start,
                error=f"Draft stage failed: {exc}",
            )


class CriticPhase:
    """Phase 5: Generate critic review of draft CV."""

    def __init__(
        self,
        *,
        run_subprocess: Optional[
            Callable[[str, Dict[str, Any]], Dict[str, Any]]
        ] = None,
        apply_stage_override: Optional[Callable[[str, Any], Optional[str]]] = None,
        generate_critic: Optional[Callable[[str, Any], Dict[str, Any]]] = None,
        render_draft_html: Optional[Callable[[Dict[str, Any], str, str], str]] = None,
    ):
        self._run_subprocess = run_subprocess
        self._apply_stage_override = apply_stage_override
        self._generate_critic = generate_critic
        self._render_draft_html = render_draft_html

    @property
    def name(self) -> str:
        return "critic"

    def should_run(self, state: PipelineState) -> bool:
        return not state.skip_critic

    def execute(self, state: PipelineState) -> PhaseResult:
        start = time.time()

        try:
            # First render draft to HTML for critic review
            state.emit_progress("[RENDER] Draft HTML...")
            logger.info("Draft HTML render start")

            draft_html = ""
            if self._render_draft_html:
                draft_html = self._render_draft_html(
                    state.cv_json_draft, state.template, state.language_code
                )
            logger.info("Draft HTML render done: html_len=%s", len(draft_html or ""))

            if state.skip_critic:
                raise RuntimeError(
                    "Critic stage cannot be skipped in quality-first mode."
                )

            state.emit_progress("[CRITIC] Reviewing draft...")
            logger.info("Critic JSON generation start")

            if state.use_subprocess and self._run_subprocess:
                state.critic_json = self._run_subprocess(
                    "critic", {"cv_html": draft_html}
                )
            else:
                if self._apply_stage_override:
                    self._apply_stage_override("critic", state.progress_callback)
                if self._generate_critic:
                    state.critic_json = self._generate_critic(
                        draft_html, state.progress_callback
                    )

            logger.info("Critic JSON generation done")

            # Unload model if needed
            if (
                not state.use_subprocess
                and state.qwen_manager
                and state.qwen_manager._should_unload_between_stages()
            ):
                state.emit_progress("[VRAM] Déchargement modèle après critic...")
                state.qwen_manager.unload_model(reason="after critic")

            return PhaseResult(
                phase_name=self.name,
                status=PipelinePhaseStatus.COMPLETED,
                duration_seconds=time.time() - start,
            )

        except Exception as exc:
            logger.error("Critic phase failed: %s", exc)
            return PhaseResult(
                phase_name=self.name,
                status=PipelinePhaseStatus.FAILED,
                duration_seconds=time.time() - start,
                error=str(exc),
            )


class FinalCVPhase:
    """Phase 6: Generate final CV with alignment retries."""

    def __init__(
        self,
        *,
        run_subprocess: Optional[
            Callable[[str, Dict[str, Any]], Dict[str, Any]]
        ] = None,
        apply_stage_override: Optional[Callable[[str, Any], Optional[str]]] = None,
        generate_final: Optional[
            Callable[[Dict[str, Any], Dict[str, Any], Any], Dict[str, Any]]
        ] = None,
        postprocess_candidate: Optional[
            Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]]
        ] = None,
        score_alignment: Optional[
            Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]]
        ] = None,
        get_retry_budget: Optional[Callable[[], int]] = None,
        augment_critic_feedback: Optional[
            Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]]
        ] = None,
    ):
        self._run_subprocess = run_subprocess
        self._apply_stage_override = apply_stage_override
        self._generate_final = generate_final
        self._postprocess_candidate = postprocess_candidate
        self._score_alignment = score_alignment
        self._get_retry_budget = get_retry_budget
        self._augment_critic_feedback = augment_critic_feedback

    @property
    def name(self) -> str:
        return "final_cv"

    def should_run(self, state: PipelineState) -> bool:
        return True

    def execute(self, state: PipelineState) -> PhaseResult:
        start = time.time()
        warnings: List[str] = []

        try:
            state.emit_progress("[GENERATOR] Rewrite CVJSON...")
            logger.info("Final CVJSON generation start")

            critic_json_for_final = state.critic_json

            # Generate final CV
            if state.use_subprocess and self._run_subprocess:
                state.cv_json_final = self._run_subprocess(
                    "final",
                    {
                        "profile_json": state.profile_json,
                        "critic_json": critic_json_for_final,
                    },
                )
            else:
                if self._apply_stage_override:
                    self._apply_stage_override("final", state.progress_callback)
                if self._generate_final:
                    state.cv_json_final = self._generate_final(
                        state.profile_json,
                        critic_json_for_final,
                        state.progress_callback,
                    )

            # Post-process
            if self._postprocess_candidate:
                state.cv_json_final = self._postprocess_candidate(
                    state.cv_json_final, critic_json_for_final
                )

            # Score alignment
            if self._score_alignment:
                state.alignment_audit = self._score_alignment(
                    state.cv_json_final, critic_json_for_final
                )
                logger.info(
                    "CV alignment audit: exact=%.1f family=%.1f overall=%.1f sufficient=%s",
                    float(state.alignment_audit.get("exact_keyword_score") or 0.0),
                    float(state.alignment_audit.get("lexical_family_score") or 0.0),
                    float(state.alignment_audit.get("overall_score") or 0.0),
                    bool(state.alignment_audit.get("sufficient")),
                )

            # Alignment retry loop
            retry_budget = self._get_retry_budget() if self._get_retry_budget else 2
            retry_count = 0

            while retry_count < retry_budget and not bool(
                state.alignment_audit.get("sufficient")
            ):
                retry_count += 1
                state.emit_progress(
                    f"[ALIGN] Coverage insuffisante, regeneration final ({retry_count}/{retry_budget})..."
                )

                retry_critic_payload = (
                    dict(critic_json_for_final)
                    if isinstance(critic_json_for_final, dict)
                    else {}
                )
                if isinstance(state.cv_json_final, dict) and state.cv_json_final:
                    try:
                        from .cv_payload_diagnostics import compact_cv_payload_for_retry

                        previous_payload = compact_cv_payload_for_retry(
                            state.cv_json_final
                        )
                    except Exception:
                        previous_payload = copy.deepcopy(state.cv_json_final)
                    if previous_payload:
                        retry_critic_payload["previous_cv_payload"] = previous_payload

                if self._augment_critic_feedback:
                    retry_critic_payload = self._augment_critic_feedback(
                        retry_critic_payload, state.alignment_audit
                    )
                if not isinstance(retry_critic_payload, dict):
                    retry_critic_payload = {}
                critic_json_for_final = retry_critic_payload

                try:
                    if state.use_subprocess and self._run_subprocess:
                        candidate_final = self._run_subprocess(
                            "final",
                            {
                                "profile_json": state.profile_json,
                                "critic_json": retry_critic_payload,
                            },
                        )
                    else:
                        if self._apply_stage_override:
                            self._apply_stage_override("final", state.progress_callback)
                        if self._generate_final:
                            candidate_final = self._generate_final(
                                state.profile_json,
                                retry_critic_payload,
                                state.progress_callback,
                            )
                except Exception as exc:
                    logger.warning(
                        "Alignment retry failed at attempt %s/%s: %s",
                        retry_count,
                        retry_budget,
                        exc,
                    )
                    break

                if self._postprocess_candidate:
                    candidate_final = self._postprocess_candidate(
                        candidate_final, retry_critic_payload
                    )

                if self._score_alignment:
                    candidate_audit = self._score_alignment(
                        candidate_final, retry_critic_payload
                    )
                    logger.info(
                        "CV alignment retry %s/%s: exact=%.1f family=%.1f overall=%.1f sufficient=%s",
                        retry_count,
                        retry_budget,
                        float(candidate_audit.get("exact_keyword_score") or 0.0),
                        float(candidate_audit.get("lexical_family_score") or 0.0),
                        float(candidate_audit.get("overall_score") or 0.0),
                        bool(candidate_audit.get("sufficient")),
                    )

                    if (
                        candidate_final == state.cv_json_final
                        and candidate_audit == state.alignment_audit
                    ):
                        logger.warning(
                            "Alignment retry converged to identical candidate at attempt %s/%s; stopping early.",
                            retry_count,
                            retry_budget,
                        )
                        break

                    current_score = float(
                        state.alignment_audit.get("overall_score") or 0.0
                    )
                    candidate_score = float(candidate_audit.get("overall_score") or 0.0)
                    if (
                        bool(candidate_audit.get("sufficient"))
                        or candidate_score >= current_score
                    ):
                        state.cv_json_final = candidate_final
                        state.alignment_audit = candidate_audit

            if not bool(state.alignment_audit.get("sufficient")):
                warnings.append(
                    f"CV alignment remains below threshold: "
                    f"overall={state.alignment_audit.get('overall_score', 0):.1f}"
                )
                logger.warning(
                    "CV alignment remains below threshold after retries: exact=%.1f family=%.1f overall=%.1f",
                    float(state.alignment_audit.get("exact_keyword_score") or 0.0),
                    float(state.alignment_audit.get("lexical_family_score") or 0.0),
                    float(state.alignment_audit.get("overall_score") or 0.0),
                )

            state.critic_json = critic_json_for_final
            logger.info("Final CVJSON generation done")

            return PhaseResult(
                phase_name=self.name,
                status=PipelinePhaseStatus.COMPLETED,
                duration_seconds=time.time() - start,
                warnings=warnings,
                metadata={
                    "retry_count": retry_count,
                    "alignment_sufficient": bool(
                        state.alignment_audit.get("sufficient")
                    ),
                },
            )

        except Exception as exc:
            logger.error("Final CV phase failed: %s", exc)
            return PhaseResult(
                phase_name=self.name,
                status=PipelinePhaseStatus.FAILED,
                duration_seconds=time.time() - start,
                error=f"Final stage failed: {exc}",
            )


class RenderPhase:
    """Phase 7: Render final CV to HTML and Markdown."""

    def __init__(
        self,
        *,
        render_markdown: Optional[Callable[[Dict[str, Any], str], str]] = None,
        render_html: Optional[Callable[[Dict[str, Any], str, str], str]] = None,
    ):
        self._render_markdown = render_markdown
        self._render_html = render_html

    @property
    def name(self) -> str:
        return "render"

    def should_run(self, state: PipelineState) -> bool:
        return True

    def execute(self, state: PipelineState) -> PhaseResult:
        start = time.time()

        try:
            state.emit_progress("[RENDER] Final output...")
            logger.info("Final render start")

            if self._render_markdown:
                state.cv_markdown = self._render_markdown(
                    state.cv_json_final, state.language_code
                )

            if self._render_html:
                state.cv_html = self._render_html(
                    state.cv_json_final, state.template, state.language_code
                )

            logger.info(
                "Final render done: markdown_len=%s html_len=%s",
                len(state.cv_markdown or ""),
                len(state.cv_html or ""),
            )

            return PhaseResult(
                phase_name=self.name,
                status=PipelinePhaseStatus.COMPLETED,
                duration_seconds=time.time() - start,
                metadata={
                    "markdown_length": len(state.cv_markdown or ""),
                    "html_length": len(state.cv_html or ""),
                },
            )

        except Exception as exc:
            logger.error("Render phase failed: %s", exc)
            return PhaseResult(
                phase_name=self.name,
                status=PipelinePhaseStatus.FAILED,
                duration_seconds=time.time() - start,
                error=str(exc),
            )


class CoverLetterPhase:
    """Phase 8: Generate or reuse cover letter."""

    def __init__(
        self,
        *,
        run_subprocess: Optional[
            Callable[[str, Dict[str, Any]], Dict[str, Any]]
        ] = None,
        apply_stage_override: Optional[Callable[[str, Any], Optional[str]]] = None,
        build_prompt: Optional[Callable[[], str]] = None,
        generate_letter: Optional[Callable[[str, Any], str]] = None,
        ensure_language_consistency: Optional[Callable[[str, str], str]] = None,
        enforce_alignment: Optional[Callable[[str, str], str]] = None,
        is_structure_coherent: Optional[Callable[[str, str], bool]] = None,
        critique_and_rewrite: Optional[Callable[..., Any]] = None,
        should_run_critic: Optional[Callable[[], bool]] = None,
    ):
        self._run_subprocess = run_subprocess
        self._apply_stage_override = apply_stage_override
        self._build_prompt = build_prompt
        self._generate_letter = generate_letter
        self._ensure_language_consistency = ensure_language_consistency
        self._enforce_alignment = enforce_alignment
        self._is_structure_coherent = is_structure_coherent
        self._critique_and_rewrite = critique_and_rewrite
        self._should_run_critic = should_run_critic

    def _apply_letter_review_result(
        self,
        state: PipelineState,
        review_result: Any,
        *,
        context: str,
    ) -> bool:
        applied = False
        if isinstance(review_result, dict):
            review_payload = review_result.get("review")
            if isinstance(review_payload, dict):
                state.cover_letter_review = review_payload
            reviewed_letter = str(review_result.get("cover_letter") or "").strip()
            if reviewed_letter:
                state.cover_letter = reviewed_letter
                applied = True
            if review_result.get("applied"):
                logger.info("Cover letter %s applied corrections.", context)
            return applied

        reviewed_letter = str(review_result or "").strip()
        if reviewed_letter:
            state.cover_letter = reviewed_letter
            logger.info("Cover letter %s applied text rewrite.", context)
            return True
        return False

    @staticmethod
    def _is_language_mismatch_error(exc: Exception) -> bool:
        details = str(exc or "").strip().lower()
        if not details:
            return False
        return "language mismatch" in details

    def _degrade_cover_letter_generation(
        self,
        state: PipelineState,
        *,
        progress_message: str,
        warning_message: str,
        existing_reason: str,
        skipped_reason: str,
        existing_mode: str,
        skipped_mode: str,
        unavailable_reason: str,
    ) -> Tuple[str, List[str]]:
        existing_letter = str(state.existing_snapshot.get("cover_letter") or "").strip()
        state.emit_progress(progress_message)

        if existing_letter:
            state.add_degraded_reason(existing_reason)
            state.cover_letter = existing_letter
            state.cover_letter_review = self._load_existing_cover_letter_review(state)
            return existing_mode, [existing_reason]

        state.add_degraded_reason(skipped_reason)
        state.cover_letter = ""
        state.cover_letter_review = {
            "relevance_score": 0,
            "structure_ok": False,
            "language": state.language_code,
            "unavailable_reason": unavailable_reason,
        }
        logger.warning("%s", warning_message)
        return skipped_mode, [skipped_reason]

    def _validate_cover_letter_language(
        self,
        state: PipelineState,
        *,
        allow_rewrite: bool,
        context: str,
        prefer_subprocess_rewrite: bool = True,
    ) -> Optional[Dict[str, Any]]:
        if not self._ensure_language_consistency:
            return None
        try:
            state.cover_letter = self._ensure_language_consistency(
                state.cover_letter, state.language_code
            )
            return None
        except Exception as exc:
            logger.warning("Cover letter language check failed: %s", exc)
            if not allow_rewrite:
                # Non-fatal fallback for final validation: keep generated text.
                logger.warning(
                    "Cover letter language check degraded to fallback (context=%s).",
                    context,
                )
                return None
            if not self._critique_and_rewrite:
                raise RuntimeError(str(exc)) from exc

        state.emit_progress("[LETTER] Language mismatch detected, rewriting...")
        try:
            rewrite_result = {}
            if (
                prefer_subprocess_rewrite
                and state.use_subprocess
                and self._run_subprocess is not None
            ):
                rewrite_payload = {
                    "cover_letter": state.cover_letter,
                    "language_code": state.language_code,
                    "rewrite_reason": "language_mismatch",
                }
                try:
                    rewrite_result = self._run_subprocess(
                        "cover_letter_critic", rewrite_payload
                    )
                except Exception as exc:
                    can_fallback = self._critique_and_rewrite is not None
                    if (
                        can_fallback
                        and self._is_transient_cover_letter_subprocess_error(exc)
                    ):
                        state.emit_progress(
                            "[LETTER] Language rewrite subprocess memory retry exhausted, falling back to in-process rewrite..."
                        )
                        state.add_degraded_reason(
                            "cover_letter_language_rewrite_subprocess_memory_fallback"
                        )
                        logger.warning(
                            "Cover-letter language rewrite subprocess failed with transient memory error; "
                            "falling back to in-process rewrite: %s",
                            exc,
                        )
                        if self._apply_stage_override:
                            self._apply_stage_override(
                                "cover_letter_critic", state.progress_callback
                            )
                        rewrite_result = self._critique_and_rewrite(
                            state.cover_letter,
                            state.language_code,
                            state.progress_callback,
                            rewrite_reason="language_mismatch",
                        )
                    else:
                        raise
            else:
                rewrite_result = self._critique_and_rewrite(
                    state.cover_letter,
                    state.language_code,
                    state.progress_callback,
                    rewrite_reason="language_mismatch",
                )
            applied = self._apply_letter_review_result(
                state,
                rewrite_result,
                context=f"{context} language rewrite",
            )
            if not applied:
                raise RuntimeError("Language rewrite returned empty output.")
            state.cover_letter = self._ensure_language_consistency(
                state.cover_letter, state.language_code
            )
            return {
                "language_rewrite_applied": True,
                "skip_critic_stage": True,
            }
        except Exception as rewrite_exc:
            if self._is_language_mismatch_error(rewrite_exc):
                warning_reason = "cover_letter_kept_after_language_validation_failure"
                state.add_degraded_reason(warning_reason)
                state.emit_progress(
                    "[LETTER] Language rewrite still failed validation; keeping the generated letter and continuing..."
                )
                logger.warning(
                    "Cover-letter language rewrite still failed validation; keeping generated letter target=%s detail=%s",
                    state.language_code,
                    rewrite_exc,
                )
                if (
                    not isinstance(state.cover_letter_review, dict)
                    or not state.cover_letter_review
                ):
                    state.cover_letter_review = {
                        "relevance_score": 0,
                        "structure_ok": True,
                        "language": state.language_code,
                        "validation_warning": "language_mismatch_after_rewrite",
                    }
                return {
                    "mode": warning_reason,
                    "warnings": [warning_reason],
                    "language_rewrite_applied": True,
                    "skip_critic_stage": True,
                }
            raise RuntimeError(
                f"Cover letter language mismatch after rewrite (target={state.language_code}): {rewrite_exc}"
            ) from rewrite_exc

    @staticmethod
    def _is_transient_cover_letter_subprocess_error(exc: Exception) -> bool:
        details = str(exc or "").strip()
        if not details:
            return False
        return is_transient_stage_memory_error(details)

    @property
    def name(self) -> str:
        return "cover_letter"

    def should_run(self, state: PipelineState) -> bool:
        return True

    def execute(self, state: PipelineState) -> PhaseResult:
        start = time.time()

        try:
            if state.cv_only_regen:
                return self._execute_cv_only_mode(state, start)
            else:
                return self._execute_generation_mode(state, start)

        except Exception as exc:
            logger.error("Cover letter phase failed: %s", exc)
            return PhaseResult(
                phase_name=self.name,
                status=PipelinePhaseStatus.FAILED,
                duration_seconds=time.time() - start,
                error=f"Cover letter stage failed: {exc}",
            )

    def _execute_cv_only_mode(self, state: PipelineState, start: float) -> PhaseResult:
        """Handle CV-only regeneration mode (reuse existing letter)."""
        state.emit_progress("[LETTER] CV-only regeneration: keeping existing letter...")

        state.cover_letter = str(
            state.existing_snapshot.get("cover_letter") or ""
        ).strip()

        # Extract previous review data
        previous_letter = {}
        if isinstance(state.previous_generation_audit, dict):
            breakdown = state.previous_generation_audit.get("breakdown")
            if isinstance(breakdown, dict):
                letter_payload = breakdown.get("letter")
                if isinstance(letter_payload, dict):
                    previous_letter = letter_payload

        try:
            previous_relevance = int(
                float(previous_letter.get("relevance_score") or 80)
            )
        except Exception:
            previous_relevance = 80

        state.cover_letter_review = {
            "relevance_score": previous_relevance,
            "structure_ok": bool(previous_letter.get("structure_ok", True)),
            "language": str(previous_letter.get("language") or state.language_code),
        }

        logger.info(
            "CV-only regeneration: cover letter reused (len=%s).",
            len(state.cover_letter or ""),
        )

        return PhaseResult(
            phase_name=self.name,
            status=PipelinePhaseStatus.COMPLETED,
            duration_seconds=time.time() - start,
            metadata={"mode": "cv_only_reuse"},
        )

    def _load_existing_cover_letter_review(
        self, state: PipelineState
    ) -> Dict[str, Any]:
        previous_audit = (
            state.previous_generation_audit
            if isinstance(state.previous_generation_audit, dict)
            else {}
        )
        if not previous_audit and isinstance(state.existing_snapshot, dict):
            snapshot_audit = state.existing_snapshot.get("generation_audit")
            if isinstance(snapshot_audit, dict):
                previous_audit = snapshot_audit

        previous_letter = {}
        breakdown = previous_audit.get("breakdown")
        if isinstance(breakdown, dict):
            letter_payload = breakdown.get("letter")
            if isinstance(letter_payload, dict):
                previous_letter = dict(letter_payload)

        if previous_letter:
            return previous_letter

        return {
            "relevance_score": 80,
            "structure_ok": True,
            "language": state.language_code,
        }

    def _execute_generation_mode(
        self, state: PipelineState, start: float
    ) -> PhaseResult:
        """Handle full cover letter generation."""
        state.emit_progress("[LETTER] Generating cover letter...")
        logger.info("Cover letter generation start")

        letter_prompt = self._build_prompt() if self._build_prompt else ""
        generation_mode = "generated"
        force_inprocess_review = False

        try:
            if state.use_subprocess and self._run_subprocess:
                cover_payload = {"letter_prompt": letter_prompt}
                try:
                    cover_result = self._run_subprocess("cover_letter", cover_payload)
                    state.cover_letter = cover_result.get("cover_letter", "")
                except Exception as exc:
                    if self._is_transient_cover_letter_subprocess_error(exc):
                        warning_message = (
                            "Cover-letter subprocess failed with transient memory error; "
                            "skipping cover-letter generation without in-process fallback "
                            "to avoid parent model reload."
                        )
                        mode, warnings = self._degrade_cover_letter_generation(
                            state,
                            progress_message=(
                                "[LETTER] Subprocess memory retry exhausted; "
                                "keeping CV result and skipping cover-letter generation..."
                            ),
                            warning_message=warning_message,
                            existing_reason=(
                                "cover_letter_reused_after_subprocess_memory_exhaustion"
                            ),
                            skipped_reason=(
                                "cover_letter_generation_skipped_after_subprocess_memory_exhaustion"
                            ),
                            existing_mode=("cover_letter_reused_after_subprocess_oom"),
                            skipped_mode=("cover_letter_skipped_after_subprocess_oom"),
                            unavailable_reason="subprocess_memory_exhausted",
                        )
                        logger.warning("%s %s", warning_message, exc)
                        return PhaseResult(
                            phase_name=self.name,
                            status=PipelinePhaseStatus.COMPLETED,
                            duration_seconds=time.time() - start,
                            warnings=warnings,
                            metadata={
                                "mode": mode,
                                "length": len(state.cover_letter or ""),
                            },
                        )
                    raise
            else:
                if self._apply_stage_override:
                    self._apply_stage_override("cover_letter", state.progress_callback)
                if self._generate_letter:
                    state.cover_letter = self._generate_letter(
                        letter_prompt, state.progress_callback
                    )
        except Exception as exc:
            raise RuntimeError(f"Cover letter generation failed: {exc}") from exc

        # Post-process
        phase_warnings: List[str] = []
        skip_critic_stage = False

        language_result = self._validate_cover_letter_language(
            state,
            allow_rewrite=True,
            context="generation",
            prefer_subprocess_rewrite=not force_inprocess_review,
        )
        if isinstance(language_result, dict):
            logger.info(
                "Cover letter generation degraded after language validation failure: length=%s",
                len(state.cover_letter or ""),
            )
            generation_mode = str(
                language_result.get("mode")
                or "cover_letter_kept_after_language_validation_failure"
            )
            phase_warnings.extend(list(language_result.get("warnings") or []))
            skip_critic_stage = bool(language_result.get("skip_critic_stage"))
        if self._enforce_alignment:
            state.cover_letter = self._enforce_alignment(
                state.cover_letter, state.language_code
            )

        # Run critic if enabled
        should_run_critic = (
            self._should_run_critic() if self._should_run_critic else True
        )
        if should_run_critic and skip_critic_stage:
            logger.info(
                "Cover letter critic skipped: language rewrite already consumed rewrite stage."
            )
        elif should_run_critic:
            state.emit_progress("[LETTER] Critique + correction...")
            try:
                if (
                    state.use_subprocess
                    and self._run_subprocess
                    and (not force_inprocess_review)
                ):
                    review_payload = {
                        "cover_letter": state.cover_letter,
                        "language_code": state.language_code,
                    }
                    try:
                        review_result = self._run_subprocess(
                            "cover_letter_critic", review_payload
                        )
                    except Exception as exc:
                        can_fallback = self._critique_and_rewrite is not None
                        if (
                            can_fallback
                            and self._is_transient_cover_letter_subprocess_error(exc)
                        ):
                            state.emit_progress(
                                "[LETTER] Critic subprocess memory retry exhausted, falling back to in-process rewrite..."
                            )
                            state.add_degraded_reason(
                                "cover_letter_critic_subprocess_memory_fallback"
                            )
                            logger.warning(
                                "Cover-letter critic subprocess failed with transient memory error; "
                                "falling back to in-process rewrite: %s",
                                exc,
                            )
                            if self._apply_stage_override:
                                self._apply_stage_override(
                                    "cover_letter_critic", state.progress_callback
                                )
                            review_result = self._critique_and_rewrite(
                                state.cover_letter,
                                state.language_code,
                                state.progress_callback,
                            )
                        else:
                            raise
                else:
                    if self._apply_stage_override:
                        self._apply_stage_override(
                            "cover_letter_critic", state.progress_callback
                        )
                    if self._critique_and_rewrite:
                        review_result = self._critique_and_rewrite(
                            state.cover_letter,
                            state.language_code,
                            state.progress_callback,
                        )
                    else:
                        review_result = {}

                self._apply_letter_review_result(
                    state,
                    review_result,
                    context="critic",
                )

            except Exception as exc:
                raise RuntimeError(f"Cover letter critic stage failed: {exc}") from exc

        # Final validation
        self._validate_cover_letter_language(
            state,
            allow_rewrite=False,
            context="final validation",
        )
        if self._enforce_alignment:
            state.cover_letter = self._enforce_alignment(
                state.cover_letter, state.language_code
            )

        if self._is_structure_coherent:
            try:
                structure_ok = bool(
                    self._is_structure_coherent(state.cover_letter, state.language_code)
                )
            except TypeError:
                # Backward-compatible call path for legacy callbacks expecting only (letter).
                logger.warning(
                    "Cover letter structure callback arity mismatch; retrying with legacy signature."
                )
                structure_ok = bool(self._is_structure_coherent(state.cover_letter))
            if not structure_ok:
                raise RuntimeError(
                    "Cover letter structure not coherent after generation/review."
                )

        if (
            not isinstance(state.cover_letter_review, dict)
            or not state.cover_letter_review
        ):
            state.cover_letter_review = {
                "relevance_score": 80,
                "structure_ok": True,
                "language": state.language_code,
            }

        logger.info(
            "Cover letter generation done: length=%s", len(state.cover_letter or "")
        )

        return PhaseResult(
            phase_name=self.name,
            status=PipelinePhaseStatus.COMPLETED,
            duration_seconds=time.time() - start,
            warnings=phase_warnings,
            metadata={"mode": generation_mode, "length": len(state.cover_letter or "")},
        )


class AuditAndSavePhase:
    """Phase 9: Build generation audit and save application."""

    def __init__(
        self,
        *,
        build_audit: Optional[
            Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]]
        ] = None,
        is_audit_better: Optional[
            Callable[[Dict[str, Any], Dict[str, Any]], bool]
        ] = None,
        save_application: Optional[Callable[..., Any]] = None,
        render_markdown: Optional[Callable[[Dict[str, Any], str], str]] = None,
        render_html: Optional[Callable[[Dict[str, Any], str, str], str]] = None,
        score_alignment: Optional[
            Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]]
        ] = None,
    ):
        self._build_audit = build_audit
        self._is_audit_better = is_audit_better
        self._save_application = save_application
        self._render_markdown = render_markdown
        self._render_html = render_html
        self._score_alignment = score_alignment

    @property
    def name(self) -> str:
        return "audit_and_save"

    def should_run(self, state: PipelineState) -> bool:
        return True

    def execute(self, state: PipelineState) -> PhaseResult:
        start = time.time()

        try:
            # Build generation audit
            if self._build_audit:
                state.generation_audit = self._build_audit(
                    state.alignment_audit, state.cover_letter_review
                )

            # Handle CV-only regen score comparison
            if (
                state.cv_only_regen
                and not state.user_instruction
                and isinstance(state.previous_generation_audit, dict)
                and state.previous_generation_audit
                and self._is_audit_better
                and not self._is_audit_better(
                    state.generation_audit, state.previous_generation_audit
                )
            ):
                logger.info(
                    "CV-only regeneration score did not improve; keeping previous CV version."
                )
                previous_cv_json = state.existing_snapshot.get("cv_json_final")
                if isinstance(previous_cv_json, dict):
                    state.cv_json_final = copy.deepcopy(previous_cv_json)
                    if self._score_alignment:
                        state.alignment_audit = self._score_alignment(
                            state.cv_json_final, state.critic_json
                        )
                    previous_markdown = str(
                        state.existing_snapshot.get("cv_markdown") or ""
                    ).strip()
                    previous_html = str(
                        state.existing_snapshot.get("cv_html") or ""
                    ).strip()
                    if previous_markdown:
                        state.cv_markdown = previous_markdown
                    elif self._render_markdown:
                        state.cv_markdown = self._render_markdown(
                            state.cv_json_final, state.language_code
                        )
                    if previous_html:
                        state.cv_html = previous_html
                    elif self._render_html:
                        state.cv_html = self._render_html(
                            state.cv_json_final, state.template, state.language_code
                        )
                state.generation_audit = dict(state.previous_generation_audit)

            # Save application
            state.emit_progress("[SAVE] Persisting application...")
            logger.info("Save application start")

            application = None
            if self._save_application:
                preserve_cover_letter = bool(state.cv_only_regen) or any(
                    reason in getattr(state, "degraded_reasons", [])
                    for reason in (
                        "cover_letter_generation_skipped_after_subprocess_memory_exhaustion",
                        "cover_letter_reused_after_subprocess_memory_exhaustion",
                    )
                )
                application = self._save_application(
                    state.cv_markdown,
                    state.cover_letter,
                    profile_json=state.profile_json,
                    critic_json=state.critic_json,
                    cv_json_draft=state.cv_json_draft,
                    cv_json_final=state.cv_json_final,
                    cv_html=state.cv_html,
                    generation_audit=state.generation_audit,
                    alignment_audit=state.alignment_audit,
                    cover_letter_review=state.cover_letter_review,
                    application_id=state.application_id,
                    preserve_cover_letter=preserve_cover_letter,
                )

            application_id = (
                getattr(application, "id", "unknown") if application else "unknown"
            )
            state.saved_application_id = (
                application_id if isinstance(application_id, int) else None
            )
            logger.info("Save application done: id=%s", application_id)

            return PhaseResult(
                phase_name=self.name,
                status=PipelinePhaseStatus.COMPLETED,
                duration_seconds=time.time() - start,
                metadata={"application_id": application_id},
            )

        except Exception as exc:
            logger.error("Audit and save phase failed: %s", exc)
            return PhaseResult(
                phase_name=self.name,
                status=PipelinePhaseStatus.FAILED,
                duration_seconds=time.time() - start,
                error=str(exc),
            )


class CleanupPhase:
    """Phase 10: Release memory and finalize."""

    @property
    def name(self) -> str:
        return "cleanup"

    def should_run(self, state: PipelineState) -> bool:
        return True

    def execute(self, state: PipelineState) -> PhaseResult:
        start = time.time()

        try:
            state.emit_progress("[CLEANUP] Releasing memory...")
            qm = state.qwen_manager

            try:
                qm.mark_run_completed()
                qm._record_success("pipeline completed")
                if not state.use_subprocess and qm._should_unload_after_generation():
                    state.emit_progress(
                        "[VRAM] Unloading model after run (low headroom)..."
                    )
                    qm.unload_model(reason="after generation")
                else:
                    qm.cleanup_memory()
            except Exception:
                qm.cleanup_memory()

            return PhaseResult(
                phase_name=self.name,
                status=PipelinePhaseStatus.COMPLETED,
                duration_seconds=time.time() - start,
            )

        except Exception as exc:
            logger.error("Cleanup phase failed: %s", exc)
            return PhaseResult(
                phase_name=self.name,
                status=PipelinePhaseStatus.FAILED,
                duration_seconds=time.time() - start,
                error=str(exc),
            )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


class PipelineOrchestrator:
    """
    Orchestrates CV generation pipeline phases.

    This class replaces the monolithic run() method in CVGenerationWorker
    with a phase-based approach that's easier to test and maintain.
    """

    def __init__(self, phases: Optional[List[PipelinePhase]] = None):
        """
        Initialize orchestrator with phases.

        Args:
            phases: List of phases to execute. If None, uses default phase list.
        """
        self._phases = phases or []

    @staticmethod
    def _to_bool(value: Any, default: bool = False) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("1", "true", "yes", "y", "on")

    def _is_adaptive_subprocess_recovery_enabled(self, state: PipelineState) -> bool:
        """
        Adaptive strategy:
        - run each phase in-process first
        - on memory-related failure, retry that phase in subprocess
        - resume next phases in-process
        """
        if bool(getattr(state, "use_subprocess", False)):
            # Explicit global subprocess mode remains authoritative.
            return False

        env_value = os.getenv("CVMATCH_ADAPTIVE_SUBPROCESS_RECOVERY")
        if env_value is not None:
            return self._to_bool(env_value, True)

        custom = (
            getattr(getattr(state, "qwen_manager", None), "custom_parameters", None)
            or {}
        )
        if "adaptive_subprocess_recovery" in custom:
            return self._to_bool(custom.get("adaptive_subprocess_recovery"), True)

        return True

    def _is_memory_related_failure(
        self, state: PipelineState, error: Optional[str]
    ) -> bool:
        msg = str(error or "").strip()
        if not msg:
            return False

        qm = getattr(state, "qwen_manager", None)
        if qm is not None:
            try:
                if bool(qm._is_memory_pressure_failure_reason(msg)):
                    return True
            except Exception:
                pass

        lowered = msg.lower()
        return (
            "cuda out of memory" in lowered
            or "out of memory" in lowered
            or "oom" in lowered
            or "cpu-only device map" in lowered
            or "hybrid-only policy" in lowered
            or "insufficient for mixed placement" in lowered
            or "cublas_status_alloc_failed" in lowered
            or "failed to allocate" in lowered
        )

    @staticmethod
    def _phase_supports_subprocess_retry(phase: PipelinePhase) -> bool:
        if str(getattr(phase, "name", "") or "") == "initialization":
            return True
        runner = getattr(phase, "_run_subprocess", None)
        return callable(runner)

    def _should_keep_subprocess_after_recovery(self, state: PipelineState) -> bool:
        """Keep subprocess mode enabled after a successful memory recovery retry."""
        env_value = os.getenv("CVMATCH_STICKY_SUBPROCESS_AFTER_RECOVERY")
        if env_value is not None:
            return self._to_bool(env_value, True)

        custom = (
            getattr(getattr(state, "qwen_manager", None), "custom_parameters", None)
            or {}
        )
        if "sticky_subprocess_after_recovery" in custom:
            return self._to_bool(custom.get("sticky_subprocess_after_recovery"), True)

        return True

    def _execute_phase_with_adaptive_recovery(
        self,
        *,
        phase: PipelinePhase,
        state: PipelineState,
        adaptive_enabled: bool,
    ) -> PhaseResult:
        result = phase.execute(state)
        if result.status != PipelinePhaseStatus.FAILED:
            return result

        if not adaptive_enabled:
            return result
        if bool(getattr(state, "use_subprocess", False)):
            return result
        if not self._phase_supports_subprocess_retry(phase):
            return result
        if not self._is_memory_related_failure(state, result.error):
            return result

        logger.warning(
            "Phase '%s' failed with memory error in-process; retrying this phase in subprocess mode.",
            phase.name,
        )
        state.emit_progress(
            f"[RECOVERY] OOM detecte sur '{phase.name}', retry de l'etape en subprocess..."
        )

        qm = getattr(state, "qwen_manager", None)
        if qm is not None:
            try:
                qm.cleanup_memory()
            except Exception:
                pass

        previous_mode = bool(getattr(state, "use_subprocess", False))
        state.use_subprocess = True
        retry_result = phase.execute(state)

        if retry_result.status == PipelinePhaseStatus.COMPLETED:
            keep_subprocess = self._should_keep_subprocess_after_recovery(state)
            state.use_subprocess = True if keep_subprocess else previous_mode
            state.emit_progress(
                f"[RECOVERY] Etape '{phase.name}' recuperee en subprocess, "
                + (
                    "mode subprocess conserve."
                    if keep_subprocess
                    else "reprise en mode normal."
                )
            )
            metadata = dict(retry_result.metadata or {})
            metadata["adaptive_subprocess_retry"] = True
            metadata["initial_error"] = str(result.error or "")
            metadata["subprocess_mode_persisted"] = bool(keep_subprocess)
            retry_result = PhaseResult(
                phase_name=retry_result.phase_name,
                status=retry_result.status,
                duration_seconds=retry_result.duration_seconds,
                error=retry_result.error,
                warnings=list(retry_result.warnings or []),
                metadata=metadata,
            )
            return retry_result

        logger.error(
            "Adaptive subprocess retry failed at phase '%s': %s",
            phase.name,
            retry_result.error,
        )
        state.use_subprocess = previous_mode
        if not retry_result.error:
            retry_result.error = result.error
        return retry_result

    def run(self, state: PipelineState) -> Tuple[bool, List[PhaseResult]]:
        """
        Execute all phases in sequence.

        Args:
            state: Pipeline state to pass through phases

        Returns:
            Tuple of (success, list of phase results)
        """
        results: List[PhaseResult] = []
        adaptive_enabled = self._is_adaptive_subprocess_recovery_enabled(state)
        if adaptive_enabled:
            logger.info(
                "Adaptive subprocess recovery enabled (per-phase memory retry)."
            )

        for phase in self._phases:
            if not phase.should_run(state):
                results.append(
                    PhaseResult(
                        phase_name=phase.name,
                        status=PipelinePhaseStatus.SKIPPED,
                    )
                )
                continue

            log_memory_snapshot(
                label="phase_start",
                stage=phase.name,
                extra={
                    "subprocess_mode": state.use_subprocess,
                    "runtime_mode": state.runtime_mode,
                },
                logger_override=logger,
            )
            result = self._execute_phase_with_adaptive_recovery(
                phase=phase,
                state=state,
                adaptive_enabled=adaptive_enabled,
            )
            log_memory_snapshot(
                label="phase_end",
                stage=phase.name,
                extra={
                    "phase_status": result.status.name,
                    "subprocess_mode": state.use_subprocess,
                    "runtime_mode": state.runtime_mode,
                },
                logger_override=logger,
            )
            results.append(result)
            state.phase_results.append(result)

            if result.status == PipelinePhaseStatus.FAILED:
                logger.error(
                    "Pipeline failed at phase '%s': %s",
                    phase.name,
                    result.error,
                )
                return False, results

        return True, results

    def get_total_duration(self, results: List[PhaseResult]) -> float:
        """Get total duration of all phases."""
        return sum(r.duration_seconds for r in results)


def build_default_pipeline(
    *,
    worker: Any,
    qwen_manager: Any,
) -> Tuple[PipelineOrchestrator, PipelineState]:
    """
    Build a default pipeline orchestrator configured for a worker.

    This is a convenience function that creates all phases with the
    necessary callbacks wired to the worker's methods.

    Args:
        worker: CVGenerationWorker instance
        qwen_manager: QwenManager instance

    Returns:
        Tuple of (orchestrator, initial_state)
    """
    from ..utils.cv_json_renderer import cv_json_to_html, cv_json_to_markdown

    # Create initial state
    state = PipelineState(
        profile_data=worker.profile_data,
        offer_data=worker.offer_data,
        template=worker.template,
        application_id=worker.application_id,
        user_instruction=worker.user_instruction,
        cv_only_regen=worker.cv_only_regen,
        previous_generation_audit=worker.previous_generation_audit,
        qwen_manager=qwen_manager,
        use_subprocess=worker._should_use_stage_subprocess(),
        skip_critic=worker._should_skip_critic_stage(),
        stage_routing_enabled=worker._is_stage_model_routing_enabled(),
        extractor_model=worker._resolve_stage_model_override("offer_keywords"),
        writer_model=worker._resolve_stage_model_override("draft"),
        language_code=worker._resolve_language_code(),
    )

    # Build phases with worker method callbacks
    phases: List[PipelinePhase] = [
        InitializationPhase(),
        ProfileBuildPhase(),
        OfferKeywordsPhase(
            run_subprocess=worker._run_stage_subprocess,
            apply_stage_override=worker._apply_stage_model_override,
            generate_keywords=worker.generate_offer_keywords_json,
            merge_keywords=worker._merge_offer_keywords,
        ),
        DraftCVPhase(
            run_subprocess=worker._run_stage_subprocess,
            apply_stage_override=worker._apply_stage_model_override,
            generate_draft=lambda pj, cb: worker.generate_cv_json_draft(
                profile_json=pj, progress_callback=cb
            ),
            ensure_language_consistency=lambda cv, stage: worker._ensure_cv_json_language_consistency(
                cv, stage=stage
            ),
            apply_contact_fallback=worker._apply_contact_fallback,
            apply_target_fallback=worker._apply_target_fallback,
            post_draft_hook=lambda draft: setattr(
                worker, "_pipeline_cv_json_draft", draft
            ),
        ),
        CriticPhase(
            run_subprocess=worker._run_stage_subprocess,
            apply_stage_override=worker._apply_stage_model_override,
            generate_critic=lambda html, cb: worker.generate_critic_json(
                cv_html=html, progress_callback=cb
            ),
            render_draft_html=lambda cv, tmpl, lang: cv_json_to_html(
                cv, template=tmpl, language=lang
            ),
        ),
        FinalCVPhase(
            run_subprocess=worker._run_stage_subprocess,
            apply_stage_override=worker._apply_stage_model_override,
            generate_final=lambda pj, cj, cb: worker.generate_cv_json_final(
                profile_json=pj, critic_json=cj, progress_callback=cb
            ),
            postprocess_candidate=worker._postprocess_final_candidate_wrapper,
            score_alignment=lambda cv, cj: worker._score_cv_offer_alignment(
                cv, critic_json=cj
            ),
            get_retry_budget=worker._get_alignment_retry_attempts,
            augment_critic_feedback=worker._augment_critic_with_alignment_feedback,
        ),
        RenderPhase(
            render_markdown=lambda cv, lang: cv_json_to_markdown(cv, language=lang),
            render_html=lambda cv, tmpl, lang: cv_json_to_html(
                cv, template=tmpl, language=lang
            ),
        ),
        CoverLetterPhase(
            run_subprocess=worker._run_stage_subprocess,
            apply_stage_override=worker._apply_stage_model_override,
            build_prompt=worker.build_cover_letter_prompt,
            generate_letter=qwen_manager.generate_cover_letter,
            ensure_language_consistency=worker._ensure_cover_letter_language_consistency,
            enforce_alignment=worker._enforce_cover_letter_offer_alignment,
            is_structure_coherent=worker._is_cover_letter_structure_coherent,
            critique_and_rewrite=lambda letter, lang, cb, rewrite_reason="": worker.critique_and_rewrite_cover_letter(
                cover_letter=letter,
                language_code=lang,
                progress_callback=cb,
                rewrite_reason=rewrite_reason,
            ),
            should_run_critic=worker._should_run_cover_letter_critic_stage,
        ),
        AuditAndSavePhase(
            build_audit=lambda aa, clr: build_generation_audit_payload(
                alignment_audit=aa, cover_letter_review=clr
            ),
            is_audit_better=lambda c, b: is_generation_audit_better_payload(
                candidate=c, baseline=b
            ),
            save_application=worker.save_application,
            render_markdown=lambda cv, lang: cv_json_to_markdown(cv, language=lang),
            render_html=lambda cv, tmpl, lang: cv_json_to_html(
                cv, template=tmpl, language=lang
            ),
            score_alignment=lambda cv, cj: worker._score_cv_offer_alignment(
                cv, critic_json=cj
            ),
        ),
        CleanupPhase(),
    ]

    orchestrator = PipelineOrchestrator(phases)
    return orchestrator, state


# Import helper functions that were in llm_worker.py
try:
    from .generation_audit import (
        build_generation_audit_payload,
        is_generation_audit_better_payload,
    )
except ImportError:
    # Provide stub implementations if module not available
    def build_generation_audit_payload(
        *,
        alignment_audit: Dict[str, Any],
        cover_letter_review: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build generation audit payload."""
        return {
            "breakdown": {
                "cv": alignment_audit,
                "letter": cover_letter_review,
            },
            "overall_score": float(alignment_audit.get("overall_score") or 0.0),
        }

    def is_generation_audit_better_payload(
        *,
        candidate: Dict[str, Any],
        baseline: Dict[str, Any],
    ) -> bool:
        """Check if candidate audit is better than baseline."""
        candidate_score = float(candidate.get("overall_score") or 0.0)
        baseline_score = float(baseline.get("overall_score") or 0.0)
        return candidate_score > baseline_score
