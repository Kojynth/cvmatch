"""
Loader pour fichiers PDF
"""

import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
import fitz  # PyMuPDF

from . import BaseLoader
from ..core.types import BoundingBox

logger = logging.getLogger(__name__)


class PDFLoader(BaseLoader):
    """Loader pour fichiers PDF avec support texte et image"""

    def load(self, file_path: Path) -> Dict[str, Any]:
        """
        Charge un PDF et extrait le texte avec bounding boxes

        Returns:
            Dict avec text, pages, metadata, needs_ocr
        """
        logger.debug("📄 Chargement PDF: %s", "[FILENAME]")

        try:
            doc = fitz.open(file_path)
            pages = []
            full_text = []
            needs_ocr = False

            for page_num in range(len(doc)):
                page = doc.load_page(page_num)

                # Extraire le texte avec positions
                text_dict = page.get_text("dict")
                page_text = page.get_text()

                # Analyser si le texte est suffisant
                text_density = (
                    len(page_text.strip())
                    / (page.rect.width * page.rect.height)
                    * 10000
                )
                page_needs_ocr = text_density < 1.0  # Seuil arbitraire

                if page_needs_ocr:
                    needs_ocr = True

                pages.append(
                    {
                        "page_number": page_num,
                        "text": page_text,
                        "text_dict": text_dict,
                        "bbox": BoundingBox(
                            page=page_num,
                            x0=0,
                            y0=0,
                            x1=page.rect.width,
                            y1=page.rect.height,
                        ),
                        "needs_ocr": page_needs_ocr,
                        "text_density": text_density,
                    }
                )

                full_text.append(page_text)

            doc.close()

            result = {
                "text": "\n".join(full_text),
                "pages": pages,
                "page_count": len(pages),
                "needs_ocr": needs_ocr,
                "format": "pdf",
                "metadata": self._extract_pdf_metadata(file_path),
            }

            logger.debug(f"✅ PDF chargé: {len(pages)} pages, OCR requis: {needs_ocr}")
            return result

        except Exception as e:
            logger.error(f"❌ Erreur chargement PDF: {e}")
            return {
                "text": "",
                "pages": [],
                "page_count": 0,
                "needs_ocr": True,
                "format": "pdf",
                "metadata": self._extract_metadata(file_path),
                "error": str(e),
            }

    def _extract_pdf_metadata(self, file_path: Path) -> Dict[str, Any]:
        """Extrait les métadonnées PDF"""
        metadata = self._extract_metadata(file_path)

        try:
            doc = fitz.open(file_path)
            pdf_metadata = doc.metadata
            doc.close()

            metadata.update(
                {
                    "title": pdf_metadata.get("title", ""),
                    "author": pdf_metadata.get("author", ""),
                    "creator": pdf_metadata.get("creator", ""),
                    "producer": pdf_metadata.get("producer", ""),
                    "creation_date": pdf_metadata.get("creationDate", ""),
                    "modification_date": pdf_metadata.get("modDate", ""),
                }
            )
        except Exception as e:
            logger.warning(f"⚠️ Impossible d'extraire les métadonnées PDF: {e}")

        return metadata

    def extract_text_blocks(self, file_path: Path) -> List[Dict[str, Any]]:
        """
        Extrait les blocs de texte avec positions précises
        Utile pour l'analyse de mise en page
        """
        try:
            doc = fitz.open(file_path)
            all_blocks = []

            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                text_dict = page.get_text("dict")

                for block in text_dict.get("blocks", []):
                    if "lines" in block:  # Bloc de texte
                        block_text = ""
                        for line in block["lines"]:
                            line_text = ""
                            for span in line.get("spans", []):
                                line_text += span.get("text", "")
                            block_text += line_text + "\n"

                        if block_text.strip():
                            bbox_data = block["bbox"]
                            all_blocks.append(
                                {
                                    "text": block_text.strip(),
                                    "page": page_num,
                                    "bbox": BoundingBox(
                                        page=page_num,
                                        x0=bbox_data[0],
                                        y0=bbox_data[1],
                                        x1=bbox_data[2],
                                        y1=bbox_data[3],
                                    ),
                                    "font_info": self._extract_font_info(block),
                                }
                            )

            doc.close()
            return all_blocks

        except Exception as e:
            logger.error(f"❌ Erreur extraction blocs: {e}")
            return []

    def _extract_font_info(self, block: Dict) -> Dict[str, Any]:
        """Extrait les informations de police d'un bloc"""
        font_info = {"sizes": [], "families": [], "flags": []}

        try:
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    font_info["sizes"].append(span.get("size", 0))
                    font_info["families"].append(span.get("font", ""))
                    font_info["flags"].append(span.get("flags", 0))

            # Calculer les valeurs dominantes
            if font_info["sizes"]:
                font_info["dominant_size"] = max(
                    set(font_info["sizes"]), key=font_info["sizes"].count
                )
            if font_info["families"]:
                font_info["dominant_family"] = max(
                    set(font_info["families"]), key=font_info["families"].count
                )
        except Exception:
            pass

        return font_info
