"""
UI Sanitizer - Widget tree sanitization for mojibake prevention
===============================================================

Utilities to sanitize entire widget trees, applying text normalization
to all visible text elements to prevent mojibake in the UI.
"""

from typing import Any, List, Optional
from PySide6.QtWidgets import (
    QWidget, QLabel, QLineEdit, QTextEdit, QPlainTextEdit, 
    QPushButton, QCheckBox, QRadioButton, QGroupBox,
    QTabWidget, QTreeWidget, QTreeWidgetItem, QListWidget, QListWidgetItem,
    QTableWidget, QTableWidgetItem, QComboBox
)
from PySide6.QtCore import Qt

from .text_norm import normalize_text_for_ui


def sanitize_widget_tree(widget: QWidget, fix_mojibake: bool = True) -> int:
    """
    Recursively sanitize all text in a widget tree.
    
    Args:
        widget: Root widget to sanitize
        fix_mojibake: Whether to apply mojibake fixes
        
    Returns:
        Number of text elements sanitized
    """
    if not widget:
        return 0
    
    sanitized_count = 0
    
    # Sanitize current widget
    sanitized_count += _sanitize_widget(widget, fix_mojibake)
    
    # Recursively sanitize children
    for child in widget.findChildren(QWidget):
        if child != widget:  # Avoid infinite recursion
            sanitized_count += _sanitize_widget(child, fix_mojibake)
    
    return sanitized_count


def _sanitize_widget(widget: QWidget, fix_mojibake: bool = True) -> int:
    """
    Sanitize text in a single widget.
    
    Args:
        widget: Widget to sanitize
        fix_mojibake: Whether to apply mojibake fixes
        
    Returns:
        Number of text elements sanitized in this widget
    """
    sanitized_count = 0
    
    try:
        # Labels and static text
        if isinstance(widget, QLabel):
            original_text = widget.text()
            if original_text:
                sanitized_text = normalize_text_for_ui(original_text, fix_mojibake)
                if sanitized_text != original_text:
                    widget.setText(sanitized_text)
                    sanitized_count += 1
        
        # Text inputs
        elif isinstance(widget, QLineEdit):
            original_text = widget.text()
            if original_text:
                sanitized_text = normalize_text_for_ui(original_text, fix_mojibake)
                if sanitized_text != original_text:
                    widget.setText(sanitized_text)
                    sanitized_count += 1
            
            # Also sanitize placeholder text
            placeholder = widget.placeholderText()
            if placeholder:
                sanitized_placeholder = normalize_text_for_ui(placeholder, fix_mojibake)
                if sanitized_placeholder != placeholder:
                    widget.setPlaceholderText(sanitized_placeholder)
                    sanitized_count += 1
        
        # Multi-line text inputs
        elif isinstance(widget, (QTextEdit, QPlainTextEdit)):
            original_text = widget.toPlainText()
            if original_text:
                sanitized_text = normalize_text_for_ui(original_text, fix_mojibake)
                if sanitized_text != original_text:
                    widget.setPlainText(sanitized_text)
                    sanitized_count += 1
        
        # Buttons
        elif isinstance(widget, QPushButton):
            original_text = widget.text()
            if original_text:
                sanitized_text = normalize_text_for_ui(original_text, fix_mojibake)
                if sanitized_text != original_text:
                    widget.setText(sanitized_text)
                    sanitized_count += 1
        
        # Checkboxes and radio buttons
        elif isinstance(widget, (QCheckBox, QRadioButton)):
            original_text = widget.text()
            if original_text:
                sanitized_text = normalize_text_for_ui(original_text, fix_mojibake)
                if sanitized_text != original_text:
                    widget.setText(sanitized_text)
                    sanitized_count += 1
        
        # Group boxes
        elif isinstance(widget, QGroupBox):
            original_title = widget.title()
            if original_title:
                sanitized_title = normalize_text_for_ui(original_title, fix_mojibake)
                if sanitized_title != original_title:
                    widget.setTitle(sanitized_title)
                    sanitized_count += 1
        
        # Tab widgets
        elif isinstance(widget, QTabWidget):
            for i in range(widget.count()):
                original_text = widget.tabText(i)
                if original_text:
                    sanitized_text = normalize_text_for_ui(original_text, fix_mojibake)
                    if sanitized_text != original_text:
                        widget.setTabText(i, sanitized_text)
                        sanitized_count += 1
        
        # List widgets
        elif isinstance(widget, QListWidget):
            for i in range(widget.count()):
                item = widget.item(i)
                if item and item.text():
                    original_text = item.text()
                    sanitized_text = normalize_text_for_ui(original_text, fix_mojibake)
                    if sanitized_text != original_text:
                        item.setText(sanitized_text)
                        sanitized_count += 1
        
        # Tree widgets
        elif isinstance(widget, QTreeWidget):
            sanitized_count += _sanitize_tree_widget(widget, fix_mojibake)
        
        # Table widgets
        elif isinstance(widget, QTableWidget):
            sanitized_count += _sanitize_table_widget(widget, fix_mojibake)
        
        # Combo boxes
        elif isinstance(widget, QComboBox):
            for i in range(widget.count()):
                original_text = widget.itemText(i)
                if original_text:
                    sanitized_text = normalize_text_for_ui(original_text, fix_mojibake)
                    if sanitized_text != original_text:
                        widget.setItemText(i, sanitized_text)
                        sanitized_count += 1
        
        # Window/widget titles
        if hasattr(widget, 'windowTitle'):
            original_title = widget.windowTitle()
            if original_title:
                sanitized_title = normalize_text_for_ui(original_title, fix_mojibake)
                if sanitized_title != original_title:
                    widget.setWindowTitle(sanitized_title)
                    sanitized_count += 1
    
    except Exception as e:
        # Log error but don't crash the UI
        print(f"Warning: Error sanitizing widget {type(widget).__name__}: {e}")
    
    return sanitized_count


def _sanitize_tree_widget(tree_widget: QTreeWidget, fix_mojibake: bool = True) -> int:
    """Sanitize all items in a tree widget."""
    sanitized_count = 0
    
    def sanitize_item(item: QTreeWidgetItem):
        nonlocal sanitized_count
        
        # Sanitize all columns of this item
        for col in range(item.columnCount()):
            original_text = item.text(col)
            if original_text:
                sanitized_text = normalize_text_for_ui(original_text, fix_mojibake)
                if sanitized_text != original_text:
                    item.setText(col, sanitized_text)
                    sanitized_count += 1
        
        # Recursively sanitize children
        for i in range(item.childCount()):
            child = item.child(i)
            if child:
                sanitize_item(child)
    
    # Sanitize header labels
    for col in range(tree_widget.columnCount()):
        header_item = tree_widget.headerItem()
        if header_item:
            original_text = header_item.text(col)
            if original_text:
                sanitized_text = normalize_text_for_ui(original_text, fix_mojibake)
                if sanitized_text != original_text:
                    header_item.setText(col, sanitized_text)
                    sanitized_count += 1
    
    # Sanitize all root items
    for i in range(tree_widget.topLevelItemCount()):
        item = tree_widget.topLevelItem(i)
        if item:
            sanitize_item(item)
    
    return sanitized_count


def _sanitize_table_widget(table_widget: QTableWidget, fix_mojibake: bool = True) -> int:
    """Sanitize all items in a table widget."""
    sanitized_count = 0
    
    # Sanitize horizontal headers
    for col in range(table_widget.columnCount()):
        header_item = table_widget.horizontalHeaderItem(col)
        if header_item and header_item.text():
            original_text = header_item.text()
            sanitized_text = normalize_text_for_ui(original_text, fix_mojibake)
            if sanitized_text != original_text:
                header_item.setText(sanitized_text)
                sanitized_count += 1
    
    # Sanitize vertical headers
    for row in range(table_widget.rowCount()):
        header_item = table_widget.verticalHeaderItem(row)
        if header_item and header_item.text():
            original_text = header_item.text()
            sanitized_text = normalize_text_for_ui(original_text, fix_mojibake)
            if sanitized_text != original_text:
                header_item.setText(sanitized_text)
                sanitized_count += 1
    
    # Sanitize all cell items
    for row in range(table_widget.rowCount()):
        for col in range(table_widget.columnCount()):
            item = table_widget.item(row, col)
            if item and item.text():
                original_text = item.text()
                sanitized_text = normalize_text_for_ui(original_text, fix_mojibake)
                if sanitized_text != original_text:
                    item.setText(sanitized_text)
                    sanitized_count += 1
    
    return sanitized_count


def sanitize_text_safe(text: str) -> str:
    """
    Safe text sanitization that never raises exceptions.
    
    Args:
        text: Text to sanitize
        
    Returns:
        Sanitized text, or original text if sanitization fails
    """
    if not text:
        return text
    
    try:
        return normalize_text_for_ui(text, fix_mojibake=True)
    except Exception:
        # Return original text if sanitization fails
        return text


def safe_emoji(text: str) -> str:
    """
    Alias for sanitize_text_safe for backward compatibility.
    
    Args:
        text: Text to sanitize
        
    Returns:
        Sanitized text
    """
    return sanitize_text_safe(text)