"""
Qwen Model Loader Utilities

Reusable model loading utilities extracted from QwenManager.
These functions help with model loading configuration, error handling,
and retry logic without tight coupling to QwenManager state.

Key features:
- Model loading kwargs construction
- Error handling and retry strategies
- Device mapping normalization
- Tokenizer loading with fallbacks
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

try:
    from ..logging.safe_logger import get_safe_logger
    from ..config import DEFAULT_PII_CONFIG
    logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

# Try to import transformers
try:
    from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
    import torch
    TRANSFORMERS_AVAILABLE = True
    TORCH_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False
    TORCH_AVAILABLE = False
    torch = None  # type: ignore
    AutoTokenizer = None  # type: ignore
    AutoModelForCausalLM = None  # type: ignore
    BitsAndBytesConfig = None  # type: ignore


@dataclass
class ModelLoadConfig:
    """Configuration for model loading."""
    model_path: str
    device: str = "cpu"
    dtype: Any = None
    load_in_4bit: bool = False
    load_in_8bit: bool = False
    trust_remote_code: bool = True
    use_safetensors: bool = True
    low_cpu_mem_usage: bool = True
    device_map: Optional[str] = "auto"
    max_memory: Optional[Dict[Union[int, str], str]] = None
    offload_folder: Optional[str] = None
    offload_state_dict: bool = False
    attn_implementation: Optional[str] = None

    # Survival mode settings
    survival_mode: bool = False
    max_model_len: Optional[int] = None
    gpu_memory_utilization: Optional[float] = None


@dataclass
class LoadResult:
    """Result of a model load attempt."""
    success: bool
    model: Any = None
    tokenizer: Any = None
    device: Any = None
    error: Optional[str] = None
    load_kwargs_used: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)


def resolve_bool_setting(
    custom_value: Any,
    env_value: Optional[str],
    default: bool,
) -> bool:
    """Resolve a boolean setting from custom parameters or environment.

    Args:
        custom_value: Value from custom parameters
        env_value: Value from environment variable
        default: Default value if neither is set

    Returns:
        Resolved boolean value
    """
    if env_value is not None:
        return str(env_value).strip().lower() in ("1", "true", "yes", "y", "on")
    if custom_value is None:
        return default
    if isinstance(custom_value, bool):
        return custom_value
    return str(custom_value).strip().lower() in ("1", "true", "yes", "y", "on")


def build_model_kwargs(
    config: ModelLoadConfig,
    *,
    custom_parameters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build kwargs dictionary for model loading.

    Args:
        config: Model loading configuration
        custom_parameters: Optional custom parameters

    Returns:
        Dictionary of kwargs for from_pretrained()
    """
    custom = custom_parameters or {}

    model_kwargs: Dict[str, Any] = {
        "trust_remote_code": config.trust_remote_code,
    }

    # Set dtype
    if config.dtype is not None:
        model_kwargs["torch_dtype"] = config.dtype
    elif TORCH_AVAILABLE:
        model_kwargs["torch_dtype"] = torch.float16

    # Attention implementation for survival mode
    if config.survival_mode and config.attn_implementation:
        model_kwargs["attn_implementation"] = config.attn_implementation

    # Device mapping
    if config.device == "cuda":
        model_kwargs["device_map"] = config.device_map or "auto"

        if config.max_memory:
            model_kwargs["max_memory"] = config.max_memory
            model_kwargs["low_cpu_mem_usage"] = True

        # Disk offload
        disk_offload_enabled = resolve_bool_setting(
            custom.get("disk_offload"),
            os.getenv("CVMATCH_DISK_OFFLOAD"),
            True,
        )
        if config.survival_mode:
            disk_offload_enabled = True

        if disk_offload_enabled and config.offload_folder:
            model_kwargs["offload_folder"] = config.offload_folder
            model_kwargs["offload_state_dict"] = config.offload_state_dict
    else:
        model_kwargs["device_map"] = None

    # Quantization
    if config.load_in_8bit:
        model_kwargs["load_in_8bit"] = True
    elif config.load_in_4bit:
        if TRANSFORMERS_AVAILABLE and BitsAndBytesConfig:
            quantization_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.float16 if TORCH_AVAILABLE else None,
                bnb_4bit_use_double_quant=True,
                bnb_4bit_quant_type="nf4",
                llm_int8_enable_fp32_cpu_offload=True,
            )
            model_kwargs["quantization_config"] = quantization_config

    return model_kwargs


def resolve_offload_folder(
    custom_parameters: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Resolve the offload folder path.

    Args:
        custom_parameters: Optional custom parameters

    Returns:
        Resolved offload folder path, or None
    """
    custom = custom_parameters or {}

    custom_offload = custom.get("offload_folder")
    env_offload = os.getenv("CVMATCH_OFFLOAD_FOLDER")
    raw_path = env_offload or custom_offload

    if raw_path:
        offload_dir = Path(str(raw_path))
    else:
        offload_dir = Path.cwd() / "logs" / "hf_offload"

    try:
        offload_dir.mkdir(parents=True, exist_ok=True)
        return str(offload_dir)
    except Exception as exc:
        logger.warning("Failed to create offload folder %s: %s", offload_dir, exc)
        return None


def normalize_max_memory_keys(
    max_memory: Dict[Any, str],
) -> Dict[Union[int, str], str]:
    """Normalize max_memory keys for compatibility.

    Different transformers versions expect different key formats.
    This function normalizes keys to work with both.

    Args:
        max_memory: Original max_memory dict

    Returns:
        Normalized max_memory dict
    """
    if not max_memory:
        return {}

    result: Dict[Union[int, str], str] = {}

    for key, value in max_memory.items():
        if isinstance(key, int):
            # Try both formats
            result[f"cuda:{key}"] = value
        elif isinstance(key, str) and key.startswith("cuda:"):
            result[key] = value
            # Also try integer format
            try:
                suffix = key.split(":", 1)[1]
                result[int(suffix)] = value
            except Exception:
                pass
        else:
            result[key] = value

    return result


def is_offload_kwargs_unsupported_error(error: Exception) -> bool:
    """Check if error indicates unsupported offload kwargs."""
    msg = str(error).lower()
    return (
        "unexpected keyword argument" in msg
        and ("offload_state_dict" in msg or "offload_folder" in msg)
    )


def is_attn_implementation_unsupported_error(error: Exception) -> bool:
    """Check if error indicates unsupported attn_implementation."""
    msg = str(error).lower()
    return (
        "unexpected keyword argument" in msg
        and "attn_implementation" in msg
    )


def is_weight_conversion_error(error: Exception) -> bool:
    """Check if error indicates weight conversion failure."""
    msg = str(error).lower()
    return (
        "automatic conversion of the weights" in msg
        or ("conversion" in msg and "weights" in msg)
    )


def is_device_not_recognized_error(error: Exception) -> bool:
    """Check if error indicates unrecognized device."""
    msg = str(error)
    return "Device cuda:0 is not recognized" in msg or "Device 0 is not recognized" in msg


def is_meta_tensors_error(error: Exception) -> bool:
    """Check if error indicates meta tensors issue."""
    return "meta tensors" in str(error)


def is_oom_error(error: Exception) -> bool:
    """Check if error indicates out of memory."""
    msg = str(error).lower()
    return (
        isinstance(error, MemoryError)
        or "out of memory" in msg
        or "cuda out of memory" in msg
    )


def is_model_access_restricted_error(error_msg: str) -> bool:
    """Check if error indicates model access is restricted.

    Args:
        error_msg: Error message string

    Returns:
        True if error suggests gated/private repo access issue
    """
    lowered = error_msg.lower()
    markers = (
        "401",
        "403",
        "unauthorized",
        "access denied",
        "authentication required",
        "gated repo",
        "private repo",
        "repository not found",
        "not a valid model identifier",
    )
    return any(marker in lowered for marker in markers)


def extract_repo_prefix(model_path: Optional[str]) -> str:
    """Extract the organization/user prefix from a model path.

    Args:
        model_path: Model path like "org/model-name"

    Returns:
        Prefix like "org/" or empty string
    """
    if not model_path:
        return ""

    # Local paths don't have prefixes
    if "\\" in model_path or ":" in model_path:
        return ""

    parts = model_path.split("/")
    if len(parts) >= 2:
        return f"{parts[0]}/"

    return ""


def load_tokenizer_with_fallbacks(
    model_ref: str,
    *,
    trust_remote_code: bool = True,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> Any:
    """Load tokenizer with fallback strategies.

    Handles common tokenizer loading issues:
    - Missing protobuf/sentencepiece
    - Fast tokenizer failures

    Args:
        model_ref: Model reference (path or HF repo)
        trust_remote_code: Whether to trust remote code
        progress_callback: Optional progress callback

    Returns:
        Loaded tokenizer

    Raises:
        RuntimeError: If tokenizer cannot be loaded
    """
    if not TRANSFORMERS_AVAILABLE:
        raise RuntimeError("Transformers not available")

    try:
        return AutoTokenizer.from_pretrained(
            model_ref,
            trust_remote_code=trust_remote_code,
            use_fast=True,
        )
    except ImportError as e:
        msg = str(e).lower()
        if "protobuf" in msg:
            if progress_callback:
                progress_callback(
                    "[WARN] Missing dependency (protobuf). "
                    "Falling back to slow tokenizer..."
                )
            try:
                return AutoTokenizer.from_pretrained(
                    model_ref,
                    trust_remote_code=trust_remote_code,
                    use_fast=False,
                )
            except ImportError as e2:
                if "sentencepiece" in str(e2).lower():
                    raise RuntimeError(
                        "Tokenizer requires 'sentencepiece'. "
                        "Install: pip install sentencepiece protobuf"
                    ) from e2
                raise
        elif "sentencepiece" in msg:
            raise RuntimeError(
                "Tokenizer requires 'sentencepiece'. "
                "Install: pip install sentencepiece"
            ) from e
        else:
            raise
    except Exception as e:
        msg = str(e).lower()
        if any(token in msg for token in ("vocabulary", "sentencepiece", "tokenizer")):
            logger.warning(
                "Tokenizer load failed, retrying with use_fast=False: %s", e
            )
            return AutoTokenizer.from_pretrained(
                model_ref,
                trust_remote_code=trust_remote_code,
                use_fast=False,
            )
        raise


def build_load_error_diagnostic(
    error: Exception,
    *,
    model_id: Optional[str] = None,
    model_name: Optional[str] = None,
    optimization_config: Optional[Dict[str, Any]] = None,
) -> Tuple[str, Optional[str]]:
    """Build diagnostic information and hint for a load error.

    Args:
        error: The exception that occurred
        model_id: Model identifier
        model_name: Model name/path
        optimization_config: Optimization settings used

    Returns:
        Tuple of (diagnostic_text, hint_text)
    """
    lines: List[str] = []
    lines.append(f"- model_id: {model_id}")
    lines.append(f"- model_name: {model_name}")

    if optimization_config:
        try:
            opt = dict(optimization_config)
            dtype = opt.get("dtype")
            if dtype is not None:
                opt["dtype"] = str(dtype)
            lines.append(f"- optimization: {opt}")
        except Exception:
            pass

    try:
        import psutil
        mem = psutil.virtual_memory()
        lines.append(f"- ram_total_gb: {mem.total / (1024**3):.1f}")
        lines.append(f"- ram_available_gb: {mem.available / (1024**3):.1f}")
    except Exception:
        pass

    if TORCH_AVAILABLE:
        lines.append(f"- torch_available: True")
        lines.append(f"- torch_cuda_available: {torch.cuda.is_available()}")

    diagnostic_text = "\n".join(lines) if lines else "N/A"

    # Generate hint
    error_msg = str(error).lower()
    hint = None

    if is_oom_error(error):
        hint = (
            "Hint: GPU/RAM memory insufficient. "
            "Adjust memory budget or choose a smaller model."
        )
    elif "protobuf" in error_msg:
        hint = (
            "Hint: Missing 'protobuf' dependency. "
            "Install: pip install protobuf (and often sentencepiece), "
            "then restart the application."
        )
    elif "sentencepiece" in error_msg:
        hint = (
            "Hint: Missing 'sentencepiece' dependency. "
            "Install: pip install sentencepiece, then restart."
        )
    elif "_is_hf_initialized" in error_msg or "params4bit" in error_msg:
        hint = (
            "Hint: bitsandbytes is outdated/incompatible for 4-bit quantization. "
            "Update bitsandbytes (CUDA) or change quantization settings."
        )
    elif "bitsandbytes" in error_msg:
        hint = (
            "Hint: 'bitsandbytes' missing/incompatible. "
            "Reinstall bitsandbytes (CUDA) or choose a smaller CPU model."
        )
    elif is_weight_conversion_error(error):
        hint = (
            "Hint: Weight conversion failed (cache may be corrupted). "
            "Delete the model snapshot from HF cache, then retry."
        )

    return diagnostic_text, hint


def detect_access_violation_error(
    error: Exception,
) -> bool:
    """Detect Windows ACCESS_VIOLATION or corrupted cache errors.

    Args:
        error: The exception

    Returns:
        True if this looks like a cache corruption issue
    """
    error_msg = str(error)
    error_code = getattr(error, "winerror", None)

    return (
        "-1073741819" in error_msg
        or "0xC0000005" in error_msg
        or ("Access" in error_msg and "Violation" in error_msg)
        or error_code == 1314  # WinError 1314 - symlink permission
    )


def get_stage_model_size_requirements(
    stage_name: str,
) -> Dict[str, Any]:
    """Get model size requirements for a pipeline stage.

    Different stages have different quality requirements.
    Writer stages need larger models for better output quality.

    Args:
        stage_name: Pipeline stage name

    Returns:
        Dict with min_size_gb and prefer_quality settings
    """
    stage_key = str(stage_name or "").strip().lower()

    # Writer stages need higher quality
    writer_stages = {"draft", "final", "cover_letter", "cover_letter_critic"}

    if stage_key in writer_stages:
        return {
            "min_size_gb": 1.5,
            "prefer_quality": True,
            "is_writer_stage": True,
        }

    # Extractor stages can use smaller models
    extractor_stages = {"offer_keywords", "critic"}
    if stage_key in extractor_stages:
        return {
            "min_size_gb": 1.0,
            "prefer_quality": False,
            "is_writer_stage": False,
        }

    # Default
    return {
        "min_size_gb": 1.0,
        "prefer_quality": False,
        "is_writer_stage": False,
    }
