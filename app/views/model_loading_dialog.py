"""Dialog modal pour le chargement des modèles ML."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QProgressBar, 
                            QPushButton, QHBoxLayout, QTextEdit)


class ModelLoadingDialog(QDialog):
    """Dialog modal affiché pendant le chargement des modèles ML.
    
    Features:
    - UI complètement bloquée (modal)
    - Barre de progression indéterminée
    - Messages d'étapes courtes
    - Zone de log détaillée
    - Bouton annuler (bascule en mode mock)
    """
    
    cancel_clicked = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Chargement des modèles")
        self.setWindowModality(Qt.ApplicationModal)
        self.setMinimumWidth(420)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        
        # Titre principal
        self.lbl_title = QLabel("Le modèle travaille, veuillez patienter…")
        self.lbl_title.setWordWrap(True)
        self.lbl_title.setStyleSheet("font-weight: bold; font-size: 14px; margin: 5px;")
        
        # Barre de progression indéterminée
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # Indeterminate progress
        
        # Status line (message court de l'étape courante)
        self.lbl_status = QLabel("Initialisation du pipeline ML…")
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.lbl_status.setStyleSheet("color: #2E86AB; font-weight: bold; margin: 5px;")
        
        # Zone de log détaillée (collapsible plus tard si besoin)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(120)
        self.log.setMaximumHeight(180)
        self.log.setStyleSheet("font-family: 'Consolas', 'Monaco', monospace; font-size: 9pt;")
        
        # Bouton d'annulation
        self.btn_cancel = QPushButton("Annuler (basculer en mode Mock)")
        self.btn_cancel.clicked.connect(self.cancel_clicked.emit)
        self.btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #d32f2f;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)
        
        # Layout des boutons
        btns = QHBoxLayout()
        btns.addStretch(1)
        btns.addWidget(self.btn_cancel)
        
        # Layout principal
        layout = QVBoxLayout(self)
        layout.addWidget(self.lbl_title)
        layout.addWidget(self.progress)
        layout.addWidget(self.lbl_status)
        layout.addWidget(self.log)
        layout.addLayout(btns)
        
        # Styles généraux
        self.setStyleSheet("""
            QDialog {
                background-color: #f5f5f5;
            }
            QLabel {
                color: #333;
            }
            QProgressBar {
                border: 2px solid grey;
                border-radius: 5px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #2E86AB;
                border-radius: 3px;
            }
        """)
    
    def set_status(self, text: str):
        """Met à jour le message d'état court (limité à 200 chars)."""
        display_text = text[:200]
        if len(text) > 200:
            display_text += "..."
        self.lbl_status.setText(display_text)
    
    def append_log(self, line: str):
        """Ajoute une ligne au log détaillé (limitée à 400 chars)."""
        display_line = line[:400]
        if len(line) > 400:
            display_line += "..."
        self.log.append(display_line)
        
        # Auto-scroll vers le bas
        scrollbar = self.log.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    def set_cancel_enabled(self, enabled: bool):
        """Active/désactive le bouton d'annulation."""
        self.btn_cancel.setEnabled(enabled)
        if not enabled:
            self.btn_cancel.setText("Annulation en cours...")
    
    def closeEvent(self, event):
        """Empêche la fermeture manuelle du dialog (seulement par code)."""
        event.ignore()  # Dialog ne peut être fermé que programmatiquement
