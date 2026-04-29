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


def _load_real_export_manager():
    module = sys.modules.get("app.controllers.export_manager")
    if module is not None and module.__class__.__name__ == "module":
        export_manager = getattr(module, "ExportManager", None)
        if export_manager is not None and export_manager.__name__ == "_FakeObject":
            sys.modules.pop("app.controllers.export_manager", None)
    from app.controllers.export_manager import ExportManager

    return ExportManager


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
    assert ':root[data-page-fit="critical"] .project-section' not in css
    assert ':root[data-page-fit="critical"] .experience-entry:nth-of-type(n+5)' in css


def test_auto_fit_fallback_scale_uses_computed_fit_ratio(monkeypatch) -> None:
    template_preview_window = _load_preview_module(monkeypatch)

    script = template_preview_window.CV_AUTO_FIT_SCRIPT
    assert "MIN_READABLE_PRINT_SCALE" not in script
    assert "Math.max(scale, 0.01)" in script
    assert "Math.max(scale, 0.9)" not in script
    assert "withPrintMeasureWidth" in script
    assert 'setProperty("width", `${TARGET_WIDTH}px`, "important")' in script
    assert 'setProperty("min-width", `${TARGET_WIDTH}px`, "important")' in script


def test_webengine_print_css_keeps_readable_typography(monkeypatch) -> None:
    template_preview_window = _load_preview_module(monkeypatch)

    css = template_preview_window.ONE_PAGE_PRINT_CSS
    assert "font-size: 12.8px !important;" in css
    assert "font-size: 12.6px !important;" in css
    assert "font-size: 10.3px !important;" not in css
    assert ':root[data-page-fit="critical"] .section-content' in css


def test_webengine_print_css_uses_zoom_without_transform_double_scaling(
    monkeypatch,
) -> None:
    template_preview_window = _load_preview_module(monkeypatch)

    css = template_preview_window.ONE_PAGE_PRINT_CSS
    assert "zoom: var(--print-scale);" in css
    assert "translateX(-50%) scale(var(--print-scale))" not in css


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


def test_letter_html_renders_single_subject_and_single_body_signature(
    monkeypatch,
) -> None:
    template_preview_window = _load_preview_module(monkeypatch)
    cls = template_preview_window.TemplatePreviewWindow
    stub = SimpleNamespace(
        cv_data={
            "name": "MICHAUD Keiji",
            "email": "candidate@example.com",
            "phone": "+33 000000000",
            "job_title": "Software Engineer, QA",
            "company": "Mistral AI",
            "cover_letter": (
                "Objet: Candidature - Software Engineer, QA (Mistral Ai)\n\n"
                "Madame, Monsieur,\n\n"
                "Je souhaite contribuer aux tests API et a l'automatisation.\n\n"
                "Je vous prie d'agreer, Madame, Monsieur, l'expression de mes salutations distinguees.\n\n"
                "MICHAUD Keiji"
            ),
        }
    )
    stub._cover_letter_to_html = MethodType(cls._cover_letter_to_html, stub)
    stub._prepare_cover_letter_for_render = cls._prepare_cover_letter_for_render

    html = cls.generate_letter_html(stub)

    assert html.count("Objet:") == 1
    assert "Mistral AI" in html
    assert "Mistral Ai" not in html
    assert "<p>MICHAUD Keiji</p>" not in html
    assert '<div class="signature">MICHAUD Keiji</div>' in html


def test_letter_html_fallback_subject_reuses_offer_company_name(
    monkeypatch,
) -> None:
    template_preview_window = _load_preview_module(monkeypatch)
    cls = template_preview_window.TemplatePreviewWindow
    stub = SimpleNamespace(
        cv_data={
            "name": "MICHAUD Keiji",
            "job_title": "Software Engineer, QA",
            "company": "Mistral AI",
            "cover_letter": (
                "Madame, Monsieur,\n\n"
                "Je souhaite contribuer aux tests API.\n\n"
                "Cordialement"
            ),
        }
    )
    stub._cover_letter_to_html = MethodType(cls._cover_letter_to_html, stub)
    stub._prepare_cover_letter_for_render = cls._prepare_cover_letter_for_render

    html = cls.generate_letter_html(stub)

    assert "Candidature - Software Engineer, QA (Mistral AI)" in html


def test_cover_letter_sanitizer_removes_duplicate_subject_and_preserves_company_case() -> None:
    from app.utils.cover_letter_output import (
        normalize_company_mentions,
        sanitize_generated_cover_letter,
    )

    raw = (
        "Objet: Candidature - Software Engineer, QA\n"
        "Objet: Candidature - Software Engineer, QA (Mistral Ai)\n\n"
        "Madame, Monsieur,\n\n"
        "Je souhaite contribuer aux tests API chez Mistral Ai.\n\n"
        "Cordialement,\n\n"
        "MICHAUD Keiji"
    )

    sanitized = sanitize_generated_cover_letter(raw)
    normalized = normalize_company_mentions(sanitized, "Mistral AI")

    assert normalized.lower().count("objet:") == 1
    assert "Mistral AI" in normalized
    assert "Mistral Ai" not in normalized


def test_cover_letter_prompt_quality_rules_are_source_driven_not_seeded() -> None:
    from app.utils.cover_letter_style_policy import build_cover_letter_generation_payload

    payload = build_cover_letter_generation_payload(
        offer_data={
            "job_title": "Implementation Coordinator",
            "company": "Example Corp",
            "text": (
                "Workflow automation, reporting systems, stakeholder validation "
                "and deployment readiness."
            ),
            "analysis": {
                "language": "fr",
                "keywords": [
                    "workflow automation",
                    "reporting systems",
                    "stakeholder validation",
                    "deployment readiness",
                ],
            },
        },
        template="modern",
        preferred_language="fr",
        language_code="fr",
        profile_name="Jean Dupont",
        profile_block=(
            "EXPERIENCE: refonte Excel de suivi des flux, automatisation des "
            "calculs, graphiques de reporting et accompagnement de l'adoption."
        ),
    )

    prompt = payload["prompt"]

    assert payload["style_mode"] == "technical_precision"
    assert "REGLES QUALITE LETTRE:" in prompt
    assert "ecrire `Example Corp` exactement comme dans l'offre" in prompt
    assert "chaque paragraphe de corps doit relier une exigence forte" in prompt
    assert "Usage des projets" in prompt
    assert "solutions technologiques impactantes" in prompt
    assert "workflow automation" in prompt
    assert "reporting systems" in prompt
    assert "refonte Excel" in prompt


def test_cover_letter_style_policy_has_no_seeded_domain_tool_terms() -> None:
    policy_path = Path("app/utils/cover_letter_style_policy.py")
    source = policy_path.read_text(encoding="utf-8").casefold()
    source = source.replace("llm_worker.py", "").replace("offer_keywords_llm", "")
    forbidden = [
        "py" + "thon",
        "post" + "man",
        "play" + "wright",
        "selen" + "ium",
        "cyp" + "ress",
        "py" + "test",
        "mi" + "stral",
        "ll" + "m",
        "json schema",
        "quality assurance",
        "test automation",
        "model integration",
        "edge case",
        "regression testing",
    ]

    assert not any(term in source for term in forbidden)


def test_deterministic_cover_letter_fallback_subject_reuses_offer_company() -> None:
    from app.utils.cover_letter_fallback import generate_fallback_cover_letter_simple

    letter = generate_fallback_cover_letter_simple(
        profile_name="MICHAUD Keiji",
        job_title="Software Engineer, QA",
        company="Mistral AI",
        language_code="fr",
        matched_terms=["Python", "API testing"],
    )

    assert letter.startswith(
        "Objet: Candidature - Software Engineer, QA (Mistral AI)"
    )


def test_export_manager_profile_sentence_is_not_qa_locked() -> None:
    ExportManager = _load_real_export_manager()
    manager = ExportManager()

    sentence = manager._build_evidence_based_profile_sentence(
        {
            "language": "fr",
            "job_title": "Data Analyst",
            "ats_keywords": ["SQL", "Power BI", "dashboard KPI"],
            "featured_skills": ["SQL", "Power BI", "Tableau de bord et KPI"],
            "skills": [
                {
                    "category": "Data",
                    "skills_list": [
                        {"name": "SQL"},
                        {"name": "Power BI"},
                        {"name": "Tableau de bord et KPI"},
                    ],
                }
            ],
            "experience": [
                {
                    "title": "Analyste data",
                    "company": "ACME",
                    "_render_source_description": [
                        "Construit des dashboards Power BI et suit les KPI métiers.",
                        "Analyse les données SQL pour fiabiliser les reportings.",
                    ],
                }
            ],
            "projects": [],
        },
        rendered_signatures=[],
    )

    assert "Data Analyst" in sentence
    assert "Power BI" in sentence
    assert "SQL" in sentence
    assert "QA" not in sentence
    assert "plans de test" not in sentence.lower()


def test_export_manager_experience_evidence_reuses_source_lines_generically() -> None:
    ExportManager = _load_real_export_manager()
    manager = ExportManager()

    lines = manager._source_backed_experience_evidence_lines(
        [
            "Refond un fichier Excel de suivi des cash flows.",
            "Automatise les calculs pour limiter les erreurs de traitement.",
            "Ajoute des graphiques de suivi pour l'équipe commerciale.",
        ],
        offer_terms=["Excel", "automatisation", "reporting"],
        language_code="fr",
    )

    joined = " ".join(lines)
    assert "Excel" in joined
    assert "Automatise" in joined
    assert "QA" not in joined
    assert "Postman" not in joined
    assert "plans de test" not in joined.lower()


def test_export_manager_project_description_does_not_hardcode_cvmatch_label() -> None:
    ExportManager = _load_real_export_manager()
    manager = ExportManager()

    lines = manager._build_compact_project_description_lines(
        {
            "name": "CVMatch",
            "technologies": "Python · LLM local · JSON · pytest",
            "description": (
                "CVMatch est une application développée en Python visant à automatiser "
                "l'adaptation d'un profil candidat à une offre d'emploi précise. "
                "Le projet repose sur un pipeline de traitement assisté par LLM avec "
                "validation JSON et tests unitaires avec pytest."
            ),
        },
        technologies=["Python", "LLM", "pytest"],
        max_lines=2,
        char_budget=360,
    )

    assert lines
    assert all(not line.startswith("Application Python") for line in lines)
    assert all("Application Python/LLM" not in line for line in lines)
    assert any("pipeline" in line.lower() or "application" in line.lower() for line in lines)
