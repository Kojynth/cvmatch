"""
Module de règles d'extraction pour CVMatch.

Contient les règles JSON et le loader pour l'extraction robuste.
"""

from .loader import load_rules, clear_cache

__all__ = ['load_rules', 'clear_cache']
