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
LLM_MODEL_ID="${CVMATCH_LLM_MODEL_ID:-Qwen/Qwen2.5-7B-Instruct}"
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

TORCH_CPU_INDEX="https://download.pytorch.org/whl/cpu"
TORCH_CUDA_INDEXES=(
    "https://download.pytorch.org/whl/cu130"
    "https://download.pytorch.org/whl/cu128"
)
HAS_NVIDIA_GPU=0
if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then
    HAS_NVIDIA_GPU=1
fi

drain_stream_lines() {
    local path="$1"
    local prefix="$2"
    local seen_var="$3"
    local seen="${!seen_var:-0}"

    if [[ ! -f "$path" ]]; then
        return 0
    fi

    local count
    count="$(wc -l < "$path" 2>/dev/null | tr -d '[:space:]')"
    if [[ -z "$count" ]]; then
        count=0
    fi

    if (( count <= seen )); then
        return 0
    fi

    echo ""
    local line_num
    local line
    for ((line_num = seen + 1; line_num <= count; line_num++)); do
        line="$(sed -n "${line_num}p" "$path")"
        if [[ -n "${line//[[:space:]]/}" ]]; then
            echo "[$prefix] $line"
        fi
    done

    printf -v "$seen_var" '%s' "$count"
}

run_with_spinner() {
    local display_name="$1"
    local soft_timeout_sec="$2"
    shift 2
    local cmd=( "$@" )

    local stdout_path
    local stderr_path
    stdout_path="$(mktemp)"
    stderr_path="$(mktemp)"
    : > "$stdout_path"
    : > "$stderr_path"

    "${cmd[@]}" >"$stdout_path" 2>"$stderr_path" &
    local pid=$!
    local start_ts
    start_ts="$(date +%s)"
    local spinner='|/-\'
    local idx=0
    local soft_notified=0
    local heartbeat_sec=15
    local next_heartbeat=0
    local out_seen=0
    local err_seen=0

    while kill -0 "$pid" 2>/dev/null; do
        drain_stream_lines "$stdout_path" "$display_name" out_seen
        drain_stream_lines "$stderr_path" "${display_name}/ERR" err_seen

        local elapsed=$(( $(date +%s) - start_ts ))
        local glyph="${spinner:idx%4:1}"
        idx=$((idx + 1))
        printf '\r[WAIT] %s %s %ss ' "$display_name" "$glyph" "$elapsed"
        sleep 0.2

        if (( soft_notified == 0 && elapsed >= soft_timeout_sec )); then
            echo ""
            echo "[INFO] ${display_name}: still running (${elapsed}s), continuing..."
            soft_notified=1
            next_heartbeat=$((elapsed + heartbeat_sec))
        elif (( soft_notified == 1 && elapsed >= next_heartbeat )); then
            echo ""
            echo "[INFO] ${display_name}: still running (${elapsed}s), continuing..."
            next_heartbeat=$((elapsed + heartbeat_sec))
        fi
    done

    set +e
    wait "$pid"
    local rc=$?
    set -e

    drain_stream_lines "$stdout_path" "$display_name" out_seen
    drain_stream_lines "$stderr_path" "${display_name}/ERR" err_seen

    local total=$(( $(date +%s) - start_ts ))
    printf '\r[DONE] %s in %ss.                        \n' "$display_name" "$total"

    rm -f "$stdout_path" "$stderr_path"
    return "$rc"
}

install_torch() {
    local index_url="$1"
    if [[ -z "${index_url}" ]]; then
        index_url="${TORCH_CPU_INDEX}"
    fi
    run_with_spinner "Install PyTorch (${index_url})" 900 \
        "${PYTHON_CMD}" -m pip install --progress-bar off -v --upgrade --force-reinstall torch torchvision torchaudio --index-url "${index_url}"
}

check_torch_arch_compat() {
    local out
    out="$("${PYTHON_CMD}" "${SCRIPT_DIR}/scripts/check_torch_arch_compat.py" 2>&1 || true)"
    if [[ -n "$out" ]]; then
        echo "$out"
    fi
    local status
    status="$(echo "$out" | awk -F= '/^TORCH_CHECK_STATUS=/{print $2; exit}')"
    case "$status" in
        supported) return 0 ;;
        unsupported) return 2 ;;
        cuda_unavailable) return 3 ;;
        torch_missing) return 4 ;;
        *) return 1 ;;
    esac
}

ensure_ai_runtime() {
    local needs_runtime=0
    local cuda_ok=0

    if ! "${PYTHON_CMD}" -c "import torch, transformers, huggingface_hub" >/dev/null 2>&1; then
        needs_runtime=1
    fi

    if [[ "${needs_runtime}" -eq 0 && "${HAS_NVIDIA_GPU}" -eq 1 ]]; then
        if check_torch_arch_compat; then
            cuda_ok=1
        else
            needs_runtime=1
        fi
    fi

    if [[ "${needs_runtime}" -eq 1 ]]; then
        echo "Installing AI Python dependencies (torch/transformers/huggingface_hub)..."

        if [[ "${HAS_NVIDIA_GPU}" -eq 1 ]]; then
            local installed_cuda=0
            local idx
            for idx in "${TORCH_CUDA_INDEXES[@]}"; do
                echo "Attempting PyTorch CUDA via ${idx}..."
                if install_torch "${idx}"; then
                    if check_torch_arch_compat; then
                        installed_cuda=1
                        echo "[OK] PyTorch CUDA compatible via ${idx}"
                        break
                    else
                        local compat_status=$?
                        if [[ "${compat_status}" -eq 2 ]]; then
                            echo "[WARN] CUDA wheel installed but GPU arch is unsupported by torch (index=${idx})."
                        elif [[ "${compat_status}" -eq 3 ]]; then
                            echo "[WARN] CUDA wheel installed but torch.cuda.is_available()=False (index=${idx})."
                        else
                            echo "[WARN] Torch/CUDA compatibility check failed (index=${idx}, status=${compat_status})."
                        fi
                    fi
                else
                    echo "[WARN] PyTorch CUDA install failed via ${idx}"
                fi
            done

            if [[ "${installed_cuda}" -eq 0 ]]; then
                echo "[WARN] Falling back to CPU PyTorch build."
                install_torch "${TORCH_CPU_INDEX}" || return 1
            fi
        else
            install_torch "${TORCH_CPU_INDEX}" || return 1
        fi

        run_with_spinner "Install transformers+huggingface_hub" 240 \
            "${PYTHON_CMD}" -m pip install --progress-bar off -v --upgrade transformers huggingface_hub || return 1
    elif [[ "${HAS_NVIDIA_GPU}" -eq 1 && "${cuda_ok}" -eq 0 ]]; then
        echo "[WARN] NVIDIA GPU detected but torch.cuda.is_available() is false."
    fi

    return 0
}

echo "=== CVMatch AI Model Installer ==="
echo "Mode: ${AI_MODE}"
echo "Cache: ${CACHE_DIR}"
"${PYTHON_CMD}" -c "import google.protobuf, sentencepiece" >/dev/null 2>&1 || {
    echo "Installing missing Python dependencies (protobuf, sentencepiece)..."
    run_with_spinner "Install protobuf+sentencepiece" 120 \
        "${PYTHON_CMD}" -m pip install --progress-bar off -v --upgrade protobuf sentencepiece
}

ensure_ai_runtime

# Optional: install llama.cpp (GGUF runner) for local generation via llama-server.
LLAMA_DIR="${SCRIPT_DIR}/tools/llama.cpp"
mkdir -p "${LLAMA_DIR}"
echo "Installing llama.cpp (llama-server) into ${LLAMA_DIR}..."
run_with_spinner "Install llama.cpp" 240 \
    "${PYTHON_CMD}" "${SCRIPT_DIR}/scripts/install_llama_cpp.py" --dest-dir "${LLAMA_DIR}" || {
    echo "[WARN] llama.cpp install failed - you can install it manually later."
    echo "       Tip: set CVMATCH_LLAMA_CPP_BINARY and CVMATCH_LLAMA_CPP_MODEL_PATH if needed."
}
if [[ -n "${INSTALL_LLM}" ]]; then
    run_with_spinner "Download AI models (LLM)" 1800 \
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
    run_with_spinner "Download AI models (base)" 1800 \
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
