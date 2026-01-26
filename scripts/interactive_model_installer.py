#!/usr/bin/env python3
"""
Interactive Model Collection Installer
======================================

Provides interactive selection and installation of AI model collections
for CVMatch, with progress tracking and verification.

Features:
- Interactive model collection selection
- Progress tracking with ETA and speed reporting
- Model integrity verification
- Disk space estimation and validation
- Graceful error handling and recovery
"""

import json
import os
import shutil
import sys
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

import yaml

# Add project root to path for imports
script_dir = Path(__file__).parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root))

try:
    from cvextractor.ml.model_downloader import ModelDownloader, DownloadProgress
except ImportError:
    ModelDownloader = None
    DownloadProgress = None
    print("Note: Full CVMatch modules not available - using basic functionality")


class InstallationMode(Enum):
    """Installation mode selection."""

    INTERACTIVE = "interactive"
    MINIMAL = "minimal"
    STANDARD = "standard"
    FULL = "full"
    CUSTOM = "custom"


@dataclass
class CollectionInfo:
    """Information about a model collection."""

    name: str
    description: str
    models: List[str]
    estimated_size_gb: float
    estimated_time_min: int
    recommended_ram_gb: int
    gpu_recommended: bool
    languages: List[str]
    features: List[str]


class InteractiveModelInstaller:
    """
    Interactive installer for AI model collections.

    Handles user selection, progress tracking, and verification
    of model downloads and installation.
    """

    def __init__(self, project_root: Path = None):
        """
        Initialize interactive model installer.

        Args:
            project_root: Path to project root directory
        """
        self.project_root = project_root or Path(__file__).parent.parent
        self.config_file = self.project_root / "config" / "models.yaml"
        self.config_missing = not self.config_file.exists()
        self.models_dir = self.project_root / "models"
        self.cache_dir = self.project_root / ".hf_cache"

        # Load model configuration
        self.model_config = self._load_model_config()
        self.collections_info = self._build_collections_info()

        # Initialize downloader if available and config is compatible
        self.downloader = None
        if ModelDownloader and self.model_config.get("models"):
            self.downloader = ModelDownloader(
                self.model_config,
                cache_dir=self.cache_dir,
            )

    def _load_model_config(self) -> Dict:
        """Load model configuration from YAML file."""
        try:
            if not self.config_file.exists():
                print(f"Warning: model config not found at {self.config_file}")
                return {}
            with open(self.config_file, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as exc:
            print(f"Warning: Could not load model config: {exc}")
            return {}

    def _build_collections_info(self) -> Dict[str, CollectionInfo]:
        """Build collection information from config."""
        collections = {}

        config_collections = (
            self.model_config.get("model_collections")
            or self.model_config.get("collections")
            or {}
        )

        for collection_name, collection_data in config_collections.items():
            # Calculate estimates
            models = collection_data.get("models", [])
            estimated_size = len(models) * 0.5  # Rough estimate: 500MB per model
            estimated_time = len(models) * 3  # Rough estimate: 3 min per model

            # Determine requirements based on collection
            if "full" in collection_name.lower():
                ram_gb = 16
                gpu_recommended = True
            elif "standard" in collection_name.lower():
                ram_gb = 8
                gpu_recommended = False
            else:
                ram_gb = 4
                gpu_recommended = False

            collections[collection_name] = CollectionInfo(
                name=collection_name,
                description=collection_data.get("description", "AI model collection"),
                models=models,
                estimated_size_gb=estimated_size,
                estimated_time_min=estimated_time,
                recommended_ram_gb=ram_gb,
                gpu_recommended=gpu_recommended,
                languages=collection_data.get("languages", ["fr", "en"]),
                features=collection_data.get("features", []),
            )

        return collections

    def run_interactive_installation(self) -> bool:
        """
        Run interactive model collection installation.

        Returns:
            bool: True if installation successful, False otherwise
        """
        print("\n" + "=" * 60)
        print("CVMatch AI Model Collection Installer")
        print("=" * 60)

        # System checks
        if not self._perform_system_checks():
            return False

        if not self.collections_info:
            print("\nNo model collections configured. Skipping interactive installation.")
            return True

        # Collection selection
        selected_collection = self._select_collection()
        if not selected_collection:
            print("Installation cancelled.")
            return False

        # Confirm installation
        if not self._confirm_installation(selected_collection):
            print("Installation cancelled.")
            return False

        # Perform installation
        return self._install_collection(selected_collection)

    def _perform_system_checks(self) -> bool:
        """Perform system requirement checks."""
        print("\nSystem Requirements Check")
        print("-" * 30)

        # Check disk space
        free_space_gb = shutil.disk_usage(self.project_root).free / (1024**3)
        print(f"Available disk space: {free_space_gb:.1f} GB")

        if free_space_gb < 2.0:
            print("ERROR: Insufficient disk space (minimum 2GB required)")
            return False

        # Check Python version
        python_version = sys.version_info
        print(
            f"Python version: {python_version.major}.{python_version.minor}.{python_version.micro}"
        )

        if python_version < (3, 10):
            print("ERROR: Python 3.10+ required")
            return False

        # Check internet connectivity (basic)
        try:
            import urllib.request

            urllib.request.urlopen("https://huggingface.co", timeout=5)
            print("Internet connectivity: Available")
        except Exception:
            print("WARN: Internet connectivity: Limited (some models may not download)")

        return True

    def _select_collection(self) -> Optional[str]:
        """Interactive collection selection."""
        print("\nSelect AI Model Collection")
        print("-" * 40)

        # Display available collections
        collection_list = list(self.collections_info.keys())

        if not collection_list:
            print("ERROR: No model collections found in configuration")
            return None

        for i, collection_name in enumerate(collection_list, 1):
            info = self.collections_info[collection_name]
            print(f"\n{i}. {collection_name.upper()}")
            print(f"   Description: {info.description}")
            print(f"   Models: {len(info.models)} models")
            print(f"   Size: ~{info.estimated_size_gb:.1f} GB")
            print(f"   Time: ~{info.estimated_time_min} minutes")
            print(f"   RAM: {info.recommended_ram_gb} GB recommended")
            print(f"   Languages: {', '.join(info.languages)}")
            if info.gpu_recommended:
                print("   GPU: Recommended for best performance")

        # Get user selection
        while True:
            try:
                print(f"\nSelect collection (1-{len(collection_list)}) or 'q' to quit: ", end="")
                choice = input().strip().lower()

                if choice == "q":
                    return None

                choice_num = int(choice)
                if 1 <= choice_num <= len(collection_list):
                    return collection_list[choice_num - 1]
                print("ERROR: Invalid selection. Please try again.")

            except (ValueError, KeyboardInterrupt):
                print("\nERROR: Invalid input or cancelled.")
                return None

    def _confirm_installation(self, collection_name: str) -> bool:
        """Confirm installation details with user."""
        info = self.collections_info[collection_name]

        print(f"\nSelected: {collection_name.upper()}")
        print("-" * 40)
        print(f"Models to install: {len(info.models)}")
        print(f"Estimated download size: {info.estimated_size_gb:.1f} GB")
        print(f"Estimated time: {info.estimated_time_min} minutes")
        print(f"Installation path: {self.models_dir}")

        if info.gpu_recommended:
            print("\nThis collection is optimized for GPU acceleration.")
            print("Ensure you have CUDA-compatible GPU and drivers installed.")

        print("\nModel list:")
        for model in info.models:
            print(f"  - {model}")

        while True:
            try:
                print("\nProceed with installation? (y/n): ", end="")
                confirm = input().strip().lower()

                if confirm in ["y", "yes"]:
                    return True
                if confirm in ["n", "no"]:
                    return False
                print("ERROR: Please enter 'y' or 'n'")

            except KeyboardInterrupt:
                print("\nERROR: Installation cancelled.")
                return False

    def _install_collection(self, collection_name: str) -> bool:
        """Install selected model collection."""
        info = self.collections_info[collection_name]

        print(f"\nInstalling {collection_name.upper()} Collection")
        print("=" * 50)

        # Ensure directories exist
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        if not self.downloader:
            print("WARN: Advanced downloader not available - using basic installation")
            return self._install_collection_basic(info)

        # Download each model
        total_models = len(info.models)
        successful_downloads = 0

        for i, model_id in enumerate(info.models, 1):
            print(f"\n[{i}/{total_models}] Downloading {model_id}")
            print("-" * 40)

            try:
                # Create progress callback
                def progress_callback(progress: DownloadProgress):
                    percent = getattr(progress, "progress_percent", 0.0)
                    speed = getattr(progress, "speed_mbps", 0.0)
                    eta_seconds = getattr(progress, "eta_seconds", 0.0)
                    if speed > 0:
                        eta_str = f"ETA: {eta_seconds:.0f}s" if eta_seconds else "ETA: --"
                        print(
                            f"\n  Progress: {percent:.1f}% | "
                            f"Speed: {speed:.1f} MB/s | {eta_str}     ",
                            end="",
                        )
                    else:
                        print(f"\nProgress: {percent:.1f}%     ", end="")

                # Download model
                try:
                    self.downloader.progress_callback = progress_callback
                    success = self.downloader.download_model(model_id=model_id)
                finally:
                    self.downloader.progress_callback = None

                print()  # New line after progress

                if success:
                    print(f"  OK: {model_id} downloaded successfully")
                    successful_downloads += 1
                else:
                    print(f"  ERROR: Failed to download {model_id}")

            except Exception as exc:
                print(f"  ERROR: Error downloading {model_id}: {exc}")
                continue

        # Installation summary
        print("\nInstallation Summary")
        print("-" * 30)
        print(f"Collection: {collection_name}")
        print(f"Successful downloads: {successful_downloads}/{total_models}")

        if successful_downloads == total_models:
            print("OK: All models installed successfully!")
            self._save_installation_record(collection_name, info)
            return True
        if successful_downloads > 0:
            print("WARN: Partial installation completed")
            print("Some models failed to download but basic functionality available")
            self._save_installation_record(collection_name, info, partial=True)
            return True

        print("ERROR: Installation failed - no models downloaded")
        return False

    def _install_collection_basic(self, info: CollectionInfo) -> bool:
        """Basic installation without advanced downloader."""
        print("Using basic installation mode...")
        print("Models will be downloaded automatically when first used.")
        print("This may cause delays during initial AI operations.")

        # Create placeholder configuration
        install_info = {
            "collection": info.name,
            "models": info.models,
            "installation_mode": "lazy_download",
            "installed_at": time.time(),
        }

        install_file = self.models_dir / "installation_info.json"
        with open(install_file, "w", encoding="utf-8") as f:
            json.dump(install_info, f, indent=2)

        print("OK: Basic installation completed")
        return True

    def _save_installation_record(
        self, collection_name: str, info: CollectionInfo, partial: bool = False
    ):
        """Save installation record for future reference."""
        install_info = {
            "collection": collection_name,
            "models": info.models,
            "installation_mode": "full_download" if not partial else "partial_download",
            "installed_at": time.time(),
            "partial": partial,
        }

        install_file = self.models_dir / "installation_info.json"
        with open(install_file, "w", encoding="utf-8") as f:
            json.dump(install_info, f, indent=2)


def main():
    """Main entry point for interactive model installer."""
    try:
        installer = InteractiveModelInstaller()
        success = installer.run_interactive_installation()

        if success:
            print("\nModel installation completed!")
            print("You can now run CVMatch with AI capabilities enabled.")
            sys.exit(0)

        print("\nWARN: Model installation incomplete or cancelled.")
        print("CVMatch will run in rules-only mode without AI features.")
        sys.exit(1)

    except KeyboardInterrupt:
        print("\nWARN: Installation cancelled by user.")
        sys.exit(1)
    except Exception as exc:
        print(f"\nERROR: Installation error: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
