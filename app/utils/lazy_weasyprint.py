"""
Lazy WeasyPrint Manager
======================

Gestionnaire paresseux pour WeasyPrint.
Évite de charger WeasyPrint au démarrage et le charge seulement lors d'export PDF.
"""

import sys
import io
from typing import Optional, Any
from pathlib import Path

# Logger sécurisé
try:
    from ..logging.safe_logger import get_safe_logger
    from ..config import DEFAULT_PII_CONFIG
    logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


class WeasyPrintSuppressor:
    """Supprime les messages d'erreur WeasyPrint en capturant stderr temporairement."""
    
    def __init__(self):
        self.original_stderr = None
        
    def __enter__(self):
        self.original_stderr = sys.stderr
        sys.stderr = io.StringIO()  # Capturer stderr
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        # Récupérer les messages capturés
        captured = sys.stderr.getvalue()
        sys.stderr = self.original_stderr
        
        # Filtrer et n'afficher que les vrais messages d'erreur (pas WeasyPrint)
        # MAIS préserver les logs loguru (reconnaissables par leur format)
        if captured:
            lines = captured.strip().split('\n')
            for line in lines:
                # Garder les logs loguru et les vraies erreurs, filtrer WeasyPrint
                if (any(keyword in line.lower() for keyword in ['weasyprint', 'external libraries', 'courtbouillon', 'gtk']) 
                    and not any(marker in line for marker in ['INFO', 'WARNING', 'ERROR', 'DEBUG'])):
                    continue  # Filtrer cette ligne WeasyPrint
                else:
                    print(line, file=sys.stderr)  # Afficher les logs et vraies erreurs


class LazyWeasyPrint:
    """Gestionnaire paresseux pour WeasyPrint."""
    
    def __init__(self):
        self._weasyprint = None
        self._available = None
        self._error_reason = None
        self._bootstrap_done = False
    
    def _bootstrap_weasyprint(self):
        """Bootstrap WeasyPrint si pas encore fait."""
        if self._bootstrap_done:
            return
        
        try:
            # Essayer d'importer et exécuter le bootstrap
            try:
                from scripts import weasyprint_bootstrap
                logger.info("🔧 WeasyPrint bootstrap via scripts package")
            except ImportError:
                # Fallback si scripts n'est pas un package
                scripts_path = Path(__file__).parent.parent.parent / "scripts"
                if scripts_path.exists():
                    sys.path.insert(0, str(scripts_path))
                    try:
                        import weasyprint_bootstrap
                        logger.info("🔧 WeasyPrint bootstrap via fallback path")
                    except ImportError as e:
                        logger.warning(f"WeasyPrint bootstrap unavailable: {e}")
                else:
                    logger.warning("Scripts directory not found for WeasyPrint bootstrap")
        except Exception as e:
            logger.warning(f"WeasyPrint bootstrap failed: {e}")
        
        self._bootstrap_done = True
    
    def _load_weasyprint(self):
        """Charger WeasyPrint à la demande."""
        if self._weasyprint is not None or self._available is False:
            return self._weasyprint
        
        logger.info("📄 Loading WeasyPrint for PDF export...")
        
        # Bootstrap d'abord
        self._bootstrap_weasyprint()
        
        try:
            with WeasyPrintSuppressor():
                import weasyprint
                self._weasyprint = weasyprint
                self._available = True
                logger.info("✅ WeasyPrint loaded successfully")
                return weasyprint
        except ImportError as e:
            self._available = False
            self._error_reason = f"Import error: {e}"
            logger.error(f"❌ WeasyPrint unavailable: {e}")
            logger.info("💡 Install with: pip install weasyprint")
            return None
        except OSError as e:
            self._available = False
            self._error_reason = f"System libraries missing: {e}"
            logger.error(f"❌ WeasyPrint system error: {e}")
            logger.info("💡 See: https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#windows")
            return None
        except Exception as e:
            self._available = False
            self._error_reason = f"Unexpected error: {e}"
            logger.error(f"❌ WeasyPrint unexpected error: {e}")
            return None
    
    @property
    def available(self) -> bool:
        """Vérifier si WeasyPrint est disponible (charge si nécessaire)."""
        if self._available is None:
            self._load_weasyprint()
        return self._available
    
    @property
    def error_reason(self) -> Optional[str]:
        """Raison de l'indisponibilité de WeasyPrint."""
        return self._error_reason
    
    def HTML(self, *args, **kwargs):
        """Proxy pour weasyprint.HTML."""
        weasyprint = self._load_weasyprint()
        if weasyprint is None:
            raise RuntimeError(f"WeasyPrint not available: {self._error_reason}")
        return weasyprint.HTML(*args, **kwargs)
    
    def CSS(self, *args, **kwargs):
        """Proxy pour weasyprint.CSS."""
        weasyprint = self._load_weasyprint()
        if weasyprint is None:
            raise RuntimeError(f"WeasyPrint not available: {self._error_reason}")
        return weasyprint.CSS(*args, **kwargs)
    
    def __getattr__(self, name):
        """Proxy pour tous les autres attributs WeasyPrint."""
        weasyprint = self._load_weasyprint()
        if weasyprint is None:
            raise RuntimeError(f"WeasyPrint not available: {self._error_reason}")
        return getattr(weasyprint, name)


# Instance globale
_lazy_weasyprint = LazyWeasyPrint()

def get_weasyprint():
    """Obtenir l'instance WeasyPrint paresseuse."""
    return _lazy_weasyprint

def is_weasyprint_available() -> bool:
    """Vérifier si WeasyPrint est disponible."""
    return _lazy_weasyprint.available

def get_weasyprint_error() -> Optional[str]:
    """Obtenir la raison de l'indisponibilité de WeasyPrint."""
    return _lazy_weasyprint.error_reason


# API de compatibilité pour remplacer les imports directs
def HTML(*args, **kwargs):
    """Fonction de compatibilité pour weasyprint.HTML."""
    return _lazy_weasyprint.HTML(*args, **kwargs)

def CSS(*args, **kwargs):
    """Fonction de compatibilité pour weasyprint.CSS."""
    return _lazy_weasyprint.CSS(*args, **kwargs)


# Variables globales de compatibilité
WEASYPRINT_AVAILABLE = None  # Sera déterminé à la demande

def check_weasyprint_availability():
    """Vérifier la disponibilité de WeasyPrint et mettre à jour la variable globale."""
    global WEASYPRINT_AVAILABLE
    WEASYPRINT_AVAILABLE = is_weasyprint_available()
    return WEASYPRINT_AVAILABLE