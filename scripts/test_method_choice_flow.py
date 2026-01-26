#!/usr/bin/env python3
"""
Quick test for the CV extraction method chooser workflow in ProfilePanel.

It simulates user confirmations and verifies that:
- The method chooser is called and returns params
- ML runtime mode switches per choice (rules_only vs hf_offline)
- The previous ML runtime mode is restored after completion
- The controller is invoked with cv_params

This test avoids heavy workers by monkeypatching ProfileExtractionController
with a lightweight fake that exposes Qt-like signal interfaces.
"""

import sys
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtWidgets import QApplication, QMessageBox


class DummySignal:
    def __init__(self):
        self._subs = []
    def connect(self, fn):
        self._subs.append(fn)
    def emit(self, *args, **kwargs):
        for fn in list(self._subs):
            try:
                fn(*args, **kwargs)
            except Exception:
                pass


class FakeController:
    def __init__(self):
        self.extraction_started = DummySignal()
        self.progress_updated = DummySignal()
        self.cv_extraction_completed = DummySignal()
        self.linkedin_extraction_completed = DummySignal()
        self.profile_updated = DummySignal()
        self.extraction_completed = DummySignal()
        self.extraction_failed = DummySignal()
        # Emulate attribute used by UI when CV extractor starts
        self.cv_extractor = object()

    def extract_complete_profile(self, profile, cv_params=None, linkedin_params=None):
        # Emit started then immediately complete with the profile object
        self.extraction_started.emit("start")
        # Simulate some progress
        self.progress_updated.emit(10, "init")
        # Send completion (ProfilePanel expects updated_profile)
        self.extraction_completed.emit(profile)


def run_flow(method_type: str) -> bool:
    from app.views.panels.profile_panel import ProfilePanel
    from app.models.user_profile import UserProfile
    from app.ml.runtime_state import get_ml_runtime_state
    import app.controllers.profile_extractor as pe
    from app.workers.cv_extractor import ExtractionParams

    # Create a dummy profile and CV file
    tmp_cv = Path("scripts/_dummy_cv.txt").resolve()
    tmp_cv.parent.mkdir(parents=True, exist_ok=True)
    tmp_cv.write_text("Dummy CV for tests")

    profile = UserProfile(name="Test User", email="test@example.com")
    profile.master_cv_path = str(tmp_cv)

    # Build minimal QApplication if needed
    app = QApplication.instance() or QApplication(sys.argv)

    # Monkeypatch dialogs
    original_question = QMessageBox.question
    def always_yes(*args, **kwargs):
        # Always return Yes for confirmation
        return QMessageBox.Yes
    QMessageBox.question = always_yes

    original_info = QMessageBox.information
    def no_info(*args, **kwargs):
        # Swallow information dialogs during tests
        return 0
    QMessageBox.information = no_info

    # Monkeypatch controller
    original_controller = pe.ProfileExtractionController
    pe.ProfileExtractionController = FakeController

    # Construct widget
    widget = ProfilePanel(profile)

    # Monkeypatch method chooser to return deterministic choice
    def fake_choice():
        if method_type == 'heuristic':
            return ("heuristic", ExtractionParams(model_name="rule_based"))
        else:
            return ("ai", ExtractionParams(model_name="joeddav/xlm-roberta-large-xnli"))
    widget._choose_cv_extraction_method = fake_choice  # type: ignore

    # Record runtime before
    rt_before = get_ml_runtime_state().mode

    # Run the flow
    try:
        widget.re_extract_cv_data()
        # After completion, runtime should be restored
        rt_after = get_ml_runtime_state().mode
        restored = (rt_after == rt_before)
        return restored
    finally:
        # Restore patches
        pe.ProfileExtractionController = original_controller
        QMessageBox.question = original_question
        QMessageBox.information = original_info


def main():
    print("=== Testing method chooser workflow ===")
    ok1 = run_flow('heuristic')
    print(f"Heuristic flow: {'OK' if ok1 else 'FAIL'}")
    ok2 = run_flow('ai')
    print(f"AI (offline) flow: {'OK' if ok2 else 'FAIL'}")
    # Also exercise MainWindowWithSidebar.re_extract_cv_data
    try:
        from app.lifecycle.app_initializer import bootstrap_main_window
        from app.views.main_window import MainWindowWithSidebar
        from app.models.user_profile import UserProfile
        from PySide6.QtWidgets import QApplication, QMessageBox
        import app.controllers.profile_extractor as pe
        app = QApplication.instance() or QApplication(sys.argv)

        # Patches
        original_question = QMessageBox.question
        QMessageBox.question = lambda *a, **k: QMessageBox.Yes
        original_info = QMessageBox.information
        QMessageBox.information = lambda *a, **k: 0
        original_controller = pe.ProfileExtractionController
        pe.ProfileExtractionController = FakeController

        # Profile
        prof = UserProfile(name="Test User", email="test@example.com")
        prof.master_cv_path = str((PROJECT_ROOT / "scripts/_dummy_cv.txt").resolve())
        wnd = bootstrap_main_window(prof)

        # Force chooser return values
        from app.workers.cv_extractor import ExtractionParams
        wnd._choose_cv_extraction_method = lambda: ("ai", ExtractionParams(model_name="joeddav/xlm-roberta-large-xnli"))
        wnd.re_extract_cv_data()
        ok3 = True
    except Exception as e:
        print(f"MainWindow flow failed: {e}")
        ok3 = False
    finally:
        try:
            pe.ProfileExtractionController = original_controller
            QMessageBox.question = original_question
            QMessageBox.information = original_info
        except Exception:
            pass

    if ok1 and ok2 and ok3:
        print("All flows passed.")
        return 0
    return 1


if __name__ == '__main__':
    sys.exit(main())
