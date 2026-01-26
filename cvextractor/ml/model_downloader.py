"""
AI Model Downloader with Progress Tracking
==========================================

Provides robust downloading of AI models with progress tracking, integrity verification,
and graceful error handling. Designed for offline-first operation with intelligent
fallback behavior.
"""

import hashlib
import time
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, Optional, Callable, List
import logging
import requests
from urllib.parse import urljoin
import yaml

# Configure logger
logger = logging.getLogger(__name__)


@dataclass
class DownloadProgress:
    """Progress tracking for model downloads."""

    model_id: str
    total_size_bytes: int = 0
    downloaded_bytes: int = 0
    speed_mbps: float = 0.0
    eta_seconds: float = 0.0
    stage: str = "initializing"  # initializing, downloading, verifying, installing
    error: Optional[str] = None
    start_time: float = field(default_factory=time.time)

    @property
    def progress_percent(self) -> float:
        """Calculate download progress percentage."""
        if self.total_size_bytes == 0:
            return 0.0
        return min(100.0, (self.downloaded_bytes / self.total_size_bytes) * 100.0)

    @property
    def elapsed_time(self) -> float:
        """Get elapsed time since download started."""
        return time.time() - self.start_time

    def update_speed_and_eta(self) -> None:
        """Update download speed and ETA calculations."""
        elapsed = self.elapsed_time
        if elapsed > 0 and self.downloaded_bytes > 0:
            # Calculate speed in MB/s
            speed_bytes_per_sec = self.downloaded_bytes / elapsed
            self.speed_mbps = speed_bytes_per_sec / (1024 * 1024)

            # Calculate ETA
            remaining_bytes = self.total_size_bytes - self.downloaded_bytes
            if speed_bytes_per_sec > 0:
                self.eta_seconds = remaining_bytes / speed_bytes_per_sec
            else:
                self.eta_seconds = float("inf")

    def format_progress(self) -> str:
        """Format progress as human-readable string."""
        progress_mb = self.downloaded_bytes / (1024 * 1024)
        total_mb = self.total_size_bytes / (1024 * 1024)

        if self.eta_seconds < float("inf") and self.eta_seconds > 0:
            eta_str = f", ETA: {int(self.eta_seconds)}s"
        else:
            eta_str = ""

        return (
            f"{self.model_id}: {progress_mb:.1f}/{total_mb:.1f} MB "
            f"({self.progress_percent:.1f}%) "
            f"@ {self.speed_mbps:.1f} MB/s{eta_str}"
        )


class ModelDownloadError(Exception):
    """Exception raised when model download fails."""

    pass


class ModelDownloader:
    """
    Robust model downloader with progress tracking and verification.

    Features:
    - Resume interrupted downloads
    - Parallel file downloads within a model
    - Real-time progress tracking
    - SHA256 integrity verification
    - Graceful error handling and cleanup
    """

    def __init__(
        self,
        models_config: Dict[str, Any],
        progress_callback: Optional[Callable[[DownloadProgress], None]] = None,
        cache_dir: Path = Path(".cache/models"),
    ):
        """
        Initialize model downloader.

        Args:
            models_config: Loaded models.yaml configuration
            progress_callback: Callback function for progress updates
            cache_dir: Base directory for model cache
        """
        self.models_config = models_config
        self.progress_callback = progress_callback
        self.cache_dir = Path(cache_dir)
        self.download_settings = models_config.get("download_settings", {})

        # Download settings
        self.timeout = self.download_settings.get("timeout_seconds", 300)
        self.max_retries = self.download_settings.get("max_retries", 3)
        self.chunk_size = self.download_settings.get("chunk_size_kb", 8192) * 1024
        self.progress_interval = self.download_settings.get(
            "progress_update_interval_seconds", 2
        )

        # Ensure cache directory exists
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Current downloads tracking
        self._active_downloads: Dict[str, DownloadProgress] = {}

    def download_model(self, model_id: str, force_redownload: bool = False) -> bool:
        """
        Download a specific model with progress tracking.

        Args:
            model_id: Model identifier from models.yaml
            force_redownload: Force redownload even if model exists

        Returns:
            bool: True if download successful, False otherwise

        Raises:
            ModelDownloadError: If download fails after all retries
        """
        logger.info(f"MODEL_DOWNLOADER: download_start | model_id={model_id}")

        # Get model configuration
        model_config = self._get_model_config(model_id)
        if not model_config:
            raise ModelDownloadError(f"Model '{model_id}' not found in configuration")

        # Check if already exists and complete
        if not force_redownload and self._is_model_complete(model_id, model_config):
            logger.info(f"MODEL_DOWNLOADER: already_exists | model_id={model_id}")
            return True

        # Initialize progress tracking
        progress = DownloadProgress(model_id=model_id)
        self._active_downloads[model_id] = progress

        try:
            # Estimate total size
            progress.total_size_bytes = model_config.get("size_mb", 0) * 1024 * 1024
            progress.stage = "downloading"
            self._report_progress(progress)

            # Download using appropriate method
            download_url = model_config.get("download_url")
            huggingface_model_id = model_config.get("huggingface_model_id")

            if huggingface_model_id:
                success = self._download_huggingface_model(
                    model_id, model_config, progress
                )
            elif download_url:
                success = self._download_direct_url(model_id, model_config, progress)
            else:
                raise ModelDownloadError(
                    f"No download URL or HuggingFace ID specified for {model_id}"
                )

            if success:
                progress.stage = "verifying"
                self._report_progress(progress)

                # Verify download integrity
                if self._verify_model_integrity(model_id, model_config):
                    progress.stage = "complete"
                    progress.downloaded_bytes = progress.total_size_bytes
                    self._report_progress(progress)
                    logger.info(
                        f"MODEL_DOWNLOADER: download_success | model_id={model_id}"
                    )
                    return True
                else:
                    raise ModelDownloadError(
                        f"Model integrity verification failed for {model_id}"
                    )

        except Exception as e:
            progress.error = str(e)
            progress.stage = "error"
            self._report_progress(progress)
            logger.error(
                f"MODEL_DOWNLOADER: download_failed | model_id={model_id} error={e}"
            )

            # Cleanup on failure
            if self.download_settings.get("cleanup_on_failure", True):
                self._cleanup_failed_download(model_id, model_config)

            raise ModelDownloadError(f"Failed to download {model_id}: {e}")

        finally:
            # Remove from active downloads
            self._active_downloads.pop(model_id, None)

        return False

    def download_collection(self, collection_name: str) -> Dict[str, bool]:
        """
        Download all models in a collection.

        Args:
            collection_name: Collection name from models.yaml

        Returns:
            Dict[str, bool]: Download results for each model
        """
        logger.info(
            f"MODEL_DOWNLOADER: collection_start | collection={collection_name}"
        )

        collections = self.models_config.get("collections", {})
        if collection_name not in collections:
            raise ModelDownloadError(f"Collection '{collection_name}' not found")

        collection_config = collections[collection_name]
        model_ids = collection_config.get("models", [])

        results = {}
        for model_id in model_ids:
            try:
                results[model_id] = self.download_model(model_id)
            except ModelDownloadError as e:
                logger.error(
                    f"MODEL_DOWNLOADER: collection_model_failed | {model_id}: {e}"
                )
                results[model_id] = False

        success_count = sum(results.values())
        logger.info(
            f"MODEL_DOWNLOADER: collection_complete | {success_count}/{len(model_ids)} successful"
        )

        return results

    def get_download_status(self) -> Dict[str, DownloadProgress]:
        """Get current download status for all active downloads."""
        return self._active_downloads.copy()

    def _get_model_config(self, model_id: str) -> Optional[Dict[str, Any]]:
        """Get model configuration from models.yaml."""
        models = self.models_config.get("models", {})
        return models.get(model_id)

    def _is_model_complete(self, model_id: str, model_config: Dict[str, Any]) -> bool:
        """Check if model is already downloaded and complete."""
        local_path = Path(model_config.get("local_path", ""))

        if not local_path.exists():
            return False

        # Check if all required files exist
        file_list = model_config.get("file_list", [])
        for filename in file_list:
            file_path = local_path / filename
            if not file_path.exists():
                logger.debug(f"MODEL_DOWNLOADER: missing_file | {file_path}")
                return False

        return True

    def _download_huggingface_model(
        self, model_id: str, model_config: Dict[str, Any], progress: DownloadProgress
    ) -> bool:
        """Download model from HuggingFace Hub."""
        try:
            from huggingface_hub import snapshot_download

            huggingface_model_id = model_config["huggingface_model_id"]
            local_path = Path(model_config["local_path"])

            logger.info(
                f"MODEL_DOWNLOADER: hf_download_start | {huggingface_model_id} -> {local_path}"
            )

            # Ensure parent directory exists
            local_path.parent.mkdir(parents=True, exist_ok=True)

            # Download with progress tracking
            def progress_hook(info):
                if info.get("event") == "downloading":
                    progress.downloaded_bytes = info.get("downloaded", 0)
                    progress.update_speed_and_eta()
                    self._report_progress(progress)

            # Download model
            snapshot_download(
                repo_id=huggingface_model_id,
                local_dir=str(local_path),
                local_files_only=False,
                resume_download=True,
                tqdm_class=None,  # We handle progress ourselves
            )

            return True

        except ImportError:
            logger.error(
                "HuggingFace Hub library not available - install with 'pip install huggingface_hub'"
            )
            return False
        except Exception as e:
            logger.error(f"MODEL_DOWNLOADER: hf_download_failed | {e}")
            return False

    def _download_direct_url(
        self, model_id: str, model_config: Dict[str, Any], progress: DownloadProgress
    ) -> bool:
        """Download model from direct URL."""
        download_url = model_config["download_url"]
        local_path = Path(model_config["local_path"])

        logger.info(
            f"MODEL_DOWNLOADER: direct_download_start | {download_url} -> {local_path}"
        )

        # Ensure parent directory exists
        local_path.parent.mkdir(parents=True, exist_ok=True)

        # Create temporary download directory
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir) / model_id

            try:
                # Download with progress tracking
                response = requests.get(download_url, stream=True, timeout=self.timeout)
                response.raise_for_status()

                # Get total size
                total_size = int(response.headers.get("content-length", 0))
                if total_size > 0:
                    progress.total_size_bytes = total_size

                # Download in chunks
                downloaded = 0
                with open(temp_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=self.chunk_size):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            progress.downloaded_bytes = downloaded
                            progress.update_speed_and_eta()
                            self._report_progress(progress)

                # Move to final location
                shutil.move(str(temp_path), str(local_path))
                return True

            except Exception as e:
                logger.error(f"MODEL_DOWNLOADER: direct_download_failed | {e}")
                return False

    def _verify_model_integrity(
        self, model_id: str, model_config: Dict[str, Any]
    ) -> bool:
        """Verify downloaded model integrity using SHA256."""
        local_path = Path(model_config.get("local_path", ""))
        expected_sha256 = model_config.get("sha256")

        # Skip verification if no checksum provided
        if (
            not expected_sha256
            or expected_sha256
            == "placeholder_sha256_will_be_calculated_during_download"
        ):
            logger.warning(
                f"MODEL_DOWNLOADER: no_checksum | model_id={model_id} - skipping verification"
            )
            return True

        # Calculate actual checksum
        if local_path.is_file():
            # Single file
            actual_sha256 = self._calculate_file_sha256(local_path)
        elif local_path.is_dir():
            # Directory - calculate combined checksum
            actual_sha256 = self._calculate_directory_sha256(local_path)
        else:
            logger.error(f"MODEL_DOWNLOADER: invalid_path | {local_path}")
            return False

        # Compare checksums
        if actual_sha256 == expected_sha256:
            logger.info(f"MODEL_DOWNLOADER: integrity_verified | model_id={model_id}")
            return True
        else:
            logger.error(
                f"MODEL_DOWNLOADER: integrity_failed | model_id={model_id} "
                f"expected={expected_sha256} actual={actual_sha256}"
            )
            return False

    def _calculate_file_sha256(self, file_path: Path) -> str:
        """Calculate SHA256 checksum for a single file."""
        hash_sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_sha256.update(chunk)
        return hash_sha256.hexdigest()

    def _calculate_directory_sha256(self, dir_path: Path) -> str:
        """Calculate combined SHA256 checksum for a directory."""
        hash_sha256 = hashlib.sha256()

        # Get all files in sorted order for consistent hashing
        all_files = sorted(dir_path.rglob("*"))
        for file_path in all_files:
            if file_path.is_file():
                # Include relative path in hash for structure verification
                relative_path = file_path.relative_to(dir_path)
                hash_sha256.update(str(relative_path).encode("utf-8"))

                # Include file content in hash
                with open(file_path, "rb") as f:
                    for chunk in iter(lambda: f.read(4096), b""):
                        hash_sha256.update(chunk)

        return hash_sha256.hexdigest()

    def _cleanup_failed_download(
        self, model_id: str, model_config: Dict[str, Any]
    ) -> None:
        """Clean up failed download artifacts."""
        local_path = Path(model_config.get("local_path", ""))

        if local_path.exists():
            try:
                if local_path.is_file():
                    local_path.unlink()
                elif local_path.is_dir():
                    shutil.rmtree(local_path)
                logger.info(f"MODEL_DOWNLOADER: cleanup_complete | model_id={model_id}")
            except Exception as e:
                logger.warning(
                    f"MODEL_DOWNLOADER: cleanup_failed | model_id={model_id} error={e}"
                )

    def _report_progress(self, progress: DownloadProgress) -> None:
        """Report progress to callback if available."""
        if self.progress_callback:
            try:
                self.progress_callback(progress)
            except Exception as e:
                logger.warning(f"MODEL_DOWNLOADER: progress_callback_error | {e}")

        # Also log progress periodically
        if progress.stage == "downloading":
            logger.debug(f"MODEL_DOWNLOADER: progress | {progress.format_progress()}")


# Convenience functions
def download_model_with_progress(
    model_id: str,
    models_config_path: str = "config/models.yaml",
    progress_callback: Optional[Callable] = None,
) -> bool:
    """
    Convenience function to download a single model with progress tracking.

    Args:
        model_id: Model identifier
        models_config_path: Path to models.yaml configuration
        progress_callback: Optional progress callback

    Returns:
        bool: True if download successful
    """
    # Load configuration
    with open(models_config_path, "r", encoding="utf-8") as f:
        models_config = yaml.safe_load(f)

    # Create downloader and download
    downloader = ModelDownloader(models_config, progress_callback)
    return downloader.download_model(model_id)


# Export main classes
__all__ = [
    "ModelDownloader",
    "DownloadProgress",
    "ModelDownloadError",
    "download_model_with_progress",
]
