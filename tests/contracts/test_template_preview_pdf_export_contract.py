from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path
from types import MethodType, SimpleNamespace


class _FakeSignal:
    def __init__(self) -> None:
        self.callbacks = []

    def connect(self, callback) -> None:
        self.callbacks.append(callback)


class _FakePage:
    def __init__(self) -> None:
        self.pdfPrintingFinished = _FakeSignal()
        self.printed_paths = []

    def printToPdf(self, path: str) -> None:
        self.printed_paths.append(path)


class _FakeWebView:
    instances = []

    def __init__(self, parent=None) -> None:
        self.parent = parent
        self.loadFinished = _FakeSignal()
        self._page = _FakePage()
        self.hidden = False
        self.html_calls = []
        self.stopped = False
        self.deleted = False
        self.resize_calls = []
        self.__class__.instances.append(self)

    def resize(self, width: int, height: int) -> None:
        self.resize_calls.append((width, height))

    def hide(self) -> None:
        self.hidden = True

    def page(self) -> _FakePage:
        return self._page

    def setHtml(self, html: str, baseUrl=None) -> None:
        self.html_calls.append((html, baseUrl))

    def stop(self) -> None:
        self.stopped = True

    def deleteLater(self) -> None:
        self.deleted = True


def _install_preview_import_stubs(monkeypatch) -> None:
    def module(name: str, **attrs):
        mod = types.ModuleType(name)
        for key, value in attrs.items():
            setattr(mod, key, value)
        monkeypatch.setitem(sys.modules, name, mod)
        return mod

    class _FakeObject:
        def __init__(self, *args, **kwargs) -> None:
            pass

    class _FakeThread:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def start(self) -> None:
            pass

    fake_qt = SimpleNamespace(
        Window=1,
        WA_QuitOnClose=2,
        WA_DeleteOnClose=3,
        Orientation=SimpleNamespace(Horizontal=1),
    )
    fake_profile = type(
        "_FakeProfile",
        (),
        {
            "NoCache": 0,
            "NoPersistentCookies": 0,
            "MemoryHttpCache": 1,
            "defaultProfile": staticmethod(lambda: _FakeObject()),
        },
    )

    module("PySide6")
    module(
        "PySide6.QtWidgets",
        QMainWindow=_FakeObject,
        QWidget=_FakeObject,
        QVBoxLayout=_FakeObject,
        QHBoxLayout=_FakeObject,
        QLabel=_FakeObject,
        QComboBox=_FakeObject,
        QPushButton=_FakeObject,
        QTextEdit=_FakeObject,
        QScrollArea=_FakeObject,
        QMessageBox=_FakeObject,
        QFrame=_FakeObject,
        QSplitter=_FakeObject,
        QApplication=_FakeObject,
        QToolTip=_FakeObject,
        QTabWidget=_FakeObject,
        QStackedWidget=_FakeObject,
    )
    module(
        "PySide6.QtCore",
        Qt=fake_qt,
        QThread=_FakeThread,
        Signal=lambda *args, **kwargs: _FakeSignal(),
        QTimer=_FakeObject,
        QUrl=lambda value="": value,
    )
    module(
        "PySide6.QtGui",
        QFont=_FakeObject,
        QPixmap=_FakeObject,
        QPainter=_FakeObject,
        QIcon=_FakeObject,
    )
    module("PySide6.QtWebEngineWidgets", QWebEngineView=_FakeWebView)
    module("PySide6.QtWebEngineCore", QWebEngineProfile=fake_profile)
    module("loguru", logger=SimpleNamespace(warning=lambda *a, **k: None))
    module("app.controllers.export_manager", ExportManager=_FakeObject)
    module(
        "app.utils.generation_audit",
        build_generation_audit=lambda **kwargs: {},
    )
    module("app.widgets.audit_header_widget", AuditHeaderWidget=_FakeObject)
    module("app.views.text_cleaner", sanitize_widget_tree=lambda widget: None)


def _load_preview_module(monkeypatch):
    _install_preview_import_stubs(monkeypatch)
    views_pkg = types.ModuleType("app.views")
    views_pkg.__path__ = [str(Path("app/views").resolve())]
    monkeypatch.setitem(sys.modules, "app.views", views_pkg)
    sys.modules.pop("app.views.template_preview_window", None)
    return importlib.import_module("app.views.template_preview_window")


def _build_export_stub(
    template_preview_window, visible_web_view: _FakeWebView
) -> SimpleNamespace:
    template_preview_window_cls = template_preview_window.TemplatePreviewWindow
    stub = SimpleNamespace()
    stub.cv_web_view = visible_web_view
    stub.letter_web_view = _FakeWebView()
    stub._pdf_web_view = None
    stub._pdf_web_view_owned = False
    stub._pending_pdf_path = None
    stub._pending_pdf_html = None
    stub._pdf_export_method = None
    stub.status_label = SimpleNamespace(
        setText=lambda value: setattr(stub, "status_text", value)
    )
    stub._set_preview_loaded = lambda web_view, loaded: setattr(
        stub, "preview_loaded", (web_view, loaded)
    )
    stub._is_preview_loaded = lambda web_view: False
    stub._on_preview_loaded = lambda ok: setattr(stub, "loaded_signal", ok)
    stub._on_pdf_print_finished = lambda path, success: setattr(
        stub, "printed_signal", (path, success)
    )
    stub.on_export_error = lambda message: setattr(stub, "export_error", message)
    stub._cleanup_pdf_export_view = MethodType(
        template_preview_window_cls._cleanup_pdf_export_view, stub
    )
    stub._load_html_for_pdf = MethodType(
        template_preview_window_cls._load_html_for_pdf, stub
    )
    return stub


def test_webengine_pdf_export_uses_hidden_view_without_reloading_visible_preview(
    monkeypatch,
) -> None:
    template_preview_window = _load_preview_module(monkeypatch)
    _FakeWebView.instances = []
    visible_web_view = _FakeWebView()
    stub = _build_export_stub(template_preview_window, visible_web_view)

    template_preview_window.TemplatePreviewWindow._start_webengine_pdf_export(
        stub,
        "out.pdf",
        "<html><body>export</body></html>",
        visible_web_view,
    )

    hidden_web_view = stub._pdf_web_view
    assert hidden_web_view is not visible_web_view
    assert stub._pdf_web_view_owned is True
    assert hidden_web_view.resize_calls == [(794, 1123)]
    assert hidden_web_view.hidden is True
    assert hidden_web_view.html_calls
    assert visible_web_view.html_calls == []


def test_fit_tiers_hide_optional_content_before_scaling(monkeypatch) -> None:
    template_preview_window = _load_preview_module(monkeypatch)

    css = template_preview_window.CV_BASE_LAYOUT_CSS
    assert ':root[data-page-fit="compact"] .fit-compact-hide' in css
    assert ':root[data-page-fit="tight"] .fit-tight-hide' in css
    assert ':root[data-page-fit="ultra"] .fit-ultra-hide' in css
    assert ':root[data-page-fit="critical"] .project-section' in css
    assert ':root[data-page-fit="critical"] .experience-entry:nth-of-type(n+5)' in css


def test_auto_fit_fallback_scale_is_readability_capped(monkeypatch) -> None:
    template_preview_window = _load_preview_module(monkeypatch)

    script = template_preview_window.CV_AUTO_FIT_SCRIPT
    assert "MIN_READABLE_PRINT_SCALE = 0.9" in script
    assert "Math.max(scale, MIN_READABLE_PRINT_SCALE)" in script
    assert "Math.max(scale, 0.01)" not in script


def test_webengine_print_css_keeps_readable_typography(monkeypatch) -> None:
    template_preview_window = _load_preview_module(monkeypatch)

    css = template_preview_window.ONE_PAGE_PRINT_CSS
    assert "font-size: 12.8px !important;" in css
    assert "font-size: 12.6px !important;" in css
    assert "font-size: 10.3px !important;" not in css
    assert ':root[data-page-fit="critical"] .section-content' in css


def test_hidden_pdf_view_load_triggers_print_without_visible_preview_branch(
    monkeypatch,
) -> None:
    template_preview_window = _load_preview_module(monkeypatch)
    hidden_web_view = _FakeWebView()
    visible_web_view = _FakeWebView()
    stub = SimpleNamespace()
    stub.cv_web_view = visible_web_view
    stub.letter_web_view = _FakeWebView()
    stub._pdf_export_method = "webengine"
    stub._pending_pdf_path = "out.pdf"
    stub._pdf_web_view = hidden_web_view
    stub._print_pdf_with_webengine = lambda: setattr(stub, "print_started", True)
    stub.on_export_error = lambda message: setattr(stub, "export_error", message)
    stub.sender = lambda: hidden_web_view

    template_preview_window.TemplatePreviewWindow._on_preview_loaded(stub, True)

    assert stub.print_started is True
    assert not hasattr(stub, "_cv_preview_loaded")
