from .text_cleaner import sanitize_widget_tree
"""
Template Preview Window
=======================

Fenêtre de prévisualisation des templates de CV avec sélection et export PDF.
"""

import os
import sys
import html as html_lib
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QComboBox, QPushButton, QTextEdit, QScrollArea,
    QMessageBox, QFrame, QSplitter, QApplication, QToolTip,
    QTabWidget, QStackedWidget
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QFont, QPixmap, QPainter, QIcon
from PySide6.QtWebEngineWidgets import QWebEngineView
from loguru import logger

from ..controllers.export_manager import ExportManager


FALLBACK_TEMPLATE_ACCENTS = {
    "modern": "#2563eb",
    "classic": "#1f2937",
    "tech": "#0f766e",
    "creative": "#c2410c",
    "minimal": "#475569",
}

LETTER_TEMPLATES = {
    "formal": {
        "name": "Formel",
        "description": "Mise en page classique avec en-tete structure.",
        "style": "Lettre classique",
    },
    "modern": {
        "name": "Moderne",
        "description": "Bloc epure avec accents discrets.",
        "style": "Lettre moderne",
    },
    "minimal": {
        "name": "Minimal",
        "description": "Texte dense et lisible, sans fioritures.",
        "style": "Lettre sobre",
    },
}

ONE_PAGE_PRINT_CSS = """
@page {
  size: A4;
  margin: 0;
}
@media print {
  :root {
    --print-scale: 1;
  }
  html,
  body {
    width: 210mm;
    height: 297mm;
    margin: 0;
    padding: 0;
    overflow: hidden;
    background: #ffffff;
  }
  .cv-container,
  .letter-container {
    margin: 0 auto;
    transform: scale(var(--print-scale));
    transform-origin: top left;
    width: calc(100% / var(--print-scale));
  }
}
"""


def _build_fallback_css(template_name: str) -> str:
    accent = FALLBACK_TEMPLATE_ACCENTS.get(template_name, "#2563eb")
    return f"""
    :root {{
        --accent: {accent};
        --text: #1f2937;
        --muted: #6b7280;
        --border: #e5e7eb;
        --bg: #f8fafc;
    }}
    * {{
        box-sizing: border-box;
    }}
    body {{
        margin: 0;
        padding: 24px;
        background: var(--bg);
        color: var(--text);
        font-family: "Georgia", "Times New Roman", serif;
    }}
    .cv-container {{
        max-width: 880px;
        margin: 0 auto;
        background: #ffffff;
        border-left: 8px solid var(--accent);
        box-shadow: 0 12px 30px rgba(15, 23, 42, 0.12);
        padding: 32px 36px 40px;
    }}
    .cv-header {{
        border-bottom: 2px solid var(--border);
        padding-bottom: 16px;
        margin-bottom: 24px;
    }}
    .cv-header .name {{
        margin: 0;
        font-size: 32px;
        letter-spacing: 0.4px;
        text-transform: uppercase;
    }}
    .cv-header .title {{
        margin: 8px 0 0;
        font-size: 14px;
        letter-spacing: 1.2px;
        text-transform: uppercase;
        color: var(--accent);
        font-family: "Arial", "Helvetica", sans-serif;
    }}
    .contact-info {{
        margin-top: 12px;
        display: flex;
        flex-wrap: wrap;
        gap: 12px 20px;
        font-family: "Arial", "Helvetica", sans-serif;
        font-size: 12px;
        color: var(--muted);
    }}
    .contact-item {{
        display: flex;
        align-items: center;
        gap: 6px;
    }}
    .contact-item .icon {{
        display: none;
    }}
    .cv-section {{
        margin-top: 22px;
    }}
    .section-title {{
        margin: 0 0 10px;
        font-size: 13px;
        letter-spacing: 1px;
        text-transform: uppercase;
        color: var(--accent);
        font-family: "Arial", "Helvetica", sans-serif;
    }}
    .section-content {{
        font-size: 14px;
        line-height: 1.6;
    }}
    .section-content h2,
    .section-content h3 {{
        margin: 16px 0 8px;
        font-size: 16px;
        font-family: "Arial", "Helvetica", sans-serif;
        color: var(--text);
    }}
    .section-content p {{
        margin: 0 0 10px;
    }}
    .section-content ul {{
        margin: 6px 0 12px 18px;
        padding: 0;
    }}
    .section-content li {{
        margin-bottom: 6px;
    }}
    .dynamic-content strong {{
        font-family: "Arial", "Helvetica", sans-serif;
    }}
    @media print {{
        body {{
            padding: 0;
            background: #ffffff;
        }}
        .cv-container {{
            box-shadow: none;
            border-left-width: 6px;
        }}
    }}
    """


def _build_letter_fallback_css() -> str:
    return """
    :root {
        --accent: #1f2937;
        --text: #111827;
        --muted: #6b7280;
        --border: #e5e7eb;
        --bg: #f8fafc;
    }
    * {
        box-sizing: border-box;
    }
    body {
        margin: 0;
        padding: 32px;
        background: var(--bg);
        color: var(--text);
        font-family: "Georgia", "Times New Roman", serif;
    }
    .letter-container {
        max-width: 820px;
        margin: 0 auto;
        background: #ffffff;
        border: 1px solid var(--border);
        padding: 32px 36px;
        box-shadow: 0 16px 30px rgba(15, 23, 42, 0.12);
    }
    .letter-header {
        display: flex;
        justify-content: space-between;
        gap: 24px;
        border-bottom: 1px solid var(--border);
        padding-bottom: 16px;
        margin-bottom: 18px;
    }
    .sender-name {
        font-size: 20px;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    .sender-meta {
        font-size: 12px;
        color: var(--muted);
        margin-top: 6px;
    }
    .recipient-line {
        font-size: 12px;
        color: var(--muted);
        text-align: right;
    }
    .letter-subject {
        font-size: 13px;
        margin-bottom: 16px;
    }
    .letter-content p {
        margin: 0 0 12px;
        line-height: 1.7;
    }
    .letter-footer {
        margin-top: 24px;
        font-weight: 600;
    }
    @media print {
        body {
            padding: 0;
            background: #ffffff;
        }
        .letter-container {
            box-shadow: none;
            border: none;
        }
    }
    """


class PDFExportThread(QThread):
    """Thread pour l'export PDF en arrière-plan."""

    finished = Signal(str)  # Chemin du fichier généré
    error = Signal(str)     # Message d'erreur

    def __init__(
        self,
        cv_data: Dict[str, Any],
        template: str,
        output_path: str,
        html_content: Optional[str] = None,
        use_inline_css: bool = False,
    ):
        super().__init__()
        self.cv_data = cv_data
        self.template = template
        self.output_path = output_path
        self.html_content = html_content
        self.use_inline_css = use_inline_css
        self.export_manager = ExportManager()

    def run(self):
        try:
            if self.html_content:
                pdf_path = self.export_manager.generate_pdf(
                    self.html_content,
                    self.template,
                    self.output_path,
                    use_css_file=not self.use_inline_css,
                )
            else:
                # Générer le PDF via le pipeline standard
                pdf_path = self.export_manager.export_cv(
                    self.cv_data,
                    self.template,
                    "pdf",
                    self.output_path,
                )
            self.finished.emit(pdf_path)
        except Exception as e:
            logger.error(f"Erreur export PDF: {e}")
            self.error.emit(str(e))


class TemplatePreviewWindow(QMainWindow):
    """Fenêtre de prévisualisation des templates avec export PDF."""
    
    # Définition des templates disponibles
    TEMPLATES = {
        "modern": {
            "name": "Moderne",
            "description": "Design moderne avec sidebar colorée et sections bien organisées",
            "style": "Professionnel moderne"
        },
        "tech": {
            "name": "Technique", 
            "description": "Style technique avec focus sur les compétences et projets",
            "style": "Développeur/Tech"
        },
        "classic": {
            "name": "Classique",
            "description": "Template traditionnel, élégant et professionnel",
            "style": "Corporate classique"
        },
        "creative": {
            "name": "Créatif",
            "description": "Design coloré et créatif avec timeline et éléments visuels",
            "style": "Créatif/Artistique"
        },
        "minimal": {
            "name": "Minimal",
            "description": "Design épuré et minimaliste, focus sur le contenu",
            "style": "Minimaliste élégant"
        }
    }
    
    def __init__(self, cv_data: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.cv_data = cv_data
        self.export_manager = ExportManager()
        requested_template = None
        if isinstance(cv_data, dict):
            requested_template = cv_data.get("template") or cv_data.get("template_used")
        requested_template = requested_template or "modern"
        self.current_template = (
            requested_template if requested_template in self.TEMPLATES else "modern"
        )
        requested_letter_template = None
        if isinstance(cv_data, dict):
            requested_letter_template = (
                cv_data.get("letter_template")
                or cv_data.get("cover_letter_template")
            )
        requested_letter_template = requested_letter_template or "formal"
        self.current_letter_template = (
            requested_letter_template
            if requested_letter_template in LETTER_TEMPLATES
            else "formal"
        )
        self.export_thread = None
        self.splitter = None
        self.last_html_export_path = None
        self.last_rendered_html = ""
        self.last_letter_html_export_path = None
        self.last_letter_rendered_html = ""
        self.edit_mode = "markdown"
        self.force_single_page = True
        self.cv_template_validated = False
        self.letter_template_validated = False
        self._cv_preview_loaded = False
        self._letter_preview_loaded = False
        self._pending_pdf_path = None
        self._pending_pdf_html = None
        self._pdf_export_method = None
        self._pdf_web_view = None
        self._last_export_kind = None
        
        self.setWindowTitle("Prévisualisation et Export CV")
        self.setGeometry(100, 100, 1400, 900)
        
        # IMPORTANT: Cette fenêtre ne doit pas fermer l'application quand elle se ferme
        self.setAttribute(Qt.WA_QuitOnClose, False)
        
        # Style de la fenêtre
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f5f5f5;
                color: #333;
            }
        """)
        
        # Créer le dossier de sortie
        self.output_dir = Path.cwd() / "CV" / "générés"
        self.output_dir.mkdir(exist_ok=True)
        
        self.setup_ui()
        self.load_template_preview()
    
    def setup_ui(self):
        """Configure l'interface utilisateur."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Layout principal
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # Header avec titre et bouton retour
        header_layout = QHBoxLayout()
        
        # Titre
        title_label = QLabel("Prévisualisation du CV")
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: #2c3e50; margin-bottom: 10px;")
        
        # Bouton retour
        back_button = QPushButton("Retour à l'interface principale")
        back_button.setStyleSheet("""
            QPushButton {
                background-color: #95a5a6;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #7f8c8d;
            }
        """)
        back_button.clicked.connect(self.close)

        back_to_edit_button = QPushButton("Retour à l'édition")
        back_to_edit_button.setStyleSheet("""
            QPushButton {
                background-color: #17a2b8;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 5px;
                font-weight: bold;
                margin-right: 10px;
            }
            QPushButton:hover {
                background-color: #138496;
            }
        """)
        back_to_edit_button.setToolTip("Ouvrir l'editeur CV/lettre depuis l'Historique.")
        back_to_edit_button.clicked.connect(self.back_to_edit)
        
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        header_layout.addWidget(back_to_edit_button)
        header_layout.addWidget(back_button)
        
        main_layout.addLayout(header_layout)
        
        # Section sélection de template
        template_frame = QFrame()
        template_frame.setFrameStyle(QFrame.Shape.StyledPanel)
        template_frame.setStyleSheet("""
            QFrame {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 8px;
                padding: 15px;
            }
        """)
        
        template_layout = QVBoxLayout(template_frame)
        
        # Titre section
        template_title = QLabel("Sélection du Template")
        template_title.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        template_title.setStyleSheet("color: #495057; margin-bottom: 10px;")
        template_layout.addWidget(template_title)
        
        # Template selectors for CV / Lettre
        self.template_selector_stack = QStackedWidget()

        combo_style = """
            QComboBox {
                padding: 8px 12px;
                border: 2px solid #dee2e6;
                border-radius: 4px;
                background-color: white;
                color: #333333;
                font-size: 14px;
                min-width: 200px;
                font-weight: 500;
            }
            QComboBox:hover {
                border-color: #3498db;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 30px;
                border-left-width: 1px;
                border-left-color: #dee2e6;
                border-left-style: solid;
                border-top-right-radius: 4px;
                border-bottom-right-radius: 4px;
                background-color: #f8f9fa;
            }
            QComboBox::down-arrow {
                image: none;
                border: 2px solid #6c757d;
                border-radius: 1px;
                width: 6px;
                height: 6px;
                border-left: none;
                border-top: none;
                margin-right: 8px;
            }
            QComboBox QAbstractItemView {
                border: 2px solid #dee2e6;
                background-color: white;
                color: #333333;
                selection-background-color: #3498db;
                selection-color: white;
                outline: none;
                font-size: 14px;
            }
            QComboBox QAbstractItemView::item {
                padding: 8px 12px;
                border: none;
                background-color: white;
                color: #333333;
                min-height: 20px;
            }
            QComboBox QAbstractItemView::item:hover {
                background-color: #e3f2fd;
                color: #1976d2;
            }
            QComboBox QAbstractItemView::item:selected {
                background-color: #3498db;
                color: white;
            }
        """

        info_style = """
            color: #6c757d;
            font-style: italic;
            padding: 8px;
            background-color: #e9ecef;
            border-radius: 4px;
            border-left: 4px solid #3498db;
        """

        cv_selector = QWidget()
        cv_selector_layout = QHBoxLayout(cv_selector)
        cv_selector_layout.setContentsMargins(0, 0, 0, 0)

        cv_template_label = QLabel("Template CV:")
        cv_template_label.setStyleSheet("color: #6c757d; font-weight: bold;")

        self.cv_template_combo = QComboBox()
        self.cv_template_combo.setStyleSheet(combo_style)

        for template_id, template_info in self.TEMPLATES.items():
            display_name = f"{template_info['name']} ({template_info['style']})"
            self.cv_template_combo.addItem(display_name, template_id)

        self.cv_template_info = QLabel()
        self.cv_template_info.setStyleSheet(info_style)
        self.cv_template_info.setWordWrap(True)

        initial_index = 0
        for index in range(self.cv_template_combo.count()):
            if self.cv_template_combo.itemData(index) == self.current_template:
                initial_index = index
                break
        self.cv_template_combo.setCurrentIndex(initial_index)
        self.current_template = self.cv_template_combo.currentData() or self.current_template

        self.cv_template_combo.currentTextChanged.connect(self.on_cv_template_changed)
        self.update_cv_template_info()

        cv_selector_layout.addWidget(cv_template_label)
        cv_selector_layout.addWidget(self.cv_template_combo)
        cv_selector_layout.addWidget(self.cv_template_info, 1)

        letter_selector = QWidget()
        letter_selector_layout = QHBoxLayout(letter_selector)
        letter_selector_layout.setContentsMargins(0, 0, 0, 0)

        letter_template_label = QLabel("Template Lettre:")
        letter_template_label.setStyleSheet("color: #6c757d; font-weight: bold;")

        self.letter_template_combo = QComboBox()
        self.letter_template_combo.setStyleSheet(combo_style)

        for template_id, template_info in LETTER_TEMPLATES.items():
            display_name = f"{template_info['name']} ({template_info['style']})"
            self.letter_template_combo.addItem(display_name, template_id)

        self.letter_template_info = QLabel()
        self.letter_template_info.setStyleSheet(info_style)
        self.letter_template_info.setWordWrap(True)

        initial_letter_index = 0
        for index in range(self.letter_template_combo.count()):
            if self.letter_template_combo.itemData(index) == self.current_letter_template:
                initial_letter_index = index
                break
        self.letter_template_combo.setCurrentIndex(initial_letter_index)
        self.current_letter_template = (
            self.letter_template_combo.currentData() or self.current_letter_template
        )

        self.letter_template_combo.currentTextChanged.connect(self.on_letter_template_changed)
        self.update_letter_template_info()

        letter_selector_layout.addWidget(letter_template_label)
        letter_selector_layout.addWidget(self.letter_template_combo)
        letter_selector_layout.addWidget(self.letter_template_info, 1)

        self.template_selector_stack.addWidget(cv_selector)
        self.template_selector_stack.addWidget(letter_selector)
        template_layout.addWidget(self.template_selector_stack)

        main_layout.addWidget(template_frame)
        
        # Splitter pour prévisualisation et actions
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter = splitter
        
        # Zone de prévisualisation
        preview_frame = QFrame()
        preview_frame.setFrameStyle(QFrame.Shape.StyledPanel)
        preview_frame.setStyleSheet("""
            QFrame {
                background-color: white;
                border: 2px solid #dee2e6;
                border-radius: 8px;
            }
        """)
        
        preview_layout = QVBoxLayout(preview_frame)
        preview_layout.setContentsMargins(10, 10, 10, 10)
        
        preview_title = QLabel("Prévisualisation")
        preview_title.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        preview_title.setStyleSheet("color: #495057; margin-bottom: 10px;")
        preview_layout.addWidget(preview_title)
        
        # Onglets de previsualisation
        self.preview_tabs = QTabWidget()
        self.preview_tabs.currentChanged.connect(self.on_preview_tab_changed)

        self.cv_web_view = QWebEngineView()
        self.cv_web_view.setStyleSheet("border: 1px solid #dee2e6; border-radius: 4px;")
        self.cv_web_view.loadFinished.connect(self._on_preview_loaded)
        try:
            page = self.cv_web_view.page()
            if hasattr(page, "pdfPrintingFinished"):
                page.pdfPrintingFinished.connect(self._on_pdf_print_finished)
        except Exception:
            logger.warning("QWebEngine page signals not available for PDF export.")

        cv_tab = QWidget()
        cv_tab_layout = QVBoxLayout(cv_tab)
        cv_tab_layout.setContentsMargins(0, 0, 0, 0)
        cv_tab_layout.addWidget(self.cv_web_view)
        self.cv_tab_index = self.preview_tabs.addTab(cv_tab, "CV")

        self.letter_web_view = QWebEngineView()
        self.letter_web_view.setStyleSheet("border: 1px solid #dee2e6; border-radius: 4px;")
        self.letter_web_view.loadFinished.connect(self._on_preview_loaded)
        try:
            page = self.letter_web_view.page()
            if hasattr(page, "pdfPrintingFinished"):
                page.pdfPrintingFinished.connect(self._on_pdf_print_finished)
        except Exception:
            logger.warning("QWebEngine page signals not available for PDF export.")

        letter_tab = QWidget()
        letter_tab_layout = QVBoxLayout(letter_tab)
        letter_tab_layout.setContentsMargins(0, 0, 0, 0)
        letter_tab_layout.addWidget(self.letter_web_view)
        self.letter_tab_index = self.preview_tabs.addTab(letter_tab, "Lettre de motivation")

        preview_layout.addWidget(self.preview_tabs)

        
        splitter.addWidget(preview_frame)
        
        # Panel d'actions
        actions_frame = QFrame()
        actions_frame.setFrameStyle(QFrame.Shape.StyledPanel)
        actions_frame.setStyleSheet("""
            QFrame {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 8px;
                padding: 20px;
            }
        """)
        actions_frame.setMaximumWidth(400)
        actions_frame.setMinimumWidth(350)
        
        actions_layout = QVBoxLayout(actions_frame)
        
        # Titre actions
        actions_title = QLabel("Actions")
        actions_title.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        actions_title.setStyleSheet("color: #495057; margin-bottom: 15px;")
        actions_layout.addWidget(actions_title)

        # Bouton Valider Template
        self.validate_button = QPushButton("✓ Valider ce Template")
        self.validate_button.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                border: none;
                padding: 12px 20px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #218838;
            }
            QPushButton:pressed {
                background-color: #1e7e34;
            }
        """)
        self.validate_button.clicked.connect(self.validate_template)
        actions_layout.addWidget(self.validate_button)
        
        # Bouton Export PDF
        self.export_button = QPushButton("📰 Exporter en PDF")
        self.export_button.setStyleSheet("""
            QPushButton {
                background-color: #007bff;
                color: white;
                border: none;
                padding: 12px 20px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 14px;
                margin-top: 10px;
            }
            QPushButton:hover {
                background-color: #0056b3;
            }
            QPushButton:pressed {
                background-color: #004085;
            }
            QPushButton:disabled {
                background-color: #6c757d;
                cursor: not-allowed;
            }
        """)
        self.export_button.clicked.connect(self.export_pdf)
        self.export_button.setEnabled(False)  # Désactivé jusqu'à validation
        actions_layout.addWidget(self.export_button)
        
        # Bouton Modifier CSS (MVP)
        modify_css_button = QPushButton("🎨 Modifier le CSS")
        modify_css_button.setStyleSheet("""
            QPushButton {
                background-color: #ffc107;
                color: #212529;
                border: none;
                padding: 12px 20px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 14px;
                margin-top: 10px;
            }
            QPushButton:hover {
                background-color: #e0a800;
            }
        """)
        modify_css_button.clicked.connect(self.show_css_tooltip)
        actions_layout.addWidget(modify_css_button)
        
        # Spacer
        actions_layout.addStretch()
        
        # Info export
        # Séparateur
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setStyleSheet("color: #dee2e6; margin: 10px 0;")
        actions_layout.addWidget(separator)
        
        info_label = QLabel("Le PDF sera sauvegarde dans le dossier 'CV generes'.\nEditez le CV et la lettre via Retour a l'edition.")
        info_label.setStyleSheet("""
            color: #6c757d;
            font-size: 12px;
            padding: 10px;
            background-color: #e7f3ff;
            border: 1px solid #b8daff;
            border-radius: 4px;
        """)
        info_label.setWordWrap(True)
        actions_layout.addWidget(info_label)
        
        splitter.addWidget(actions_frame)
        
        # Définir les proportions du splitter
        splitter.setStretchFactor(0, 3)  # Preview prend plus de place
        splitter.setStretchFactor(1, 1)  # Actions panel plus petit
        
        main_layout.addWidget(splitter)
        
        # Status bar simulée
        status_frame = QFrame()
        status_frame.setFrameStyle(QFrame.Shape.StyledPanel) 
        status_frame.setStyleSheet("""
            QFrame {
                background-color: #e9ecef;
                border: 1px solid #dee2e6;
                border-radius: 4px;
                padding: 8px;
            }
        """)
        
        status_layout = QHBoxLayout(status_frame)
        self.status_label = QLabel("Prêt - Sélectionnez un template et validez pour exporter")
        self.status_label.setStyleSheet("color: #495057; font-size: 12px;")
        status_layout.addWidget(self.status_label)
        
        main_layout.addWidget(status_frame)
        
        # Mettre a jour l'info des templates
        self.update_cv_template_info()
        self.update_letter_template_info()
    
        self.on_preview_tab_changed(self.preview_tabs.currentIndex())

        # Final sanitization of the constructed UI
        sanitize_widget_tree(self)

    def back_to_edit(self):
        """Retourne vers l'editeur CV/lettre (Historique)."""
        if self._navigate_to_history_editor():
            return
        QMessageBox.information(
            self,
            "Edition indisponible",
            "Impossible d'ouvrir l'editeur. Ouvrez l'Historique et choisissez la candidature.",
        )

    def _navigate_to_history_editor(self) -> bool:
        application_id = self.cv_data.get("application_id")
        if not application_id:
            return False

        parent = self.parent()
        history_widget = None
        main_window = None

        if parent is not None and hasattr(parent, "open_editor_for_application"):
            history_widget = parent
        elif parent is not None:
            if hasattr(parent, "history_widget"):
                main_window = parent
            elif hasattr(parent, "main_window"):
                main_window = getattr(parent, "main_window")
            else:
                try:
                    candidate = parent.window()
                except Exception:
                    candidate = None
                if candidate is not None and hasattr(candidate, "history_widget"):
                    main_window = candidate

        if history_widget is None and main_window is not None:
            history_widget = getattr(main_window, "history_widget", None)

        if history_widget is None:
            return False

        try:
            if main_window is not None and hasattr(main_window, "change_section"):
                main_window.change_section("history")
            opened = bool(history_widget.open_editor_for_application(application_id))
        except Exception as exc:
            logger.warning(f"Navigation vers l'editeur impossible: {exc}")
            return False

        if opened:
            try:
                updated = history_widget.get_cv_data_for_application(application_id)
                if isinstance(updated, dict):
                    self.cv_data = updated
                    self.load_template_preview()
                    self.status_label.setText("Previsualisation mise a jour.")
            except Exception as exc:
                logger.warning(f"Refresh preview failed: {exc}")

        return opened

    def _fallback_inline_edit(self) -> None:
        """Fallback: reste sur l'editeur HTML integre."""
        if not hasattr(self, "content_editor") or self.content_editor is None:
            return
        try:
            if self.splitter is not None:
                try:
                    total_width = max(int(self.width()), 900)
                except Exception:
                    total_width = 1200
                actions_width = 380
                self.splitter.setSizes([max(total_width - actions_width, 400), actions_width])
        except Exception:
            pass

        try:
            self.edit_mode = "html"
            html_source = self.cv_data.get("raw_html") or self.last_rendered_html
            if not html_source:
                html_source = self.generate_dynamic_html()
                self.last_rendered_html = html_source
            if html_source:
                self.content_editor.setPlainText(html_source)
            self.content_editor.setFocus()
            self.status_label.setText(
                "Mode edition HTML - Modifiez puis cliquez sur 'Appliquer les modifications'."
            )
        except Exception:
            pass

    def _active_preview_kind(self) -> str:
        if hasattr(self, "preview_tabs") and self.preview_tabs.currentIndex() == getattr(
            self, "letter_tab_index", -1
        ):
            return "letter"
        return "cv"

    def _set_preview_loaded(self, web_view, loaded: bool) -> None:
        if web_view is self.cv_web_view:
            self._cv_preview_loaded = loaded
        elif web_view is self.letter_web_view:
            self._letter_preview_loaded = loaded

    def _is_preview_loaded(self, web_view) -> bool:
        if web_view is self.cv_web_view:
            return self._cv_preview_loaded
        if web_view is self.letter_web_view:
            return self._letter_preview_loaded
        return False

    def _update_export_state(self) -> None:
        active = self._active_preview_kind()
        if active == "letter":
            enabled = self.letter_template_validated
            label = "Exporter la lettre en PDF"
        else:
            enabled = self.cv_template_validated
            label = "Exporter le CV en PDF"
        self.export_button.setEnabled(enabled)
        self.export_button.setText(label)

    def on_preview_tab_changed(self, index: int) -> None:
        if hasattr(self, "template_selector_stack"):
            self.template_selector_stack.setCurrentIndex(
                1 if index == getattr(self, "letter_tab_index", 1) else 0
            )
        if index == getattr(self, "letter_tab_index", 1):
            self.load_letter_preview()
        if hasattr(self, "export_button"):
            self._update_export_state()

    def update_cv_template_info(self):
        """Met a jour l'information du template CV selectionne."""
        current_data = self.cv_template_combo.currentData()
        if current_data and current_data in self.TEMPLATES:
            template_info = self.TEMPLATES[current_data]
            self.cv_template_info.setText(f"{template_info['description']}")

    def update_letter_template_info(self):
        """Met a jour l'information du template lettre selectionne."""
        current_data = self.letter_template_combo.currentData()
        if current_data and current_data in LETTER_TEMPLATES:
            template_info = LETTER_TEMPLATES[current_data]
            self.letter_template_info.setText(f"{template_info['description']}")

    def on_cv_template_changed(self):
        """Appelle quand l'utilisateur change de template CV."""
        current_data = self.cv_template_combo.currentData()
        if current_data:
            self.current_template = current_data
            self.cv_template_validated = False
            self.update_cv_template_info()
            self.load_cv_preview()
            self.status_label.setText(
                f"Template CV '{self.TEMPLATES[current_data]['name']}' previsualise - Validez pour exporter"
            )
            self._update_export_state()

    def on_letter_template_changed(self):
        """Appelle quand l'utilisateur change de template lettre."""
        current_data = self.letter_template_combo.currentData()
        if current_data:
            self.current_letter_template = current_data
            self.letter_template_validated = False
            self.update_letter_template_info()
            self.load_letter_preview()
            self.status_label.setText(
                f"Template lettre '{LETTER_TEMPLATES[current_data]['name']}' previsualise - Validez pour exporter"
            )
            self._update_export_state()

    def load_template_preview(self):
        """Charge la previsualisation des deux onglets."""
        self.load_cv_preview()
        self.load_letter_preview()

    def load_cv_preview(self):
        """Charge la previsualisation du CV."""
        try:
            html_content = self.generate_dynamic_html()
            if not html_content or not html_content.strip():
                logger.warning(
                    f"Preview HTML vide pour template '{self.current_template}', fallback sur le contenu brut."
                )
                html_content = self.create_html_from_raw_content()
            self.last_rendered_html = html_content or ""

            self.update_content_editor()
            html_with_css = self.inject_css_into_html(html_content, self.current_template)

            logger.info(
                f"HTML preview ready (len={len(html_content)}, template={self.current_template}, "
                f"raw_html={bool(self.cv_data.get('raw_html'))}, raw_content={bool(self.cv_data.get('raw_content'))})"
            )

            templates_dir = Path(__file__).parent.parent.parent / "templates"
            base_url = f"file:///{str(templates_dir).replace(chr(92), '/')}/"
            self._cv_preview_loaded = False
            self.cv_web_view.setHtml(html_with_css, baseUrl=base_url)

            logger.info(f"Previsualisation chargee pour template: {self.current_template}")

        except Exception as e:
            logger.error(f"Erreur chargement previsualisation CV: {e}")
            error_html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    body {{ 
                        font-family: Arial, sans-serif; 
                        padding: 40px; 
                        text-align: center; 
                        background: #f8f9fa; 
                        margin: 0;
                    }}
                    .error-container {{
                        background: white;
                        padding: 30px;
                        border-radius: 8px;
                        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                        max-width: 500px;
                        margin: 0 auto;
                    }}
                    h2 {{ color: #dc3545; margin-bottom: 20px; }}
                    p {{ color: #6c757d; line-height: 1.5; }}
                </style>
            </head>
            <body>
                <div class="error-container">
                    <h2>Erreur de previsualisation</h2>
                    <p>Impossible de charger le template <strong>{self.current_template}</strong></p>
                    <p>Erreur: {str(e)}</p>
                </div>
            </body>
            </html>
            """
            self.cv_web_view.setHtml(error_html)

    def load_letter_preview(self):
        """Charge la previsualisation de la lettre."""
        try:
            html_content = self.generate_letter_html()
            self.last_letter_rendered_html = html_content or ""

            html_with_css = self.inject_letter_css_into_html(
                html_content, self.current_letter_template
            )

            templates_dir = Path(__file__).parent.parent.parent / "templates"
            base_url = f"file:///{str(templates_dir).replace(chr(92), '/')}/"
            self._letter_preview_loaded = False
            self.letter_web_view.setHtml(html_with_css, baseUrl=base_url)

            logger.info(
                f"Lettre preview ready (len={len(html_content)}, template={self.current_letter_template})"
            )

        except Exception as e:
            logger.error(f"Erreur chargement previsualisation lettre: {e}")
            error_html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    body {{ 
                        font-family: Arial, sans-serif; 
                        padding: 40px; 
                        text-align: center; 
                        background: #f8f9fa; 
                        margin: 0;
                    }}
                    .error-container {{
                        background: white;
                        padding: 30px;
                        border-radius: 8px;
                        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                        max-width: 500px;
                        margin: 0 auto;
                    }}
                    h2 {{ color: #dc3545; margin-bottom: 20px; }}
                    p {{ color: #6c757d; line-height: 1.5; }}
                </style>
            </head>
            <body>
                <div class="error-container">
                    <h2>Erreur de previsualisation</h2>
                    <p>Impossible de charger la lettre de motivation.</p>
                    <p>Erreur: {str(e)}</p>
                </div>
            </body>
            </html>
            """
            self.letter_web_view.setHtml(error_html)

    def generate_letter_html(self) -> str:
        """Genere le HTML de la lettre de motivation."""
        cover_letter = self.cv_data.get("cover_letter") or ""

        def _safe(value: str) -> str:
            return html_lib.escape(str(value)) if value else ""

        name = _safe(self.cv_data.get("name") or "Candidat")
        email = _safe(self.cv_data.get("email") or "")
        phone = _safe(self.cv_data.get("phone") or "")
        location = _safe(self.cv_data.get("location") or "")
        job_title_raw = self.cv_data.get("job_title") or ""
        company_raw = self.cv_data.get("company") or ""
        job_title = _safe(job_title_raw)
        company = _safe(company_raw)
        date_label = datetime.now().strftime("%d/%m/%Y")

        subject = "Candidature"
        if job_title:
            subject = f"Candidature - {job_title}"

        contact_parts = [part for part in (email, phone, location) if part]
        contact_html = " | ".join(contact_parts)

        recipient_lines = []
        if company_raw:
            recipient_lines.append(f"Entreprise: {company_raw}")
        if job_title_raw:
            recipient_lines.append(f"Poste: {job_title_raw}")
        recipient_lines.append(date_label)
        recipient_html = "".join(
            f"<div class=\"recipient-line\">{html_lib.escape(line)}</div>"
            for line in recipient_lines
        )

        body_html = self._cover_letter_to_html(cover_letter)

        return f"""
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Lettre - {name}</title>
</head>
<body>
    <div class="letter-container">
        <header class="letter-header">
            <div class="sender">
                <div class="sender-name">{name}</div>
                <div class="sender-meta">{contact_html}</div>
            </div>
            <div class="recipient">
                {recipient_html}
            </div>
        </header>
        <div class="letter-body">
            <div class="letter-subject"><strong>Objet:</strong> {html_lib.escape(subject)}</div>
            <div class="letter-content">
                {body_html}
            </div>
        </div>
        <div class="letter-footer">
            <div class="signature">{name}</div>
        </div>
    </div>
</body>
</html>
        """

    def _cover_letter_to_html(self, raw_text: str) -> str:
        if not raw_text or not isinstance(raw_text, str) or not raw_text.strip():
            return "<p>Aucune lettre de motivation disponible.</p>"
        if raw_text.lstrip().startswith("<"):
            return raw_text

        paragraphs = []
        buffer = []
        for line in raw_text.splitlines():
            if not line.strip():
                if buffer:
                    paragraph = " ".join(buffer).strip()
                    if paragraph:
                        paragraphs.append(paragraph)
                    buffer = []
                continue
            buffer.append(line.strip())

        if buffer:
            paragraph = " ".join(buffer).strip()
            if paragraph:
                paragraphs.append(paragraph)

        if not paragraphs:
            return "<p>Aucune lettre de motivation disponible.</p>"

        return "\n".join(f"<p>{html_lib.escape(p)}</p>" for p in paragraphs)

    def inject_css_into_html(self, html_content: str, template_name: str) -> str:
        """Injecte le CSS directement dans le HTML pour la prévisualisation."""
        try:
            # Chemin vers le fichier CSS
            css_file = Path(__file__).parent.parent.parent / "templates" / "css" / f"{template_name}.css"
            
            if css_file.exists():
                css_content = css_file.read_text(encoding="utf-8")
                logger.info(f"CSS injecté pour template {template_name}")
            else:
                css_content = _build_fallback_css(template_name)
                logger.warning(f"Fichier CSS non trouvé: {css_file} - fallback appliqué")

            if self.force_single_page:
                css_content = f"{css_content}\n{ONE_PAGE_PRINT_CSS}"

            # Injecter le CSS dans le HTML
            if "<head>" in html_content:
                css_tag = f"<style>\n{css_content}\n</style>"
                html_content = html_content.replace("<head>", f"<head>\n{css_tag}")
            else:
                # Si pas de head, ajouter au début
                css_tag = f"<style>\n{css_content}\n</style>\n"
                html_content = css_tag + html_content
            
            return html_content
            
        except Exception as e:
            logger.error(f"Erreur injection CSS: {e}")
            return html_content
    

    def inject_letter_css_into_html(self, html_content: str, template_name: str) -> str:
        """Injecte le CSS de lettre de motivation dans le HTML."""
        try:
            css_file = (
                Path(__file__).parent.parent.parent
                / "templates"
                / "letter_css"
                / f"{template_name}.css"
            )

            if css_file.exists():
                css_content = css_file.read_text(encoding="utf-8")
                logger.info(f"CSS lettre injecte pour template {template_name}")
            else:
                css_content = _build_letter_fallback_css()
                logger.warning(f"CSS lettre manquant: {css_file} - fallback applique")

            if self.force_single_page:
                css_content = f"{css_content}\n{ONE_PAGE_PRINT_CSS}"

            if "<head>" in html_content:
                css_tag = f"<style>\n{css_content}\n</style>"
                html_content = html_content.replace("<head>", f"<head>\n{css_tag}")
            else:
                css_tag = f"<style>\n{css_content}\n</style>\n"
                html_content = css_tag + html_content

            return html_content
        except Exception as e:
            logger.error(f"Erreur injection CSS lettre: {e}")
            return html_content

    def validate_template(self):
        """Valide le template selectionne."""
        active = self._active_preview_kind()
        if active == "letter":
            template_name = LETTER_TEMPLATES[self.current_letter_template]["name"]
            self.letter_template_validated = True
            target_label = "lettre"
        else:
            template_name = self.TEMPLATES[self.current_template]["name"]
            self.cv_template_validated = True
            target_label = "CV"
        self.status_label.setText(
            f"Template '{template_name}' valide - Export PDF disponible"
        )
        self._update_export_state()

        QMessageBox.information(
            self,
            "Template Valide",
            f"Template '{template_name}' selectionne avec succes !\n\n"
            f"Vous pouvez maintenant exporter votre {target_label} en PDF."
        )

    def show_css_tooltip(self):
        """Affiche le tooltip pour le bouton CSS (MVP)."""
        QToolTip.showText(
            self.sender().mapToGlobal(self.sender().rect().center()),
            "🚧 Fonctionnalité à venir\n\nLa modification personnalisée du CSS sera disponible dans une future version.",
            self.sender(),
            self.sender().rect(),
            3000  # 3 secondes
        )
    
    def _is_weasyprint_available(self) -> bool:
        try:
            support = self.export_manager.check_pdf_support()
        except Exception:
            return False
        return bool(support.get("pdf_available"))

    def _load_html_for_pdf(self, html_with_css: str, web_view) -> None:
        templates_dir = Path(__file__).parent.parent.parent / "templates"
        base_url = f"file:///{str(templates_dir).replace(chr(92), '/')}/"
        if web_view is self.cv_web_view:
            self.last_rendered_html = html_with_css
        elif web_view is self.letter_web_view:
            self.last_letter_rendered_html = html_with_css
        self._set_preview_loaded(web_view, False)
        web_view.setHtml(html_with_css, baseUrl=base_url)

    def _apply_print_scale(self, web_view, callback) -> None:
        page = web_view.page()
        script = """
        (() => {
          const container = document.querySelector('.cv-container') || document.querySelector('.letter-container') || document.body;
          const height = container.scrollHeight || document.body.scrollHeight || 1;
          const width = container.scrollWidth || document.body.scrollWidth || 1;
          const pageHeight = 1122;
          const pageWidth = 794;
          let scale = Math.min(1, pageHeight / height, pageWidth / width);
          if (!isFinite(scale) || scale <= 0) {
            scale = 1;
          }
          document.documentElement.style.setProperty('--print-scale', scale.toFixed(3));
          return scale;
        })();
        """

        def _after_scale(_result=None) -> None:
            callback()

        try:
            page.runJavaScript(script, _after_scale)
        except Exception as exc:
            logger.warning(f"Print scale JS failed: {exc}")
            callback()

    def _start_webengine_pdf_export(self, pdf_output_path: str, html_with_css: str, web_view) -> None:
        self._pdf_export_method = "webengine"
        self._pdf_web_view = web_view
        page = web_view.page()
        if not hasattr(page, "pdfPrintingFinished"):
            self.on_export_error("Export PDF via WebEngine non supporte. Installez WeasyPrint.")
            return
        self._pending_pdf_path = pdf_output_path
        self._pending_pdf_html = html_with_css
        self.status_label.setText(
            "Export PDF via la previsualisation..."
        )
        if html_with_css:
            self._load_html_for_pdf(html_with_css, web_view)
        else:
            self._set_preview_loaded(web_view, False)
            self.load_template_preview()

        if self._is_preview_loaded(web_view):
            self._print_pdf_with_webengine()

    def _print_pdf_with_webengine(self) -> None:
        pdf_path = self._pending_pdf_path
        if not pdf_path:
            return
        web_view = self._pdf_web_view
        if web_view is None:
            self.on_export_error("Export PDF via WebEngine indisponible.")
            return
        page = web_view.page()

        def _do_print() -> None:
            self._pending_pdf_path = None
            try:
                page.printToPdf(pdf_path)
            except Exception as exc:
                self.on_export_error(f"Export PDF via WebEngine impossible: {exc}")

        if self.force_single_page:
            self._apply_print_scale(web_view, _do_print)
            return

        _do_print()

    def _on_preview_loaded(self, ok: bool) -> None:
        sender = self.sender()
        if sender is None:
            return
        if sender is self.cv_web_view:
            self._cv_preview_loaded = bool(ok)
        elif sender is self.letter_web_view:
            self._letter_preview_loaded = bool(ok)
        else:
            return

        if self._pdf_export_method == "webengine" and self._pending_pdf_path and sender is self._pdf_web_view:
            if not ok:
                self.on_export_error(
                    "Echec du chargement de la previsualisation pour l'export PDF."
                )
                return
            self._print_pdf_with_webengine()

    def _on_pdf_print_finished(self, file_path: str, success: bool) -> None:
        if self._pdf_export_method != "webengine":
            return
        if success:
            self.on_export_finished(file_path)
        else:
            self.on_export_error(
                "Export PDF via le moteur de previsualisation a echoue."
            )

    def export_pdf(self):
        """Exporte le CV ou la lettre en PDF."""
        if not self.export_button.isEnabled():
            return

        active = self._active_preview_kind()
        if active == "letter":
            self._export_letter_pdf()
        else:
            self._export_cv_pdf()

    def _export_cv_pdf(self) -> None:
        try:
            job_title = self.cv_data.get("job_title", "Poste").replace(" ", "_")
            company = (
                self.cv_data.get("company", "Entreprise").replace(" ", "_")
                if "company" in self.cv_data
                else "Entreprise"
            )
            date_str = datetime.now().strftime("%Y%m%d")
            base_name = f"CV_{job_title}_{company}_{date_str}"
            pdf_output_path = self.output_dir / f"{base_name}.pdf"
            html_output_path = self.output_dir / f"{base_name}.html"

            html_content = self.generate_dynamic_html()
            html_with_css = self.inject_css_into_html(html_content, self.current_template)

            try:
                self.export_manager.save_html(html_with_css, str(html_output_path))
                self.last_html_export_path = str(html_output_path)
            except Exception as e:
                logger.error(f"Erreur export HTML: {e}")
                raise

            self._last_export_kind = "cv"
            self.export_button.setEnabled(False)
            self.export_button.setText("Export en cours...")

            if self.force_single_page:
                logger.info("Single-page PDF export enabled; using WebEngine.")
                self._start_webengine_pdf_export(
                    str(pdf_output_path), html_with_css, self.cv_web_view
                )
                return

            if not self._is_weasyprint_available():
                logger.warning("WeasyPrint non disponible - export PDF via WebEngine.")
                self._start_webengine_pdf_export(
                    str(pdf_output_path), html_with_css, self.cv_web_view
                )
                return

            self._pdf_export_method = "weasyprint"
            self.status_label.setText("Export HTML + PDF en cours, veuillez patienter...")

            self.export_thread = PDFExportThread(
                self.cv_data,
                self.current_template,
                str(pdf_output_path),
                html_content=html_with_css,
                use_inline_css=True,
            )
            self.export_thread.finished.connect(self.on_export_finished)
            self.export_thread.error.connect(self.on_export_error)
            self.export_thread.start()

        except Exception as e:
            logger.error(f"Erreur preparation export: {e}")
            self.on_export_error(str(e))

    def _export_letter_pdf(self) -> None:
        try:
            job_title = self.cv_data.get("job_title", "Poste").replace(" ", "_")
            company = (
                self.cv_data.get("company", "Entreprise").replace(" ", "_")
                if "company" in self.cv_data
                else "Entreprise"
            )
            date_str = datetime.now().strftime("%Y%m%d")
            base_name = f"Lettre_{job_title}_{company}_{date_str}"
            pdf_output_path = self.output_dir / f"{base_name}.pdf"
            html_output_path = self.output_dir / f"{base_name}.html"

            html_content = self.generate_letter_html()
            html_with_css = self.inject_letter_css_into_html(
                html_content, self.current_letter_template
            )

            try:
                self.export_manager.save_html(html_with_css, str(html_output_path))
                self.last_html_export_path = str(html_output_path)
                self.last_letter_html_export_path = str(html_output_path)
            except Exception as e:
                logger.error(f"Erreur export HTML lettre: {e}")
                raise

            self._last_export_kind = "letter"
            self.export_button.setEnabled(False)
            self.export_button.setText("Export en cours...")

            logger.info("Letter PDF export uses WebEngine.")
            self._start_webengine_pdf_export(
                str(pdf_output_path), html_with_css, self.letter_web_view
            )

        except Exception as e:
            logger.error(f"Erreur preparation export lettre: {e}")
            self.on_export_error(str(e))

    def on_export_finished(self, pdf_path: str):
        """Appelle quand l'export PDF est termine."""
        self.export_button.setEnabled(True)
        self._pdf_export_method = None
        self._pending_pdf_path = None
        self._pending_pdf_html = None
        self._pdf_web_view = None

        export_kind = self._last_export_kind or "cv"
        self._last_export_kind = None
        self._update_export_state()

        if export_kind == "letter":
            template_name = LETTER_TEMPLATES[self.current_letter_template]["name"]
            label = "Lettre"
        else:
            template_name = self.TEMPLATES[self.current_template]["name"]
            label = "CV"

        html_path = getattr(self, "last_html_export_path", None)
        if html_path:
            self.status_label.setText(
                f"{label} HTML + PDF exportes: {Path(html_path).name}, {Path(pdf_path).name}"
            )
        else:
            self.status_label.setText(f"{label} PDF exporte: {Path(pdf_path).name}")

        html_line = f"HTML: {Path(html_path).name}\n" if html_path else ""
        reply = QMessageBox.question(
            self,
            "Export reussi",
            f"{label} exporte avec succes !\n\n"
            f"Template: {template_name}\n"
            f"{html_line}"
            f"PDF: {Path(pdf_path).name}\n"
            f"Dossier: {Path(pdf_path).parent}\n\n"
            f"Voulez-vous ouvrir le dossier de destination ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            if sys.platform == "win32":
                os.startfile(Path(pdf_path).parent)
            else:
                import subprocess
                subprocess.run([
                    "xdg-open" if sys.platform == "linux" else "open",
                    str(Path(pdf_path).parent),
                ])

        logger.info(f"Export PDF reussi: {pdf_path}")

    def on_export_error(self, error_message: str):
        """Appelle en cas d'erreur d'export."""
        self.export_button.setEnabled(True)
        export_method = self._pdf_export_method
        self._pdf_export_method = None
        self._pending_pdf_path = None
        self._pending_pdf_html = None
        self._pdf_web_view = None
        self._last_export_kind = None
        self._update_export_state()

        html_path = getattr(self, "last_html_export_path", None)
        if html_path:
            self.status_label.setText(
                "Erreur export PDF (HTML sauvegarde)"
            )
        else:
            self.status_label.setText("Erreur lors de l'export PDF")

        hint = "Verifiez que WeasyPrint est correctement installe."
        if export_method == "webengine":
            hint = "Le moteur de previsualisation n'a pas pu generer le PDF. Essayez d'installer WeasyPrint pour l'export PDF."
        QMessageBox.critical(
            self,
            "Erreur Export PDF",
            f"Impossible d'exporter le PDF :\n\n{error_message}\n\n"
            f"{hint}",
        )

        logger.error(f"Erreur export PDF: {error_message}")

    def update_content_editor(self):
        """Met à jour l'éditeur avec le contenu du CV."""
        if not hasattr(self, 'content_editor') or self.content_editor is None:
            return
        try:
            if self.cv_data.get('raw_html') or self.edit_mode == "html":
                html_source = self.cv_data.get('raw_html') or self.last_rendered_html
                if html_source:
                    self.content_editor.setPlainText(html_source)
                    self.edit_mode = "html"
                    return

            # Si on a du contenu brut markdown
            if 'raw_content' in self.cv_data:
                self.content_editor.setPlainText(self.cv_data['raw_content'])
                self.edit_mode = "markdown"
            else:
                # Sinon, créer un résumé du contenu structuré
                content_parts = []
                
                if self.cv_data.get('profile_summary'):
                    content_parts.append(f"# Profil\n{self.cv_data['profile_summary']}\n")
                
                if self.cv_data.get('experience'):
                    content_parts.append("# Expérience")
                    for exp in self.cv_data['experience']:
                        if exp.get('raw_text'):
                            content_parts.append(exp['raw_text'])
                        else:
                            content_parts.append(f"**{exp.get('title', 'Poste')}** - {exp.get('company', 'Entreprise')}")
                    content_parts.append("")
                
                if self.cv_data.get('skills'):
                    content_parts.append("# Compétences")
                    for skill_cat in self.cv_data['skills']:
                        content_parts.append(f"**{skill_cat.get('category', 'Compétences')}:**")
                        for skill in skill_cat.get('skills_list', []):
                            content_parts.append(f"- {skill.get('name', 'Compétence')}")
                    content_parts.append("")
                
                self.edit_mode = "markdown"
                self.content_editor.setPlainText('\n'.join(content_parts) if content_parts else "Contenu du CV à compléter...")
                
        except Exception as e:
            logger.error(f"Erreur mise à jour éditeur: {e}")
            self.content_editor.setPlainText("Erreur chargement contenu...")

    def _is_empty_value(self, value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, str):
            return not value.strip()
        if isinstance(value, (list, dict, tuple, set)):
            return len(value) == 0
        return False

    def _has_structured_content(self) -> bool:
        keys = [
            "profile_summary",
            "experience",
            "education",
            "skills",
            "languages",
            "projects",
            "certifications",
            "interests",
        ]
        return any(not self._is_empty_value(self.cv_data.get(key)) for key in keys)

    def _normalize_skills(self, skills: Any) -> Any:
        if not skills or not isinstance(skills, list):
            return skills
        if all(isinstance(item, str) for item in skills):
            items = [item.strip() for item in skills if item and str(item).strip()]
            return [
                {
                    "category": "Skills",
                    "skills_list": [{"name": item, "level": None} for item in items],
                }
            ]

        normalized = []
        for block in skills:
            if isinstance(block, dict):
                if isinstance(block.get("skills_list"), list):
                    normalized.append(block)
                    continue
                items = block.get("items") or block.get("skills") or []
                skills_list = []
                for item in items:
                    if isinstance(item, dict):
                        name = item.get("name") or item.get("skill") or ""
                        level = item.get("level")
                    else:
                        name = str(item)
                        level = None
                    name = str(name).strip()
                    if name:
                        skills_list.append({"name": name, "level": level})
                if skills_list:
                    normalized.append(
                        {
                            "category": block.get("category") or "Skills",
                            "skills_list": skills_list,
                        }
                    )
            elif isinstance(block, str):
                name = block.strip()
                if not name:
                    continue
                if not normalized:
                    normalized.append({"category": "Skills", "skills_list": []})
                normalized[0]["skills_list"].append({"name": name, "level": None})

        return normalized or skills

    def _try_parse_raw_content(self) -> bool:
        raw_content = self.cv_data.get("raw_content")
        if not raw_content or not isinstance(raw_content, str):
            return False
        if self._has_structured_content():
            return False
        try:
            from ..controllers.cv_generator import CVGenerator

            parser = CVGenerator()
            parsed = parser.parse_cv_from_markdown(raw_content)
            if parsed.get("skills"):
                parsed["skills"] = self._normalize_skills(parsed["skills"])

            merged = False
            for key, value in parsed.items():
                if self._is_empty_value(self.cv_data.get(key)) and not self._is_empty_value(value):
                    self.cv_data[key] = value
                    merged = True

            if merged:
                logger.info("CV preview: structured data restored from raw_content.")
            return merged
        except Exception as exc:
            logger.warning(f"CV preview: raw_content parsing failed: {exc}")
            return False

    def apply_content_changes(self):
        """Applique les modifications du contenu et recharge la previsualisation."""
        if not hasattr(self, "content_editor") or self.content_editor is None:
            return
        try:
            # Recuperer le nouveau contenu
            new_content = self.content_editor.toPlainText()
            is_html = self.edit_mode == "html" or new_content.lstrip().startswith("<")

            if is_html:
                self.cv_data["raw_html"] = new_content
                self.last_rendered_html = new_content
            else:
                self.cv_data["raw_content"] = new_content
                self.cv_data.pop("raw_html", None)
                self.edit_mode = "markdown"

                # Re-parser le contenu modifie
                if hasattr(self, "parent") and hasattr(self.parent(), "parse_cv_markdown"):
                    try:
                        parsed_data = self.parent().parse_cv_markdown(new_content)
                        self.cv_data.update(parsed_data)
                    except Exception:
                        pass

            # Recharger la previsualisation
            self.load_template_preview()

            # Feedback utilisateur
            self.status_label.setText("Contenu mis a jour avec succes")

            # Timer pour remettre le status normal
            QTimer.singleShot(3000, lambda: self.status_label.setText("Pret - Selectionnez un template et validez pour exporter"))

        except Exception as e:
            logger.error(f"Erreur application modifications: {e}")
            QMessageBox.warning(self, "Erreur", f"Impossible d'appliquer les modifications:\n{e}")

    def generate_dynamic_html(self) -> str:
        """Génère le HTML avec contenu dynamique."""
        try:
            raw_html = self.cv_data.get("raw_html")
            if raw_html:
                logger.info(f"CV preview: raw_html used (len={len(raw_html)})")
                return raw_html

            raw_content = self.cv_data.get("raw_content")
            self._try_parse_raw_content()
            if raw_content and isinstance(raw_content, str) and not self._has_structured_content():
                logger.warning("CV preview: structured data empty, using raw_content HTML fallback.")
                return self.create_html_from_raw_content()

            templates_dir = Path(__file__).parent.parent.parent / "templates"
            template_file = templates_dir / "cv_templates" / f"{self.current_template}.html"

            if template_file.exists():
                return self.export_manager.generate_html(self.cv_data, self.current_template)

            # Si pas de template, fallback sur le contenu brut
            if raw_content and isinstance(raw_content, str):
                return self.create_html_from_raw_content()

            # Dernier recours: essayer le générateur HTML standard
            return self.export_manager.generate_html(self.cv_data, self.current_template)
        except Exception as e:
            logger.error(f"Erreur génération HTML dynamique: {e}")
            return self.export_manager.generate_html(self.cv_data, self.current_template)
    
    def create_html_from_raw_content(self) -> str:
        """Crée du HTML à partir du contenu brut markdown."""
        raw_content = self.cv_data.get('raw_content', '')
        
        # Conversion markdown basique vers HTML
        html_content = raw_content
        html_content = html_content.replace('\n# ', '\n<h2>')
        html_content = html_content.replace('\n## ', '\n<h3>')
        html_content = html_content.replace('\n**', '\n<strong>')
        html_content = html_content.replace('**\n', '</strong>\n')
        html_content = html_content.replace('\n- ', '\n<li>')
        html_content = html_content.replace('\n\n', '</p>\n<p>')
        
        # Nettoyer et structurer
        if not html_content.startswith('<'):
            html_content = '<p>' + html_content + '</p>'
        
        # Template HTML complet avec le contenu dynamique
        full_html = f"""
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CV - {self.cv_data.get('name', 'Candidat')}</title>
</head>
<body>
    <div class="cv-container">
        <!-- Header Section -->
        <header class="cv-header">
            <div class="header-content">
                <h1 class="name">{self.cv_data.get('name', 'Candidat')}</h1>
                <h2 class="title">{self.cv_data.get('job_title', 'Professionnel')}</h2>
                
                <div class="contact-info">
                    <div class="contact-item">
                        <span class="icon">✉️</span>
                        <span class="text">{self.cv_data.get('email', '')}</span>
                    </div>
                    <div class="contact-item">
                        <span class="icon">📞</span>
                        <span class="text">{self.cv_data.get('phone', '')}</span>
                    </div>
                    <div class="contact-item">
                        <span class="icon">📍</span>
                        <span class="text">{self.cv_data.get('location', '')}</span>
                    </div>
                </div>
            </div>
        </header>

        <div class="cv-body">
            <div class="main-content">
                <section class="cv-section">
                    <h3 class="section-title">Contenu du CV</h3>
                    <div class="section-content dynamic-content">
                        {html_content}
                    </div>
                </section>
            </div>
        </div>
    </div>
</body>
</html>
        """
        
        return full_html
    
    def closeEvent(self, event):
        """Gère la fermeture de la fenêtre."""
        try:
            # Arrêter le thread d'export si en cours
            if self.export_thread and self.export_thread.isRunning():
                self.export_thread.terminate()
                self.export_thread.wait()
            
            # LOG: Cette fenêtre se ferme, mais ce n'est PAS une fermeture de l'app principale
            logger.info("Fermeture de la fenetre de previsualisation (fenetre secondaire)")
            
            # Accepter la fermeture sans affecter l'application principale
            event.accept()
            
            # S'assurer que cette fenêtre ne déclenche pas la fermeture de l'app
            self.setAttribute(Qt.WA_QuitOnClose, False)
            
        except Exception as e:
            logger.error(f"Erreur lors de la fermeture de la fenetre de previsualisation: {e}")
            event.accept()


# Test de la fenêtre (à utiliser pour debug)
def test_template_preview():
    """Fonction de test pour la fenêtre de prévisualisation."""
    app = QApplication(sys.argv)
    
    # Données de test
    test_cv_data = {
        "name": "Jean Dupont",
        "email": "jean.dupont@email.com",
        "phone": "+33 6 12 34 56 78",
        "location": "Paris, France",
        "job_title": "Développeur Full-Stack",
        "profile_summary": "Développeur passionné avec 5 ans d'expérience en développement web.",
        "experience": [
            {
                "title": "Développeur Senior",
                "company": "TechCorp",
                "start_date": "2022",
                "end_date": None,
                "description": ["Développement d'applications web", "Architecture et conception"]
            }
        ],
        "skills": [
            {
                "category": "Langages",
                "skills_list": [{"name": "JavaScript", "level": 90}, {"name": "Python", "level": 85}]
            }
        ]
    }
    
    window = TemplatePreviewWindow(test_cv_data)
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    test_template_preview()
