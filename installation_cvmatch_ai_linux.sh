#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}" )" && pwd)"
CACHE_DIR="${SCRIPT_DIR}/cache/hf_models"
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

echo "=== CVMatch AI Model Installer ==="
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
"${PYTHON_CMD}" "${SCRIPT_DIR}/scripts/download_ai_models.py" --cache-dir "${CACHE_DIR}" || {
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
echo "AI model cache ready in ${CACHE_DIR}"
echo "You can now run CVMatch with AI extraction enabled."
