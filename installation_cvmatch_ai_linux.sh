#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}" )" && pwd)"
CACHE_DIR="${SCRIPT_DIR}/cache/hf_models"
if [[ -n "${CVMATCH_HF_CACHE:-}" ]]; then
    CACHE_DIR="${CVMATCH_HF_CACHE}"
fi
export HUGGINGFACE_HUB_CACHE="${CACHE_DIR}"
export HF_HUB_CACHE="${CACHE_DIR}"
export TRANSFORMERS_CACHE="${CACHE_DIR}"
PYTHON_CMD="${PYTHON:-python3}"
if [ -x "${SCRIPT_DIR}/cvmatch_env/bin/python" ]; then
    PYTHON_CMD="${SCRIPT_DIR}/cvmatch_env/bin/python"
fi
PYTHON_RESOLVED="$(command -v "$PYTHON_CMD" 2>/dev/null || true)"
if [ -z "$PYTHON_RESOLVED" ]; then
    echo "ERROR: Python not found on PATH."
    exit 1
fi
PYTHON_CMD="$PYTHON_RESOLVED"
if [[ "$PYTHON_CMD" == "${SCRIPT_DIR}/"* && "$PYTHON_CMD" != "${SCRIPT_DIR}/cvmatch_env/bin/python" ]]; then
    echo "ERROR: Refusing to run python from project directory."
    exit 1
fi
if ! "$PYTHON_CMD" -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)"; then
    echo "ERROR: Python 3.10+ required."
    exit 1
fi

AI_MODE="${CVMATCH_AI_MODE:-lite}"
LLM_MODEL_ID="${CVMATCH_LLM_MODEL_ID:-Qwen/Qwen2.5-0.5B-Instruct}"
INSTALL_LLM=1
if [[ "${CVMATCH_SKIP_LLM:-}" == "1" ]]; then
    INSTALL_LLM=
fi
if [[ "${AI_MODE}" == "base-only" ]]; then
    INSTALL_LLM=
fi
if [[ "${AI_MODE}" == "llm-only" ]]; then
    INSTALL_LLM=1
fi

echo "=== CVMatch AI Model Installer ==="
echo "Mode: ${AI_MODE}"
echo "Cache: ${CACHE_DIR}"
"${PYTHON_CMD}" -c "import google.protobuf, sentencepiece" >/dev/null 2>&1 || {
    echo "Installing missing Python dependencies (protobuf, sentencepiece)..."
    "${PYTHON_CMD}" -m pip install --upgrade protobuf sentencepiece
}

# Optional: install llama.cpp (GGUF runner) for local generation via llama-server.
LLAMA_DIR="${SCRIPT_DIR}/tools/llama.cpp"
mkdir -p "${LLAMA_DIR}"
echo "Installing llama.cpp (llama-server) into ${LLAMA_DIR}..."
"${PYTHON_CMD}" "${SCRIPT_DIR}/scripts/install_llama_cpp.py" --dest-dir "${LLAMA_DIR}" || {
    echo "[WARN] llama.cpp install failed - you can install it manually later."
    echo "       Tip: set CVMATCH_LLAMA_CPP_BINARY and CVMATCH_LLAMA_CPP_MODEL_PATH if needed."
}
if [[ -n "${INSTALL_LLM}" ]]; then
    "${PYTHON_CMD}" "${SCRIPT_DIR}/scripts/download_ai_models.py" --cache-dir "${CACHE_DIR}" --mode "${AI_MODE}" --include-llm --llm-model "${LLM_MODEL_ID}" || {
        exit_code=$?
        if [ "$exit_code" -eq 401 ]; then
            echo "[ERROR] Authentication required to download models."
            echo "Run \"huggingface-cli login\" and re-run this script."
        else
            echo "Failed to download one or more models."
            echo "Verify your internet connection and that huggingface_hub is installed."
        fi
        exit $exit_code
    }
else
    "${PYTHON_CMD}" "${SCRIPT_DIR}/scripts/download_ai_models.py" --cache-dir "${CACHE_DIR}" --mode "${AI_MODE}" || {
        exit_code=$?
        if [ "$exit_code" -eq 401 ]; then
            echo "[ERROR] Authentication required to download models."
            echo "Run \"huggingface-cli login\" and re-run this script."
        else
            echo "Failed to download one or more models."
            echo "Verify your internet connection and that huggingface_hub is installed."
        fi
        exit $exit_code
    }
fi
echo "AI model cache ready in ${CACHE_DIR}"
echo "You can now run CVMatch with AI extraction enabled."
