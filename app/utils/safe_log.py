"""
Safe Logging Helpers for Critical Sites
======================================

This module provides convenient helper functions for PII-safe logging at critical
sites throughout the CVMatch application. These helpers wrap common logging patterns
and ensure PII is automatically sanitized before logging.

Features:
- Automatic PII sanitization for all log messages
- Specialized logging for file operations, user data, and system events
- Performance-optimized with caching
- Consistent log formatting across the application
- Error-safe operation (fail-closed security)
"""

import logging
import traceback
from typing import Any, Dict, Optional, Union, List
from pathlib import Path

from .log_sanitizer import get_sanitizer
from .redactor import safe_path_for_log, safe_repr, sanitize_dict_for_log
from ..config import DEFAULT_PII_CONFIG


class SafeLogger:
    """
    PII-safe logger wrapper that sanitizes all messages before logging.
    
    This class wraps a standard Python logger and ensures all messages
    are automatically sanitized for PII before being logged.
    """
    
    def __init__(self, logger: logging.Logger, strict: bool = False):
        """
        Initialize the safe logger.
        
        Args:
            logger: The underlying logger to wrap
            strict: Enable strict mode for additional PII detection
        """
        self.logger = logger
        self.strict = strict
        self._sanitizer = get_sanitizer(strict=strict)
    
    def _safe_log(self, level: int, msg: str, *args, **kwargs) -> None:
        """
        Safely log a message with PII sanitization.
        
        Args:
            level: Logging level
            msg: Message to log
            *args: Message formatting arguments
            **kwargs: Additional logging parameters
        """
        try:
            # Sanitize the message
            safe_msg = self._sanitizer.sanitize_text(str(msg))
            
            # Sanitize arguments if present
            if args:
                safe_args = []
                for arg in args:
                    if isinstance(arg, str):
                        safe_args.append(self._sanitizer.sanitize_text(arg))
                    else:
                        safe_args.append(safe_repr(arg))
                args = tuple(safe_args)
            
            # Log the sanitized message
            self.logger.log(level, safe_msg, *args, **kwargs)
            
        except Exception as e:
            # Fail-closed: log the error but don't expose potentially unsafe content
            error_msg = f"[SAFE-LOG-ERROR:{type(e).__name__}] <message redacted for safety>"
            self.logger.log(level, error_msg)
    
    def debug(self, msg: str, *args, **kwargs) -> None:
        """Log a debug message safely."""
        self._safe_log(logging.DEBUG, msg, *args, **kwargs)
    
    def info(self, msg: str, *args, **kwargs) -> None:
        """Log an info message safely."""
        self._safe_log(logging.INFO, msg, *args, **kwargs)
    
    def warning(self, msg: str, *args, **kwargs) -> None:
        """Log a warning message safely."""
        self._safe_log(logging.WARNING, msg, *args, **kwargs)
    
    def error(self, msg: str, *args, **kwargs) -> None:
        """Log an error message safely."""
        self._safe_log(logging.ERROR, msg, *args, **kwargs)
    
    def critical(self, msg: str, *args, **kwargs) -> None:
        """Log a critical message safely."""
        self._safe_log(logging.CRITICAL, msg, *args, **kwargs)
    
    def exception(self, msg: str, *args, **kwargs) -> None:
        """Log an exception message safely."""
        # Sanitize exception information
        exc_info = kwargs.pop('exc_info', True)
        if exc_info:
            # Get sanitized traceback
            tb_lines = traceback.format_exc().splitlines()
            sanitized_tb = []
            for line in tb_lines:
                sanitized_tb.append(self._sanitizer.sanitize_text(line))
            
            # Add sanitized exception info to the message
            safe_msg = self._sanitizer.sanitize_text(str(msg))
            full_msg = f"{safe_msg}\n" + "\n".join(sanitized_tb)
            self.logger.error(full_msg, *args, **kwargs)
        else:
            self.error(msg, *args, **kwargs)


# Global safe loggers cache
_safe_loggers: Dict[str, SafeLogger] = {}


def get_safe_logger(name: str, strict: bool = False) -> SafeLogger:
    """
    Get or create a safe logger for the given name.
    
    Args:
        name: Logger name
        strict: Enable strict mode
        
    Returns:
        PII-safe logger instance
    """
    cache_key = f"{name}_{strict}"
    if cache_key not in _safe_loggers:
        base_logger = logging.getLogger(name)
        _safe_loggers[cache_key] = SafeLogger(base_logger, strict=strict)
    
    return _safe_loggers[cache_key]


# Specialized logging functions for common use cases

def log_file_operation(operation: str, file_path: Union[str, Path], 
                      success: bool = True, 
                      logger_name: str = "cvmatch.files",
                      details: Optional[str] = None) -> None:
    """
    Log file operations with PII-safe path handling.
    
    Args:
        operation: Description of the operation (e.g., "loaded", "saved", "deleted")
        file_path: Path to the file
        success: Whether the operation succeeded
        logger_name: Name of the logger to use
        details: Additional details to log
    """
    safe_logger = get_safe_logger(logger_name)
    safe_path = safe_path_for_log(str(file_path))
    
    status = "successfully" if success else "failed to"
    level_func = safe_logger.info if success else safe_logger.error
    
    msg = f"File operation: {status} {operation} {safe_path}"
    if details:
        sanitized_details = get_sanitizer().sanitize_text(details)
        msg += f" - {sanitized_details}"
    
    level_func(msg)


def log_user_data_processing(operation: str, data_type: str, 
                           record_count: Optional[int] = None,
                           success: bool = True,
                           logger_name: str = "cvmatch.data",
                           sample_data: Optional[Dict] = None) -> None:
    """
    Log user data processing operations safely.
    
    Args:
        operation: Description of the operation (e.g., "extracted", "validated", "stored")
        data_type: Type of data being processed (e.g., "experience", "education", "personal_info")
        record_count: Number of records processed
        success: Whether the operation succeeded
        logger_name: Name of the logger to use
        sample_data: Sample data (will be sanitized automatically)
    """
    safe_logger = get_safe_logger(logger_name, strict=True)  # Use strict mode for user data
    
    status = "successfully" if success else "failed to"
    level_func = safe_logger.info if success else safe_logger.error
    
    msg = f"Data processing: {status} {operation} {data_type}"
    if record_count is not None:
        msg += f" ({record_count} records)"
    
    if sample_data:
        sanitized_sample = sanitize_dict_for_log(
            sample_data, 
            salt=DEFAULT_PII_CONFIG.HASH_SALT,
            sensitive_keys={'name', 'email', 'phone', 'address', 'company', 'school'}
        )
        msg += f" - Sample: {sanitized_sample}"
    
    level_func(msg)


def log_model_operation(model_name: str, operation: str, 
                       input_sample: Optional[str] = None,
                       output_sample: Optional[str] = None,
                       performance_ms: Optional[float] = None,
                       success: bool = True,
                       logger_name: str = "cvmatch.models") -> None:
    """
    Log AI model operations with input/output sanitization.
    
    Args:
        model_name: Name of the model
        operation: Operation performed (e.g., "inference", "loading", "initialization")
        input_sample: Sample input text (will be sanitized)
        output_sample: Sample output text (will be sanitized)  
        performance_ms: Processing time in milliseconds
        success: Whether the operation succeeded
        logger_name: Name of the logger to use
    """
    safe_logger = get_safe_logger(logger_name)
    
    status = "successfully" if success else "failed to"
    level_func = safe_logger.info if success else safe_logger.error
    
    msg = f"Model operation: {status} {operation} with {model_name}"
    
    if performance_ms is not None:
        msg += f" ({performance_ms:.1f}ms)"
    
    if input_sample:
        sanitized_input = get_sanitizer().sanitize_text(input_sample[:100])
        msg += f" - Input: {sanitized_input}"
    
    if output_sample:
        sanitized_output = get_sanitizer().sanitize_text(output_sample[:100])
        msg += f" - Output: {sanitized_output}"
    
    level_func(msg)


def log_system_event(event_type: str, description: str,
                    metadata: Optional[Dict[str, Any]] = None,
                    severity: str = "info",
                    logger_name: str = "cvmatch.system") -> None:
    """
    Log system events with metadata sanitization.
    
    Args:
        event_type: Type of event (e.g., "startup", "shutdown", "config_change", "error")
        description: Description of the event
        metadata: Additional event metadata (will be sanitized)
        severity: Log severity level ("debug", "info", "warning", "error", "critical")
        logger_name: Name of the logger to use
    """
    safe_logger = get_safe_logger(logger_name)
    
    # Get appropriate logging function
    log_func = getattr(safe_logger, severity.lower(), safe_logger.info)
    
    msg = f"System event [{event_type}]: {description}"
    
    if metadata:
        sanitized_metadata = sanitize_dict_for_log(
            metadata,
            salt=DEFAULT_PII_CONFIG.HASH_SALT
        )
        msg += f" - Metadata: {sanitized_metadata}"
    
    log_func(msg)


def log_performance_metric(metric_name: str, value: Union[int, float],
                          unit: str = "", context: Optional[Dict] = None,
                          logger_name: str = "cvmatch.performance") -> None:
    """
    Log performance metrics safely.
    
    Args:
        metric_name: Name of the metric
        value: Metric value
        unit: Unit of measurement
        context: Additional context (will be sanitized)
        logger_name: Name of the logger to use
    """
    safe_logger = get_safe_logger(logger_name)
    
    msg = f"Performance metric: {metric_name} = {value}"
    if unit:
        msg += f" {unit}"
    
    if context:
        sanitized_context = sanitize_dict_for_log(
            context,
            salt=DEFAULT_PII_CONFIG.HASH_SALT
        )
        msg += f" (context: {sanitized_context})"
    
    safe_logger.info(msg)


def log_security_event(event_type: str, description: str,
                      risk_level: str = "medium",
                      metadata: Optional[Dict] = None,
                      logger_name: str = "cvmatch.security") -> None:
    """
    Log security-related events with appropriate handling.
    
    Args:
        event_type: Type of security event (e.g., "pii_detected", "access_denied", "validation_failed")
        description: Description of the event
        risk_level: Risk level ("low", "medium", "high", "critical")
        metadata: Event metadata (will be heavily sanitized)
        logger_name: Name of the logger to use
    """
    safe_logger = get_safe_logger(logger_name, strict=True)  # Always use strict mode for security
    
    # Map risk levels to log levels
    level_mapping = {
        "low": safe_logger.info,
        "medium": safe_logger.warning, 
        "high": safe_logger.error,
        "critical": safe_logger.critical
    }
    
    log_func = level_mapping.get(risk_level.lower(), safe_logger.warning)
    
    msg = f"Security event [{event_type}] RISK:{risk_level.upper()}: {description}"
    
    if metadata:
        # Extra sanitization for security events
        sanitized_metadata = sanitize_dict_for_log(
            metadata,
            salt=DEFAULT_PII_CONFIG.HASH_SALT,
            sensitive_keys={'user', 'name', 'email', 'phone', 'address', 'file', 'path', 'content', 'data'}
        )
        msg += f" - Details: {sanitized_metadata}"
    
    log_func(msg)


# Decorator for automatic logging of function calls
def safe_log_calls(logger_name: str = None, log_args: bool = False, log_result: bool = False):
    """
    Decorator to automatically log function calls with PII sanitization.
    
    Args:
        logger_name: Name of logger to use (defaults to module name)
        log_args: Whether to log function arguments
        log_result: Whether to log function result
    """
    def decorator(func):
        import functools
        
        nonlocal logger_name
        if logger_name is None:
            logger_name = f"cvmatch.{func.__module__}"
        
        safe_logger = get_safe_logger(logger_name)
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            func_name = f"{func.__module__}.{func.__name__}"
            
            try:
                # Log function entry
                msg = f"Entering {func_name}"
                if log_args and (args or kwargs):
                    safe_args = [safe_repr(arg) for arg in args]
                    safe_kwargs = {k: safe_repr(v) for k, v in kwargs.items()}
                    msg += f" with args={safe_args}, kwargs={safe_kwargs}"
                safe_logger.debug(msg)
                
                # Execute function
                result = func(*args, **kwargs)
                
                # Log function exit
                msg = f"Exiting {func_name}"
                if log_result:
                    msg += f" with result={safe_repr(result)}"
                safe_logger.debug(msg)
                
                return result
                
            except Exception as e:
                safe_logger.exception(f"Exception in {func_name}: {type(e).__name__}")
                raise
        
        return wrapper
    return decorator


# Context manager for logging code blocks
class SafeLogContext:
    """Context manager for safe logging of code blocks."""
    
    def __init__(self, description: str, logger_name: str = "cvmatch.context",
                 log_duration: bool = True, log_success: bool = True):
        """
        Initialize the logging context.
        
        Args:
            description: Description of the code block
            logger_name: Logger to use
            log_duration: Whether to log execution duration
            log_success: Whether to log success/failure
        """
        self.description = description
        self.log_duration = log_duration
        self.log_success = log_success
        self.safe_logger = get_safe_logger(logger_name)
        self.start_time = None
    
    def __enter__(self):
        """Enter the context."""
        import time
        self.start_time = time.time()
        self.safe_logger.info(f"Starting: {self.description}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit the context."""
        import time
        
        if self.start_time and self.log_duration:
            duration_ms = (time.time() - self.start_time) * 1000
            duration_info = f" (took {duration_ms:.1f}ms)"
        else:
            duration_info = ""
        
        if exc_type is None:
            if self.log_success:
                self.safe_logger.info(f"Completed: {self.description}{duration_info}")
        else:
            self.safe_logger.error(f"Failed: {self.description}{duration_info} - {exc_type.__name__}")
        
        return False  # Don't suppress exceptions


# Convenience functions for quick safe logging
def safe_debug(msg: str, logger_name: str = "cvmatch") -> None:
    """Quick safe debug logging."""
    get_safe_logger(logger_name).debug(msg)


def safe_info(msg: str, logger_name: str = "cvmatch") -> None:
    """Quick safe info logging.""" 
    get_safe_logger(logger_name).info(msg)


def safe_warning(msg: str, logger_name: str = "cvmatch") -> None:
    """Quick safe warning logging."""
    get_safe_logger(logger_name).warning(msg)


def safe_error(msg: str, logger_name: str = "cvmatch") -> None:
    """Quick safe error logging."""
    get_safe_logger(logger_name).error(msg)


def safe_critical(msg: str, logger_name: str = "cvmatch") -> None:
    """Quick safe critical logging."""
    get_safe_logger(logger_name).critical(msg)