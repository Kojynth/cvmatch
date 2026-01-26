from typing import Iterable
import unicodedata

from PySide6.QtWidgets import (
    QWidget, QLabel, QPushButton, QGroupBox, QCheckBox, QTabWidget,
    QTreeWidget, QTreeWidgetItem, QTableWidget, QTableWidgetItem
)
from app.utils.emoji_utils import get_display_text

# Common mojibake (UTF-8 mis-decoded as ISO-8859-1/Windows-1252) fixes
MOJIBAKE_MAP = {
    # Accents (lowercase)
    "Ã ": "à", "Ã¢": "â", "Ã¤": "ä", "Ã§": "ç", "Ã©": "é", "Ã¨": "è",
    "Ãª": "ê", "Ã«": "ë", "Ã¯": "ï", "Ã®": "î", "Ã¶": "ö", "Ã´": "ô",
    "Ã¹": "ù", "Ã»": "û", "Ã¼": "ü",
    # Accents (uppercase)
    "Ã€": "À", "Ã‚": "Â", "Ã„": "Ä", "ÃŸ": "ß", "Ã‡": "Ç", "Ã‰": "É",
    "Ãˆ": "È", "ÃŠ": "Ê", "Ã‹": "Ë", "ÃŒ": "Ì", "ÃŽ": "Î", "Ã": "Ï",
    "Ã–": "Ö", "Ã”": "Ô", "Ã™": "Ù", "Ã›": "Û", "Ãœ": "Ü",
    # Punctuation & symbols
    "â€“": "–", "â€”": "—", "â€˜": "‘", "â€™": "’", "â€œ": "“", "â€\x9d": "”",
    "â€¢": "•", "â€¦": "…", "Â«": "«", "Â»": "»", "Â°": "°", "Â·": "·",
    # Arrows and checkmarks
    "â†": "←", "â†’": "→", "âœ…": "✅", "âŒ": "❌", "âœ”": "✔", "âœ•": "✕",
    "âœï¸": "✏️", "âš¡": "⚡", "âš ": "⚠️",
    # Common emojis mis-decoded
    "ðŸ“„": "📄", "ðŸ“‹": "📋", "ðŸ“": "📝", "ðŸŽ¨": "🎨", "ðŸ“ž": "📞",
    "ðŸ“": "📍", "ðŸ”": "🔍", "ðŸ”„": "🔄",
}

def _attempt_repair(text: str) -> str:
    """Try to repair common mojibake by re-decoding as UTF-8.

    Strategy: if we detect suspicious markers (Ã, Â, ð, �), try
    latin-1->utf-8 and cp1252->utf-8 round-trips and pick the best.
    """
    suspicious = any(mark in text for mark in ("Ã", "Â", "ð", "�"))
    if not suspicious:
        return text

    candidates = []
    for enc in ("latin-1", "cp1252"):
        try:
            repaired = text.encode(enc, errors="ignore").decode("utf-8", errors="ignore")
            candidates.append(repaired)
        except Exception:
            pass

    # Choose the candidate that reduces replacement chars and mojibake markers
    def score(s: str) -> int:
        return sum(s.count(x) for x in ("Ã", "Â", "ð", "�"))

    best = text
    best_score = score(text)
    for cand in candidates:
        sc = score(cand)
        if sc < best_score and cand:
            best, best_score = cand, sc
    return best


def _clean_text(text: str) -> str:
    if not isinstance(text, str):
        return text
    # First, try a general repair pass
    fixed = _attempt_repair(text)
    # Then fix common mojibake so real Unicode is restored
    try:
        for bad, good in MOJIBAKE_MAP.items():
            fixed = fixed.replace(bad, good)
        # Remove stray 'Â' often left from encoding issues
        fixed = fixed.replace('Â', '')
    except Exception:
        fixed = text
    # Then normalize emojis to display-safe text (emoji or ASCII fallback)
    cleaned = get_display_text(fixed)
    try:
        for bad, good in MOJIBAKE_MAP.items():
            cleaned = cleaned.replace(bad, good)
        cleaned = cleaned.replace('Â', '')
    except Exception:
        pass
    # Remove replacement char (�)
    cleaned = cleaned.replace('\ufffd', '')
    # Remove zero-width and variation selectors that often render as empty boxes
    ZW_CHARS = {
        '\u200b', '\u200c', '\u200d', '\u2060',  # ZWSP, ZWNJ, ZWJ, WORD JOINER
        '\u200e', '\u200f',  # LRM, RLM
        '\ufe0e', '\ufe0f',  # VS15/VS16
    }
    cleaned = ''.join(ch for ch in cleaned if ch not in ZW_CHARS)
    # Remove bidirectional control characters ranges
    cleaned = ''.join(
        ch for ch in cleaned
        if not (0x202A <= ord(ch) <= 0x202E or 0x2066 <= ord(ch) <= 0x2069)
    )
    # Remove private use areas that appear as tofu on some systems
    def _is_pua(cp: int) -> bool:
        return (
            0xE000 <= cp <= 0xF8FF or
            0xF0000 <= cp <= 0xFFFFD or
            0x100000 <= cp <= 0x10FFFD
        )
    cleaned = ''.join(ch for ch in cleaned if not _is_pua(ord(ch)))
    # Remove other control chars (except new line and tab)
    cleaned = ''.join(
        ch for ch in cleaned
        if not (unicodedata.category(ch) == 'Cc' and ch not in ('\n', '\t'))
    )
    # Collapse excessive spaces
    cleaned = ' '.join(cleaned.split())
    return cleaned


def sanitize_widget_tree(root: QWidget):
    stack: list[QWidget] = [root]
    while stack:
        w = stack.pop()
        # Sanitize known text-bearing widgets
        if isinstance(w, (QLabel, QPushButton, QCheckBox)):
            try:
                text = w.text()
                cleaned = _clean_text(text)
                if cleaned != text:
                    w.setText(cleaned)
            except Exception:
                pass
        # QGroupBox uses title(), not text()
        if isinstance(w, QGroupBox):
            try:
                t = w.title()
                cleaned = _clean_text(t)
                if cleaned != t:
                    w.setTitle(cleaned)
            except Exception:
                pass
        # Sanitize QTabWidget tab titles
        if isinstance(w, QTabWidget):
            try:
                for i in range(w.count()):
                    t = w.tabText(i)
                    cleaned = _clean_text(t)
                    if cleaned != t:
                        w.setTabText(i, cleaned)
            except Exception:
                pass
        # Sanitize QTreeWidget item texts
        if isinstance(w, QTreeWidget):
            try:
                def walk_item(item: QTreeWidgetItem):
                    cols = item.columnCount()
                    for col in range(cols):
                        t = item.text(col)
                        cleaned = _clean_text(t)
                        if cleaned != t:
                            item.setText(col, cleaned)
                    for i in range(item.childCount()):
                        walk_item(item.child(i))
                for i in range(w.topLevelItemCount()):
                    walk_item(w.topLevelItem(i))
            except Exception:
                pass
        # Sanitize QTableWidget item texts
        if isinstance(w, QTableWidget):
            try:
                rows = w.rowCount()
                cols = w.columnCount()
                for r in range(rows):
                    for c in range(cols):
                        item = w.item(r, c)
                        if item is not None:
                            t = item.text()
                            cleaned = _clean_text(t)
                            if cleaned != t:
                                item.setText(cleaned)
            except Exception:
                pass
        stack.extend(w.findChildren(QWidget))
