"""NER français pour l'extraction d'entités dans les CV."""

import logging
from typing import List, Dict, Any, Optional
from ..logging.safe_logger import get_safe_logger
from ..config import DEFAULT_PII_CONFIG

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


class FrenchNer:
    """NER français pour taguer ORG/LOC/DATE dans les CV."""
    
    def __init__(self, ml_config: Dict[str, Any]):
        """Initialise le NER français.
        
        Args:
            ml_config: Configuration ML depuis ml_config.json
        """
        self.config = ml_config
        self.ner_config = ml_config.get("ner", {})
        self.use_mock = ml_config.get("use_mock", False)
        
        if self.use_mock:
            from .mock import MockNer
            self.ner = MockNer()
            logger.info(f"ML: ner:loaded model=mock enabled=True mock=True")
        else:
            try:
                self._init_huggingface_pipeline()
                logger.info(f"ML: ner:loaded model={self.ner_config.get('model', 'unknown')} enabled=True mock=False")
            except Exception as e:
                logger.warning(f"ML: ner:fallback to mock due to error: {e}")
                from .mock import MockNer
                self.ner = MockNer()
                self.use_mock = True
    
    def _init_huggingface_pipeline(self):
        """Initialise le pipeline HuggingFace pour NER."""
        try:
            from transformers import pipeline
            model_name = self.ner_config.get("model", "CATIE-AQ/NERmembert-large-3entities")
            self.ner = pipeline(
                "ner",
                model=model_name,
                aggregation_strategy="simple",  # Groupe les tokens
                device=-1  # CPU pour éviter les problèmes CUDA
            )
        except ImportError:
            raise ImportError("transformers library not available, falling back to mock")
        except Exception as e:
            raise RuntimeError(f"Failed to load NER model: {e}")
    
    def tag_entities(self, lines: List[str]) -> List[List[Dict[str, Any]]]:
        """Tagge les entités dans les lignes.
        
        Args:
            lines: Liste des lignes de texte
            
        Returns:
            Liste de listes d'entités pour chaque ligne
            Chaque entité: {"entity_group": str, "word": str, "start": int, "end": int, "score": float}
        """
        if not lines:
            return []
        
        results = []
        batch_size = self.ner_config.get("batch_size", 16)
        
        # Traitement par batch
        for i in range(0, len(lines), batch_size):
            batch = lines[i:i + batch_size]
            try:
                batch_results = self._tag_batch(batch)
                results.extend(batch_results)
            except Exception as e:
                logger.warning(f"ML: ner:batch_error at {i}-{i+batch_size}: {e}")
                # Fallback vide pour ce batch
                results.extend([[] for _ in batch])
        
        return results
    
    def _tag_batch(self, batch: List[str]) -> List[List[Dict[str, Any]]]:
        """Tagge un batch de lignes."""
        results = []
        
        for line in batch:
            line = line.strip()
            if not line or len(line) < 2:
                results.append([])
                continue
            
            try:
                if self.use_mock:
                    entities = self.ner.tag_entities([line])[0]
                else:
                    # HuggingFace NER
                    ner_results = self.ner(line)
                    entities = []
                    for entity in ner_results:
                        # Normaliser le format de sortie
                        entity_group = entity.get("entity_group", entity.get("label", ""))
                        # Mapper les labels du modèle vers nos catégories
                        if entity_group in ["PER", "PERSON"]:
                            continue  # On ignore les personnes
                        elif entity_group in ["ORG", "ORGANISATION"]:
                            entity_group = "ORG"
                        elif entity_group in ["LOC", "LOCATION", "GPE"]:
                            entity_group = "LOC"
                        elif entity_group in ["DATE", "TIME"]:
                            entity_group = "DATE"
                        elif entity_group in ["MISC", "MISCELLANEOUS"]:
                            entity_group = "MISC"
                        else:
                            continue  # Ignorer les autres types
                        
                        entities.append({
                            "entity_group": entity_group,
                            "word": entity.get("word", ""),
                            "start": entity.get("start", 0),
                            "end": entity.get("end", 0),
                            "score": entity.get("score", 0.0)
                        })
                
                results.append(entities)
                
                # Log sample pour debug (pas trop verbeux)
                if entities and len(results) % 20 == 1:  # Un échantillon de temps en temps
                    ents_str = ", ".join([f"{e['entity_group']}:'{e['word']}'" for e in entities[:3]])
                    if len(entities) > 3:
                        ents_str += f", +{len(entities)-3} more"
                    logger.debug(f"NER: sample | line_i={len(results)-1} ents=[{ents_str}]")
                    
            except Exception as e:
                logger.warning(f"ML: ner:single_error for '{line[:50]}...': {e}")
                results.append([])
        
        return results
    
    def extract_entities_by_type(self, entities: List[Dict[str, Any]], entity_type: str) -> List[str]:
        """Extrait les entités d'un type donné.
        
        Args:
            entities: Liste d'entités
            entity_type: Type d'entité à extraire (ORG, LOC, DATE, etc.)
            
        Returns:
            Liste des mots des entités du type demandé
        """
        return [ent["word"] for ent in entities if ent.get("entity_group") == entity_type]
