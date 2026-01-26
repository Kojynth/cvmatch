"""ML workflow coordinator handling progress dialog orchestration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Optional, Tuple

from app.services import ProgressService

from .base import Coordinator, SimpleCoordinator

logger = logging.getLogger(__name__)

WarningCallback = Callable[[str, str], None]


@dataclass(slots=True)
class _ViewCallbacks:
    lock_ui: Callable[[bool], None]
    show_warning: WarningCallback
    show_error: WarningCallback
    show_info: WarningCallback


class MlWorkflowCoordinator(SimpleCoordinator, Coordinator):
    """Handles ML worker lifecycle (progress, cancellation, teardown)."""

    __slots__ = (
        "progress_service",
        "runtime_state_factory",
        "_callbacks",
        "_extractor",
        "_cancel_handler",
    )

    def __init__(
        self,
        progress_service: ProgressService | None = None,
        runtime_state_factory: Callable[[], object] | None = None,
    ) -> None:
        super().__init__()
        self.progress_service = progress_service or ProgressService()
        self.runtime_state_factory = runtime_state_factory
        self._callbacks = _ViewCallbacks(
            lock_ui=lambda _: None,
            show_warning=lambda *_: None,
            show_error=lambda *_: None,
            show_info=lambda *_: None,
        )
        self._extractor = None
        self._cancel_handler: Optional[Callable[[], None]] = None

    def bind_view(
        self,
        *,
        parent: object | None = None,
        lock_ui: Callable[[bool], None] | None = None,
        show_warning: WarningCallback | None = None,
        show_error: WarningCallback | None = None,
        show_info: WarningCallback | None = None,
    ) -> None:
        """Provide UI callbacks used during ML orchestration."""

        self.progress_service.set_parent(parent)
        self._callbacks = _ViewCallbacks(
            lock_ui=lock_ui or (lambda _: None),
            show_warning=show_warning or (lambda *_: None),
            show_error=show_error or (lambda *_: None),
            show_info=show_info or (lambda *_: None),
        )

    def attach_extractor(
        self,
        extractor: object | None,
        *,
        cancel_handler: Callable[[], None] | None = None,
    ) -> None:
        """Connect to the worker/extractor ML signals."""

        self.detach_extractor()
        if extractor is None:
            return

        self._extractor = extractor
        self._cancel_handler = cancel_handler
        self.progress_service.set_cancel_callback(self._handle_cancel_requested)

        for signal_name, handler in [
            ("ml_started", self._handle_started),
            ("ml_finished", self._handle_finished),
            ("ml_failed", self._handle_failed),
            ("ml_stage", self._handle_stage),
            ("ml_log", self._handle_log),
            ("ml_phase", self._handle_stage),
            ("ml_progress", self._handle_progress),
        ]:
            self._connect_signal(extractor, signal_name, handler)

    def detach_extractor(self) -> None:
        """Disconnect any previously attached extractor."""

        if not self._extractor:
            return

        for signal_name, handler in [
            ("ml_started", self._handle_started),
            ("ml_finished", self._handle_finished),
            ("ml_failed", self._handle_failed),
            ("ml_stage", self._handle_stage),
            ("ml_log", self._handle_log),
            ("ml_phase", self._handle_stage),
            ("ml_progress", self._handle_progress),
        ]:
            self._disconnect_signal(self._extractor, signal_name, handler)

        self._extractor = None
        self._cancel_handler = None
        self.progress_service.set_cancel_callback(None)

    def teardown(self) -> None:
        """Release resources before disposal."""

        self.detach_extractor()
        self.progress_service.close()
        super().teardown()

    # ------------------------------------------------------------------ #
    # Signal handlers                                                    #
    # ------------------------------------------------------------------ #

    def _handle_started(self, *_) -> None:
        logger.info("ML workflow started")
        self._callbacks.lock_ui(True)
        self.progress_service.show("Initialisation du pipeline ML…")
        self.progress_service.append_log("RUN: ML init started")

    def _handle_stage(self, message: str, *_args) -> None:
        short_message = message[:200] + "…" if len(message) > 200 else message
        self.progress_service.set_status(short_message)
        self.progress_service.append_log(f"STAGE: {short_message}")

    def _handle_log(self, line: str, *_args) -> None:
        self.progress_service.append_log(line)

    def _handle_progress(self, value: int | float, *_args) -> None:
        # ModelLoadingDialog does not expose a progress setter yet, but we log it for telemetry.
        self.progress_service.append_log(f"PROGRESS: {value}")

    def _handle_finished(self, *_) -> None:
        logger.info("ML workflow finished")
        self.progress_service.append_log("RUN: ML init completed")
        self.progress_service.close()
        self._callbacks.lock_ui(False)
        self._cancel_handler = None

    def _handle_failed(self, error: str, *_args) -> None:
        logger.error("ML workflow failed: %s", error)
        self.progress_service.set_status(f"Erreur ML: {error[:120]}")
        self.progress_service.append_log(f"ERREUR: {error}")
        self.progress_service.set_cancel_enabled(False)
        self.progress_service.close()
        self._callbacks.lock_ui(False)
        self._callbacks.show_warning("Erreur ML", "Échec de l'initialisation ML. Passage aux règles simples.")
        self._cancel_handler = None

    def _handle_cancel_requested(self) -> None:
        logger.info("ML workflow cancellation requested")
        if self._cancel_handler:
            try:
                self._cancel_handler()
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Cancel handler raised error: %s", exc)
        self.progress_service.set_cancel_enabled(False)
        self.progress_service.append_log("USER: cancel requested → fallback to mock")

    # ------------------------------------------------------------------ #
    # Runtime state helpers                                             #
    # ------------------------------------------------------------------ #

    def toggle_zero_shot(self, enabled: bool) -> Tuple[bool, Optional[str]]:
        return self._with_runtime_state("toggle_zero_shot", enabled)

    def toggle_ner(self, enabled: bool) -> Tuple[bool, Optional[str]]:
        return self._with_runtime_state("toggle_ner", enabled)

    def toggle_mock_mode(self, enabled: bool) -> Tuple[bool, Optional[str]]:
        return self._with_runtime_state("set_force_mock", enabled)

    def toggle_lite_mode(self, enabled: bool) -> Tuple[bool, Optional[str]]:
        return self._with_runtime_state("set_lite_mode", enabled)

    def reset_settings(self) -> Tuple[bool, Optional[str]]:
        success, error = self._with_runtime_state("reset_to_defaults", None)
        return success, error

    def status_summary(self) -> Tuple[bool, Optional[str]]:
        state = self._runtime_state()
        if state is None:
            return False, "Runtime ML non disponible."
        try:
            summary = state.get_status_summary()  # type: ignore[attr-defined]
            if isinstance(summary, dict):
                message = (
                    "Statut Machine Learning:\n\n"
                    f"• Zero-shot: {'✅ Activé' if summary.get('zero_shot_enabled') else '❌ Désactivé'}\n"
                    f"• NER Router: {'✅ Activé' if summary.get('ner_enabled') else '❌ Désactivé'}\n"
                    f"• Mode Mock: {'✅ Forcé' if summary.get('force_mock') else '⚙ Auto'}\n"
                    f"• Mode Lite: {'✅ Activé' if summary.get('lite_mode') else '⚙ Standard'}\n"
                    f"• Debug Snapshots: {'✅ Activé' if summary.get('debug_snapshots') else '⚙ Désactivé'}\n\n"
                    "Ces paramètres s'appliquent lors de la prochaine extraction."
                )
            else:
                message = str(summary)
            return True, message
        except Exception as exc:  # pragma: no cover
            logger.error("Unable to fetch ML status: %s", exc)
            return False, str(exc)

    # ------------------------------------------------------------------ #
    # Internal helpers                                                   #
    # ------------------------------------------------------------------ #

    def _runtime_state(self) -> Optional[object]:
        if self.runtime_state_factory is None:
            return None
        try:
            return self.runtime_state_factory()
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Runtime state factory failure: %s", exc)
            return None

    def _with_runtime_state(self, method: str, argument) -> Tuple[bool, Optional[str]]:
        state = self._runtime_state()
        if state is None:
            return False, "Runtime ML non disponible."
        try:
            func = getattr(state, method)
            if argument is None:
                func()
            else:
                func(argument)
            return True, None
        except Exception as exc:
            logger.error("ML runtime operation %s failed: %s", method, exc)
            return False, str(exc)

    @staticmethod
    def _connect_signal(extractor: object, signal_name: str, handler: Callable) -> None:
        if hasattr(extractor, signal_name):
            try:
                getattr(extractor, signal_name).connect(handler)  # type: ignore[attr-defined]
            except Exception:
                logger.debug("Unable to connect signal %s", signal_name, exc_info=True)

    @staticmethod
    def _disconnect_signal(extractor: object, signal_name: str, handler: Callable) -> None:
        if hasattr(extractor, signal_name):
            try:
                getattr(extractor, signal_name).disconnect(handler)  # type: ignore[attr-defined]
            except Exception:
                logger.debug("Unable to disconnect signal %s", signal_name, exc_info=True)
