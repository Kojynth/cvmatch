#!/usr/bin/env python3
"""
Windows-Safe Emoji Sanitizer for Logging
========================================
Prevents UnicodeEncodeError on Windows cp1252 consoles by replacing emojis with ASCII tokens.
"""

import os
import sys
import logging
from typing import Dict


# Emoji to ASCII token mapping for Windows cp1252 compatibility
EMOJI_REPLACEMENTS: Dict[str, str] = {
    "🎯": "[TARGET]",
    "📦": "[PACKAGE]", 
    "📱": "[MOBILE]",
    "🚀": "[ROCKET]",
    "✅": "[SUCCESS]",
    "⚠️": "[WARNING]",
    "❌": "[ERROR]",
    "🔧": "[CONFIG]",
    "💾": "[DISK]",
    "📊": "[CHART]",
    "🆔": "[ID]",
    "🏠": "[HOME]",
    "🔒": "[SECURE]",
    "🔓": "[UNSECURE]",
    "📁": "[FOLDER]",
    "🛠️": "[TOOL]",
    "🎨": "[STYLE]",
    "🎭": "[MASK]",
    "🔍": "[SEARCH]",
    "📝": "[DOCUMENT]",
    "💻": "[COMPUTER]",
    "🌐": "[NETWORK]",
    "⚙️": "[GEAR]",
    "🧪": "[TEST]",
    "🎉": "[CELEBRATION]",
    "👋": "[WAVE]",
    "🔚": "[END]"
}


def sanitize_emojis_for_logging(message: str) -> str:
    """
    Replace emojis in a message with ASCII tokens safe for Windows cp1252 consoles.
    
    Args:
        message: The original log message that may contain emojis
        
    Returns:
        Message with emojis replaced by ASCII tokens
    """
    if not message or not isinstance(message, str):
        return message
    
    sanitized_message = message
    for emoji, replacement in EMOJI_REPLACEMENTS.items():
        sanitized_message = sanitized_message.replace(emoji, replacement)
    
    return sanitized_message


def should_sanitize_emojis() -> bool:
    """
    Determine if emoji sanitization should be applied based on environment.
    
    Returns:
        True if running on Windows with cp1252 console or forced via env var
    """
    # Check for manual override via environment variable
    emoji_env = os.getenv("CVMATCH_LOG_EMOJI", "").strip().lower()
    if emoji_env in ("0", "false", "no", "off"):
        return True
    elif emoji_env in ("1", "true", "yes", "on"):
        return False
    
    # Auto-detect Windows cp1252 console
    return _is_windows_cp1252_console()


def _is_windows_cp1252_console() -> bool:
    """
    Check if we're on Windows with a cp1252 console that can't handle emojis.
    
    Returns:
        True if Windows console likely uses cp1252 encoding
    """
    if os.name != "nt":
        return False
    
    # Check stdout encoding
    stdout_encoding = getattr(sys.stdout, "encoding", "") or ""
    stderr_encoding = getattr(sys.stderr, "encoding", "") or ""
    
    # Common Windows encodings that struggle with emojis
    problematic_encodings = {
        "cp1252", "cp1251", "cp850", "cp437", "latin1", "iso-8859-1"
    }
    
    return (
        stdout_encoding.lower() in problematic_encodings or
        stderr_encoding.lower() in problematic_encodings or
        # Fallback: if encoding is empty or unknown on Windows, assume cp1252
        (not stdout_encoding and not stderr_encoding)
    )


class EmojiSanitizingFormatter(logging.Formatter):
    """
    Logging formatter that sanitizes emojis for Windows cp1252 compatibility.
    
    This formatter wraps the standard logging.Formatter and applies emoji
    sanitization when needed, while preserving all other formatting behavior.
    """
    
    def __init__(self, fmt=None, datefmt=None, style='%', validate=True):
        super().__init__(fmt, datefmt, style, validate)
        self._should_sanitize = should_sanitize_emojis()
    
    def format(self, record: logging.LogRecord) -> str:
        """
        Format a log record, sanitizing emojis if necessary.
        
        Args:
            record: The log record to format
            
        Returns:
            Formatted log message with emojis sanitized if needed
        """
        # Get the standard formatted message
        formatted_message = super().format(record)
        
        # Apply emoji sanitization if needed
        if self._should_sanitize:
            formatted_message = sanitize_emojis_for_logging(formatted_message)
        
        return formatted_message


def create_windows_safe_console_handler(level=logging.INFO, fmt=None) -> logging.StreamHandler:
    """
    Create a console handler that's safe for Windows cp1252 consoles.
    
    Args:
        level: Logging level for the handler
        fmt: Format string for the formatter
        
    Returns:
        StreamHandler configured with emoji sanitization
    """
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setLevel(level)
    
    # Use default format if none provided
    if fmt is None:
        fmt = "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d - %(message)s"
    
    formatter = EmojiSanitizingFormatter(fmt)
    handler.setFormatter(formatter)
    
    return handler


def create_utf8_file_handler(filepath: str, level=logging.INFO, fmt=None) -> logging.FileHandler:
    """
    Create a UTF-8 file handler that preserves emojis in log files.
    
    Args:
        filepath: Path to the log file
        level: Logging level for the handler
        fmt: Format string for the formatter
        
    Returns:
        FileHandler configured with UTF-8 encoding
    """
    handler = logging.FileHandler(filepath, encoding="utf-8")
    handler.setLevel(level)
    
    # Use default format if none provided
    if fmt is None:
        fmt = "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d - %(message)s"
    
    # File logs keep emojis - use standard formatter
    formatter = logging.Formatter(fmt)
    handler.setFormatter(formatter)
    
    return handler


# Utility functions for manual testing
def test_emoji_sanitization():
    """Test function to verify emoji sanitization works correctly."""
    test_messages = [
        "🎯 Starting CVMatch application",
        "📦 Loading configuration files",
        "🚀 Launching main window",
        "✅ Profile setup completed successfully", 
        "⚠️ WeasyPrint not available",
        "❌ Database connection failed",
        "🔧 Configuring logging system",
        "Mixed message with 🎯 target and 📦 package emojis"
    ]
    
    print("Testing emoji sanitization:")
    print("=" * 50)
    
    for message in test_messages:
        sanitized = sanitize_emojis_for_logging(message)
        print(f"Original:  {message}")
        print(f"Sanitized: {sanitized}")
        print("-" * 30)


if __name__ == "__main__":
    # Run tests when executed directly
    test_emoji_sanitization()
    
    # Test environment detection
    print(f"\nEnvironment Detection:")
    print(f"OS: {os.name}")
    print(f"Should sanitize: {should_sanitize_emojis()}")
    print(f"Windows cp1252: {_is_windows_cp1252_console()}")
    print(f"Stdout encoding: {getattr(sys.stdout, 'encoding', 'unknown')}")
    print(f"Stderr encoding: {getattr(sys.stderr, 'encoding', 'unknown')}")
