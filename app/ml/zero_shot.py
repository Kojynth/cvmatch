"""Classificateur zero-shot pour la classification de sections de CV."""

import logging
from typing import List, Dict, Any, Optional, Callable
from collections import Counter
from ..logging.safe_logger import get_safe_logger
from ..config import DEFAULT_PII_CONFIG
from pathlib import Path

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


class ZeroShotSectionClassifier:
    """Classificateur zero-shot multilingue pour sections de CV."""
    
    def __init__(self, ml_config: Dict[str, Any], 
                 device: str = "auto", 
                 local_files_only: bool = False, 
                 cache_dir: str = ".hf_cache", 
                 use_mock: bool = False,
                 on_event: Optional[Callable[[str, str], None]] = None):
        """Initialise le classificateur.
        
        Args:
            ml_config: Configuration ML depuis ml_config.json
            device: Device à utiliser ("auto", "cpu", "cuda")
            local_files_only: Utiliser uniquement les fichiers locaux
            cache_dir: Répertoire de cache HuggingFace
            use_mock: Forcer l'utilisation du mock
            on_event: Callback pour les événements de chargement (kind, detail)
        """
        self.config = ml_config
        self.zero_shot_config = ml_config.get("zero_shot", {})
        self.labels_config = ml_config.get("labels", {})
        self.use_mock = use_mock or ml_config.get("use_mock", False)
        self.device = device
        self.local_files_only = local_files_only
        self.cache_dir = Path(cache_dir or ".hf_cache").as_posix()
        self.on_event = on_event
        
        # Préparer les labels et hypothèses
        self._prepare_labels()
        
        if self.use_mock:
            from .mock import MockZeroShot
            self.classifier = MockZeroShot(self.labels_config)
            logger.info("MLBACKEND: summary | zero_shot=mock | reason=configured_use_mock")
            if self.on_event:
                self.on_event("info", "using mock classifier")
        else:
            try:
                if self.on_event:
                    backend_type = "local" if self.local_files_only else "remote"
                    self.on_event("info", f"loading {self.zero_shot_config.get('model', 'unknown')} ({backend_type})")
                self._init_huggingface_pipeline()
                # Log détaillé après succès HF
            except Exception as e:
                logger.warning(f"ML: init error → fallback mock | zero_shot: {e}")
                # Log spécifique fallback mock
                short_reason = str(e)[:50].replace("|", "-")
                logger.info(f"MLBACKEND: summary | zero_shot=mock | reason={short_reason}")
                if self.on_event:
                    self.on_event("warn", f"fallback to mock due to error: {str(e)[:100]}")
                from .mock import MockZeroShot
                self.classifier = MockZeroShot(self.labels_config)
                self.use_mock = True
    
    def _prepare_labels(self):
        """Prépare les labels et hypothèses pour la classification."""
        self.section_labels = list(self.labels_config.keys())
        # Créer des hypothèses multilingues pour chaque section
        self.candidate_labels = []
        for section, keywords in self.labels_config.items():
            for keyword in keywords:
                self.candidate_labels.append(f"This text is about {keyword}")
        
        # Mapping label -> section
        self.label_to_section = {}
        for section, keywords in self.labels_config.items():
            for keyword in keywords:
                self.label_to_section[f"This text is about {keyword}"] = section
    
    def _init_huggingface_pipeline(self):
        """Initialise le pipeline HuggingFace."""
        try:
            import os
            from transformers import pipeline
            
            model_name = self.zero_shot_config.get("model", "MoritzLaurer/deberta-v3-large-zeroshot-v2")
            
            # Utiliser les paramètres passés au constructeur
            device_config = self.device
            local_only = self.local_files_only
            cache_dir = self.cache_dir
            
            # Déterminer le device final
            device = -1  # CPU par défaut
            device_str = "cpu"
            if device_config == "cuda" and self._cuda_available():
                device = 0
                device_str = "cuda:0"
            elif device_config == "auto" and self._cuda_available():
                device = 0
                device_str = "cuda:0"
            
            batch_size = self.zero_shot_config.get("batch_size", 8)
            
            # Configuration offline si nécessaire
            if local_only:
                os.environ["TRANSFORMERS_OFFLINE"] = "1"
                os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
                logger.info("Runtime: local_only=True, set offline environment")
            
            logger.info(f"ML: zero_shot:loading model={model_name} device={device_config} -> {device_str}")
            
            # Indiquer le début du chargement
            if self.on_event:
                self.on_event("progress", f"model files (~1.34GB)")
            
            # Préparer les arguments pour le pipeline
            pipeline_kwargs = {
                "model": model_name,
                "return_all_scores": True,
                "device": device,
                "model_kwargs": {"cache_dir": cache_dir}
            }
            
            # Ajouter local_files_only si en mode local_only
            if local_only:
                pipeline_kwargs["model_kwargs"]["local_files_only"] = True
                
                # Hard gate: check if model exists locally before attempting to load
                import tempfile
                model_cache_path = Path(cache_dir) / model_name.replace('/', '_')
                cache_display = model_cache_path.as_posix()
                if not model_cache_path.exists():
                    logger.error(f"LOCAL_ONLY_GATE: model not found locally | model={model_name} | cache_path={cache_display}")
                    raise RuntimeError(f"Local-only mode enabled but model {model_name!r} not available locally. Expected at: {cache_display}")
                
                logger.info(f"LOCAL_ONLY_GATE: using local model | path={cache_display}")
            
            self.classifier = pipeline("zero-shot-classification", **pipeline_kwargs)
            
            # Log explicite après succès HF
            backend_type = "local" if local_only else "remote"
            logger.info(f"MLBACKEND: summary | zero_shot=hf({backend_type}) | model={model_name} | device={device_str} | batch={batch_size}")
            
            if self.on_event:
                self.on_event("info", "model loaded successfully")
            
        except ImportError:
            raise ImportError("transformers library not available, falling back to mock")
        except Exception as e:
            # Vérifier les erreurs spécifiques au mode local_only
            error_str = str(e).lower()
            if any(keyword in error_str for keyword in ["http", "repository", "entry not found", "offline", "token", "authorization"]):
                logger.warning(f"Local-only mode: model not in cache - {e}")
                raise RuntimeError(f"local_only_miss: {model_name} not in local cache")
            else:
                raise RuntimeError(f"Failed to load model {model_name}: {e}")
    
    def _cuda_available(self) -> bool:
        """Vérifie si CUDA est disponible."""
        try:
            import torch
            return torch.cuda.is_available()
        except ImportError:
            return False
    
    def classify_lines(self, lines: List[str]) -> List[Dict[str, Any]]:
        """Classifie les lignes par section.
        
        Args:
            lines: Liste des lignes de texte
            
        Returns:
            Liste de dict avec label, score, scores pour chaque ligne
        """
        if not lines:
            return []
        
        results = []
        batch_size = self.zero_shot_config.get("batch_size", 16)
        
        # Filtrer les lignes vides ou trop courtes
        processed_lines = []
        line_indices = []
        for i, line in enumerate(lines):
            cleaned = line.strip()
            if cleaned and len(cleaned) >= 3:
                processed_lines.append(cleaned)
                line_indices.append(i)
        
        if not processed_lines:
            return [{"label": "other", "score": 0.0, "scores": {}} for _ in lines]
        
        # Traitement par batch
        all_classifications = []
        for i in range(0, len(processed_lines), batch_size):
            batch = processed_lines[i:i + batch_size]
            try:
                if self.use_mock:
                    batch_results = [self.classifier.classify(text) for text in batch]
                else:
                    batch_results = self._classify_batch_hf(batch)
                all_classifications.extend(batch_results)
            except Exception as e:
                logger.warning(f"ML: zero_shot:batch_error at {i}-{i+batch_size}: {e}")
                # Fallback pour ce batch
                fallback_results = [{"label": "other", "score": 0.0, "scores": {}} for _ in batch]
                all_classifications.extend(fallback_results)
        
        # Reconstituer les résultats pour toutes les lignes
        classification_idx = 0
        for i, line in enumerate(lines):
            if i in line_indices:
                results.append(all_classifications[classification_idx])
                classification_idx += 1
            else:
                # Ligne vide ou trop courte
                results.append({"label": "other", "score": 0.0, "scores": {}})
        
        return results
    
    def _classify_batch_hf(self, batch: List[str]) -> List[Dict[str, Any]]:
        """Classifie un batch avec HuggingFace."""
        results = []
        
        for text in batch:
            try:
                # Classification zero-shot
                result = self.classifier(text, self.candidate_labels)
                
                # Agréger les scores par section
                section_scores = {}
                for label, score in zip(result['labels'], result['scores']):
                    section = self.label_to_section.get(label, 'other')
                    if section not in section_scores:
                        section_scores[section] = 0.0
                    section_scores[section] = max(section_scores[section], score)
                
                # Trouver le meilleur score
                if section_scores:
                    best_section = max(section_scores.keys(), key=lambda k: section_scores[k])
                    best_score = section_scores[best_section]
                else:
                    best_section = "other"
                    best_score = 0.0
                
                results.append({
                    "label": best_section,
                    "score": best_score,
                    "scores": section_scores
                })
                
            except Exception as e:
                logger.warning(f"ML: zero_shot:single_error for '{text[:50]}...': {e}")
                results.append({"label": "other", "score": 0.0, "scores": {}})
        
        return results
