"""
Loaders pour différents formats de CV
"""

from pathlib import Path
from typing import Dict, Any


class BaseLoader:
    """Classe de base pour tous les loaders"""

    def load(self, file_path: Path) -> Dict[str, Any]:
        """
        Charge un document et retourne sa structure

        Args:
            file_path: Chemin vers le fichier

        Returns:
            Dict contenant:
            - text: texte extrait
            - pages: liste des pages avec bbox si dispo
            - metadata: métadonnées du document
        """
        raise NotImplementedError

    def _extract_metadata(self, file_path: Path) -> Dict[str, Any]:
        """Extrait les métadonnées de base"""
        stat = file_path.stat()
        return {
            "filename": file_path.name,
            "size": stat.st_size,
            "created": stat.st_ctime,
            "modified": stat.st_mtime,
        }


# Imports après définition de BaseLoader pour éviter l'import circulaire
from .pdf_loader import PDFLoader
from .docx_loader import DOCXLoader
from .odt_loader import ODTLoader
from .image_loader import ImageLoader

# Mapping extension -> loader
LOADERS = {
    ".pdf": PDFLoader,
    ".docx": DOCXLoader,
    ".doc": DOCXLoader,
    ".odt": ODTLoader,
    ".jpg": ImageLoader,
    ".jpeg": ImageLoader,
    ".png": ImageLoader,
    ".tiff": ImageLoader,
    ".tif": ImageLoader,
}


def get_loader(file_path: Path):
    """
    Retourne le loader approprié pour un fichier

    Args:
        file_path: Chemin vers le fichier

    Returns:
        Instance du loader approprié

    Raises:
        ValueError: Format non supporté
    """
    extension = file_path.suffix.lower()

    if extension not in LOADERS:
        raise ValueError(f"Format non supporté: {extension}")

    loader_class = LOADERS[extension]
    return loader_class()


__all__ = [
    "BaseLoader",
    "PDFLoader",
    "DOCXLoader",
    "ODTLoader",
    "ImageLoader",
    "get_loader",
]
