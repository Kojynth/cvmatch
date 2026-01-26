"""
Garde-fou pour garantir la cohérence du schéma de données extraites.

Ce module assure que :
- personal_info est toujours un dict
- Les autres sections sont toujours des listes
- Aucune corruption de type ne peut faire planter l'UI en aval
"""

from typing import Any, Dict, List
from loguru import logger
from ..common.sections import LIST_SECTIONS

def sanitize_extracted_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalise et sécurise le payload d'extraction pour garantir le bon schéma.
    
    Args:
        data: Données extraites potentiellement corrompues
        
    Returns:
        Dict avec schéma garanti: personal_info=dict, autres=list
    """
    if not isinstance(data, dict):
        logger.warning("🛡️ Payload d'extraction n'est pas un dict, initialisation par défaut")
        return {
            "personal_info": {},
            **{k: [] for k in LIST_SECTIONS}
        }

    out: Dict[str, Any] = {}

    # personal_info = dict obligatoire
    pi = data.get("personal_info")
    out["personal_info"] = pi if isinstance(pi, dict) else {}
    
    if not isinstance(pi, dict) and pi is not None:
        logger.warning(f"🛡️ personal_info n'était pas un dict ({type(pi).__name__}), converti en dict vide")

    # sections listes obligatoires
    for k in LIST_SECTIONS:
        v = data.get(k)
        if v is None:
            out[k] = []
        elif isinstance(v, list):
            out[k] = v
        elif isinstance(v, tuple):
            out[k] = list(v)
            logger.debug(f"🛡️ {k} converti de tuple vers list")
        else:
            # cas dégénéré: élément seul → liste à 1 élément
            out[k] = [v]
            logger.warning(f"🛡️ {k} n'était pas une liste ({type(v).__name__}), encapsulé dans une liste")

    return out

def log_schema_types(data: Dict[str, Any], context: str = "schema") -> None:
    """
    Log les types de chaque section pour diagnostic rapide.
    
    Args:
        data: Données à analyser
        context: Contexte du log pour identification
    """
    sections_to_check = ["personal_info"] + LIST_SECTIONS
    
    for k in sections_to_check:
        v = data.get(k)
        if isinstance(v, (list, tuple)):
            length = len(v)
        elif isinstance(v, dict):
            length = len(v)
        else:
            length = "n/a"
        
        logger.info(f"[{context}] {k}: {type(v).__name__} len={length}")
