"""Plain-text QTextEdit that ignores images and file drops."""

from __future__ import annotations

from PySide6.QtCore import QMimeData
from PySide6.QtWidgets import QTextEdit


class TextOnlyEdit(QTextEdit):
    """QTextEdit that accepts plain text only (no images or local file drops)."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.setAcceptRichText(False)

    def canInsertFromMimeData(self, source: QMimeData) -> bool:  # noqa: N802
        if source is None:
            return False
        if source.hasImage():
            return False
        if source.hasUrls():
            urls = source.urls()
            if urls and all(url.isLocalFile() for url in urls):
                return False
        return source.hasText()

    def insertFromMimeData(self, source: QMimeData) -> None:  # noqa: N802
        if not self.canInsertFromMimeData(source):
            return
        text = source.text()
        if not text:
            return
        # Remove object replacement characters from rich sources.
        text = text.replace("\uFFFC", "")
        self.insertPlainText(text)
