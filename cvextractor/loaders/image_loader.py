"""
Loader pour fichiers images avec OCR
"""

import logging
from pathlib import Path
from typing import Dict, Any, List
from PIL import Image
import numpy as np

from . import BaseLoader

logger = logging.getLogger(__name__)


class ImageLoader(BaseLoader):
    """Loader pour fichiers images (JPG, PNG, TIFF) avec OCR"""

    def load(self, file_path: Path) -> Dict[str, Any]:
        """
        Charge une image et prépare pour OCR

        Returns:
            Dict avec text, pages, metadata, needs_ocr=True
        """
        logger.debug("🖼️ Chargement image: %s", "[FILENAME]")

        try:
            # Charger l'image
            image = Image.open(file_path)

            # Convertir en RGB si nécessaire
            if image.mode != "RGB":
                image = image.convert("RGB")

            # Analyser l'image
            image_info = self._analyze_image(image)

            result = {
                "text": "",  # Sera rempli par l'OCR
                "pages": [
                    {
                        "page_number": 0,
                        "text": "",
                        "image": image,
                        "image_path": str(file_path),
                        "image_info": image_info,
                    }
                ],
                "page_count": 1,
                "needs_ocr": True,  # Toujours vrai pour les images
                "format": "image",
                "metadata": self._extract_image_metadata(image, file_path),
            }

            logger.debug(f"✅ Image chargée: {image.width}x{image.height}")
            return result

        except Exception as e:
            logger.error(f"❌ Erreur chargement image: {e}")
            return {
                "text": "",
                "pages": [],
                "page_count": 0,
                "needs_ocr": True,
                "format": "image",
                "metadata": self._extract_metadata(file_path),
                "error": str(e),
            }

    def _analyze_image(self, image: Image.Image) -> Dict[str, Any]:
        """Analyse la qualité et les caractéristiques de l'image"""

        # Convertir en numpy array pour l'analyse
        img_array = np.array(image)

        # Calculer des métriques de qualité
        info = {
            "width": image.width,
            "height": image.height,
            "mode": image.mode,
            "format": image.format,
            "dpi": image.info.get("dpi", (72, 72)),
            "has_transparency": image.mode in ("RGBA", "LA")
            or "transparency" in image.info,
        }

        # Analyse de la luminosité moyenne
        if len(img_array.shape) == 3:
            gray = np.dot(img_array[..., :3], [0.2989, 0.5870, 0.1140])
        else:
            gray = img_array

        info.update(
            {
                "mean_brightness": float(np.mean(gray)),
                "std_brightness": float(np.std(gray)),
                "is_mostly_dark": np.mean(gray) < 85,
                "is_mostly_light": np.mean(gray) > 170,
                "contrast_ratio": (
                    float(np.std(gray) / np.mean(gray)) if np.mean(gray) > 0 else 0
                ),
            }
        )

        # Recommandations pour l'OCR
        info["ocr_recommendations"] = self._get_ocr_recommendations(info)

        return info

    def _get_ocr_recommendations(self, image_info: Dict) -> Dict[str, Any]:
        """Génère des recommandations pour améliorer l'OCR"""
        recommendations = {"needs_enhancement": False, "suggested_operations": []}

        # Vérifier la résolution
        dpi = image_info.get("dpi", (72, 72))
        if isinstance(dpi, tuple):
            avg_dpi = sum(dpi) / len(dpi)
        else:
            avg_dpi = dpi

        if avg_dpi < 200:
            recommendations["needs_enhancement"] = True
            recommendations["suggested_operations"].append("upscale")

        # Vérifier le contraste
        if image_info.get("contrast_ratio", 0) < 0.3:
            recommendations["needs_enhancement"] = True
            recommendations["suggested_operations"].append("enhance_contrast")

        # Vérifier la luminosité
        if image_info.get("is_mostly_dark"):
            recommendations["needs_enhancement"] = True
            recommendations["suggested_operations"].append("brighten")
        elif image_info.get("is_mostly_light"):
            recommendations["needs_enhancement"] = True
            recommendations["suggested_operations"].append("darken")

        return recommendations

    def _extract_image_metadata(
        self, image: Image.Image, file_path: Path
    ) -> Dict[str, Any]:
        """Extrait les métadonnées de l'image"""
        metadata = self._extract_metadata(file_path)

        # Métadonnées EXIF si disponibles
        try:
            exif = image.getexif()
            if exif:
                metadata["exif"] = dict(exif)
        except Exception:
            pass

        # Informations de base
        metadata.update(
            {
                "width": image.width,
                "height": image.height,
                "mode": image.mode,
                "format": image.format or file_path.suffix[1:].upper(),
                "dpi": image.info.get("dpi", "unknown"),
                "color_depth": (
                    len(image.getbands()) * 8
                    if hasattr(image, "getbands")
                    else "unknown"
                ),
            }
        )

        return metadata

    def preprocess_for_ocr(
        self, image: Image.Image, operations: List[str] = None
    ) -> Image.Image:
        """
        Pré-traite une image pour améliorer l'OCR

        Args:
            image: Image PIL
            operations: Liste des opérations à appliquer

        Returns:
            Image traitée
        """
        if not operations:
            return image

        processed = image.copy()

        try:
            for operation in operations:
                if operation == "upscale":
                    # Doubler la résolution
                    new_size = (processed.width * 2, processed.height * 2)
                    processed = processed.resize(new_size, Image.Resampling.LANCZOS)

                elif operation == "enhance_contrast":
                    from PIL import ImageEnhance

                    enhancer = ImageEnhance.Contrast(processed)
                    processed = enhancer.enhance(1.5)

                elif operation == "brighten":
                    from PIL import ImageEnhance

                    enhancer = ImageEnhance.Brightness(processed)
                    processed = enhancer.enhance(1.3)

                elif operation == "darken":
                    from PIL import ImageEnhance

                    enhancer = ImageEnhance.Brightness(processed)
                    processed = enhancer.enhance(0.8)

                elif operation == "sharpen":
                    from PIL import ImageEnhance

                    enhancer = ImageEnhance.Sharpness(processed)
                    processed = enhancer.enhance(2.0)

        except Exception as e:
            logger.warning(f"⚠️ Erreur pré-traitement image: {e}")
            return image

        return processed
