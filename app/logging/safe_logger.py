# PATCH-PII: Logger sécurisé avec protection automatique des PII
import logging
from typing import Any, Dict
import sys
import os

# Import emoji sanitizer for Windows cp1252 compatibility
from .emoji_sanitizer import EmojiSanitizingFormatter, create_windows_safe_console_handler, create_utf8_file_handler

# Import relatif vers les modules PII
try:
    from ..config import PIIConfig, DEFAULT_PII_CONFIG
    from ..utils.pii import redact_all, has_pii
    from ..utils.redactor import truncate_for_log, safe_repr
except ImportError:
    # Fallback pour tests ou imports directs
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from config import PIIConfig, DEFAULT_PII_CONFIG
    from utils.pii import redact_all, has_pii
    from utils.redactor import truncate_for_log, safe_repr

class SafeLoggerAdapter(logging.LoggerAdapter):
    """Adaptateur de logger qui applique automatiquement la protection PII."""
    
    def __init__(self, logger: logging.Logger, extra: Dict[str, Any] = None, cfg: PIIConfig = None):
        super().__init__(logger, extra or {})
        self.cfg = cfg or DEFAULT_PII_CONFIG
        self._pii_detection_cache = {}  # Cache pour éviter les re-détections
    
    def process(self, msg, kwargs):
        """Traite le message avant logging en appliquant la protection PII si nécessaire."""
        # Ne pas traiter dans process() car ça interfère avec les overrides des méthodes
        # Laisser les overrides (info, debug, etc.) gérer le formatage
        
        # Traiter seulement les données extra si présentes
        if 'extra' in kwargs and isinstance(kwargs['extra'], dict):
            kwargs['extra'] = self._sanitize_extra(kwargs['extra'])
        
        return msg, kwargs
    
    def _sanitize_extra(self, extra: Dict[str, Any]) -> Dict[str, Any]:
        """Assainit les données extra du log."""
        if not self.cfg.should_redact():
            return extra
        
        sanitized = {}
        for key, value in extra.items():
            if isinstance(value, str) and has_pii(value):
                sanitized[key] = redact_all(value, salt=self.cfg.HASH_SALT)
            else:
                sanitized[key] = safe_repr(value) if isinstance(value, str) else value
        
        return sanitized
    
    def log_with_context(self, level: int, msg: str, context: Dict[str, Any] = None, **kwargs):
        """Log avec contexte supplémentaire, en appliquant la protection PII sur le contexte."""
        if context:
            sanitized_context = self._sanitize_extra(context)
            self.log(level, f"{msg} | context={sanitized_context}", **kwargs)
        else:
            self.log(level, msg, **kwargs)
    
    def debug_safe(self, msg: str, sensitive_data: Dict[str, Any] = None, **kwargs):
        """Log de debug avec données sensibles automatiquement protégées."""
        if sensitive_data:
            protected_data = self._sanitize_extra(sensitive_data)
            self.debug(f"{msg} | data={protected_data}", **kwargs)
        else:
            self.debug(msg, **kwargs)
    
    def info_safe(self, msg: str, sensitive_data: Dict[str, Any] = None, **kwargs):
        """Log d'info avec données sensibles automatiquement protégées."""
        if sensitive_data:
            protected_data = self._sanitize_extra(sensitive_data)
            self.info(f"{msg} | data={protected_data}", **kwargs)
        else:
            self.info(msg, **kwargs)
    
    def warn_safe(self, msg: str, sensitive_data: Dict[str, Any] = None, **kwargs):
        """Log de warning avec données sensibles automatiquement protégées."""
        if sensitive_data:
            protected_data = self._sanitize_extra(sensitive_data)
            self.warning(f"{msg} | data={protected_data}", **kwargs)
        else:
            self.warning(msg, **kwargs)
    
    def error_safe(self, msg: str, sensitive_data: Dict[str, Any] = None, **kwargs):
        """Log d'erreur avec données sensibles automatiquement protégées."""
        if sensitive_data:
            protected_data = self._sanitize_extra(sensitive_data)
            self.error(f"{msg} | data={protected_data}", **kwargs)
        else:
            self.error(msg, **kwargs)
    
    def info(self, msg, *args, **kwargs):
        """Override pour gérer format loguru {} et PII."""
        if args and isinstance(msg, str) and '{}' in msg:
            # Format loguru détecté, formater directement avec .format()
            try:
                # Appliquer redaction PII aux arguments seulement si nécessaire
                if self.cfg.should_redact():
                    safe_args = []
                    for arg in args:
                        if isinstance(arg, str) and has_pii(arg):
                            safe_args.append(redact_all(arg, salt=self.cfg.HASH_SALT))
                        else:
                            safe_args.append(arg)
                    formatted_msg = msg.format(*safe_args)
                else:
                    formatted_msg = msg.format(*args)
                
                # Appliquer redaction PII au message final si nécessaire
                if self.cfg.should_redact() and has_pii(formatted_msg):
                    formatted_msg = redact_all(formatted_msg, salt=self.cfg.HASH_SALT)
                
                super().info(formatted_msg, **kwargs)
            except:
                # En cas d'erreur, utiliser le message original
                super().info(msg, **kwargs)
        else:
            # Appliquer redaction PII au message si nécessaire
            final_msg = msg
            if self.cfg.should_redact() and isinstance(msg, str) and has_pii(msg, strict_logging_mode=True):
                final_msg = redact_all(msg, salt=self.cfg.HASH_SALT)
            super().info(final_msg, *args, **kwargs)
    
    def debug(self, msg, *args, **kwargs):
        """Override pour gérer format loguru {} et PII."""
        if args and isinstance(msg, str) and '{}' in msg:
            try:
                # Appliquer redaction PII aux arguments seulement si nécessaire
                if self.cfg.should_redact():
                    safe_args = []
                    for arg in args:
                        if isinstance(arg, str) and has_pii(arg):
                            safe_args.append(redact_all(arg, salt=self.cfg.HASH_SALT))
                        else:
                            safe_args.append(arg)
                    formatted_msg = msg.format(*safe_args)
                else:
                    formatted_msg = msg.format(*args)
                
                # Appliquer redaction PII au message final si nécessaire
                if self.cfg.should_redact() and has_pii(formatted_msg):
                    formatted_msg = redact_all(formatted_msg, salt=self.cfg.HASH_SALT)
                
                super().debug(formatted_msg, **kwargs)
            except:
                super().debug(msg, **kwargs)
        else:
            final_msg = msg
            if self.cfg.should_redact() and isinstance(msg, str) and has_pii(msg, strict_logging_mode=True):
                final_msg = redact_all(msg, salt=self.cfg.HASH_SALT)
            super().debug(final_msg, *args, **kwargs)
    
    def warning(self, msg, *args, **kwargs):
        """Override pour gérer format loguru {} et PII."""
        if args and isinstance(msg, str) and '{}' in msg:
            try:
                # Appliquer redaction PII aux arguments seulement si nécessaire
                if self.cfg.should_redact():
                    safe_args = []
                    for arg in args:
                        if isinstance(arg, str) and has_pii(arg):
                            safe_args.append(redact_all(arg, salt=self.cfg.HASH_SALT))
                        else:
                            safe_args.append(arg)
                    formatted_msg = msg.format(*safe_args)
                else:
                    formatted_msg = msg.format(*args)
                
                # Appliquer redaction PII au message final si nécessaire
                if self.cfg.should_redact() and has_pii(formatted_msg):
                    formatted_msg = redact_all(formatted_msg, salt=self.cfg.HASH_SALT)
                
                super().warning(formatted_msg, **kwargs)
            except:
                super().warning(msg, **kwargs)
        else:
            final_msg = msg
            if self.cfg.should_redact() and isinstance(msg, str) and has_pii(msg, strict_logging_mode=True):
                final_msg = redact_all(msg, salt=self.cfg.HASH_SALT)
            super().warning(final_msg, *args, **kwargs)
    
    def error(self, msg, *args, **kwargs):
        """Override pour gérer format loguru {} et PII."""
        if args and isinstance(msg, str) and '{}' in msg:
            try:
                # Appliquer redaction PII aux arguments seulement si nécessaire
                if self.cfg.should_redact():
                    safe_args = []
                    for arg in args:
                        if isinstance(arg, str) and has_pii(arg):
                            safe_args.append(redact_all(arg, salt=self.cfg.HASH_SALT))
                        else:
                            safe_args.append(arg)
                    formatted_msg = msg.format(*safe_args)
                else:
                    formatted_msg = msg.format(*args)
                
                # Appliquer redaction PII au message final si nécessaire
                if self.cfg.should_redact() and has_pii(formatted_msg):
                    formatted_msg = redact_all(formatted_msg, salt=self.cfg.HASH_SALT)
                
                super().error(formatted_msg, **kwargs)
            except:
                super().error(msg, **kwargs)
        else:
            final_msg = msg
            if self.cfg.should_redact() and isinstance(msg, str) and has_pii(msg, strict_logging_mode=True):
                final_msg = redact_all(msg, salt=self.cfg.HASH_SALT)
            super().error(final_msg, *args, **kwargs)

def get_safe_logger(name: str, cfg: PIIConfig = None) -> SafeLoggerAdapter:
    """Crée un logger sécurisé avec protection PII automatique.

    Args:
        name: Nom du logger (généralement __name__)
        cfg: Configuration PII (utilise la config par défaut si None)

    Returns:
        Logger sécurisé avec protection PII
    """
    base_logger = logging.getLogger(name)

    # IMPORTANT: Skip handler configuration - root logger handlers are configured in main.py
    # This prevents duplicate logging from multiple handler chains
    root_logger = logging.getLogger()
    if root_logger.handlers:
        # Root logger is already configured (via main.py), don't add duplicate handlers
        pass
    elif not base_logger.handlers and base_logger.parent is logging.root:
        # Fallback: only add handlers if root is not configured AND this logger has none
        base_logger.setLevel(logging.INFO)

        # ENHANCED: Windows-safe console handler with emoji sanitization
        console_handler = create_windows_safe_console_handler(
            level=logging.INFO,
            fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        base_logger.addHandler(console_handler)

        # ENHANCED: UTF-8 file handler that preserves emojis
        try:
            import os
            from pathlib import Path
            log_dir = Path("logs")
            log_dir.mkdir(exist_ok=True)

            file_handler = create_utf8_file_handler(
                "logs/cvmatch.log",
                level=logging.INFO,
                fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            base_logger.addHandler(file_handler)
        except Exception:
            # Si erreur fichier, continuer avec console seulement
            pass

    return SafeLoggerAdapter(base_logger, cfg=cfg or DEFAULT_PII_CONFIG)

def configure_logging_with_pii_protection(
    level: int = logging.INFO,
    format_string: str = None,
    cfg: PIIConfig = None
):
    """Configure le logging global avec protection PII.
    
    Args:
        level: Niveau de logging
        format_string: Format des messages (optionnel)
        cfg: Configuration PII
    """
    if format_string is None:
        format_string = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    # Configuration de base
    logging.basicConfig(
        level=level,
        format=format_string,
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Ajout d'un message d'information sur la protection PII
    config = cfg or DEFAULT_PII_CONFIG
    root_logger = get_safe_logger(__name__, cfg=config)
    
    if config.should_redact():
        root_logger.info("🔒 Protection PII activée - les données sensibles seront redactées dans les logs")
    else:
        if config.is_dev_mode():
            root_logger.info("🔓 Mode développement PII activé - données sensibles visibles")
        else:
            root_logger.info("⚠️ Protection PII désactivée - attention aux données sensibles")

# Aliases pour compatibilité
get_logger = get_safe_logger  # Alias pour faciliter la migration
