"""
Compact Sidebar Statistics Widget
=================================

Encart « Statistiques » minimaliste pour la sidebar de navigation.
Affiche une ligne de synthèse lisible afin d’éviter la surcharge.
"""

from __future__ import annotations

from typing import Optional, Dict
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont
from loguru import logger

from ..utils.user_statistics import UserStatsData, get_user_stats
from ..models.user_profile import UserProfile
from ..models.database import get_session


class StatsWidget(QWidget):
    """Widget d’encart statistiques – version compacte.

    Affiche seulement deux métriques clés sur une ligne:
    - nombre de CV
    - taux de réussite
    """

    # Conservé pour compatibilité avec la Sidebar
    stat_clicked = Signal(str, dict)

    def __init__(self, profile: UserProfile, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.profile: UserProfile = profile
        self.current_stats: Optional[UserStatsData] = None

        self._setup_ui()
        self.refresh_stats()

        # Mise à jour automatique (toutes les 10 minutes)
        self._update_timer = QTimer(self)
        self._update_timer.timeout.connect(self.refresh_stats)
        self._update_timer.start(600_000)

    # --- UI -----------------------------------------------------------------
    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self._container = QFrame(self)
        self._container.setStyleSheet(
            "QFrame { background: transparent; border: none; padding: 0; }"
        )

        self._stats_layout = QVBoxLayout(self._container)
        self._stats_layout.setContentsMargins(0, 0, 0, 0)
        self._stats_layout.setSpacing(0)

        self.summary_label = QLabel("Chargement…", self._container)
        self.summary_label.setFont(QFont("Arial", 10))
        self.summary_label.setStyleSheet("color: #cccccc;")
        self.summary_label.setAlignment(Qt.AlignLeft)
        self._stats_layout.addWidget(self.summary_label)

        layout.addWidget(self._container)

    def _set_loading(self) -> None:
        self.summary_label.setText("Chargement…")

    # --- Data ----------------------------------------------------------------
    def refresh_stats(self) -> None:
        """Actualise les statistiques depuis la base de données."""
        try:
            if not getattr(self.profile, 'id', None):
                self._set_loading()
                return

            with get_session() as session:
                # Recharger un profil frais pour disposer des dernières données
                fresh = session.get(UserProfile, self.profile.id)
                if fresh is not None:
                    self.profile = fresh

                stats = get_user_stats(session, self.profile)
                self.update_display(stats)
                self.current_stats = stats

            logger.info("Statistiques sidebar mises à jour (compact)")
        except Exception as e:
            logger.error(f"Erreur refresh_stats StatsWidget: {e}")
            self.show_error_state()

    def update_display(self, stats: UserStatsData) -> None:
        """Met à jour la synthèse compacte (2 métriques)."""
        cv_count = getattr(stats, 'cv_generated_count', getattr(self.profile, 'total_cvs_generated', 0))
        positive_count = getattr(stats, 'positive_response_count', 0)
        # Affiche le volume de CV générés et les réponses positives obtenues.
        self.summary_label.setText(f"CV: {cv_count} • Réponses+: {positive_count}")

    def show_error_state(self) -> None:
        """Affiche un état d’erreur minimal."""
        self.summary_label.setText("Erreur de chargement — réessayer plus tard")

    # --- API externe ---------------------------------------------------------
    def update_profile(self, new_profile: UserProfile) -> None:
        """Met à jour le profil et rafraîchit l’encart."""
        self.profile = new_profile
        QTimer.singleShot(100, self.refresh_stats)

    def cleanup(self) -> None:
        if hasattr(self, '_update_timer'):
            self._update_timer.stop()
            self._update_timer.deleteLater()

