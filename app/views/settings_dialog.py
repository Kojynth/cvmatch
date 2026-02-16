"""
Settings Dialog
==============

Interface de configuration des paramètres utilisateur.
"""

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QButtonGroup,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..models.database import get_session
from ..models.user_profile import ModelVersion, UserProfile
from ..services.dialogs import confirm, show_error, show_success, show_warning
from ..widgets.phone_widget import create_phone_widget

if TYPE_CHECKING:
    from ..controllers.main_window.ml_workflow import MlWorkflowCoordinator


class ProfileTab(QWidget):
    """Tab pour les paramètres de profil."""

    def __init__(self, profile: UserProfile):
        super().__init__()
        self.profile = profile
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()

        # Informations personnelles
        personal_group = QGroupBox("Informations personnelles")
        personal_layout = QFormLayout()

        self.name_edit = QLineEdit(self.profile.name)
        personal_layout.addRow("Nom:", self.name_edit)

        self.email_edit = QLineEdit(self.profile.email)
        personal_layout.addRow("Email:", self.email_edit)

        self.phone_widget = create_phone_widget(
            self.profile.phone or "", "Téléphone...", self
        )
        personal_layout.addRow("Téléphone:", self.phone_widget)

        self.linkedin_edit = QLineEdit(self.profile.linkedin_url or "")
        personal_layout.addRow("LinkedIn:", self.linkedin_edit)

        personal_group.setLayout(personal_layout)
        layout.addWidget(personal_group)

        # CV maître
        cv_group = QGroupBox("CV de référence")
        cv_layout = QVBoxLayout()

        if self.profile.master_cv_path:
            cv_info = QLabel(f"Fichier: {Path(self.profile.master_cv_path).name}")
            cv_layout.addWidget(cv_info)
        else:
            cv_layout.addWidget(QLabel("Aucun CV configuré"))

        cv_buttons = QHBoxLayout()
        self.replace_cv_btn = QPushButton("📎 Remplacer")
        self.replace_cv_btn.clicked.connect(self.replace_cv)
        cv_buttons.addWidget(self.replace_cv_btn)

        self.edit_cv_btn = QPushButton("✏️ Éditer contenu")
        self.edit_cv_btn.clicked.connect(self.edit_cv_content)
        cv_buttons.addWidget(self.edit_cv_btn)

        cv_buttons.addStretch()
        cv_layout.addLayout(cv_buttons)

        cv_group.setLayout(cv_layout)
        layout.addWidget(cv_group)

        layout.addStretch()
        self.setLayout(layout)

    def replace_cv(self):
        """Remplace le CV de référence."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Sélectionner le nouveau CV",
            "",
            "Documents (*.pdf *.docx *.txt);;Tous les fichiers (*.*)",
        )
        if file_path:
            # Parse et met à jour
            try:
                from ..utils.parsers import DocumentParser

                parser = DocumentParser()
                content = parser.parse_document(file_path)

                self.profile.master_cv_path = file_path
                self.profile.master_cv_content = content

                show_success("CV mis à jour avec succès", title="Succès", parent=self)
            except Exception as e:
                show_error(
                    f"Erreur lors du traitement:\n{e}", title="Erreur", parent=self
                )

    def edit_cv_content(self):
        """Édite le contenu du CV."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Éditer le contenu du CV")
        dialog.setMinimumSize(600, 400)

        layout = QVBoxLayout()

        text_edit = QTextEdit()
        text_edit.setText(self.profile.master_cv_content or "")
        layout.addWidget(text_edit)

        buttons = QHBoxLayout()
        save_btn = QPushButton("Sauvegarder")
        save_btn.clicked.connect(
            lambda: self.save_cv_content(text_edit.toPlainText(), dialog)
        )
        buttons.addWidget(save_btn)

        cancel_btn = QPushButton("Annuler")
        cancel_btn.clicked.connect(dialog.reject)
        buttons.addWidget(cancel_btn)

        layout.addLayout(buttons)
        dialog.setLayout(layout)
        dialog.exec()

    def save_cv_content(self, content: str, dialog: QDialog):
        """Sauvegarde le contenu du CV."""
        self.profile.master_cv_content = content
        dialog.accept()
        show_success("Contenu du CV mis à jour", title="Succès", parent=self)

    def get_values(self) -> dict:
        """Retourne les valeurs modifiées."""
        return {
            "name": self.name_edit.text(),
            "email": self.email_edit.text(),
            "phone": self.phone_widget.get_full_phone_number() or None,
            "linkedin_url": self.linkedin_edit.text() or None,
        }


class PreferencesTab(QWidget):
    """Tab pour les préférences."""

    def __init__(self, profile: UserProfile):
        super().__init__()
        self.profile = profile
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()

        # Préférences générales
        general_group = QGroupBox("Préférences générales")
        general_layout = QFormLayout()

        self.template_combo = QComboBox()
        self.template_combo.addItems(["modern", "classic", "tech", "creative"])
        self.template_combo.setCurrentText(self.profile.preferred_template)
        general_layout.addRow("Template favori:", self.template_combo)

        self.language_combo = QComboBox()
        self.language_combo.addItems(["fr", "en", "es", "de"])
        self.language_combo.setCurrentText(self.profile.preferred_language)
        general_layout.addRow("Langue:", self.language_combo)

        general_group.setLayout(general_layout)
        layout.addWidget(general_group)

        # Apprentissage
        learning_group = QGroupBox("Apprentissage IA")
        learning_layout = QVBoxLayout()

        self.learning_check = QCheckBox("Apprentissage automatique activé")
        self.learning_check.setChecked(self.profile.learning_enabled)
        learning_layout.addWidget(self.learning_check)

        learning_info = QLabel(
            "L'IA apprendra de vos modifications pour s'améliorer.\n"
            "Les données restent privées et locales."
        )
        learning_info.setWordWrap(True)
        learning_layout.addWidget(learning_info)

        learning_group.setLayout(learning_layout)
        layout.addWidget(learning_group)

        layout.addStretch()
        self.setLayout(layout)

    def get_values(self) -> dict:
        """Retourne les valeurs modifiées."""
        return {
            "preferred_template": self.template_combo.currentText(),
            "preferred_language": self.language_combo.currentText(),
            "learning_enabled": self.learning_check.isChecked(),
        }


class AIModelTab(QWidget):
    """Tab pour la configuration du modèle IA."""

    def __init__(
        self,
        profile: UserProfile,
        *,
        ml_coordinator: "MlWorkflowCoordinator | None" = None,
    ):
        super().__init__()
        self.profile = profile
        self.ml_coordinator = ml_coordinator
        self._updating_memory_limits = False
        self._updating_chunked_generation = False
        self._updating_unload_between_stages = False
        self._updating_subprocess_stages = False
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()

        # Modèle actuel
        current_group = QGroupBox("Modèle IA personnalisé")
        current_layout = QFormLayout()

        current_layout.addRow(
            "Version actuelle:", QLabel(f"{self.profile.model_version.value}")
        )
        current_layout.addRow(
            "CV appris:", QLabel(str(self.profile.total_cvs_validated))
        )
        current_layout.addRow(
            "Note moyenne:", QLabel(f"{self.profile.average_rating:.1f}/5")
        )

        if self.profile.last_fine_tuning:
            last_update = self.profile.last_fine_tuning.strftime("%d/%m/%Y %H:%M")
        else:
            last_update = "Jamais"
        current_layout.addRow("Dernière mise à jour:", QLabel(last_update))

        current_group.setLayout(current_layout)
        layout.addWidget(current_group)

        # Actions
        actions_group = QGroupBox("Actions")
        actions_layout = QVBoxLayout()

        self.force_update_btn = QPushButton("🔄 Forcer mise à jour")
        self.force_update_btn.clicked.connect(self.force_model_update)
        actions_layout.addWidget(self.force_update_btn)

        self.view_stats_btn = QPushButton("📊 Voir statistiques")
        self.view_stats_btn.clicked.connect(self.view_learning_stats)
        actions_layout.addWidget(self.view_stats_btn)

        self.reset_ml_btn = QPushButton("🔁 Réinitialiser les paramètres ML")
        self.reset_ml_btn.clicked.connect(self.reset_ml_settings)
        actions_layout.addWidget(self.reset_ml_btn)

        actions_group.setLayout(actions_layout)
        layout.addWidget(actions_group)

        # Configuration technique avancée
        tech_group = QGroupBox("🔧 Configuration technique")
        tech_layout = QVBoxLayout()

        # Section modèle principal
        model_section = QGroupBox("Modèle IA")
        model_layout = QFormLayout()

        # Sélecteur de modèle principal (synchronisé avec le compact)
        self.model_selector_combo = QComboBox()
        self.model_selector_combo.currentTextChanged.connect(self.on_model_changed)
        model_layout.addRow("🤖 Modèle:", self.model_selector_combo)
        self.auto_follow_check = QCheckBox("Auto (registre recommande)")
        self.auto_follow_check.stateChanged.connect(self.on_auto_follow_changed)
        model_layout.addRow("", self.auto_follow_check)

        # Informations sur le modèle sélectionné
        self.model_info_label = QLabel()
        self.model_info_label.setWordWrap(True)
        self.model_info_label.setStyleSheet(
            "color: #666; font-size: 11px; padding: 5px;"
        )
        model_layout.addRow("", self.model_info_label)

        model_section.setLayout(model_layout)
        tech_layout.addWidget(model_section)

        # Section quantification
        quant_section = QGroupBox("Quantification")
        quant_layout = QFormLayout()

        self.quantization_combo = QComboBox()
        self.quantization_combo.addItems(
            [
                "Auto (Recommandé)",
                "GPTQ (4-bit)",
                "AWQ (4-bit)",
                "Q4 (Compatible)",
                "Q8 (Qualité)",
                "FP16 (Maximum)",
            ]
        )
        self.quantization_combo.currentTextChanged.connect(self.on_quantization_changed)
        quant_layout.addRow("🔢 Type:", self.quantization_combo)

        quant_info = QLabel(
            "GPTQ/AWQ: Meilleur compromis qualité/vitesse\nQ4/Q8: Compatibilité étendue\nFP16: Qualité maximale (VRAM++)"
        )
        quant_info.setStyleSheet("color: #666; font-size: 10px;")
        quant_info.setWordWrap(True)
        quant_layout.addRow("", quant_info)

        quant_section.setLayout(quant_layout)
        tech_layout.addWidget(quant_section)

        # Section optimisations
        opt_section = QGroupBox("Optimisations")
        opt_layout = QVBoxLayout()

        self.flash_attention_check = QCheckBox("⚡ Flash-Attention (Linux uniquement)")
        self.flash_attention_check.stateChanged.connect(self.on_optimization_changed)
        opt_layout.addWidget(self.flash_attention_check)

        self.vllm_check = QCheckBox("🚀 vLLM (Inférence ultra-rapide)")
        self.vllm_check.stateChanged.connect(self.on_optimization_changed)
        opt_layout.addWidget(self.vllm_check)

        self.xformers_check = QCheckBox("💾 xFormers (Optimisations mémoire)")
        self.xformers_check.stateChanged.connect(self.on_optimization_changed)
        opt_layout.addWidget(self.xformers_check)

        self.auto_gptq_check = QCheckBox("🔧 Auto-GPTQ (Quantification avancée)")
        self.auto_gptq_check.stateChanged.connect(self.on_optimization_changed)
        opt_layout.addWidget(self.auto_gptq_check)

        # Informations sur les optimisations
        opt_info = QLabel(
            "💡 Optimisations détectées automatiquement selon votre hardware"
        )
        opt_info.setStyleSheet("color: #0078d4; font-size: 10px; font-style: italic;")
        opt_layout.addWidget(opt_info)

        opt_section.setLayout(opt_layout)
        tech_layout.addWidget(opt_section)

        # Section allocation memoire (max_memory)
        memory_section = QGroupBox("Allocation memoire (max_memory)")
        memory_layout = QFormLayout()

        self.max_memory_gpu_spin = QSpinBox()
        self.max_memory_gpu_spin.setRange(10, 99)
        self.max_memory_gpu_spin.setSuffix("%")
        self.max_memory_gpu_spin.valueChanged.connect(self.on_memory_limits_changed)
        memory_layout.addRow("GPU (VRAM):", self.max_memory_gpu_spin)

        self.max_memory_cpu_spin = QSpinBox()
        self.max_memory_cpu_spin.setRange(10, 99)
        self.max_memory_cpu_spin.setSuffix("%")
        self.max_memory_cpu_spin.valueChanged.connect(self.on_memory_limits_changed)
        memory_layout.addRow("CPU (RAM):", self.max_memory_cpu_spin)

        memory_hint = QLabel(
            "Augmenter utilise plus de memoire (risque d'OOM). "
            "Baisser augmente l'offload CPU et peut ralentir."
        )
        memory_hint.setStyleSheet("color: #666; font-size: 10px;")
        memory_hint.setWordWrap(True)
        memory_layout.addRow("", memory_hint)

        memory_buttons = QHBoxLayout()
        self.reset_memory_btn = QPushButton("Reinitialiser (90%/80%)")
        self.reset_memory_btn.clicked.connect(self.reset_memory_limits)
        memory_buttons.addWidget(self.reset_memory_btn)
        memory_buttons.addStretch()
        memory_layout.addRow("", memory_buttons)

        memory_section.setLayout(memory_layout)
        tech_layout.addWidget(memory_section)

        # Section generation (VRAM)
        gen_section = QGroupBox("Generation (VRAM)")
        gen_layout = QVBoxLayout()

        self.chunked_generation_group = QButtonGroup(self)
        self.chunked_generation_auto = QRadioButton("Auto (recommande)")
        self.chunked_generation_on = QRadioButton("Force ON")
        self.chunked_generation_off = QRadioButton("Force OFF")

        self.chunked_generation_group.addButton(self.chunked_generation_auto)
        self.chunked_generation_group.addButton(self.chunked_generation_on)
        self.chunked_generation_group.addButton(self.chunked_generation_off)

        self.chunked_generation_auto.setChecked(True)

        self.chunked_generation_auto.toggled.connect(self.on_chunked_generation_changed)
        self.chunked_generation_on.toggled.connect(self.on_chunked_generation_changed)
        self.chunked_generation_off.toggled.connect(self.on_chunked_generation_changed)

        gen_layout.addWidget(self.chunked_generation_auto)
        gen_layout.addWidget(self.chunked_generation_on)
        gen_layout.addWidget(self.chunked_generation_off)

        self.unload_between_stages_check = QCheckBox(
            "Decharger le modele entre les etapes (draft/critic/final)"
        )
        self.unload_between_stages_check.stateChanged.connect(
            self.on_unload_between_stages_changed
        )
        gen_layout.addWidget(self.unload_between_stages_check)

        self.subprocess_stages_check = QCheckBox(
            "Isoler les etapes dans un sous-processus (libere VRAM)"
        )
        self.subprocess_stages_check.stateChanged.connect(
            self.on_subprocess_stages_changed
        )
        gen_layout.addWidget(self.subprocess_stages_check)

        gen_hint = QLabel(
            "Auto = selon VRAM libre. "
            "Force ON = mode fragmente actif. "
            "Force OFF = mode fragmente desactive."
        )
        gen_hint.setStyleSheet("color: #666; font-size: 10px;")
        gen_hint.setWordWrap(True)
        gen_layout.addWidget(gen_hint)

        gen_section.setLayout(gen_layout)
        tech_layout.addWidget(gen_section)

        # Section cache et maintenance
        cache_section = QGroupBox("Cache et maintenance")
        cache_layout = QFormLayout()

        self.cache_info_label = QLabel()
        self.cache_info_label.setStyleSheet("font-family: monospace; color: #666;")
        cache_layout.addRow("📁 Emplacement:", self.cache_info_label)

        cache_buttons = QHBoxLayout()
        self.clean_cache_btn = QPushButton("🗑️ Nettoyer cache")
        self.clean_cache_btn.clicked.connect(self.clean_cache)
        cache_buttons.addWidget(self.clean_cache_btn)

        self.open_folder_btn = QPushButton("📁 Ouvrir dossier")
        self.open_folder_btn.clicked.connect(self.open_cache_folder)
        cache_buttons.addWidget(self.open_folder_btn)

        self.refresh_cache_btn = QPushButton("🔄 Actualiser")
        self.refresh_cache_btn.clicked.connect(self.refresh_cache_info)
        cache_buttons.addWidget(self.refresh_cache_btn)

        cache_buttons.addStretch()
        cache_layout.addRow("", cache_buttons)

        cache_section.setLayout(cache_layout)
        tech_layout.addWidget(cache_section)

        tech_group.setLayout(tech_layout)
        layout.addWidget(tech_group)

        # Initialiser l'affichage
        self.init_technical_config()

        layout.addStretch()
        self.setLayout(layout)

    def force_model_update(self):
        """Force la mise à jour du modèle."""
        reply = QMessageBox.question(
            self,
            "Confirmer",
            "Forcer la mise à jour du modèle IA ?\nCela peut prendre plusieurs minutes.",
            QMessageBox.Yes | QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            # TODO: Implémenter le fine-tuning forcé
            QMessageBox.information(
                self, "Info", "Mise à jour du modèle démarrée (à implémenter)"
            )

    def view_learning_stats(self):
        """Affiche les statistiques d'apprentissage."""
        # TODO: Implémenter la vue des stats
        QMessageBox.information(
            self, "Stats", "Statistiques d'apprentissage (à implémenter)"
        )

    def reset_ml_settings(self):
        """Réinitialise uniquement les réglages ML."""
        if self.ml_coordinator is None:
            show_warning(
                "Service ML indisponible pour le moment.",
                title="Réinitialisation ML",
                parent=self,
            )
            return

        success, message = self.ml_coordinator.reset_settings()
        if success:
            show_success("Paramètres ML réinitialisés.", title="Succès", parent=self)
        else:
            show_warning(
                message or "Impossible de réinitialiser les paramètres ML.",
                title="Réinitialisation ML",
                parent=self,
            )

    def clean_cache(self):
        """Nettoie le cache des modèles."""
        reply = QMessageBox.question(
            self,
            "Confirmer",
            "Nettoyer le cache des modèles ?\nLes modèles seront retéléchargés au besoin.",
            QMessageBox.Yes | QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            # TODO: Implémenter le nettoyage
            QMessageBox.information(self, "Info", "Cache nettoyé (à implémenter)")

    def open_cache_folder(self):
        """Ouvre le dossier de cache."""
        import subprocess
        import sys

        cache_path = Path.home() / ".cache" / "cvmatch"

        try:
            if sys.platform == "win32":
                subprocess.run(["explorer", str(cache_path)])
            elif sys.platform == "darwin":
                subprocess.run(["open", str(cache_path)])
            else:
                subprocess.run(["xdg-open", str(cache_path)])
        except Exception as e:
            QMessageBox.warning(self, "Erreur", f"Impossible d'ouvrir le dossier:\n{e}")

    def init_technical_config(self):
        """Initialise la configuration technique."""
        try:
            from ..utils.model_config_manager import model_config_manager
            from ..utils.model_manager import model_manager

            # Charger la configuration actuelle
            config = model_config_manager.get_current_config()

            # Remplir le sélecteur de modèles
            self.model_selector_combo.blockSignals(True)
            self.model_selector_combo.clear()

            models = model_manager.get_models_for_dropdown()
            current_index = 0

            for i, model_data in enumerate(models):
                # Ajouter l'item avec tooltip détaillé
                self.model_selector_combo.addItem(model_data["text"], model_data["id"])

                # Définir la couleur selon le statut
                if model_data["model_status"] == "recommended":
                    # Vert pour recommandé
                    self.model_selector_combo.setItemData(
                        i,
                        "QComboBox::item { color: #2d5f3f; font-weight: bold; }",
                        Qt.ForegroundRole,
                    )
                elif model_data["model_status"] == "gpu_required":
                    # Rouge pour incompatible
                    self.model_selector_combo.setItemData(
                        i, "QComboBox::item { color: #8b4513; }", Qt.ForegroundRole
                    )
                elif model_data["model_status"] == "cpu_fallback":
                    # Bleu pour CPU
                    self.model_selector_combo.setItemData(
                        i, "QComboBox::item { color: #1e3a8a; }", Qt.ForegroundRole
                    )

                # Ajouter tooltip avec infos détaillées
                if i == 0:  # Seulement pour le premier pour éviter les bugs
                    self.model_selector_combo.setToolTip(
                        model_data.get("detailed_info", model_data["description"])
                    )

                if model_data["id"] == config.model_id:
                    current_index = i

            self.model_selector_combo.setCurrentIndex(current_index)
            self.model_selector_combo.blockSignals(False)

            self.auto_follow_check.blockSignals(True)
            self.auto_follow_check.setChecked(config.use_registry_auto)
            self.auto_follow_check.blockSignals(False)
            self.model_selector_combo.setEnabled(not config.use_registry_auto)

            # Mettre à jour les informations du modèle
            self.update_model_info()

            # Configuration quantification
            quant_mapping = {
                "auto": 0,
                "gptq": 1,
                "awq": 2,
                "q4": 3,
                "q8": 4,
                "fp16": 5,
            }
            quant_index = quant_mapping.get(config.quantization.value.lower(), 0)
            self.quantization_combo.setCurrentIndex(quant_index)

            # Configuration optimisations
            self.flash_attention_check.setChecked(config.use_flash_attention)
            self.vllm_check.setChecked(config.use_vllm)
            self.xformers_check.setChecked(config.use_xformers)
            self.auto_gptq_check.setChecked(config.use_auto_gptq)

            # Allocation memoire
            custom = config.custom_parameters or {}
            gpu_percent = custom.get("max_memory_gpu_percent", 90)
            cpu_percent = custom.get("max_memory_cpu_percent", 80)
            self._set_memory_limits(gpu_percent, cpu_percent)
            self._set_chunked_generation(custom.get("chunked_generation"))
            self._set_unload_between_stages(custom.get("unload_between_stages"))
            self._set_subprocess_stages(custom.get("subprocess_stages"))

            # Désactiver les optimisations non disponibles sur Windows
            import platform

            if platform.system() == "Windows":
                self.flash_attention_check.setEnabled(False)
                self.flash_attention_check.setToolTip("Non disponible sur Windows")
                self.vllm_check.setEnabled(False)
                self.vllm_check.setToolTip("Non disponible sur Windows")

            # Informations cache
            self.refresh_cache_info()

            # Observer pour synchronisation
            model_config_manager.add_observer(self.on_config_changed)

        except ImportError as e:
            logger.warning(f"Configuration technique non disponible: {e}")

    def _set_memory_limits(self, gpu_percent: int, cpu_percent: int) -> None:
        """Met a jour les controles max_memory sans declencher de sauvegarde."""
        self._updating_memory_limits = True
        try:
            self.max_memory_gpu_spin.setValue(int(gpu_percent))
            self.max_memory_cpu_spin.setValue(int(cpu_percent))
        finally:
            self._updating_memory_limits = False

    def _set_chunked_generation(self, value) -> None:
        """Met a jour le controle de generation fragmente sans sauvegarde."""
        self._updating_chunked_generation = True
        try:
            if value is None:
                self.chunked_generation_auto.setChecked(True)
            elif value:
                self.chunked_generation_on.setChecked(True)
            else:
                self.chunked_generation_off.setChecked(True)
        finally:
            self._updating_chunked_generation = False

    def _set_unload_between_stages(self, value) -> None:
        """Met a jour le controle unload entre etapes sans sauvegarde."""
        self._updating_unload_between_stages = True
        try:
            self.unload_between_stages_check.setChecked(bool(value))
        finally:
            self._updating_unload_between_stages = False

    def _set_subprocess_stages(self, value) -> None:
        """Met a jour le controle subprocess stages sans sauvegarde."""
        self._updating_subprocess_stages = True
        try:
            self.subprocess_stages_check.setChecked(bool(value))
        finally:
            self._updating_subprocess_stages = False

    def on_memory_limits_changed(self) -> None:
        """Sauvegarde les allocations max_memory configurees."""
        if self._updating_memory_limits:
            return
        try:
            from ..utils.model_config_manager import model_config_manager

            gpu_percent = int(self.max_memory_gpu_spin.value())
            cpu_percent = int(self.max_memory_cpu_spin.value())
            model_config_manager.update_custom_parameters(
                {
                    "max_memory_gpu_percent": gpu_percent,
                    "max_memory_cpu_percent": cpu_percent,
                }
            )
        except Exception as e:
            logger.error(f"Erreur mise a jour max_memory: {e}")

    def on_chunked_generation_changed(self, _state=None) -> None:
        """Sauvegarde le mode de generation fragmente."""
        if self._updating_chunked_generation:
            return
        try:
            from ..utils.model_config_manager import model_config_manager
            if self.chunked_generation_auto.isChecked():
                value = None
            elif self.chunked_generation_on.isChecked():
                value = True
            else:
                value = False
            model_config_manager.update_custom_parameters(
                {"chunked_generation": value}
            )
        except Exception as e:
            logger.error(f"Erreur mise a jour generation fragmente: {e}")

    def on_unload_between_stages_changed(self, _state=None) -> None:
        """Sauvegarde l'option dechargement entre etapes."""
        if self._updating_unload_between_stages:
            return
        try:
            from ..utils.model_config_manager import model_config_manager

            value = bool(self.unload_between_stages_check.isChecked())
            model_config_manager.update_custom_parameters(
                {"unload_between_stages": value}
            )
        except Exception as e:
            logger.error(f"Erreur mise a jour unload entre etapes: {e}")

    def on_subprocess_stages_changed(self, _state=None) -> None:
        """Sauvegarde l'option subprocess stages."""
        if self._updating_subprocess_stages:
            return
        try:
            from ..utils.model_config_manager import model_config_manager

            value = bool(self.subprocess_stages_check.isChecked())
            model_config_manager.update_custom_parameters(
                {"subprocess_stages": value}
            )
        except Exception as e:
            logger.error(f"Erreur mise a jour subprocess stages: {e}")

    def reset_memory_limits(self) -> None:
        """Reinitialise les valeurs max_memory par defaut."""
        default_gpu = 90
        default_cpu = 80
        self._set_memory_limits(default_gpu, default_cpu)
        try:
            from ..utils.model_config_manager import model_config_manager

            model_config_manager.update_custom_parameters(
                {
                    "max_memory_gpu_percent": default_gpu,
                    "max_memory_cpu_percent": default_cpu,
                }
            )
        except Exception as e:
            logger.error(f"Erreur reinitialisation max_memory: {e}")

    def update_model_info(self):
        """Met à jour les informations du modèle sélectionné."""
        try:
            from ..utils.model_manager import model_manager

            model_id = self.model_selector_combo.currentData()
            if not model_id:
                return

            model_info = model_manager.get_model_display_info(model_id)
            if model_info:
                # Statut avec icône
                status_icons = {
                    "recommended": "🏆",
                    "available": "✅",
                    "gpu_required": "🔒",
                    "cpu_fallback": "💻",
                    "incompatible": "❌",
                }

                status_icon = status_icons.get(model_info["model_status"], "❓")
                status_text = model_manager._get_status_text(model_info["model_status"])

                # VRAM info selon le mode
                if model_info["vram_required"] > 0:
                    vram_text = f"💾 VRAM requise: {model_info['vram_required']:.1f} GB"
                else:
                    vram_text = "💻 Mode CPU - Pas de VRAM requise"

                # Qualité adaptée au hardware
                quality_stars = "★" * model_info["quality_stars"] + "☆" * (
                    5 - model_info["quality_stars"]
                )
                speed_rating = "⚡" * model_info["speed_rating"] + "⚪" * (
                    3 - model_info["speed_rating"]
                )
                loader = model_info.get("loader", "transformers")
                quant_hint = model_info.get("quantization", "auto")
                tag_text = ", ".join(model_info.get("tags", []))
                # Temps avec couleur selon la rapidite
                time_color = (
                    "#2d5f3f"
                    if model_info["estimated_time"] <= 5
                    else "#b45309" if model_info["estimated_time"] <= 10 else "#dc2626"
                )

                info_text = f"""
                <b>{model_info['display_name']}</b><br>
                {status_icon} <b>Statut:</b> {status_text}<br>
                {vram_text}<br>
                📊 <b>Score performance:</b> {model_info['performance_score']}/10<br>
                🌟 <b>Qualite:</b> {quality_stars} ({model_info['quality_stars']}/5)<br>
                ⚡ <b>Vitesse:</b> {speed_rating} ({model_info['speed_rating']}/3)<br>
                🧩 <b>Backend:</b> {loader}<br>
                🎯 <b>Quantification suggeree:</b> {quant_hint}<br>
                🆔 <b>Profil:</b> {model_id}<br>
                <span style="color: {time_color}">⏱️ <b>Temps estime:</b> ~{model_info['estimated_time']} minutes</span><br>
                <br>
                <i>{model_info['description']}</i>
                """.strip()
                if tag_text:
                    info_text += f"<br><br>🔖 <b>Tags:</b> {tag_text}"

                # Ajouter des conseils selon le statut
                if model_info["model_status"] == "recommended":
                    info_text += "<br><br>💡 <b style='color: #2d5f3f'>RECOMMANDÉ pour votre configuration</b>"
                elif model_info["model_status"] == "gpu_required":
                    info_text += "<br><br>⚠️ <b style='color: #dc2626'>Nécessite CUDA/GPU pour fonctionner</b>"
                elif model_info["model_status"] == "cpu_fallback":
                    info_text += "<br><br>💻 <b style='color: #1e3a8a'>Fonctionne en mode CPU</b>"

                self.model_info_label.setText(info_text)

        except Exception as e:
            logger.error(f"Erreur mise à jour info modèle: {e}")

    def on_model_changed(self):
        """Gère le changement de modèle."""
        try:
            from ..utils.model_config_manager import model_config_manager

            model_id = self.model_selector_combo.currentData()
            if model_id:
                self.auto_follow_check.blockSignals(True)
                self.auto_follow_check.setChecked(False)
                self.auto_follow_check.blockSignals(False)
                self.model_selector_combo.setEnabled(True)
                model_config_manager.update_model(model_id)
                self.update_model_info()

        except Exception as e:
            logger.error(f"Erreur changement modèle: {e}")

    def on_auto_follow_changed(self, state):
        """Active ou desactive le suivi auto du registre."""
        try:
            from PySide6.QtCore import Qt

            from ..utils.model_config_manager import model_config_manager

            enabled = state == Qt.Checked
            if model_config_manager.set_auto_mode(enabled):
                self.model_selector_combo.setEnabled(not enabled)
                config = model_config_manager.get_current_config()
                if enabled:
                    self.model_selector_combo.blockSignals(True)
                    idx = self.model_selector_combo.findData(config.model_id)
                    if idx >= 0:
                        self.model_selector_combo.setCurrentIndex(idx)
                    self.model_selector_combo.blockSignals(False)
                self.update_model_info()

        except Exception as e:
            logger.error(f"Erreur changement mode auto: {e}")

    def on_quantization_changed(self):
        """Gère le changement de quantification."""
        try:
            from ..utils.model_config_manager import (
                QuantizationType,
                model_config_manager,
            )

            index = self.quantization_combo.currentIndex()
            quant_types = [
                QuantizationType.AUTO,
                QuantizationType.GPTQ,
                QuantizationType.AWQ,
                QuantizationType.Q4,
                QuantizationType.Q8,
                QuantizationType.FP16,
            ]

            if 0 <= index < len(quant_types):
                model_config_manager.update_quantization(quant_types[index])

        except Exception as e:
            logger.error(f"Erreur changement quantification: {e}")

    def on_optimization_changed(self):
        """Gère le changement d'optimisations."""
        try:
            from ..utils.model_config_manager import (
                OptimizationType,
                model_config_manager,
            )

            optimizations = []

            if self.flash_attention_check.isChecked():
                optimizations.append(OptimizationType.FLASH_ATTENTION)
            if self.vllm_check.isChecked():
                optimizations.append(OptimizationType.VLLM)
            if self.xformers_check.isChecked():
                optimizations.append(OptimizationType.XFORMERS)
            if self.auto_gptq_check.isChecked():
                optimizations.append(OptimizationType.AUTO_GPTQ)

            model_config_manager.update_optimizations(optimizations)

        except Exception as e:
            logger.error(f"Erreur changement optimisations: {e}")

    def refresh_cache_info(self):
        """Actualise les informations du cache."""
        try:
            from ..utils.model_config_manager import model_config_manager

            cache_info = model_config_manager.get_model_cache_info()

            if cache_info["exists"]:
                size_gb = cache_info["size_mb"] / 1024
                info_text = f"{cache_info['path']}\n({size_gb:.1f} GB, {cache_info['model_count']} fichiers)"
            else:
                info_text = f"{cache_info['path']}\n(Vide)"

            self.cache_info_label.setText(info_text)

        except Exception as e:
            logger.error(f"Erreur info cache: {e}")
            self.cache_info_label.setText("Erreur lecture cache")

    def on_config_changed(self, event_type: str, *args):
        """Callback pour les changements de configuration (synchronisation)."""
        if event_type == "model_changed":
            # Mettre à jour l'interface sans déclencher d'événements
            self.model_selector_combo.blockSignals(True)
            for i in range(self.model_selector_combo.count()):
                if self.model_selector_combo.itemData(i) == args[1]:  # nouveau modèle
                    self.model_selector_combo.setCurrentIndex(i)
                    break
            self.model_selector_combo.blockSignals(False)
            self.update_model_info()

        elif event_type == "cache_cleared":
            self.refresh_cache_info()
        elif event_type == "custom_parameters_changed":
            try:
                from ..utils.model_config_manager import model_config_manager

                config = model_config_manager.get_current_config()
                custom = config.custom_parameters or {}
                gpu_percent = custom.get("max_memory_gpu_percent", 90)
                cpu_percent = custom.get("max_memory_cpu_percent", 80)
                self._set_memory_limits(gpu_percent, cpu_percent)
                self._set_chunked_generation(custom.get("chunked_generation"))
                self._set_unload_between_stages(custom.get("unload_between_stages"))
                self._set_subprocess_stages(custom.get("subprocess_stages"))
            except Exception as e:
                logger.warning(f"Erreur synchro max_memory: {e}")


class SettingsDialog(QDialog):
    """Dialog de paramètres principal."""

    def __init__(
        self,
        profile: UserProfile,
        parent=None,
        ml_coordinator: "MlWorkflowCoordinator | None" = None,
    ):
        super().__init__(parent)
        self.profile = profile
        self.ml_coordinator = ml_coordinator
        self.setup_ui()

    def setup_ui(self):
        self.setWindowTitle("Paramètres CVMatch")
        self.setMinimumSize(800, 600)
        self.resize(900, 700)

        layout = QVBoxLayout()

        # Tabs
        self.tabs = QTabWidget()

        self.profile_tab = ProfileTab(self.profile)
        self.tabs.addTab(self.profile_tab, "📑 Profil")

        self.preferences_tab = PreferencesTab(self.profile)
        self.tabs.addTab(self.preferences_tab, "🎨 Préférences")

        # Enrober l'onglet IA dans un scroll area
        ai_scroll = QScrollArea()
        ai_scroll.setWidgetResizable(True)
        ai_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        ai_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        self.ai_tab = AIModelTab(self.profile, ml_coordinator=self.ml_coordinator)
        ai_scroll.setWidget(self.ai_tab)

        self.tabs.addTab(ai_scroll, "🤖 Modèle IA")

        layout.addWidget(self.tabs)

        # Maintenance
        maintenance_group = QGroupBox("Maintenance & réinitialisation")
        maintenance_layout = QVBoxLayout()
        maintenance_label = QLabel(
            "Réinitialiser l'application supprime toutes les données locales (profils, "
            "modèles personnalisés, caches, journaux) afin de repartir comme lors du "
            "premier lancement."
        )
        maintenance_label.setWordWrap(True)
        maintenance_layout.addWidget(maintenance_label)

        self.reset_btn = QPushButton("🔄 Réinitialiser l'application")
        self.reset_btn.clicked.connect(self.reset_profile)
        maintenance_layout.addWidget(self.reset_btn)

        maintenance_group.setLayout(maintenance_layout)
        layout.addWidget(maintenance_group)

        # Boutons
        buttons_layout = QHBoxLayout()

        self.save_btn = QPushButton("💾 Sauvegarder")
        self.save_btn.clicked.connect(self.save_settings)
        buttons_layout.addWidget(self.save_btn)

        buttons_layout.addStretch()

        self.cancel_btn = QPushButton("Annuler")
        self.cancel_btn.clicked.connect(self.reject)
        buttons_layout.addWidget(self.cancel_btn)

        layout.addLayout(buttons_layout)
        self.setLayout(layout)

    def showEvent(self, event):
        """Override pour forcer le redimensionnement correct à l'affichage."""
        super().showEvent(event)
        # Forcer le recalcul de la taille après l'affichage
        self.adjustSize()

    def save_settings(self):
        """Sauvegarde les paramètres."""
        try:
            # Récupérer les valeurs de tous les tabs
            profile_values = self.profile_tab.get_values()
            preferences_values = self.preferences_tab.get_values()

            # Sauvegarder en base
            profile_id = None
            try:
                from sqlalchemy import inspect as sa_inspect

                state = sa_inspect(self.profile)
                if state.identity:
                    profile_id = state.identity[0]
            except Exception:
                profile_id = getattr(self.profile, "id", None)

            with get_session() as session:
                db_profile = session.get(UserProfile, profile_id) if profile_id else None
                if db_profile is None:
                    logger.warning(
                        "Profil introuvable en base, creation d'un nouveau profil."
                    )
                    db_profile = UserProfile(
                        **{**profile_values, **preferences_values}
                    )
                    session.add(db_profile)
                else:
                    for key, value in profile_values.items():
                        setattr(db_profile, key, value)
                    for key, value in preferences_values.items():
                        setattr(db_profile, key, value)
                session.commit()
                try:
                    session.refresh(db_profile)
                except Exception:
                    pass
                profile_id = db_profile.id

            # Mettre à jour le profil local
            for key, value in profile_values.items():
                setattr(self.profile, key, value)

            for key, value in preferences_values.items():
                setattr(self.profile, key, value)
            if getattr(self.profile, "id", None) is None and profile_id is not None:
                self.profile.id = profile_id

            logger.info("Paramètres sauvegardés pour profile_id=%s", profile_id)
            show_success(
                "Paramètres sauvegardés avec succès", title="Succès", parent=self
            )
            self.accept()

        except Exception as e:
            logger.error(f"Erreur sauvegarde paramètres : {e}")
            show_error(
                f"Erreur lors de la sauvegarde:\n{e}", title="Erreur", parent=self
            )

    def reset_profile(self):
        """Réinitialise le profil."""
        reply = QMessageBox.question(
            self,
            "Confirmer réinitialisation",
            "Réinitialiser complètement le profil ?\n"
            "ATTENTION: Toutes les données et l'apprentissage seront perdus !\n\n"
            "Cela supprimera:\n"
            "• Base de données (profils, candidatures)\n"
            "• Modèles IA personnalisés\n"
            "• Fichiers temporaires et logs\n"
            "• Configuration utilisateur",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            try:
                import shutil
                import time

                from ..models.database import DATABASE_PATH, reset_database

                logger.info("🧹 RESET: Début de réinitialisation complète")

                # 📍 Initialiser les répertoires critiques
                project_root = Path(__file__).parent.parent.parent
                cvmatch_dir = Path.home() / ".cvmatch"
                deferred_paths = [str(DATABASE_PATH)]
                logger.info(f"🧹 RESET: Répertoire projet = {project_root}")
                logger.info(f"🧹 RESET: Répertoire utilisateur = {cvmatch_dir}")

                # 1. Réinitialiser la base de données principale
                logger.info("🧹 RESET: Étape 1 - Reset base de données...")
                reset_database()
                logger.info("✅ RESET: Base de données principale réinitialisée")

                # 2. Attendre que les verrous se libèrent complètement
                time.sleep(1.0)

                # Dossiers de données à vider complètement (garder .gitkeep)
                # ATTENTION: NE PAS inclure cvmatch_env (environnement virtuel à préserver)
                data_folders = [
                    project_root / "logs",
                    project_root / "exports",
                    project_root / "CV",
                    project_root / "reports",
                    project_root / "cache",
                    project_root / ".hf_cache",
                    project_root / "models",
                    project_root / "data",
                    project_root / "datasets" / "user_learning",
                    project_root / "datasets" / "training_ready",
                    project_root / "archive",
                    project_root / "dev_tools" / "debug",
                    # Dossiers supplémentaires pouvant contenir des PII
                    project_root / ".debug",  # Fichiers de debug/smoke tests
                    project_root / "output",  # Fichiers de sortie générés
                    # Dossiers créés dynamiquement (nouvelle organisation)
                    project_root / "runtime" / "processing",
                    project_root / "runtime" / "temp_uploads",
                    project_root / "runtime" / "parsed_documents",
                    project_root / "runtime" / "extracted_text",
                    project_root / "runtime" / "checkpoints",
                    project_root / "runtime" / "training_logs",
                    project_root / "runtime" / "model_outputs",
                    # NE PAS supprimer: cvmatch_env/ (environnement virtuel)
                ]

                # Fichiers temporaires et BDD à supprimer (SANS les fichiers de lancement)
                temp_files = [
                    project_root / "cvmatch.db",
                    project_root / "data" / "cvmatch.db",
                    project_root / "test_basic.py",
                    project_root / "test_simple.py",
                    project_root / "test_extraction_logging.py",
                    project_root / "main_fallback.py",
                    project_root / "reset_operations.log",
                    project_root / "reset_history.json",
                    project_root / "reset_cleanup.log",
                    # NE PAS supprimer : CVMatch.bat, CVMatch.sh, cvmatch.sh (fichiers de lancement)
                ]

                # Supprimer tous les fichiers temporaires et BDD
                logger.info("🧹 RESET: Étape 2 - Suppression fichiers temporaires...")
                files_deleted = 0
                files_failed = 0

                for file_path in temp_files:
                    if file_path.exists():
                        try:
                            file_path.unlink()
                            files_deleted += 1
                            logger.info(f"🗑️ RESET: Fichier supprimé: {file_path}")
                        except Exception as e:
                            files_failed += 1
                            logger.warning(
                                f"⚠️ RESET: Impossible de supprimer {file_path}: {e}"
                            )
                    else:
                        logger.info(f"ℹ️ RESET: Fichier déjà absent: {file_path}")

                logger.info(
                    f"📊 RESET: Fichiers - Supprimés: {files_deleted}, Échecs: {files_failed}"
                )

                # Vider les dossiers de données (garder structure + .gitkeep)
                logger.info("🧹 RESET: Étape 3 - Nettoyage dossiers de données...")
                folders_processed = 0
                folders_protected = 0
                folders_cleaned = 0
                items_deleted = 0
                items_protected = 0

                for folder in data_folders:
                    folders_processed += 1
                    if folder.exists() and folder.is_dir():
                        # PROTECTION: Ne jamais toucher à l'environnement virtuel
                        if folder.name in ["cvmatch_env", "venv", ".venv"]:
                            folders_protected += 1
                            logger.info(
                                f"🔒 RESET: PROTECTION - Environnement virtuel préservé: {folder}"
                            )
                            continue

                        logger.info(f"🧹 RESET: Nettoyage dossier: {folder}")
                        try:
                            folder_items_deleted = 0
                            folder_items_protected = 0

                            for item in folder.iterdir():
                                # Garder les .gitkeep et README.md
                                if item.name in [".gitkeep", "README.md"]:
                                    folder_items_protected += 1
                                    logger.info(f"  🔒 RESET: Protégé: {item.name}")
                                    continue
                                try:
                                    if item.is_file():
                                        item.unlink()
                                        folder_items_deleted += 1
                                        logger.info(
                                            f"  🗑️ RESET: Fichier supprimé: {item.name}"
                                        )
                                    elif item.is_dir():
                                        shutil.rmtree(item)
                                        folder_items_deleted += 1
                                        logger.info(
                                            f"  🗂️ RESET: Dossier supprimé: {item.name}/"
                                        )
                                except Exception as e:
                                    logger.warning(
                                        f"  ⚠️ RESET: Erreur {item.name}: {e}"
                                    )

                            items_deleted += folder_items_deleted
                            items_protected += folder_items_protected
                            folders_cleaned += 1
                            logger.info(
                                f"  📊 RESET: Dossier {folder.name} - Supprimés: {folder_items_deleted}, Protégés: {folder_items_protected}"
                            )

                        except Exception as e:
                            logger.warning(f"⚠️ RESET: Erreur dossier {folder}: {e}")
                    else:
                        logger.info(f"ℹ️ RESET: Dossier absent: {folder}")

                logger.info(
                    f"📊 RESET: Résumé dossiers - Traités: {folders_processed}, Nettoyés: {folders_cleaned}, Protégés: {folders_protected}"
                )
                logger.info(
                    f"📊 RESET: Résumé éléments - Supprimés: {items_deleted}, Protégés: {items_protected}"
                )

                # Supprimer le dossier utilisateur .cvmatch
                logger.info("🧹 RESET: Étape 4 - Nettoyage dossier utilisateur...")
                cvmatch_files_deleted = 0
                cvmatch_dirs_deleted = 0
                cvmatch_items_protected = 0

                if cvmatch_dir.exists():
                    logger.info(f"🧹 RESET: Nettoyage complet de {cvmatch_dir}")

                    # Supprimer le contenu complet du dossier utilisateur (logs inclus)
                    for item in cvmatch_dir.iterdir():
                        try:
                            if item.is_file():
                                if item.name == DATABASE_PATH.name:
                                    logger.info(
                                        "RESET: Base de donnees active conservee: %s",
                                        item.name,
                                    )
                                    cvmatch_items_protected += 1
                                    continue
                                # 🔄 Retry logic for locked files (Windows-specific)
                                max_retries = 3
                                retry_delay = 0.5
                                deleted = False

                                for attempt in range(max_retries):
                                    try:
                                        item.unlink()
                                        cvmatch_files_deleted += 1
                                        logger.info(
                                            f"🗑️ RESET: Fichier utilisateur supprimé: {item.name}"
                                        )
                                        deleted = True
                                        break
                                    except PermissionError as perm_err:
                                        if attempt < max_retries - 1:
                                            logger.debug(
                                                f"⏳ RESET: Tentative {attempt + 1}/{max_retries} suppression {item.name} après délai..."
                                            )
                                            time.sleep(retry_delay)
                                        else:
                                            # Dernier essai échoué - renommer au lieu de supprimer
                                            try:
                                                backup_name = (
                                                    item.parent
                                                    / f"{item.name}.locked_reset_{time.time_ns() % 1000000}"
                                                )
                                                item.rename(backup_name)
                                                cvmatch_files_deleted += 1
                                                logger.warning(
                                                    f"⚠️ RESET: Fichier verrouillé, renommé en: {backup_name.name}"
                                                )
                                                deleted = True
                                            except Exception as rename_err:
                                                logger.warning(
                                                    f"⚠️ RESET: Impossible de renommer {item.name} ({rename_err}), sera supprimé à la fermeture"
                                                )

                            elif item.is_dir():
                                shutil.rmtree(item)
                                cvmatch_dirs_deleted += 1
                                logger.info(
                                    f"🗂️ RESET: Dossier utilisateur supprimé: {item.name}"
                                )
                            else:
                                cvmatch_items_protected += 1
                                logger.info(f"🔒 RESET: Dossier protégé: {item.name}")
                        except Exception as e:
                            logger.warning(f"⚠️ RESET: Erreur suppression {item}: {e}")

                    logger.info(
                        f"📊 RESET: Dossier utilisateur - Fichiers: {cvmatch_files_deleted}, Dossiers: {cvmatch_dirs_deleted}, Protégés: {cvmatch_items_protected}"
                    )
                else:
                    logger.info("ℹ️ RESET: Dossier utilisateur .cvmatch inexistant")

                # VÉRIFICATION CRITIQUE: S'assurer que les fichiers de lancement existent
                logger.info("🔒 RESET: Vérification des fichiers de lancement...")
                files_recreated = self._verify_launch_files_post_reset()
                if files_recreated:
                    logger.warning(
                        f"🚨 RESET: Fichiers de lancement recréés: {', '.join(files_recreated)}"
                    )

                logger.info("🎉 RESET: Réinitialisation complète terminée avec succès")

                QMessageBox.information(
                    self,
                    "Réinitialisation terminée",
                    "Le profil a été complètement réinitialisé.\n"
                    "L'application va redémarrer pour appliquer les changements.",
                )

                # Redémarrer l'application
                import subprocess
                import sys

                from PySide6.QtCore import QTimer

                def restart_application():
                    try:
                        # Chemin vers l'application
                        app_path = Path(__file__).parent.parent.parent / "main.py"
                        python_exe = sys.executable

                        cleanup_script = r"""
import sys
import time
import pathlib
import subprocess

paths_arg = sys.argv[1] if len(sys.argv) > 1 else ""
app_path = sys.argv[2] if len(sys.argv) > 2 else ""
paths = [p for p in paths_arg.split("|") if p]
cvmatch_dir = pathlib.Path.home() / ".cvmatch"

def try_delete(path: str) -> bool:
    try:
        pathlib.Path(path).unlink()
        return True
    except FileNotFoundError:
        return True
    except Exception:
        return False

for _ in range(40):
    pending = False
    for path in paths:
        if not try_delete(path):
            pending = True
    if cvmatch_dir.exists():
        for item in cvmatch_dir.glob("*.locked_reset_*"):
            try:
                item.unlink()
            except Exception:
                pending = True
    if not pending:
        break
    time.sleep(0.5)

if app_path:
    subprocess.Popen([sys.executable, app_path], cwd=str(pathlib.Path(app_path).parent))
"""
                        paths_arg = "|".join(deferred_paths)
                        subprocess.Popen(
                            [python_exe, "-c", cleanup_script, paths_arg, str(app_path)],
                            cwd=str(app_path.parent),
                            creationflags=(
                                subprocess.CREATE_NEW_CONSOLE
                                if sys.platform == "win32"
                                else 0
                            ),
                        )

                        # Fermer l'instance actuelle
                        from PySide6.QtWidgets import QApplication

                        app_instance = QApplication.instance()
                        if app_instance:
                            app_instance.quit()

                    except Exception as e:
                        logger.error(f"Erreur redémarrage: {e}")
                        # Fallback: juste fermer
                        sys.exit(0)

                # Redémarrer après un délai
                QTimer.singleShot(500, restart_application)

            except Exception as e:
                logger.error(f"Erreur lors de la réinitialisation : {e}")
                QMessageBox.critical(
                    self, "Erreur", f"Erreur lors de la réinitialisation :\n{e}"
                )

    def _verify_launch_files_post_reset(self):
        """
        Vérification critique: s'assurer que les fichiers de lancement existent après reset.
        Si manquants, les recrée automatiquement avec template minimal.
        """
        from pathlib import Path

        from loguru import logger

        project_root = Path(__file__).parent.parent.parent

        launch_files = {
            "cvmatch.bat": self._get_minimal_bat_template(),
            "cvmatch.sh": self._get_minimal_sh_template(),
        }

        files_recreated = []

        for filename, template in launch_files.items():
            file_path = project_root / filename

            if not file_path.exists():
                logger.warning(f"🚨 ALERTE: Fichier de lancement manquant: {filename}")
                try:
                    file_path.write_text(template, encoding="utf-8")
                    if filename.endswith(".sh"):
                        # Rendre exécutable sur Unix
                        import stat

                        file_path.chmod(file_path.stat().st_mode | stat.S_IEXEC)

                    files_recreated.append(filename)
                    logger.info(f"✅ Fichier de lancement recréé: {filename}")
                except Exception as e:
                    logger.error(f"❌ Impossible de recréer {filename}: {e}")

        return files_recreated

    def _get_minimal_bat_template(self) -> str:
        """Template minimal pour cvmatch.bat en cas de suppression accidentelle."""
        return """@echo off
setlocal EnableExtensions EnableDelayedExpansion
rem CVMatch - Lanceur de secours (recrée automatiquement)
chcp 65001 >nul

echo CVMatch - Lanceur de secours
cd /d "%~dp0"

python --version >nul 2>&1 || (echo ERREUR: Python requis && pause && exit /b 1)

set "VENV_DIR=%~dp0cvmatch_env"
if not exist "%VENV_DIR%" python -m venv "%VENV_DIR%"
call "%VENV_DIR%\\Scripts\\activate.bat" || (echo ERREUR: Activation venv && pause && exit /b 1)

"%VENV_DIR%\\Scripts\\pip.exe" install -r "%~dp0requirements_windows.txt" --quiet
"%VENV_DIR%\\Scripts\\python.exe" main.py
exit /b %ERRORLEVEL%"""

    def _get_minimal_sh_template(self) -> str:
        """Template minimal pour cvmatch.sh en cas de suppression accidentelle."""
        return """#!/bin/bash
# CVMatch - Lanceur de secours (recrée automatiquement)
set -e
cd "$(dirname "${BASH_SOURCE[0]}")"

command -v python3 &> /dev/null || { echo "ERREUR: Python 3 requis"; exit 1; }

VENV_DIR="./cvmatch_env"
[[ ! -d "$VENV_DIR" ]] && python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate" || { echo "ERREUR: Activation venv"; exit 1; }

"$VENV_DIR/bin/pip" install -r "./requirements_linux.txt" --quiet
"$VENV_DIR/bin/python" main.py"""
