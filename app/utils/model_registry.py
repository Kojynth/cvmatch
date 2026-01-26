"""
Model Registry
==============

Central registry for LLM profiles and hardware tiers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import yaml
from loguru import logger


@dataclass
class ModelProfile:
    """Structured information about a generation model."""

    key: str
    display_name: str
    model_id: str
    loader: str
    quantization: str
    min_vram_gb: float
    min_ram_gb: float  # RAM CPU requise (permet modèles personnalisés)
    quality_stars: int
    speed_rating: int
    description: str
    tags: List[str] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        data = {
            "key": self.key,
            "display_name": self.display_name,
            "model_id": self.model_id,
            "loader": self.loader,
            "quantization": self.quantization,
            "min_vram_gb": self.min_vram_gb,
            "min_ram_gb": self.min_ram_gb,
            "quality_stars": self.quality_stars,
            "speed_rating": self.speed_rating,
            "description": self.description,
            "tags": list(self.tags),
        }
        data.update(self.extra)
        return data


@dataclass
class HardwareTier:
    """Configuration used to pick default models for a hardware slice."""

    key: str
    label: str
    min_vram_gb: float = 0.0
    min_ram_gb: float = 0.0
    default_model: Optional[str] = None
    fallback_models: List[str] = field(default_factory=list)

    def candidates(self) -> Iterable[str]:
        if self.default_model:
            yield self.default_model
        for item in self.fallback_models:
            if item != self.default_model:
                yield item


class ModelRegistry:
    """Loads profile definitions from YAML and resolves best fits."""

    def __init__(
        self,
        config_path: Optional[Path] = None,
        user_override_path: Optional[Path] = None,
    ) -> None:
        base_path = Path(__file__).resolve().parents[2] / "config" / "model_registry.yaml"
        self._config_path = config_path or base_path
        self._user_override_path = (
            user_override_path or Path.home() / ".cvmatch" / "model.yaml"
        )
        self._raw_config: Dict[str, Any] = {}
        self.profiles: Dict[str, ModelProfile] = {}
        self.hardware_tiers: Dict[str, HardwareTier] = {}
        self._default_profile_key: Optional[str] = None
        self.reload()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def reload(self) -> None:
        """Reload definitions from disk."""
        base_config = self._load_yaml(self._config_path)
        merged = dict(base_config)
        user_config = self._load_yaml(self._user_override_path, required=False)
        if user_config:
            merged = self._deep_merge_dicts(merged, user_config)
        self._raw_config = merged
        self.profiles = self._parse_profiles(merged.get("profiles", {}))
        self.hardware_tiers = self._parse_tiers(merged.get("hardware_tiers", {}))
        self._default_profile_key = self._resolve_default_profile_key()
        logger.debug(
            "Model registry loaded: %s profiles, %s tiers",
            len(self.profiles),
            len(self.hardware_tiers),
        )

    def list_profiles(self) -> List[ModelProfile]:
        return list(self.profiles.values())

    def get_profile(self, key: str) -> Optional[ModelProfile]:
        return self.profiles.get(key)

    def select_profile(
        self,
        hardware: Dict[str, Any],
        requested_key: Optional[str] = None,
    ) -> Optional[ModelProfile]:
        """Return the best profile for provided hardware info."""

        if requested_key and requested_key in self.profiles:
            logger.info("Using user requested model: %s", requested_key)
            return self.profiles[requested_key]

        # Try a tier match based on GPU first.
        gpu_available = bool(hardware.get("available"))
        vram_gb = float(hardware.get("vram_gb") or 0.0)
        if gpu_available and vram_gb > 0:
            profile = self._select_for_gpu(vram_gb)
            if profile:
                return profile

        # CPU fallback based on RAM if we did not select a GPU profile.
        ram_candidates = [
            hardware.get("ram_gb"),
            hardware.get("system_ram_gb"),
            hardware.get("ram_total_gb"),
            hardware.get("ram_available_gb"),
        ]
        ram_gb = next((float(val) for val in ram_candidates if val is not None), 0.0)
        profile = self._select_for_cpu(ram_gb)
        if profile:
            return profile

        # Fall back to default profile key.
        if self._default_profile_key and self._default_profile_key in self.profiles:
            default_profile = self.profiles[self._default_profile_key]

            # Validation: si pas de GPU mais modèle GPU requis, forcer un modèle CPU
            if not gpu_available and default_profile.min_vram_gb > 0:
                logger.warning(
                    "Fallback GPU %s incompatible (pas de GPU), recherche modèle CPU...",
                    self._default_profile_key,
                )
                # Tenter de trouver un modèle CPU compatible avec la RAM disponible
                cpu_profile = self._select_for_cpu(ram_gb)
                if cpu_profile:
                    return cpu_profile
                # Si aucun tier CPU ne correspond, choisir le profil CPU le plus léger
                cpu_profiles = [p for p in self.profiles.values() if p.min_vram_gb == 0]
                if cpu_profiles:
                    cpu_profiles.sort(key=lambda p: p.min_ram_gb)
                    lightest = cpu_profiles[0]
                    logger.info(
                        "Fallback ultime vers profil CPU le plus leger: %s (%.1fGB RAM)",
                        lightest.key,
                        lightest.min_ram_gb,
                    )
                    return lightest

            logger.info(
                "Fallback to default registry profile: %s", self._default_profile_key
            )
            return default_profile

        # As a last resort, return the lightest CPU-compatible profile.
        cpu_profiles = [p for p in self.profiles.values() if p.min_vram_gb == 0]
        if cpu_profiles:
            # Trier par RAM requise (le plus léger en premier)
            cpu_profiles.sort(key=lambda p: p.min_ram_gb)
            lightest = cpu_profiles[0]
            logger.warning(
                "Dernier recours: profil CPU le plus leger %s (%.1fGB RAM)",
                lightest.key,
                lightest.min_ram_gb,
            )
            return lightest

        # Vraiment dernier recours: premier profil disponible
        return next(iter(self.profiles.values()), None)

    def describe_profiles_for_dropdown(self) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        for profile in self.profiles.values():
            payload = profile.as_dict()
            payload["model_status"] = "available"
            payload["id"] = profile.key
            payload["text"] = f"{profile.display_name}"
            result.append(payload)
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _select_for_gpu(self, vram_gb: float) -> Optional[ModelProfile]:
        gpu_tiers = [
            tier
            for tier in self.hardware_tiers.values()
            if tier.min_vram_gb > 0 and vram_gb >= tier.min_vram_gb
        ]
        gpu_tiers.sort(key=lambda tier: tier.min_vram_gb, reverse=True)
        for tier in gpu_tiers:
            profile = self._pick_first_available(tier.candidates())
            if profile:
                logger.info(
                    "Resolved GPU tier %s (>=%.1fGB) to profile %s",
                    tier.key,
                    tier.min_vram_gb,
                    profile.key,
                )
                return profile
        return None

    def _select_for_cpu(self, ram_gb: float) -> Optional[ModelProfile]:
        cpu_tiers = [
            tier
            for tier in self.hardware_tiers.values()
            if tier.min_vram_gb == 0
        ]
        cpu_tiers.sort(key=lambda tier: tier.min_ram_gb, reverse=True)
        for tier in cpu_tiers:
            if ram_gb and tier.min_ram_gb and ram_gb < tier.min_ram_gb:
                continue
            profile = self._pick_first_available(tier.candidates())
            if profile:
                logger.info(
                    "Resolved CPU tier %s (>=%.1fGB RAM) to profile %s",
                    tier.key,
                    tier.min_ram_gb,
                    profile.key,
                )
                return profile
        return None

    def _pick_first_available(self, keys: Iterable[str]) -> Optional[ModelProfile]:
        for key in keys:
            profile = self.profiles.get(key)
            if profile:
                return profile
        return None

    def _parse_profiles(self, data: Dict[str, Any]) -> Dict[str, ModelProfile]:
        profiles: Dict[str, ModelProfile] = {}
        for key, raw in data.items():
            try:
                # Pour modèles personnalisés sans min_ram_gb, estimer selon min_vram_gb
                min_vram = float(raw.get("min_vram_gb", 0) or 0)
                min_ram_default = max(4.0, min_vram * 2)  # Estimation: RAM ~= 2x VRAM

                profile = ModelProfile(
                    key=key,
                    display_name=str(raw.get("display_name", key)),
                    model_id=str(raw.get("model_id", "")),
                    loader=str(raw.get("loader", "transformers")),
                    quantization=str(raw.get("quantization", "auto")),
                    min_vram_gb=min_vram,
                    min_ram_gb=float(raw.get("min_ram_gb", min_ram_default) or min_ram_default),
                    quality_stars=int(raw.get("quality_stars", 3) or 0),
                    speed_rating=int(raw.get("speed_rating", 3) or 0),
                    description=str(raw.get("description", "")),
                    tags=list(raw.get("tags", [])),
                    extra={
                        k: v
                        for k, v in raw.items()
                        if k
                        not in {
                            "display_name",
                            "model_id",
                            "loader",
                            "quantization",
                            "min_vram_gb",
                            "min_ram_gb",
                            "quality_stars",
                            "speed_rating",
                            "description",
                            "tags",
                        }
                    },
                )
                profiles[key] = profile
            except Exception as exc:  # pragma: no cover - defensive
                logger.error("Invalid profile %s: %s", key, exc)
        return profiles

    def _parse_tiers(self, data: Dict[str, Any]) -> Dict[str, HardwareTier]:
        tiers: Dict[str, HardwareTier] = {}
        for key, raw in data.items():
            tier = HardwareTier(
                key=key,
                label=str(raw.get("label", key)),
                min_vram_gb=float(raw.get("min_vram_gb", 0) or 0),
                min_ram_gb=float(raw.get("min_ram_gb", 0) or 0),
                default_model=raw.get("default_model"),
                fallback_models=list(raw.get("fallback_models", [])),
            )
            tiers[key] = tier
        return tiers

    def _resolve_default_profile_key(self) -> Optional[str]:
        """Résout le profil par défaut - prioriser CPU pour compatibilité universelle."""
        # D'abord, chercher un modèle CPU fiable comme fallback universel
        # Cela garantit que même sans GPU, un modèle compatible sera disponible
        cpu_defaults = [
            (tier.min_ram_gb, tier.default_model)
            for tier in self.hardware_tiers.values()
            if tier.default_model and tier.min_vram_gb == 0
        ]
        if cpu_defaults:
            # Prendre le tier CPU avec le moins de RAM requis (plus compatible)
            cpu_defaults.sort(key=lambda item: item[0])
            for _, key in cpu_defaults:
                if key in self.profiles:
                    logger.debug("Default profile (CPU compatible): %s", key)
                    return key

        # Sinon, profils GPU (pour machines avec GPU)
        gpu_defaults = [
            (tier.min_vram_gb, tier.default_model)
            for tier in self.hardware_tiers.values()
            if tier.default_model and tier.min_vram_gb > 0
        ]
        if gpu_defaults:
            gpu_defaults.sort(key=lambda item: item[0], reverse=True)
            for _, key in gpu_defaults:
                if key in self.profiles:
                    return key

        # Dernier recours : premier profil disponible
        if self.profiles:
            return next(iter(self.profiles.keys()))
        return None

    def _load_yaml(self, path: Path, required: bool = True) -> Dict[str, Any]:
        if not path.exists():
            if required:
                logger.warning("Model registry file not found: %s", path)
            return {}
        try:
            with path.open("r", encoding="utf-8") as handle:
                content = yaml.safe_load(handle) or {}
                if not isinstance(content, dict):
                    raise ValueError("Registry file root must be a mapping")
                return content
        except Exception as exc:
            logger.error("Failed to load registry file %s: %s", path, exc)
            return {}

    def _deep_merge_dicts(
        self, base: Dict[str, Any], override: Dict[str, Any]
    ) -> Dict[str, Any]:
        merged = dict(base)
        for key, value in override.items():
            if (
                key in merged
                and isinstance(merged[key], dict)
                and isinstance(value, dict)
            ):
                merged[key] = self._deep_merge_dicts(merged[key], value)
            else:
                merged[key] = value
        return merged


# Global singleton used across the app
model_registry = ModelRegistry()
