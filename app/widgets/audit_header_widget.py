"""
AuditHeaderWidget
=================

Bandeau horizontal affichant les métriques d'audit et d'alignement d'un CV généré.

Ce widget est autonome et réutilisable. Il expose une seule méthode publique :
    update_audit(cv_data: dict) -> None

Il se masque automatiquement quand aucune donnée n'est disponible.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)


def _score_colors(val: float) -> tuple[str, str]:
    """Retourne (bar_color, text_color) selon les seuils 80 / 60."""
    if val >= 80:
        return "#28a745", "#155724"
    if val >= 60:
        return "#ffc107", "#856404"
    return "#dc3545", "#721c24"


def _safe_float(val: Any) -> float | None:
    try:
        return float(val) if val is not None else None
    except (TypeError, ValueError):
        return None


class AuditHeaderWidget(QFrame):
    """Bandeau horizontal de métriques audit & alignement.

    Usage::
        widget = AuditHeaderWidget()
        main_layout.addWidget(widget)
        # Après génération :
        widget.update_audit(cv_data)
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("audit_header_widget")
        self.setStyleSheet("""
            QFrame#audit_header_widget {
                background-color: #f0f4f8;
                border: 1px solid #c8d6e5;
                border-radius: 8px;
                padding: 4px;
            }
        """)
        self._setup_ui()
        self.setVisible(False)  # masqué jusqu'à la première mise à jour avec données

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    def update_audit(self, cv_data: dict) -> None:
        """Met à jour toutes les métriques depuis cv_data.

        Clés lues :
          - ``generation_audit``    → global_score, cv_score, letter_score, sufficient
          - ``alignment_audit``     → exact_present_terms, exact_missing_terms
          - ``cover_letter_review`` → score (fallback letter_score)
          - ``degraded_mode``       → bool
          - ``degraded_reasons``    → list[str]

        Se masque automatiquement si aucune donnée significative.
        """
        if not isinstance(cv_data, dict):
            self.setVisible(False)
            return

        audit = self._resolve_audit(cv_data)
        if not audit:
            self.setVisible(False)
            return

        self.setVisible(True)

        global_score = _safe_float(audit.get("global_score"))
        cv_score = _safe_float(audit.get("cv_score"))
        letter_score = _safe_float(audit.get("letter_score"))

        self._apply_bar(self._bar_global, self._lbl_global, global_score, 10)
        self._apply_bar(self._bar_cv, self._lbl_cv, cv_score, 8)
        self._apply_bar(self._bar_letter, self._lbl_letter, letter_score, 8)

        # Suffixe ✓/✗ sur le score global
        if global_score is not None:
            sufficient = bool(audit.get("sufficient"))
            icon = "✓" if sufficient else "✗"
            _, text_color = _score_colors(global_score)
            self._lbl_global.setText(f"{global_score:.1f}/100 {icon}")
            self._lbl_global.setStyleSheet(
                f"color: {text_color}; font-size: 11px; font-weight: bold;"
            )

        # Mots-clés présents / manquants
        alignment_audit = cv_data.get("alignment_audit") or {}
        breakdown = audit.get("breakdown") or {}
        cv_breakdown = breakdown.get("cv") or {} if isinstance(breakdown, dict) else {}
        present_terms = (
            alignment_audit.get("exact_present_terms") or cv_breakdown.get("exact_present_terms") or []
        )
        missing_terms = (
            alignment_audit.get("exact_missing_terms") or cv_breakdown.get("exact_missing_terms") or []
        )

        has_row2 = False

        if present_terms and isinstance(present_terms, list):
            shown = ", ".join(str(t) for t in present_terms[:8])
            if len(present_terms) > 8:
                shown += f"… +{len(present_terms) - 8}"
            self._lbl_present.setText(f"✓ {len(present_terms)} présents : {shown}")
            self._lbl_present.setVisible(True)
            has_row2 = True
        else:
            self._lbl_present.setVisible(False)

        if missing_terms and isinstance(missing_terms, list):
            shown = ", ".join(str(t) for t in missing_terms[:6])
            if len(missing_terms) > 6:
                shown += f"… +{len(missing_terms) - 6}"
            self._lbl_missing.setText(f"✗ {len(missing_terms)} manquants : {shown}")
            self._lbl_missing.setVisible(True)
            has_row2 = True
        else:
            self._lbl_missing.setVisible(False)

        # Mode dégradé
        degraded_mode = bool(cv_data.get("degraded_mode", False))
        degraded_reasons = cv_data.get("degraded_reasons") or []
        if degraded_mode:
            reasons_text = (
                ", ".join(str(r) for r in degraded_reasons[:2])
                if degraded_reasons
                else "mode dégradé"
            )
            self._lbl_degraded.setText(f"⚠ Mode dégradé : {reasons_text}")
            self._lbl_degraded.setVisible(True)
            has_row2 = True
        else:
            self._lbl_degraded.setVisible(False)

        self._row2.setVisible(has_row2)

    # ------------------------------------------------------------------
    # Construction de l'UI
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 8, 10, 8)
        outer.setSpacing(4)

        # Ligne 1 : titre + 3 blocs de score côte à côte
        row1 = QHBoxLayout()
        row1.setSpacing(8)

        title = QLabel("🎯 Audit & Alignement")
        title.setStyleSheet("color: #3d5a80; font-weight: bold; font-size: 12px;")
        row1.addWidget(title)
        row1.addStretch(1)

        self._bar_global, self._lbl_global = self._make_score_block(row1, "Global", height=10)
        row1.addWidget(self._vsep())
        self._bar_cv, self._lbl_cv = self._make_score_block(row1, "CV", height=8)
        row1.addWidget(self._vsep())
        self._bar_letter, self._lbl_letter = self._make_score_block(row1, "Lettre", height=8)

        outer.addLayout(row1)

        # Ligne 2 : mots-clés présents/manquants + mode dégradé (masquée par défaut)
        self._row2 = QWidget()
        row2_layout = QHBoxLayout(self._row2)
        row2_layout.setContentsMargins(0, 0, 0, 0)
        row2_layout.setSpacing(8)

        self._lbl_present = self._make_tag_label("green")
        self._lbl_missing = self._make_tag_label("red")
        self._lbl_degraded = self._make_tag_label("yellow")

        row2_layout.addWidget(self._lbl_present, 1)
        row2_layout.addWidget(self._lbl_missing, 1)
        row2_layout.addWidget(self._lbl_degraded, 1)

        self._row2.setVisible(False)
        outer.addWidget(self._row2)

    @staticmethod
    def _make_score_block(
        parent_layout: QHBoxLayout, label: str, height: int
    ) -> tuple[QProgressBar, QLabel]:
        """Crée un conteneur [préfixe | barre | score_label] et l'ajoute au layout parent."""
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        prefix = QLabel(label)
        prefix.setStyleSheet("color: #495057; font-size: 11px; font-weight: bold;")
        layout.addWidget(prefix)

        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(0)
        bar.setTextVisible(False)
        bar.setFixedHeight(height)
        bar.setMinimumWidth(100)
        bar.setMaximumWidth(180)
        radius = height // 2
        bar.setStyleSheet(
            f"QProgressBar {{ border: 1px solid #dee2e6; border-radius: {radius}px;"
            f" background-color: #e9ecef; }}"
            f" QProgressBar::chunk {{ border-radius: {radius}px;"
            f" background-color: #6c757d; }}"
        )
        layout.addWidget(bar)

        score_label = QLabel("N/A")
        score_label.setStyleSheet("color: #6c757d; font-size: 11px;")
        score_label.setMinimumWidth(70)
        score_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(score_label)

        parent_layout.addWidget(container)
        return bar, score_label

    @staticmethod
    def _vsep() -> QFrame:
        """Séparateur vertical 1px entre blocs de score."""
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("color: #c8d6e5; max-width: 1px;")
        return sep

    @staticmethod
    def _make_tag_label(color: str) -> QLabel:
        """QLabel avec fond coloré pour afficher les tags mots-clés / dégradé."""
        palettes = {
            "green": "color: #155724; background-color: #d4edda; border: 1px solid #c3e6cb;",
            "red": "color: #721c24; background-color: #f8d7da; border: 1px solid #f5c6cb;",
            "yellow": "color: #856404; background-color: #fff3cd; border: 1px solid #ffc107;",
        }
        lbl = QLabel()
        base = palettes.get(color, palettes["green"])
        lbl.setStyleSheet(base + " border-radius: 4px; padding: 3px 6px; font-size: 11px;")
        lbl.setWordWrap(True)
        lbl.setVisible(False)
        return lbl

    def _apply_bar(
        self,
        bar: QProgressBar,
        label: QLabel,
        score_val: float | None,
        height: int,
    ) -> None:
        """Applique la valeur et la couleur à une barre + son label."""
        radius = height // 2
        if score_val is None:
            bar.setValue(0)
            label.setText("N/A")
            label.setStyleSheet("color: #6c757d; font-size: 11px;")
            bar.setStyleSheet(
                f"QProgressBar {{ border: 1px solid #dee2e6; border-radius: {radius}px;"
                f" background-color: #e9ecef; }}"
                f" QProgressBar::chunk {{ border-radius: {radius}px;"
                f" background-color: #6c757d; }}"
            )
            return
        bar_color, text_color = _score_colors(score_val)
        bar.setValue(int(score_val))
        label.setText(f"{score_val:.1f}/100")
        label.setStyleSheet(f"color: {text_color}; font-size: 11px; font-weight: bold;")
        bar.setStyleSheet(
            f"QProgressBar {{ border: 1px solid #dee2e6; border-radius: {radius}px;"
            f" background-color: #e9ecef; }}"
            f" QProgressBar::chunk {{ border-radius: {radius}px;"
            f" background-color: {bar_color}; }}"
        )

    # ------------------------------------------------------------------
    # Résolution des données d'audit depuis cv_data
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_audit(cv_data: dict) -> dict | None:
        """Extrait le dict d'audit depuis cv_data.

        Priorité : generation_audit direct → calcul depuis alignment_audit /
        cover_letter_review → offer_analysis.generation_audit.
        Retourne None si aucune donnée disponible.
        """
        direct = cv_data.get("generation_audit")
        if isinstance(direct, dict) and direct:
            return dict(direct)

        alignment_audit = cv_data.get("alignment_audit")
        cover_letter_review = cv_data.get("cover_letter_review")
        if isinstance(alignment_audit, dict) or isinstance(cover_letter_review, dict):
            try:
                from app.utils.generation_audit import build_generation_audit as _build
                return _build(
                    alignment_audit=alignment_audit if isinstance(alignment_audit, dict) else {},
                    cover_letter_review=(
                        cover_letter_review if isinstance(cover_letter_review, dict) else {}
                    ),
                )
            except Exception:
                pass

        offer_analysis = cv_data.get("offer_analysis")
        if isinstance(offer_analysis, dict):
            nested = offer_analysis.get("generation_audit")
            if isinstance(nested, dict) and nested:
                return dict(nested)

        return None
