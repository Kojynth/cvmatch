"""Router NER par langue avec cache LRU et fallback."""

import logging
import json
from typing import Dict, List, Optional, Any, Callable
from functools import lru_cache
import os
from pathlib import Path
from ..logging.safe_logger import get_safe_logger
from ..config import DEFAULT_PII_CONFIG

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


class NERBackend:
    """Interface pour un backend NER."""
    
    def __init__(self, model_name: str, config: Dict[str, Any], on_event: Optional[Callable[[str, str], None]] = None):
        self.model_name = model_name
        self.config = config
        self.loaded = False
        self.model = None
        self.tokenizer = None
        self.use_mock = config.get('use_mock', False)
        self.device = config.get('device', 'auto')
        self.local_files_only = config.get('local_files_only', False)
        self.cache_dir = config.get('hf_cache_dir', '.hf_cache')
        self.on_event = on_event
    
    def load(self) -> bool:
        """Charge le modèle NER."""
        if self.loaded:
            device_str = "cuda:0" if self.device == "cuda" and self._cuda_available() else "cpu"
            logger.info(f"NER: load | model={self.model_name} | device={device_str} | cached=true")
            return True
            
        try:
            if self.use_mock:
                logger.info(f"NER: load | model=mock | device=cpu | cached=false")
                if self.on_event:
                    self.on_event("info", "using mock NER")
                self.loaded = True
                return True
            
            # Import HuggingFace
            import os
            from transformers import AutoTokenizer, AutoModelForTokenClassification, pipeline
            
            # Configuration offline si nécessaire
            if self.local_files_only:
                os.environ["TRANSFORMERS_OFFLINE"] = "1"
                os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
                logger.info("Runtime: local_only=True, set offline environment")
            
            if self.on_event:
                self.on_event("info", f"loading NER model {self.model_name} (local_only={self.local_files_only})")
                self.on_event("progress", f"model files (~1.34GB)")
            
            # Préparer les arguments pour le chargement
            model_kwargs = {"cache_dir": self.cache_dir}
            if self.local_files_only:
                model_kwargs["local_files_only"] = True
            
            # Charger tokenizer et modèle
            self.tokenizer = AutoTokenizer.from_pretrained(
                self.model_name, 
                **model_kwargs
            )
            self.model = AutoModelForTokenClassification.from_pretrained(
                self.model_name,
                **model_kwargs
            )
            
            # Créer pipeline NER
            device_num = 0 if self.device == "cuda" and self._cuda_available() else -1
            device_str = "cuda:0" if device_num == 0 else "cpu"
            
            batch_size = self.config.get('batch_size', 16)
            
            self.pipeline = pipeline(
                "ner",
                model=self.model,
                tokenizer=self.tokenizer,
                aggregation_strategy="simple",
                device=device_num
            )
            
            self.loaded = True
            logger.info(f"NER: load | model={self.model_name} | device={device_str} | cached=false | batch={batch_size}")
            if self.on_event:
                self.on_event("info", f"NER model {self.model_name} loaded successfully")
            return True
            
        except Exception as e:
            logger.warning(f"NER: load_failed | model={self.model_name} | error={e}")
            if self.on_event:
                self.on_event("warn", f"NER load failed: {str(e)[:100]}")
            return False
    
    def _cuda_available(self) -> bool:
        """Vérifie si CUDA est disponible."""
        try:
            import torch
            return torch.cuda.is_available()
        except ImportError:
            return False
    
    def extract_entities(self, lines: List[str]) -> List[List[Dict[str, Any]]]:
        """
        Extrait les entités des lignes de texte.
        
        Args:
            lines: Liste de lignes de texte
            
        Returns:
            Liste d'entités par ligne au format normalisé
        """
        if not self.loaded:
            if not self.load():
                return self._fallback_mock_extract(lines)
        
        if self.use_mock:
            return self._fallback_mock_extract(lines)
        
        try:
            results = []
            batch_size = self.config.get('batch_size', 16)
            
            # Traitement par batch
            for i in range(0, len(lines), batch_size):
                batch = lines[i:i + batch_size]
                batch_results = []
                
                for line_idx, line in enumerate(batch):
                    if not line.strip():
                        batch_results.append([])
                        continue
                    
                    # Extraction NER
                    entities = self.pipeline(line)
                    
                    # Normalisation des entités
                    normalized = []
                    for ent in entities:
                        normalized.append({
                            'text': ent.get('word', ent.get('text', '')),
                            'label': self._normalize_label(ent.get('entity_group', ent.get('entity', 'MISC'))),
                            'start': ent.get('start', 0),
                            'end': ent.get('end', 0),
                            'line_idx': i + line_idx,
                            'score': ent.get('score', 0.0)
                        })
                    
                    batch_results.append(normalized)
                
                results.extend(batch_results)
            
            return results
            
        except Exception as e:
            logger.warning(f"NER: extract_failed | model={self.model_name} | error={e}")
            return self._fallback_mock_extract(lines)
    
    def _normalize_label(self, label: str) -> str:
        """Normalise les labels d'entités."""
        label = label.upper()
        
        # Mapping des labels courants
        if label in ['PERSON', 'PER', 'PERS']:
            return 'PER'
        elif label in ['ORGANIZATION', 'ORG']:
            return 'ORG'
        elif label in ['LOCATION', 'LOC']:
            return 'LOC'
        elif label in ['DATE', 'TIME']:
            return 'DATE'
        else:
            return 'MISC'
    
    def _fallback_mock_extract(self, lines: List[str]) -> List[List[Dict[str, Any]]]:
        """Fallback vers extraction mock."""
        try:
            from .mock import MockNer
            mock_ner = MockNer()
            mock_results = mock_ner.tag_entities(lines)
            
            # Normaliser le format des entités du mock
            normalized_results = []
            for line_entities in mock_results:
                normalized_line = []
                for entity in line_entities:
                    normalized_entity = {
                        'text': entity.get('word', entity.get('text', '')),
                        'label': self._normalize_label(entity.get('entity_group', entity.get('label', 'MISC'))),
                        'start': entity.get('start', 0),
                        'end': entity.get('end', 0), 
                        'score': entity.get('score', 0.0),
                        'line_idx': 0  # Sera mis à jour par extract()
                    }
                    normalized_line.append(normalized_entity)
                normalized_results.append(normalized_line)
            
            return normalized_results
            
        except ImportError as e:
            logger.warning(f"NER: mock_fallback_failed | error={e}")
            return [[] for _ in lines]


class NERRouter:
    """Router pour les modèles NER par langue."""
    
    def __init__(self, config: Dict[str, Any], 
                 device: str = "auto", 
                 local_files_only: bool = False, 
                 cache_dir: str = ".hf_cache", 
                 use_mock: bool = False,
                 on_event: Optional[Callable[[str, str], None]] = None):
        self.config = config.copy()
        # Injecter les nouveaux paramètres dans la config pour les backends
        self.config["device"] = device
        self.config["local_files_only"] = local_files_only
        self.config["hf_cache_dir"] = cache_dir
        self.config["use_mock"] = use_mock or config.get("use_mock", False)
        
        self.ner_config = self.config.get('ner', {})
        self.registry = self.ner_config.get('registry', {})
        self.cache = {}  # Cache LRU simple
        self.cache_order = []  # Ordre pour LRU
        self.max_cache_size = 3  # Max 3 modèles en cache
        self.on_event = on_event
        
        # Options globales
        self.enable_multilingual_fallback = self.config.get('enable_multilingual_fallback', True)
        self.max_total_ram_mb = self.config.get('max_total_model_ram_mb', 1800)
    
    @lru_cache(maxsize=8)
    def _get_model_name(self, lang_code: str) -> str:
        """Obtient le nom du modèle pour une langue."""
        if lang_code in self.registry:
            return self.registry[lang_code]
        elif self.enable_multilingual_fallback and 'multi' in self.registry:
            logger.info(f"NER: route | lang={lang_code} -> fallback=multi")
            return self.registry['multi']
        else:
            # Fallback vers français si disponible
            if 'fr' in self.registry:
                logger.info(f"NER: route | lang={lang_code} -> fallback=fr")
                return self.registry['fr']
            else:
                raise ValueError(f"No NER model available for language: {lang_code}")
    
    def load(self, lang_code: str) -> NERBackend:
        """
        Charge et met en cache un backend NER pour la langue.
        
        Args:
            lang_code: Code langue ('fr', 'en', 'multi')
            
        Returns:
            Backend NER chargé
        """
        try:
            model_name = self._get_model_name(lang_code)
            local_only = self.ner_config.get('local_only', True)
            
            # Log explicit de routage avant load
            logger.info(f"NER: route | lang={lang_code} -> backend={model_name} | local_only={local_only}")
            
            # Vérifier le cache
            cache_key = f"{lang_code}:{model_name}"
            if cache_key in self.cache:
                # Déplacer en fin de cache (LRU)
                self.cache_order.remove(cache_key)
                self.cache_order.append(cache_key)
                logger.debug(f"NER: route | lang={lang_code} -> backend={model_name} | cached=true")
                return self.cache[cache_key]
            
            # Créer nouveau backend
            backend = NERBackend(model_name, {
                **self.ner_config,
                'use_mock': self.config.get('use_mock', False),
                'hf_cache_dir': self.config.get('hf_cache_dir', '.hf_cache'),
                'runtime': self.config.get('runtime', {})
            }, self.on_event)
            
            # Gestion du cache LRU
            if len(self.cache) >= self.max_cache_size:
                # Supprimer le plus ancien
                oldest_key = self.cache_order.pop(0)
                del self.cache[oldest_key]
                logger.debug(f"NER: cache_evict | key={oldest_key}")
            
            # Ajouter au cache
            self.cache[cache_key] = backend
            self.cache_order.append(cache_key)
            
            return backend
            
        except Exception as e:
            logger.error(f"NER: load_error | lang={lang_code} | error={e}")
            # Fallback vers mock
            return self._create_mock_backend()
    
    def _create_mock_backend(self) -> NERBackend:
        """Crée un backend mock en fallback."""
        backend = NERBackend("mock", {
            'use_mock': True,
            'batch_size': self.ner_config.get('batch_size', 16)
        }, self.on_event)
        backend.load()  # Charge immédiatement le mock
        return backend
    
    def extract(self, lang_code: str, lines: List[str]) -> List[Dict[str, Any]]:
        """
        Extrait les entités pour les lignes données.
        
        Args:
            lang_code: Code langue
            lines: Lignes de texte
            
        Returns:
            Entités normalisées au format:
            [{"text":"...", "label":"ORG|LOC|DATE|MISC", "start":i, "end":j, "line_idx":k}]
        """
        if not lines:
            return []
        
        try:
            backend = self.load(lang_code)
            entities_by_line = backend.extract_entities(lines)
            
            # Aplatir les entités avec line_idx
            all_entities = []
            for line_idx, line_entities in enumerate(entities_by_line):
                for entity in line_entities:
                    entity['line_idx'] = line_idx
                    all_entities.append(entity)
            
            return all_entities
            
        except Exception as e:
            logger.error(f"NER: extract_error | lang={lang_code} | error={e}")
            logger.warning("NER: backend_error -> mock")
            # Fallback complet vers mock
            try:
                from .mock import MockNer
                mock_ner = MockNer()
                entities_by_line = mock_ner.tag_entities(lines)
                
                all_entities = []
                for line_idx, line_entities in enumerate(entities_by_line):
                    for entity in line_entities:
                        entity['line_idx'] = line_idx
                        all_entities.append(entity)
                
                return all_entities
                
            except Exception as mock_error:
                logger.error(f"NER: mock_fallback_error | error={mock_error}")
                return []
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques du cache."""
        return {
            'cached_models': len(self.cache),
            'cache_keys': list(self.cache.keys()),
            'cache_order': self.cache_order.copy(),
            'max_cache_size': self.max_cache_size
        }
    
    def clear_cache(self):
        """Vide le cache des modèles."""
        self.cache.clear()
        self.cache_order.clear()
        logger.info("NER: cache_cleared")
