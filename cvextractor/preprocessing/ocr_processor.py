"""
Processeur OCR avec Tesseract
"""

import logging
import tempfile
from pathlib import Path
from typing import Dict, Any, List, Optional
import subprocess
import shutil
from PIL import Image

logger = logging.getLogger(__name__)


class OCRProcessor:
    """Processeur OCR utilisant Tesseract"""

    def __init__(self, config):
        self.config = config
        self.tesseract_cmd = self._find_tesseract()

    def _find_tesseract(self) -> Optional[str]:
        """Trouve l'exécutable Tesseract"""

        # Utiliser la config si spécifiée
        if self.config.tesseract_cmd:
            if shutil.which(self.config.tesseract_cmd):
                return self.config.tesseract_cmd

        # Recherche automatique
        possible_paths = [
            "tesseract",  # Dans le PATH
            "/usr/bin/tesseract",  # Linux standard
            "/usr/local/bin/tesseract",  # macOS Homebrew
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",  # Windows
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        ]

        for path in possible_paths:
            if shutil.which(path):
                logger.info(f"✅ Tesseract trouvé: {path}")
                return path

        logger.warning("⚠️ Tesseract non trouvé - OCR indisponible")
        return None

    def is_available(self) -> bool:
        """Vérifie si l'OCR est disponible"""
        return self.tesseract_cmd is not None

    def process(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """
        Applique l'OCR sur un document

        Args:
            document: Document avec pages à traiter

        Returns:
            Document avec texte OCR ajouté
        """
        if not self.is_available():
            logger.warning("⚠️ OCR non disponible - texte non traité")
            return document

        logger.debug("👁️ Application OCR...")

        processed_doc = document.copy()
        ocr_pages = 0
        all_ocr_text = []

        for page in processed_doc.get("pages", []):
            if self._page_needs_ocr(page):
                try:
                    ocr_text = self._ocr_page(page)
                    if ocr_text:
                        # Combiner texte existant et OCR
                        existing_text = page.get("text", "")
                        if existing_text.strip():
                            page["text"] = existing_text + "\n" + ocr_text
                        else:
                            page["text"] = ocr_text

                        all_ocr_text.append(ocr_text)
                        ocr_pages += 1

                except Exception as e:
                    logger.error(
                        f"❌ Erreur OCR page {page.get('page_number', 0)}: {e}"
                    )

        # Mettre à jour le texte complet
        if all_ocr_text:
            existing_text = processed_doc.get("text", "")
            if existing_text.strip():
                processed_doc["text"] = existing_text + "\n" + "\n".join(all_ocr_text)
            else:
                processed_doc["text"] = "\n".join(all_ocr_text)

        processed_doc["ocr_pages"] = ocr_pages
        logger.debug(f"✅ OCR appliqué sur {ocr_pages} pages")

        return processed_doc

    def _page_needs_ocr(self, page: Dict[str, Any]) -> bool:
        """Détermine si une page a besoin d'OCR"""

        # Si marquée explicitement
        if page.get("needs_ocr"):
            return True

        # Si peu de texte disponible
        text = page.get("text", "")
        if len(text.strip()) < 50:
            return True

        # Si image disponible et texte suspect
        if "image" in page or "image_path" in page:
            return True

        return False

    def _ocr_page(self, page: Dict[str, Any]) -> str:
        """Applique l'OCR sur une page"""

        # Récupérer l'image
        image = None
        if "image" in page:
            image = page["image"]
        elif "image_path" in page:
            image = Image.open(page["image_path"])
        else:
            logger.warning("⚠️ Pas d'image pour OCR")
            return ""

        # Pré-traitement si recommandé
        image_info = page.get("image_info", {})
        ocr_recs = image_info.get("ocr_recommendations", {})

        if ocr_recs.get("needs_enhancement"):
            from ..loaders.image_loader import ImageLoader

            loader = ImageLoader()
            image = loader.preprocess_for_ocr(
                image, ocr_recs.get("suggested_operations", [])
            )

        # Déterminer les langues OCR
        ocr_languages = "+".join(self.config.ocr_languages)

        # Sauvegarder temporairement
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_file:
            image.save(tmp_file.name, "PNG")
            tmp_path = tmp_file.name

        try:
            # Exécuter Tesseract
            result = subprocess.run(
                [
                    self.tesseract_cmd,
                    tmp_path,
                    "stdout",
                    "-l",
                    ocr_languages,
                    "--psm",
                    "3",  # Page segmentation mode
                    "-c",
                    f"tessedit_char_whitelist= !\"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\\\]^_`abcdefghijklmnopqrstuvwxyz{{|}}~ÀÁÃÄÅÆÇÈÉÊËÌÍÎÏÐÑÒÓÔÕÖØÙÚÛÜÝÞßàáâãäåæçèéêëìíîïðñòóôõöøùúûüýþÿ",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                ocr_text = result.stdout.strip()
                if len(ocr_text) > 10:  # Filtre les résultats trop courts
                    return ocr_text
            else:
                logger.warning(f"⚠️ Tesseract erreur: {result.stderr}")

        except subprocess.TimeoutExpired:
            logger.error("❌ Timeout OCR")
        except Exception as e:
            logger.error(f"❌ Erreur exécution Tesseract: {e}")
        finally:
            # Nettoyer le fichier temporaire
            try:
                Path(tmp_path).unlink()
            except:
                pass

        return ""

    def get_available_languages(self) -> List[str]:
        """Retourne la liste des langues OCR disponibles"""
        if not self.is_available():
            return []

        try:
            result = subprocess.run(
                [self.tesseract_cmd, "--list-langs"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                languages = result.stdout.strip().split("\n")[1:]  # Skip first line
                return [lang.strip() for lang in languages if lang.strip()]
        except Exception as e:
            logger.error(f"❌ Erreur récupération langues OCR: {e}")

        return []

    def optimize_for_language(self, language: str) -> str:
        """Optimise les paramètres OCR pour une langue spécifique"""

        # Mapping langues détectées -> langues Tesseract
        lang_mapping = {
            "fr": "fra",
            "en": "eng",
            "de": "deu",
            "es": "spa",
            "it": "ita",
            "pt": "por",
            "nl": "nld",
            "pl": "pol",
            "ro": "ron",
            "tr": "tur",
            "ja": "jpn",
            "ar": "ara",
        }

        tesseract_lang = lang_mapping.get(language, "eng")
        available_langs = self.get_available_languages()

        if tesseract_lang in available_langs:
            return tesseract_lang
        else:
            logger.warning(
                f"⚠️ Langue {tesseract_lang} non disponible, utilisation anglais"
            )
            return (
                "eng"
                if "eng" in available_langs
                else available_langs[0] if available_langs else "eng"
            )
