"""
Model Selector Widget
=====================

Widget compact pour la sélection de modèles IA dans l'interface de nouvelle candidature.
"""

from typing import Optional, Callable
import os
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QComboBox, 
    QPushButton, QFrame, QToolTip
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QCursor
from loguru import logger

from ..utils.model_manager import model_manager


class CompactModelSelector(QWidget):
    """Sélecteur de modèles compact pour l'interface principale."""

    model_changed = Signal(str)  # Émis quand le modèle change

    def __init__(self, parent=None):
        super().__init__(parent)

        # Flag pour éviter le spam d'erreurs
        self._last_validation_error = None
        self._is_initializing = True

        # Utiliser la configuration centralisée
        try:
            from ..utils.model_config_manager import model_config_manager
            self.config_manager = model_config_manager
            saved_model = model_config_manager.get_current_config().model_id
            # Valider le modele sauvegarde (warning only)
            model_info = model_manager.get_model_info(saved_model)
            if model_info:
                self.current_model = saved_model
                validation = model_manager.validate_model_selection(saved_model)
                if not validation.get('valid'):
                    logger.warning(
                        f"Modele sauvegarde '{saved_model}' incompatible: {validation.get('error')}"
                    )
            else:
                self.current_model = model_manager.recommended_model
                logger.warning(
                    f"Modele sauvegarde '{saved_model}' inconnu, fallback sur '{self.current_model}'"
                )

            # S'abonner aux changements
            model_config_manager.add_observer(self.on_config_changed)
        except ImportError:
            self.config_manager = None
            self.current_model = model_manager.recommended_model

        self.setup_ui()
        self.update_display()
        self._is_initializing = False
    
    def setup_ui(self):
        """Configure l'interface utilisateur."""
        # Style général du widget
        self.setStyleSheet("""
            CompactModelSelector {
                background-color: #1e1e1e;
                border-radius: 8px;
                border: 1px solid #333;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)
        
        # Header avec titre et status
        header_layout = QHBoxLayout()
        
        # Titre
        title_label = QLabel("🤖 Modèle IA")
        title_label.setFont(QFont("Arial", 11, QFont.Bold))
        title_label.setStyleSheet("color: #0078d4;")
        header_layout.addWidget(title_label)
        
        # Status hardware
        self.hardware_label = QLabel()
        self.hardware_label.setFont(QFont("Arial", 9))
        self.hardware_label.setStyleSheet("color: #666;")
        header_layout.addWidget(self.hardware_label)
        
        header_layout.addStretch()
        layout.addLayout(header_layout)
        
        # Sélecteur principal
        selector_layout = QHBoxLayout()
        
        # Dropdown de sélection
        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(200)
        self.model_combo.setStyleSheet("""
            QComboBox {
                padding: 8px 12px;
                border: 2px solid #555;
                border-radius: 6px;
                background-color: #2b2b2b;
                color: #ffffff;
                font-size: 11px;
                font-weight: bold;
                selection-background-color: #0078d4;
            }
            QComboBox:hover {
                border-color: #0078d4;
                background-color: #333333;
            }
            QComboBox:focus {
                border-color: #0078d4;
                outline: none;
                background-color: #333333;
            }
            QComboBox::drop-down {
                border: none;
                width: 25px;
                background-color: #0078d4;
                border-top-right-radius: 6px;
                border-bottom-right-radius: 6px;
            }
            QComboBox::down-arrow {
                image: none;
                border: none;
                width: 0;
                height: 0;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 8px solid #ffffff;
                margin: 2px;
            }
            QComboBox QAbstractItemView {
                background-color: #2b2b2b;
                color: #ffffff;
                border: 2px solid #0078d4;
                border-radius: 6px;
                selection-background-color: #0078d4;
                selection-color: #ffffff;
                font-weight: bold;
            }
            QComboBox QAbstractItemView::item {
                padding: 8px;
                border-bottom: 1px solid #444;
            }
            QComboBox QAbstractItemView::item:hover {
                background-color: #0078d4;
                color: #ffffff;
            }
        """)
        
        self.model_combo.currentTextChanged.connect(self.on_model_changed)
        selector_layout.addWidget(self.model_combo)
        
        # Bouton info/détails
        self.info_button = QPushButton("ℹ️")
        self.info_button.setFixedSize(30, 30)
        self.info_button.setToolTip("Voir les détails du modèle")
        self.info_button.clicked.connect(self.show_model_details)
        self.info_button.setStyleSheet("""
            QPushButton {
                border: 2px solid #555;
                border-radius: 6px;
                background-color: #2b2b2b;
                color: #ffffff;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0078d4;
                border-color: #0078d4;
                color: #ffffff;
            }
            QPushButton:pressed {
                background-color: #005a9e;
            }
        """)
        selector_layout.addWidget(self.info_button)
        
        layout.addLayout(selector_layout)
        
        # Ligne d'informations
        self.info_label = QLabel()
        self.info_label.setFont(QFont("Arial", 9))
        self.info_label.setStyleSheet("color: #666; padding: 2px 0;")
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)
        
        # Optionnel: ligne de recommandation
        self.recommendation_label = QLabel()
        self.recommendation_label.setFont(QFont("Arial", 9))
        self.recommendation_label.setStyleSheet("color: #0078d4; font-style: italic;")
        layout.addWidget(self.recommendation_label)
        
        # Ligne de séparation avec style amélioré
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        separator.setStyleSheet("""
            QFrame {
                color: #444;
                background-color: #444;
                border: none;
                height: 1px;
                margin: 5px 0;
            }
        """)
        layout.addWidget(separator)
    
    def update_display(self):
        """Met à jour l'affichage avec les informations actuelles."""
        # Hardware info
        gpu_info = model_manager.gpu_info
        if gpu_info["available"]:
            gpu_name = gpu_info["name"][:15] + "..." if len(gpu_info["name"]) > 15 else gpu_info["name"]
            self.hardware_label.setText(f"🎮 {gpu_name} ({gpu_info['vram_gb']:.1f}GB)")
        else:
            self.hardware_label.setText("💻 Mode CPU")
        
        # Remplir le dropdown
        self.model_combo.blockSignals(True)  # Éviter les signaux pendant la mise à jour
        self.model_combo.clear()
        
        models = model_manager.get_models_for_dropdown()
        current_index = 0
        
        for i, model_data in enumerate(models):
            text = model_data["text"]
            if model_data["is_recommended"]:
                text += " (Recommandé)"
            
            self.model_combo.addItem(text, model_data["id"])
            
            if model_data["id"] == self.current_model:
                current_index = i
        
        self.model_combo.setCurrentIndex(current_index)
        self.model_combo.blockSignals(False)
        
        # Mettre à jour les informations
        self.update_model_info()
    
    def update_model_info(self):
        """Met à jour les informations du modèle sélectionné."""
        model_info = model_manager.get_model_display_info(self.current_model)
        if not model_info:
            return
        
        # Ligne d'informations principales avec style amélioré
        info_parts = [
            f"💾 {model_info['vram_required']:.0f}GB",
            f"🌟 {model_info['quality_stars']}",
            f"⚡ {model_info['speed_rating']}",
            f"⏱️ ~{model_info['estimated_time']}min"
        ]
        info_text = " • ".join(info_parts)
        self.info_label.setText(info_text)
        self.info_label.setStyleSheet("color: #cccccc; padding: 2px 0; font-size: 10px;")
        
        # Recommandation
        if model_info["is_recommended"]:
            self.recommendation_label.setText("✅ Recommandé pour votre configuration")
            self.recommendation_label.setStyleSheet("color: #00aa00; font-style: italic; font-size: 9px;")
        else:
            # Vérifier si c'est un downgrade ou upgrade
            recommended_info = model_manager.get_model_display_info(model_manager.recommended_model)
            if model_info["vram_required"] > recommended_info["vram_required"]:
                self.recommendation_label.setText("⚠️ Peut être lent sur votre configuration")
                self.recommendation_label.setStyleSheet("color: #ff6600; font-style: italic; font-size: 9px;")
            else:
                self.recommendation_label.setText("💡 Version allégée pour plus de rapidité")
                self.recommendation_label.setStyleSheet("color: #0078d4; font-style: italic; font-size: 9px;")
    
    def on_model_changed(self):
        """Gere le changement de modele."""
        # Ignorer pendant l'initialisation
        if self._is_initializing:
            return

        model_id = self.model_combo.currentData()
        if not model_id or model_id == self.current_model:
            return

        # Valider la selection (warning only)
        validation = model_manager.validate_model_selection(model_id)
        if validation.get('valid'):
            self._last_validation_error = None
        else:
            error_key = f"{model_id}:{validation.get('error')}"
            if self._last_validation_error != error_key:
                self._last_validation_error = error_key
                logger.warning(f"Modele {model_id} non compatible: {validation.get('error')}")

            model_info = model_manager.get_model_info(model_id)
            display_name = getattr(model_info, 'display_name', None) or model_id
            tooltip_msg = (
                f"Warning: {validation.get('error')}\n\n"
                f"Attempting to use {display_name} anyway."
            )
            QToolTip.showText(QCursor.pos(), tooltip_msg, self, self.rect(), 5000)

        self.current_model = model_id

        # Mettre a jour la configuration centralisee si disponible
        if self.config_manager:
            self.config_manager.update_model(model_id)

        self.update_model_info()
        self.model_changed.emit(model_id)
        logger.info(f"Modele selectionne: {model_id}")

        # Nettoyer les caches de modeles non selectionnes
        if os.getenv("CVMATCH_PRUNE_MODEL_CACHE") == "1":
            try:
                pruned = model_manager.prune_model_cache_except(model_id)
                if pruned:
                    logger.info(f"Cache modeles supprime: {len(pruned)} entrees")
            except Exception as exc:
                logger.warning(f"Nettoyage cache modeles ignore: {exc}")
        else:
            logger.debug("Cache modeles conserve (CVMATCH_PRUNE_MODEL_CACHE=1 pour activer).")

    def on_config_changed(self, event_type: str, *args):
        """Callback pour les changements de configuration (synchronisation)."""
        if event_type == 'model_changed' and len(args) >= 2:
            new_model_id = args[1]
            if new_model_id != self.current_model:
                self.current_model = new_model_id
                
                # Mettre à jour l'interface sans déclencher d'événements
                self.model_combo.blockSignals(True)
                for i in range(self.model_combo.count()):
                    if self.model_combo.itemData(i) == new_model_id:
                        self.model_combo.setCurrentIndex(i)
                        break
                self.model_combo.blockSignals(False)
                
                self.update_model_info()
                logger.info(f"Sélecteur synchronisé: {new_model_id}")
    
    def show_model_details(self):
        """Affiche les détails du modèle dans un tooltip."""
        model_info = model_manager.get_model_display_info(self.current_model)
        if not model_info:
            return
        
        tooltip_text = f"""
<b>{model_info['display_name']}</b><br>
<br>
<b>Qualité:</b> {model_info['quality_stars']}<br>
<b>Vitesse:</b> {model_info['speed_rating']}<br>
<b>VRAM requise:</b> {model_info['vram_required']:.1f} GB<br>
<b>Temps estimé:</b> ~{model_info['estimated_time']} minutes<br>
<br>
<i>{model_info['description']}</i>
        """.strip()
        
        QToolTip.showText(QCursor.pos(), tooltip_text, self.info_button)
    
    def get_current_model(self) -> str:
        """Retourne le modèle actuellement sélectionné."""
        return self.current_model
    
    def set_model(self, model_id: str):
        """Définit le modèle sélectionné."""
        if model_id in model_manager.available_models:
            self.current_model = model_id
            self.update_display()
    
    def refresh(self):
        """Rafraîchit l'affichage (utile après changement de hardware)."""
        self.update_display()
