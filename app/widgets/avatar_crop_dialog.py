"""Avatar circular-crop dialog.

Presents the user with a fixed circle overlay on top of their chosen image.
They can drag the image and zoom (wheel or slider) to frame their face,
then click "Valider" to extract the cropped region as a PIL Image.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import (
    QColor,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QSlider,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

# Widget dimensions (px)
_WIDGET_SIZE = 480
_CIRCLE_DIAMETER = 280
_CIRCLE_RADIUS = _CIRCLE_DIAMETER // 2

# Overlay color — semi-transparent black
_OVERLAY_COLOR = QColor(0, 0, 0, 160)

# Circle border
_BORDER_COLOR = QColor(255, 255, 255, 220)
_BORDER_WIDTH = 2

# Zoom bounds
_SCALE_MIN = 0.5
_SCALE_MAX = 5.0


class _CropWidget(QWidget):
    """Interactive widget: fixed circle, image moves/zooms underneath."""

    def __init__(self, pixmap: QPixmap, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedSize(_WIDGET_SIZE, _WIDGET_SIZE)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

        self._pixmap = pixmap
        self._scale: float = 1.0
        self._offset = QPointF(0.0, 0.0)
        self._drag_start: Optional[QPointF] = None

        # Initial fit so image fills the circle
        self.reset_fit()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reset_fit(self) -> None:
        """Scale image so it exactly covers the crop circle."""
        if self._pixmap.isNull():
            return
        w, h = self._pixmap.width(), self._pixmap.height()
        if w <= 0 or h <= 0:
            return
        self._scale = max(_CIRCLE_DIAMETER / w, _CIRCLE_DIAMETER / h)
        self._scale = max(_SCALE_MIN, min(_SCALE_MAX, self._scale))
        # Centre the scaled image on the widget
        cx = _WIDGET_SIZE / 2
        cy = _WIDGET_SIZE / 2
        self._offset = QPointF(cx - w * self._scale / 2, cy - h * self._scale / 2)
        self.update()

    def set_scale(self, value: float) -> None:
        """Set zoom level; keep crop-circle centre fixed."""
        value = max(_SCALE_MIN, min(_SCALE_MAX, value))
        if abs(value - self._scale) < 1e-6:
            return

        # Pivot around the widget centre
        cx = _WIDGET_SIZE / 2.0
        cy = _WIDGET_SIZE / 2.0
        ratio = value / self._scale
        self._offset = QPointF(
            cx + (self._offset.x() - cx) * ratio,
            cy + (self._offset.y() - cy) * ratio,
        )
        self._scale = value
        self.update()

    def get_cropped_pil_image(self, output_size: int = 512):
        """Return PIL Image of the circle crop region (output_size × output_size).

        Returns None if Pillow is not available or an error occurs.
        """
        try:
            from PIL import Image  # type: ignore[import]
        except ImportError:
            return None

        if self._pixmap.isNull():
            return None

        # Circle centre in widget space
        cx = _WIDGET_SIZE / 2.0
        cy = _WIDGET_SIZE / 2.0

        # Circle edges in widget space
        left_w = cx - _CIRCLE_RADIUS
        top_w = cy - _CIRCLE_RADIUS
        right_w = cx + _CIRCLE_RADIUS
        bottom_w = cy + _CIRCLE_RADIUS

        # Map widget coords → image coords:
        # widget_x = offset.x + img_x * scale  →  img_x = (widget_x - offset.x) / scale
        def to_img(wx: float, wy: float):
            return (
                (wx - self._offset.x()) / self._scale,
                (wy - self._offset.y()) / self._scale,
            )

        x0, y0 = to_img(left_w, top_w)
        x1, y1 = to_img(right_w, bottom_w)

        # Clamp to image bounds
        iw = self._pixmap.width()
        ih = self._pixmap.height()
        x0 = max(0.0, x0)
        y0 = max(0.0, y0)
        x1 = min(float(iw), x1)
        y1 = min(float(ih), y1)

        if x1 <= x0 or y1 <= y0:
            return None

        # Convert QPixmap → PIL Image via QImage
        qimage = self._pixmap.toImage()
        qimage = qimage.convertToFormat(qimage.Format.Format_RGB888)
        width_qi = qimage.width()
        height_qi = qimage.height()
        ptr = qimage.bits()
        try:
            # PySide6 bits() returns a memoryview
            pil_img = Image.frombytes(
                "RGB",
                (width_qi, height_qi),
                bytes(ptr),
            )
        except Exception:
            return None

        # Crop and resize
        box = (int(x0), int(y0), int(x1), int(y1))
        cropped = pil_img.crop(box)
        cropped = cropped.resize((output_size, output_size), Image.LANCZOS)
        return cropped

    # ------------------------------------------------------------------
    # Qt event overrides
    # ------------------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # 1. Black background
        painter.fillRect(self.rect(), QColor(0, 0, 0))

        # 2. Draw the image at current offset/scale
        if not self._pixmap.isNull():
            w = self._pixmap.width() * self._scale
            h = self._pixmap.height() * self._scale
            target = QRectF(self._offset.x(), self._offset.y(), w, h)
            painter.drawPixmap(target.toRect(), self._pixmap)

        # 3. Semi-transparent overlay covering entire widget
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.fillRect(self.rect(), _OVERLAY_COLOR)

        # 4. Cut the circle out of the overlay using Source mode (fully transparent)
        cx = _WIDGET_SIZE / 2.0
        cy = _WIDGET_SIZE / 2.0
        circle_path = QPainterPath()
        circle_path.addEllipse(
            QRectF(
                cx - _CIRCLE_RADIUS,
                cy - _CIRCLE_RADIUS,
                _CIRCLE_DIAMETER,
                _CIRCLE_DIAMETER,
            )
        )
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(Qt.GlobalColor.transparent)
        painter.drawPath(circle_path)

        # 5. White border around the circle
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        pen = QPen(_BORDER_COLOR, _BORDER_WIDTH)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(
            QRectF(
                cx - _CIRCLE_RADIUS,
                cy - _CIRCLE_RADIUS,
                _CIRCLE_DIAMETER,
                _CIRCLE_DIAMETER,
            )
        )

        painter.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = QPointF(event.position())
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_start is not None:
            pos = QPointF(event.position())
            delta = pos - self._drag_start
            self._drag_start = pos
            self._offset += delta
            self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag_start = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def wheelEvent(self, event) -> None:  # noqa: N802
        delta = event.angleDelta().y()
        factor = 1.1 if delta > 0 else (1.0 / 1.1)
        self.set_scale(self._scale * factor)
        # Notify parent dialog to sync slider
        self.parent()._sync_slider_from_widget()  # type: ignore[union-attr]


class AvatarCropDialog(QDialog):
    """Dialog wrapping _CropWidget with zoom slider and Valider/Annuler buttons."""

    def __init__(self, image_path: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Recadrer la photo de profil")
        self.setModal(True)

        pixmap = QPixmap(image_path)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        # Instruction label
        hint = QLabel("Déplacez l'image pour centrer votre visage · molette pour zoomer")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet("color: #888; font-size: 12px;")
        layout.addWidget(hint)

        # Crop widget
        self._crop_widget = _CropWidget(pixmap, parent=self)
        layout.addWidget(self._crop_widget, alignment=Qt.AlignmentFlag.AlignCenter)

        # Zoom slider row
        zoom_row = QHBoxLayout()
        zoom_label = QLabel("Zoom :")
        zoom_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        zoom_row.addWidget(zoom_label)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(50, 500)
        initial_pct = int(self._crop_widget._scale * 100)
        initial_pct = max(50, min(500, initial_pct))
        self._slider.setValue(initial_pct)
        zoom_row.addWidget(self._slider)

        self._pct_label = QLabel(f"{initial_pct}%")
        self._pct_label.setFixedWidth(46)
        self._pct_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        zoom_row.addWidget(self._pct_label)
        layout.addLayout(zoom_row)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok_btn = buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok_btn:
            ok_btn.setText("Valider")
        cancel_btn = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_btn:
            cancel_btn.setText("Annuler")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Wiring
        self._slider.valueChanged.connect(self._on_slider_changed)

        self.setFixedWidth(_WIDGET_SIZE + 32)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_cropped_pil_image(self, output_size: int = 512):
        """Return the cropped PIL Image, or None if unavailable."""
        return self._crop_widget.get_cropped_pil_image(output_size=output_size)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _on_slider_changed(self, value: int) -> None:
        self._pct_label.setText(f"{value}%")
        self._crop_widget.set_scale(value / 100.0)

    def _sync_slider_from_widget(self) -> None:
        """Called by _CropWidget on wheel event to keep slider in sync."""
        pct = int(self._crop_widget._scale * 100)
        pct = max(50, min(500, pct))
        self._slider.blockSignals(True)
        self._slider.setValue(pct)
        self._pct_label.setText(f"{pct}%")
        self._slider.blockSignals(False)
