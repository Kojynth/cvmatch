"""Safe logging package.

If this package is imported accidentally as top-level ``logging`` (for example
when ``python app/main.py`` puts ``app/`` first on ``sys.path``), proxy to the
stdlib logging module to avoid circular import crashes.
"""

if __name__ == "logging":
    import importlib.util
    import sysconfig
    from pathlib import Path

    stdlib_init = Path(sysconfig.get_path("stdlib")) / "logging" / "__init__.py"
    spec = importlib.util.spec_from_file_location("_stdlib_logging_proxy", stdlib_init)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to locate stdlib logging module at {stdlib_init}")
    stdlib_logging = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(stdlib_logging)
    globals().update(stdlib_logging.__dict__)
else:
    from .safe_logger import (
        SafeLoggerAdapter,
        configure_logging_with_pii_protection,
        get_logger,
        get_safe_logger,
    )

    __all__ = [
        "get_safe_logger",
        "get_logger",
        "SafeLoggerAdapter",
        "configure_logging_with_pii_protection",
    ]