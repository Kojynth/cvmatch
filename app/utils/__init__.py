"""
CVMatch Utils Package
====================

Package contenant les utilitaires de l'application.
"""

from .parsers import DocumentParser

# Éviter l'import circulaire - DatabaseManager sera importé à la demande

__all__ = [
    "DocumentParser",
]
