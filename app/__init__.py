"""
CVMatch Application Package
===========================

Package principal de l'application CVMatch contenant:
- models: Modèles de données SQLModel
- views: Interfaces utilisateur PySide6
- controllers: Logique métier
- workers: Tâches asynchrones et traitement
- utils: Utilitaires et helpers
- widgets: Composants UI réutilisables
- logging: Système de logging sécurisé
- ml: Modèles et traitement IA/ML
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
import types
from pathlib import Path

from . import config as _root_config

__version__ = "2.0.0"

# ---------------------------------------------------------------------------
# Legacy module shims (keeping app.config.feature_flags importable)
# ---------------------------------------------------------------------------

_config_package = types.ModuleType("app.config")
_config_package.__dict__.update(_root_config.__dict__)

_feature_flags_module = None
_feature_flags_path = Path(__file__).with_name("config").joinpath("feature_flags.py")

if _feature_flags_path.exists():
    try:
        spec = importlib.util.spec_from_file_location(
            "app.config.feature_flags", _feature_flags_path
        )
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            sys.modules["app.config.feature_flags"] = module
            spec.loader.exec_module(module)  # type: ignore[union-attr]
            _feature_flags_module = module
    except Exception:  # pragma: no cover - optional dependency
        sys.modules.pop("app.config.feature_flags", None)
        _feature_flags_module = None

if _feature_flags_module is None:
    try:
        _feature_flags_module = importlib.import_module("app.utils.feature_flags")
        sys.modules.setdefault("app.config.feature_flags", _feature_flags_module)
    except Exception:  # pragma: no cover - optional dependency
        _feature_flags_module = None

if _feature_flags_module is not None:
    _config_package.feature_flags = _feature_flags_module

sys.modules.setdefault("app.config", _config_package)
