"""
Loader pour fichiers ODT (OpenDocument Text)
"""

import logging
from pathlib import Path
from typing import Dict, Any
import zipfile
import xml.etree.ElementTree as ET

from . import BaseLoader

logger = logging.getLogger(__name__)


class ODTLoader(BaseLoader):
    """Loader pour fichiers ODT"""

    def load(self, file_path: Path) -> Dict[str, Any]:
        """
        Charge un document ODT et extrait le texte

        Returns:
            Dict avec text, pages, metadata
        """
        logger.debug("📄 Chargement ODT: %s", "[FILENAME]")

        try:
            text = self._extract_odt_text(file_path)

            result = {
                "text": text,
                "pages": [{"page_number": 0, "text": text}],
                "page_count": 1,
                "needs_ocr": False,
                "format": "odt",
                "metadata": self._extract_odt_metadata(file_path),
            }

            logger.debug(f"✅ ODT chargé: {len(text)} caractères")
            return result

        except Exception as e:
            logger.error(f"❌ Erreur chargement ODT: {e}")
            return {
                "text": "",
                "pages": [],
                "page_count": 0,
                "needs_ocr": False,
                "format": "odt",
                "metadata": self._extract_metadata(file_path),
                "error": str(e),
            }

    def _extract_odt_text(self, file_path: Path) -> str:
        """Extrait le texte d'un fichier ODT"""
        text_content = []

        try:
            with zipfile.ZipFile(file_path, "r") as odt_file:
                # Lire le contenu principal
                if "content.xml" in odt_file.namelist():
                    content_xml = odt_file.read("content.xml")
                    root = ET.fromstring(content_xml)

                    # Extraire tout le texte des éléments
                    for elem in root.iter():
                        if elem.text and elem.text.strip():
                            text_content.append(elem.text.strip())
                        if elem.tail and elem.tail.strip():
                            text_content.append(elem.tail.strip())

        except Exception as e:
            logger.error(f"❌ Erreur extraction texte ODT: {e}")
            raise

        return "\n".join(text_content)

    def _extract_odt_metadata(self, file_path: Path) -> Dict[str, Any]:
        """Extrait les métadonnées ODT"""
        metadata = self._extract_metadata(file_path)

        try:
            with zipfile.ZipFile(file_path, "r") as odt_file:
                if "meta.xml" in odt_file.namelist():
                    meta_xml = odt_file.read("meta.xml")
                    root = ET.fromstring(meta_xml)

                    # Namespace ODT
                    ns = {
                        "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
                        "meta": "urn:oasis:names:tc:opendocument:xmlns:meta:1.0",
                        "dc": "http://purl.org/dc/elements/1.1/",
                    }

                    # Extraire les métadonnées
                    title_elem = root.find(".//dc:title", ns)
                    if title_elem is not None:
                        metadata["title"] = title_elem.text or ""

                    creator_elem = root.find(".//dc:creator", ns)
                    if creator_elem is not None:
                        metadata["author"] = creator_elem.text or ""

                    subject_elem = root.find(".//dc:subject", ns)
                    if subject_elem is not None:
                        metadata["subject"] = subject_elem.text or ""

                    description_elem = root.find(".//dc:description", ns)
                    if description_elem is not None:
                        metadata["description"] = description_elem.text or ""

                    creation_elem = root.find(".//meta:creation-date", ns)
                    if creation_elem is not None:
                        metadata["creation_date"] = creation_elem.text or ""

        except Exception as e:
            logger.warning(f"⚠️ Impossible d'extraire les métadonnées ODT: {e}")

        return metadata
