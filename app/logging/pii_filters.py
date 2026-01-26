"""
PII Redaction Filters and Formatters for Python Logging System
=============================================================

This module provides logging filters and formatters that automatically redact PII
from log records before they are written to handlers. It integrates seamlessly
with Python's logging framework and uses the high-performance PII sanitizer.

Features:
- PiiRedactionFilter: Sanitizes all log record attributes containing text
- PiiRedactingFormatter: Formatter that applies PII sanitization to messages
- Thread-safe operation with shared sanitizer instances
- Configurable strictness levels
- Performance monitoring and metrics
- Fail-closed error handling
"""

import logging
import time
from typing import Dict, Any, Optional
from functools import lru_cache

from ..utils.log_sanitizer import get_sanitizer, PiiSanitizer
from ..config import DEFAULT_PII_CONFIG


class PiiRedactionFilter(logging.Filter):
    """
    Logging filter that sanitizes PII from log records.
    
    This filter processes log records before they reach handlers,
    sanitizing any PII found in the message, arguments, and other
    string attributes of the log record.
    """
    
    def __init__(self, name: str = "", strict: bool = False):
        """
        Initialize the PII redaction filter.
        
        Args:
            name: Filter name (standard logging.Filter parameter)
            strict: Enable strict mode for additional PII detection
        """
        super().__init__(name)
        self.strict = strict
        self._sanitizer = get_sanitizer(strict=strict)
        self._filter_count = 0
        self._sanitization_count = 0
        self._total_time = 0.0
    
    def filter(self, record: logging.LogRecord) -> bool:
        """
        Filter a log record, sanitizing any PII found.
        
        Args:
            record: The log record to filter
            
        Returns:
            True (record is always passed through, but sanitized)
        """
        start_time = time.time()
        self._filter_count += 1
        
        try:
            # Sanitize the main message
            if hasattr(record, 'msg') and record.msg:
                sanitized_msg = self._sanitize_safe(str(record.msg))
                if sanitized_msg != str(record.msg):
                    record.msg = sanitized_msg
                    self._sanitization_count += 1
            
            # Sanitize arguments if present
            if hasattr(record, 'args') and record.args:
                sanitized_args = []
                for arg in record.args:
                    if isinstance(arg, str):
                        sanitized_arg = self._sanitize_safe(arg)
                        sanitized_args.append(sanitized_arg)
                        if sanitized_arg != arg:
                            self._sanitization_count += 1
                    else:
                        sanitized_args.append(arg)
                record.args = tuple(sanitized_args)
            
            # Sanitize other string attributes that might contain PII
            for attr in ['pathname', 'filename', 'funcName', 'module']:
                if hasattr(record, attr):
                    value = getattr(record, attr)
                    if isinstance(value, str):
                        sanitized_value = self._sanitize_safe(value)
                        if sanitized_value != value:
                            setattr(record, attr, sanitized_value)
                            self._sanitization_count += 1
            
            # Handle exception info if present
            if record.exc_text:
                sanitized_exc = self._sanitize_safe(record.exc_text)
                if sanitized_exc != record.exc_text:
                    record.exc_text = sanitized_exc
                    self._sanitization_count += 1
        
        except Exception as e:
            # Fail-closed: add error info to record but don't block logging
            error_msg = f"[PII-FILTER-ERROR: {type(e).__name__}]"
            if hasattr(record, 'msg'):
                record.msg = f"{error_msg} {record.msg}"
            else:
                record.msg = error_msg
        
        finally:
            elapsed = time.time() - start_time
            self._total_time += elapsed
        
        return True
    
    def _sanitize_safe(self, text: str) -> str:
        """
        Safely sanitize text with error handling.
        
        Args:
            text: Text to sanitize
            
        Returns:
            Sanitized text or error placeholder
        """
        try:
            return self._sanitizer.sanitize_text(text)
        except Exception:
            return f"[PII-SANITIZATION-ERROR]"
    
    def get_stats(self) -> Dict[str, Any]:
        """Get filter performance statistics."""
        return {
            "filter_count": self._filter_count,
            "sanitization_count": self._sanitization_count,
            "total_time_seconds": self._total_time,
            "avg_time_ms": (self._total_time / max(self._filter_count, 1)) * 1000,
            "sanitization_rate": self._sanitization_count / max(self._filter_count, 1)
        }


class PiiRedactingFormatter(logging.Formatter):
    """
    Logging formatter that sanitizes PII from formatted messages.
    
    This formatter wraps the standard logging.Formatter and applies
    PII sanitization after formatting but before output. It's useful
    as a secondary safety measure or when filters aren't suitable.
    """
    
    def __init__(self, fmt=None, datefmt=None, style='%', validate=True, strict: bool = False):
        """
        Initialize the PII redacting formatter.
        
        Args:
            fmt: Format string (standard logging.Formatter parameter)
            datefmt: Date format string (standard logging.Formatter parameter)
            style: Format style (standard logging.Formatter parameter)
            validate: Validate format string (standard logging.Formatter parameter)
            strict: Enable strict mode for additional PII detection
        """
        super().__init__(fmt, datefmt, style, validate)
        self.strict = strict
        self._sanitizer = get_sanitizer(strict=strict)
        self._format_count = 0
        self._sanitization_count = 0
        self._total_time = 0.0
    
    def format(self, record: logging.LogRecord) -> str:
        """
        Format a log record, sanitizing PII from the result.
        
        Args:
            record: The log record to format
            
        Returns:
            Formatted and PII-sanitized log message
        """
        start_time = time.time()
        self._format_count += 1
        
        try:
            # Get the standard formatted message
            formatted_message = super().format(record)
            
            # Apply PII sanitization
            sanitized_message = self._sanitizer.sanitize_text(formatted_message)
            
            if sanitized_message != formatted_message:
                self._sanitization_count += 1
            
            return sanitized_message
        
        except Exception as e:
            # Fail-closed: return error message instead of potentially unsafe content
            self._sanitization_count += 1
            return f"[FORMAT-ERROR:{type(e).__name__}] {record.levelname}: <message redacted for safety>"
        
        finally:
            elapsed = time.time() - start_time
            self._total_time += elapsed
    
    def get_stats(self) -> Dict[str, Any]:
        """Get formatter performance statistics."""
        return {
            "format_count": self._format_count,
            "sanitization_count": self._sanitization_count,
            "total_time_seconds": self._total_time,
            "avg_time_ms": (self._total_time / max(self._format_count, 1)) * 1000,
            "sanitization_rate": self._sanitization_count / max(self._format_count, 1)
        }


class PiiContextFilter(logging.Filter):
    """
    Advanced PII filter that adds context information about redacted content.
    
    This filter not only sanitizes PII but also adds metadata about what
    was found and redacted, useful for security auditing and debugging.
    """
    
    def __init__(self, name: str = "", strict: bool = False, add_context: bool = True):
        """
        Initialize the context-aware PII filter.
        
        Args:
            name: Filter name
            strict: Enable strict mode
            add_context: Whether to add PII context information to records
        """
        super().__init__(name)
        self.strict = strict
        self.add_context = add_context
        self._sanitizer = get_sanitizer(strict=strict)
    
    def filter(self, record: logging.LogRecord) -> bool:
        """
        Filter a log record with context tracking.
        
        Args:
            record: The log record to filter
            
        Returns:
            True (record is always passed through, but sanitized)
        """
        try:
            original_msg = str(record.msg) if record.msg else ""
            
            # Get sanitized message and PII metrics
            sanitized_msg, pii_counts = self._sanitizer.sanitize_mapping(original_msg)
            
            # Update record with sanitized message
            record.msg = sanitized_msg
            
            # Add context information if requested and PII was found
            if self.add_context and pii_counts:
                pii_summary = ", ".join(f"{kind}:{count}" for kind, count in pii_counts.items())
                record.pii_redacted = pii_summary
                record.pii_count = sum(pii_counts.values())
            else:
                record.pii_redacted = None
                record.pii_count = 0
        
        except Exception as e:
            # Fail-closed handling
            record.msg = f"[PII-CONTEXT-ERROR: {type(e).__name__}]"
            record.pii_redacted = "error"
            record.pii_count = -1
        
        return True


# Factory functions for easy filter/formatter creation

def create_pii_filter(strict: bool = False) -> PiiRedactionFilter:
    """
    Create a standard PII redaction filter.
    
    Args:
        strict: Enable strict mode for additional PII detection
        
    Returns:
        Configured PII redaction filter
    """
    return PiiRedactionFilter(strict=strict)


def create_pii_formatter(fmt: Optional[str] = None, strict: bool = False) -> PiiRedactingFormatter:
    """
    Create a PII redacting formatter.
    
    Args:
        fmt: Format string (uses default if None)
        strict: Enable strict mode for additional PII detection
        
    Returns:
        Configured PII redacting formatter
    """
    if fmt is None:
        fmt = "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d - %(message)s"
    
    return PiiRedactingFormatter(fmt=fmt, strict=strict)


def create_context_filter(strict: bool = False, add_context: bool = True) -> PiiContextFilter:
    """
    Create a context-aware PII filter.
    
    Args:
        strict: Enable strict mode
        add_context: Whether to add PII context to log records
        
    Returns:
        Configured context PII filter
    """
    return PiiContextFilter(strict=strict, add_context=add_context)


# Convenience function to add PII protection to existing logger
def add_pii_protection(logger: logging.Logger, 
                      use_filter: bool = True, 
                      use_formatter: bool = False,
                      strict: bool = False) -> None:
    """
    Add PII protection to an existing logger.
    
    Args:
        logger: Logger to protect
        use_filter: Whether to add PII redaction filter
        use_formatter: Whether to replace formatters with PII-safe versions
        strict: Enable strict mode
    """
    if use_filter:
        pii_filter = create_pii_filter(strict=strict)
        logger.addFilter(pii_filter)
    
    if use_formatter:
        for handler in logger.handlers:
            if handler.formatter:
                # Preserve original format string if possible
                original_fmt = getattr(handler.formatter, '_fmt', None)
                pii_formatter = create_pii_formatter(fmt=original_fmt, strict=strict)
                handler.setFormatter(pii_formatter)


# Global registry for tracking active filters (for monitoring)
_active_filters: Dict[str, PiiRedactionFilter] = {}
_active_formatters: Dict[str, PiiRedactingFormatter] = {}


def register_pii_component(component, name: str = None) -> None:
    """Register a PII component for monitoring."""
    if name is None:
        name = f"{type(component).__name__}_{id(component)}"
    
    if isinstance(component, PiiRedactionFilter):
        _active_filters[name] = component
    elif isinstance(component, PiiRedactingFormatter):
        _active_formatters[name] = component


def get_pii_logging_stats() -> Dict[str, Any]:
    """Get comprehensive statistics for all registered PII logging components."""
    stats = {
        "filters": {name: filter_obj.get_stats() for name, filter_obj in _active_filters.items()},
        "formatters": {name: fmt.get_stats() for name, fmt in _active_formatters.items()},
        "summary": {
            "active_filters": len(_active_filters),
            "active_formatters": len(_active_formatters),
            "total_filter_calls": sum(f.get_stats()["filter_count"] for f in _active_filters.values()),
            "total_formatter_calls": sum(f.get_stats()["format_count"] for f in _active_formatters.values())
        }
    }
    return stats


# Test functions for validation
def test_pii_filter():
    """Test function to validate PII filter functionality."""
    import sys
    
    # Create test logger
    test_logger = logging.getLogger("pii_filter_test")
    test_logger.setLevel(logging.DEBUG)
    
    # Add console handler with PII protection
    console_handler = logging.StreamHandler(sys.stdout)
    pii_filter = create_pii_filter(strict=False)
    pii_formatter = create_pii_formatter(strict=False)
    
    console_handler.addFilter(pii_filter)
    console_handler.setFormatter(pii_formatter)
    test_logger.addHandler(console_handler)
    
    # Test messages with PII
    test_messages = [
        "Processing user Test User",
        "Email sent to user@example.com",
        "File loaded from C:\\Users\\username\\Documents\\test.pdf",
        "+33 6 12 34 56 78 called for support",
        "Address: 123 Example St 00000 City",
        "Normal log message without PII"
    ]
    
    print("=== PII Filter Test Results ===")
    for i, msg in enumerate(test_messages, 1):
        test_logger.info(f"Test {i}: {msg}")
    
    # Print statistics
    filter_stats = pii_filter.get_stats()
    formatter_stats = pii_formatter.get_stats()
    
    print(f"\nFilter Stats: {filter_stats}")
    print(f"Formatter Stats: {formatter_stats}")


if __name__ == "__main__":
    test_pii_filter()
