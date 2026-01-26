"""Options de debug pour l'extraction CV."""

from typing import Optional
from dataclasses import dataclass
from pathlib import Path


@dataclass
class DebugOptions:
    """Options de debug pour l'extraction CV."""
    
    # Snapshot ML 
    dump_snapshot: bool = False
    snapshot_path: Optional[str] = None
    
    # Autres options debug
    verbose_logging: bool = False
    save_intermediate_results: bool = False
    
    def __post_init__(self):
        """Post-initialisation."""
        if self.dump_snapshot and not self.snapshot_path:
            # Chemin par défaut
            debug_dir = Path(".debug")
            debug_dir.mkdir(exist_ok=True)
            self.snapshot_path = str(debug_dir / "cv_snapshot.json")
    
    @classmethod
    def default(cls) -> 'DebugOptions':
        """Retourne les options par défaut."""
        return cls()
    
    @classmethod
    def with_snapshot(cls, path: Optional[str] = None) -> 'DebugOptions':
        """Retourne les options avec snapshot activé."""
        return cls(dump_snapshot=True, snapshot_path=path)
