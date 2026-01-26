"""Lifecycle shutdown helpers for the refactored main window."""

from __future__ import annotations

import gc
import logging
import time
from collections.abc import Iterable
from typing import Any, Optional

from app.controllers.main_window.base import Coordinator
from app.controllers.main_window.job_applications import JobApplicationCoordinator
from app.services import ProgressService

logger = logging.getLogger(__name__)

__all__ = [
    "cleanup_application_resources",
    "shutdown_background_workers",
    "shutdown_application",
    "shutdown_gui",
]


def cleanup_application_resources() -> None:
    """
    Close database connections, stop timers, and release log handlers.

    The implementation mirrors the legacy teardown logic while exposing it as a reusable
    helper for both GUI and CLI flows.
    """

    try:
        from sqlalchemy.orm import Session as SQLASession  # type: ignore
        from sqlalchemy.orm import scoped_session, sessionmaker  # type: ignore
    except Exception:  # pragma: no cover - SQLAlchemy optional during tests
        SQLASession = ()  # type: ignore
        scoped_session = ()  # type: ignore
        sessionmaker = ()  # type: ignore

    try:
        from sqlalchemy.engine import Engine  # type: ignore
    except Exception:  # pragma: no cover - SQLAlchemy optional during tests
        Engine = ()  # type: ignore

    try:
        from PySide6.QtWidgets import QApplication  # type: ignore
        from PySide6.QtCore import QTimer  # type: ignore
    except Exception:  # pragma: no cover - PySide6 unavailable in some tests
        QApplication = None  # type: ignore
        QTimer = ()  # type: ignore

    try:
        for obj in gc.get_objects():
            if isinstance(obj, (SQLASession, scoped_session)):
                close = getattr(obj, "close", None)
                remove = getattr(obj, "remove", None)
                try:
                    if callable(close):
                        close()
                    elif callable(remove):
                        remove()
                except Exception:
                    pass
        logger.info("Closed SQLAlchemy sessions")
    except Exception as exc:
        logger.warning("Failed to close SQLAlchemy sessions: %s", exc)

    try:
        for obj in gc.get_objects():
            if isinstance(obj, Engine):
                try:
                    obj.dispose()
                except Exception:
                    pass
        logger.info("Disposed SQLAlchemy engines")
    except Exception as exc:
        logger.warning("Failed to dispose SQLAlchemy engines: %s", exc)

    try:
        if QApplication is not None:
            app = QApplication.instance()
            if app:
                for obj in gc.get_objects():
                    if isinstance(obj, QTimer) and obj.isActive():
                        try:
                            obj.stop()
                        except Exception:
                            pass
                app.processEvents()
                time.sleep(0.1)
                app.processEvents()
        logger.info("Stopped Qt timers")
    except Exception as exc:
        logger.warning("Failed to stop Qt timers: %s", exc)

    try:
        from loguru import logger as loguru_logger  # type: ignore

        loguru_logger.remove()
        logger.info("Removed loguru handlers")
    except Exception as exc:
        logger.warning("Failed to remove loguru handlers: %s", exc)

    try:
        from app.models.database import engine as sqlmodel_engine  # type: ignore

        try:
            sqlmodel_engine.dispose()
            logger.info("Disposed SQLModel engine")
        except Exception:
            pass
    except Exception as exc:
        logger.warning("Failed to dispose SQLModel engine: %s", exc)

    try:
        collected = 0
        for _ in range(3):
            collected = gc.collect()
            time.sleep(0.2)
        logger.info("Garbage collection released %s objects", collected)
        time.sleep(1.0)
    except Exception as exc:
        logger.warning("Garbage collection during shutdown failed: %s", exc)


def _call_safely(obj: object, method_name: str, *args: Any) -> None:
    """Invoke an optional method on an object, ignoring errors."""

    method = getattr(obj, method_name, None)
    if not callable(method):
        return
    try:
        method(*args)
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.debug("Error while calling %s on %s: %s", method_name, obj, exc)


def shutdown_background_workers(workers: Iterable[object]) -> None:
    """Terminate background Qt workers created during the session."""

    for worker in workers:
        _call_safely(worker, "requestInterruption")
        _call_safely(worker, "quit")
        _call_safely(worker, "wait", 2000)
        _call_safely(worker, "deleteLater")


def shutdown_application(
    coordinators: Iterable[Coordinator],
    *,
    perform_cleanup: bool = True,
) -> None:
    """Teardown coordinators created during bootstrap and optionally perform cleanup."""

    for coordinator in coordinators:
        try:
            coordinator.teardown()
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.debug("Coordinator teardown failed for %s: %s", coordinator, exc)

    if perform_cleanup:
        cleanup_application_resources()


def shutdown_gui(
    *,
    coordinators: Iterable[Coordinator] = (),
    job_application_coordinator: Optional[JobApplicationCoordinator] = None,
    progress_service: Optional[ProgressService] = None,
    perform_cleanup: bool = True,
) -> None:
    """
    Shutdown helper tailored for GUI entry points.

    This routine ensures active workers spawned by the job application coordinator are
    terminated, the progress dialog is dismissed, and the shared coordinators release
    their resources.
    """

    coordinator_list = list(coordinators)

    if job_application_coordinator is not None:
        try:
            shutdown_background_workers(job_application_coordinator.iter_active_workers())
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.debug("Failed to shutdown job application workers: %s", exc)
        if job_application_coordinator not in coordinator_list:
            coordinator_list.append(job_application_coordinator)

    if progress_service is not None:
        try:
            progress_service.close()
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.debug("Failed to close progress service: %s", exc)

    shutdown_application(coordinator_list, perform_cleanup=perform_cleanup)
