"""Navigation registry service placeholder."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


@dataclass(slots=True)
class NavigationService:
    """Provides access to registered window sections."""

    sections: Dict[str, object] = field(default_factory=dict)

    def register(self, name: str, section: object) -> None:
        """Register a new navigable section."""

        self.sections[name] = section

