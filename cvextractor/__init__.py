"""
CVExtractor - Module d'extraction de CV hors-ligne
=================================================

Module principal d'extraction de CV supportant:
- Formats: PDF (texte/image), DOCX, ODT, images
- OCR Tesseract intégré
- Segmentation sémantique multi-langues
- Provenance et scores de confiance
- Normalisation automatique
"""

from .core.types import ExtractionResult, CVSection, ExtractedField
from .core.extractor import CVExtractor

__version__ = "1.0.0"
__all__ = ["CVExtractor", "ExtractionResult", "CVSection", "ExtractedField"]


def extract(cv_path, config=None):
    """
    Interface simple d'extraction de CV

    Args:
        cv_path: Chemin vers le fichier CV
        config: Configuration optionnelle

    Returns:
        ExtractionResult: Résultat complet avec provenance
    """
    extractor = CVExtractor(config)
    return extractor.extract(cv_path)
