"""
Extracteur principal de CV
"""

import time
from pathlib import Path
from typing import Optional, Dict, Any
import logging
import sys
import os
from pathlib import Path

# Add app path for safe_logger import
app_path = Path(__file__).parent.parent.parent / "app"
sys.path.insert(0, str(app_path))

try:
    from logging.safe_logger import get_safe_logger
    from config import DEFAULT_PII_CONFIG

    logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)
except ImportError:
    # Fallback to standard logging if safe_logger not available
    logger = logging.getLogger(__name__)

from .types import ExtractionResult, ExtractionMetrics
from .config import ExtractionConfig
from ..loaders import get_loader
from ..preprocessing import DocumentPreprocessor
from ..segmentation import SectionSegmenter
from ..extraction import FieldExtractor
from ..normalization import DataNormalizer


class CVExtractor:
    """Extracteur principal de CV"""

    def __init__(self, config: Optional[ExtractionConfig] = None):
        self.config = config or ExtractionConfig()
        self.preprocessor = DocumentPreprocessor(self.config)
        self.segmenter = SectionSegmenter(self.config)
        self.extractor = FieldExtractor(self.config)
        self.normalizer = DataNormalizer(self.config)

    def extract(self, cv_path: str) -> ExtractionResult:
        """
        Extrait toutes les informations d'un CV

        Args:
            cv_path: Chemin vers le fichier CV

        Returns:
            ExtractionResult: Résultat complet avec provenance
        """
        start_time = time.time()
        cv_path = Path(cv_path)

        logger.info("🚀 Début extraction CV")

        try:
            # 1. Chargement du document
            logger.debug("📄 Chargement du document...")
            loader = get_loader(cv_path)
            document = loader.load(cv_path)

            # 2. Pré-traitement
            logger.debug("🔧 Pré-traitement...")
            processed_doc = self.preprocessor.process(document)

            # 3. Segmentation sémantique
            logger.debug("📋 Segmentation des sections...")
            sections = self.segmenter.segment(processed_doc)

            # 4. Extraction des champs
            logger.debug("⚙️ Extraction des champs...")
            raw_result = self.extractor.extract(sections, processed_doc)

            # 5. Normalisation
            logger.debug("✨ Normalisation des données...")
            normalized_result = self.normalizer.normalize(raw_result)

            # 6. Calcul des métriques
            processing_time = time.time() - start_time
            metrics = self._calculate_metrics(
                normalized_result, processed_doc, processing_time
            )
            normalized_result.metrics = metrics

            logger.info(
                f"✅ Extraction terminée en {processing_time:.2f}s - "
                f"{metrics.fields_extracted} champs extraits"
            )

            return normalized_result

        except Exception as e:
            logger.error(f"❌ Erreur lors de l'extraction: {e}")
            # Retourner un résultat vide avec l'erreur
            result = ExtractionResult()
            result.source_file = str(cv_path)
            result.metrics = ExtractionMetrics(
                total_pages=0,
                ocr_pages=0,
                processing_time=time.time() - start_time,
                warnings=[f"Erreur d'extraction: {str(e)}"],
            )
            return result

    def _calculate_metrics(
        self, result: ExtractionResult, document: Dict[str, Any], processing_time: float
    ) -> ExtractionMetrics:
        """Calcule les métriques d'extraction"""

        # Compter les champs extraits
        fields_count = 0
        high_confidence_count = 0

        def count_fields(obj):
            nonlocal fields_count, high_confidence_count
            if hasattr(obj, "__dict__"):
                for field_value in obj.__dict__.values():
                    if hasattr(field_value, "provenance"):  # ExtractedField
                        fields_count += 1
                        if field_value.provenance.confidence >= 0.8:
                            high_confidence_count += 1
                    elif isinstance(field_value, list):
                        for item in field_value:
                            count_fields(item)
                    elif hasattr(field_value, "__dict__"):
                        count_fields(field_value)

        count_fields(result)

        # Calculer le taux de complétude
        total_possible_fields = 20  # Estimation des champs principaux
        completion_rate = min(fields_count / total_possible_fields, 1.0)

        return ExtractionMetrics(
            total_pages=document.get("page_count", 0),
            ocr_pages=document.get("ocr_pages", 0),
            processing_time=processing_time,
            sections_detected=len(document.get("sections", [])),
            fields_extracted=fields_count,
            fields_with_high_confidence=high_confidence_count,
            completion_rate=completion_rate,
            warnings=document.get("warnings", []),
        )
