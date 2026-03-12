#!/bin/bash
# ================================================================
# CVMatch - Installateur Linux (recrÃ©e automatiquement)
# ================================================================
if [ -z "${BASH_VERSION:-}" ]; then
    exec bash "$0" "$@"
fi

set -e

echo "CVMatch - Installateur Linux"
echo "===================================="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
cd "$PROJECT_ROOT"

detect_python() {
    local candidate resolved
    for candidate in python3.13 python3.12 python3.11 python3.10 python3.9 python3 python; do
        resolved="$(command -v "$candidate" 2>/dev/null || true)"
        if [[ -n "$resolved" ]]; then
            if [[ "$resolved" == "$PROJECT_ROOT/"* ]]; then
                continue
            fi
            if "$resolved" -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >/dev/null 2>&1; then
                echo "$resolved"
                return 0
            fi
        fi
    done

    for resolved in /usr/bin/python3.13 /usr/bin/python3.12 /usr/bin/python3.11 /usr/bin/python3.10 /usr/bin/python3.9 /usr/bin/python3 /usr/local/bin/python3 /opt/homebrew/bin/python3; do
        if [[ -x "$resolved" ]]; then
            if [[ "$resolved" == "$PROJECT_ROOT/"* ]]; then
                continue
            fi
            if "$resolved" -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >/dev/null 2>&1; then
                echo "$resolved"
                return 0
            fi
        fi
    done
    return 1
}

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

# VÃ©rification Python
PYTHON_BIN=""
if [[ -n "${CVMATCH_PYTHON:-}" ]]; then
    if [[ -x "$CVMATCH_PYTHON" ]]; then
        if [[ "$CVMATCH_PYTHON" == "$PROJECT_ROOT/"* ]]; then
            echo "ERREUR: CVMATCH_PYTHON pointe vers le dossier projet."
            exit 1
        fi
        if "$CVMATCH_PYTHON" -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >/dev/null 2>&1; then
            PYTHON_BIN="$CVMATCH_PYTHON"
        else
            echo "ERREUR: CVMATCH_PYTHON doit etre en Python 3.10+."
            exit 1
        fi
    else
        echo "ERREUR: CVMATCH_PYTHON n'est pas executable."
        exit 1
    fi
fi
if [[ -z "$PYTHON_BIN" ]]; then
    PYTHON_BIN="$(detect_python || true)"
fi
if [[ -z "$PYTHON_BIN" ]]; then
    echo "ERREUR: Python 3.10+ requis (hors du dossier projet)"
    echo "Installez Python avec: sudo apt install python3 python3-venv python3-pip"
    echo "Astuce: desactivez le venv puis relancez l'installateur."
    exit 1
fi
PYTHON_VERSION="$("$PYTHON_BIN" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")"
if [[ "${CVMATCH_FORCE_GPU:-}" == "1" ]]; then
    case "$PYTHON_VERSION" in
        3.12|3.13)
            echo "[WARN] Python $PYTHON_VERSION peut poser probleme avec flash-attn/xformers."
            echo "[WARN] Recommande: Python 3.11 pour un stack GPU stable."
            ;;
    esac
fi

# CrÃ©ation environnement virtuel
echo "CrÃ©ation environnement virtuel..."
VENV_DIR="$PROJECT_ROOT/cvmatch_env"
if [[ -d "$VENV_DIR" ]]; then
    if [[ -z "$PROJECT_ROOT" || "$PROJECT_ROOT" == "/" ]]; then
        echo "ERROR: Unsafe project root; refusing to delete venv."
        exit 1
    fi
    if [[ "$VENV_DIR" != "$PROJECT_ROOT/cvmatch_env" ]]; then
        echo "ERROR: Unsafe venv path; refusing to delete."
        exit 1
    fi
    rm -rf "$VENV_DIR"
fi
run_with_spinner "Create virtualenv" 180 "$PYTHON_BIN" -m venv "$VENV_DIR"

# Activation environnement
source "$VENV_DIR/bin/activate" || {
    echo "ERREUR: Activation environnement"
    exit 1
}

# Mise a jour pip/setuptools/wheel (evite erreurs de build)
echo "Mise a jour pip/setuptools/wheel..."
run_with_spinner "Upgrade pip/setuptools/wheel" 240 \
    "$VENV_DIR/bin/python" -m pip install --progress-bar off -v --upgrade pip setuptools wheel

# Detection GPU pour PyTorch + verification compat arch
TORCH_CPU_INDEX="https://download.pytorch.org/whl/cpu"
TORCH_CUDA_INDEXES=(
    "https://download.pytorch.org/whl/cu130"
    "https://download.pytorch.org/whl/cu128"
)
HAS_NVIDIA_GPU=0
if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then
    HAS_NVIDIA_GPU=1
fi

install_torch_from_index() {
    local index_url="$1"
    run_with_spinner "Install PyTorch (${index_url})" 900 \
        "$VENV_DIR/bin/python" -m pip install --progress-bar off -v --upgrade --force-reinstall torch torchvision torchaudio --index-url "$index_url"
}

check_torch_arch_compat() {
    local out
    out="$("$VENV_DIR/bin/python" scripts/check_torch_arch_compat.py 2>&1 || true)"
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

if [[ "$HAS_NVIDIA_GPU" -eq 1 ]]; then
    echo "Installation PyTorch (CUDA auto)..."
    TORCH_OK=0
    for index_url in "${TORCH_CUDA_INDEXES[@]}"; do
        echo "Tentative CUDA via ${index_url}..."
        if install_torch_from_index "$index_url"; then
            if check_torch_arch_compat; then
                TORCH_OK=1
                echo "[OK] PyTorch CUDA compatible via ${index_url}"
                break
            else
                compat_status=$?
                if [[ "$compat_status" -eq 2 ]]; then
                    echo "[WARN] Wheel CUDA installee mais arch GPU non supportee par torch (index=${index_url})."
                elif [[ "$compat_status" -eq 3 ]]; then
                    echo "[WARN] Wheel CUDA installee mais torch.cuda.is_available()=False (index=${index_url})."
                else
                    echo "[WARN] Verification compat torch/cuda echouee (index=${index_url}, status=${compat_status})."
                fi
            fi
        else
            echo "[WARN] Echec installation torch via ${index_url}."
        fi
    done

    if [[ "$TORCH_OK" -ne 1 ]]; then
        echo "[WARN] Aucune wheel CUDA compatible detectee. Bascule CPU."
        install_torch_from_index "$TORCH_CPU_INDEX"
    fi
else
    echo "Installation PyTorch (CPU)..."
    install_torch_from_index "$TORCH_CPU_INDEX"
fi

run_with_spinner "Install HF/Transformers deps" 300 \
    "$VENV_DIR/bin/python" -m pip install --progress-bar off -v --upgrade huggingface_hub transformers protobuf sentencepiece
run_with_spinner "Install lm-format-enforcer" 120 \
    "$VENV_DIR/bin/python" -m pip install --progress-bar off -v --upgrade lm-format-enforcer

# Installation dépendances
echo "Installation dépendances..."
REQ_FILE="$PROJECT_ROOT/requirements_linux.txt"
REQ_LOCK="$PROJECT_ROOT/requirements_linux.lock"
REQ_TARGET="$REQ_FILE"
PIP_ARGS=()
if [[ -f "$REQ_LOCK" ]]; then
    REQ_TARGET="$REQ_LOCK"
    PIP_ARGS+=(--require-hashes)
    echo "Using locked requirements file."
else
    if [[ ! -f "$REQ_FILE" ]]; then
        echo "ERREUR: requirements_linux.txt manquant"
        exit 1
    fi
    echo "[WARN] Using unpinned requirements file."
    echo "[WARN] Consider creating requirements_linux.lock with hashes."
fi
# Certains paquets utilisent torch durant le build : désactive l'isolation.
# Si nvcc est absent, ignorer les packages GPU/compile lourds.
REQ_TO_USE="$REQ_TARGET"
if ! command -v nvcc >/dev/null 2>&1; then
    if [[ "${CVMATCH_FORCE_GPU:-}" == "1" ]]; then
        echo "[ERREUR] nvcc introuvable mais CVMATCH_FORCE_GPU=1."
        echo "Installez le CUDA toolkit (nvcc) puis relancez l'installation."
        exit 1
    fi
    echo "[WARN] nvcc introuvable - desactivation des optimisations GPU (flash-attn/vllm/xformers/torch-tensorrt/onnxruntime-gpu/auto-gptq/exllamav2)."
    TMP_REQ="$(mktemp)"
    grep -v -E "^(flash-attn|vllm|xformers|torch-tensorrt|onnxruntime-gpu|auto-gptq|exllamav2)[[:space:]]*([<=>].*)?$" "$REQ_TARGET" > "$TMP_REQ"
    REQ_TO_USE="$TMP_REQ"
fi
run_with_spinner "Install Linux requirements" 1800 \
    "$VENV_DIR/bin/pip" install --progress-bar off -v --no-build-isolation "${PIP_ARGS[@]}" -r "$REQ_TO_USE"

echo "Verification LM Format Enforcer..."
if "$VENV_DIR/bin/python" -c "import lmformatenforcer; print('lmformatenforcer OK')"; then
    :
else
    echo "[WARN] lmformatenforcer non detecte apres install requirements - nouvelle tentative."
    run_with_spinner "Reinstall lm-format-enforcer" 120 \
        "$VENV_DIR/bin/python" -m pip install --progress-bar off -v --upgrade lm-format-enforcer
fi

echo
echo "Verification GPU PyTorch..."
if "$VENV_DIR/bin/python" -c "import torch, sys; print('torch', torch.__version__, 'cuda_available', torch.cuda.is_available(), 'cuda', torch.version.cuda); sys.exit(0 if torch.cuda.is_available() else 2)"; then
    :
else
    CUDA_STATUS=$?
    if [ "$CUDA_STATUS" -eq 2 ]; then
        echo "[WARN] CUDA non detectee par PyTorch. Mode CPU actif."
        echo "[WARN] Si vous avez un GPU NVIDIA, installez les drivers puis relancez l'installation."
    fi
fi


echo
echo "Verification modeles IA..."
AI_CHECK_ARGS=(--include-llm)
if [ -n "${CVMATCH_AI_MODE:-}" ]; then
    AI_CHECK_ARGS+=(--mode "$CVMATCH_AI_MODE")
fi
if run_with_spinner "Check AI models" 120 "$VENV_DIR/bin/python" scripts/check_ai_models.py "${AI_CHECK_ARGS[@]}"; then
    echo "Modeles IA detectes."
else
    AI_STATUS=$?
    if [ "$AI_STATUS" -eq 3 ]; then
        echo "Runtime IA incomplet (torch/transformers/huggingface_hub manquants)."
        read -r -p "Installer les dependances IA maintenant ? (O/n): " INSTALL_AI_RUNTIME
        if [ -z "$INSTALL_AI_RUNTIME" ] || [[ "$INSTALL_AI_RUNTIME" =~ ^[OoYy]$ ]]; then
            if [ -f "./installation_cvmatch_ai_linux.sh" ]; then
                if [ -x "./installation_cvmatch_ai_linux.sh" ]; then
                    ./installation_cvmatch_ai_linux.sh || echo "[WARN] Installation dependances IA echouee."
                else
                    bash ./installation_cvmatch_ai_linux.sh || echo "[WARN] Installation dependances IA echouee."
                fi
            else
                echo "[WARN] installation_cvmatch_ai_linux.sh introuvable."
            fi
        else
            echo "Installation dependances IA ignoree."
        fi
    elif [ "$AI_STATUS" -eq 2 ]; then
        echo "Modeles IA manquants. Installation optionnelle."
        read -r -p "Installer les modeles IA maintenant ? (O/n): " INSTALL_AI
        if [ -z "$INSTALL_AI" ] || [[ "$INSTALL_AI" =~ ^[OoYy]$ ]]; then
            if [ -f "./installation_cvmatch_ai_linux.sh" ]; then
                if [ -x "./installation_cvmatch_ai_linux.sh" ]; then
                    ./installation_cvmatch_ai_linux.sh || echo "[WARN] Installation modeles IA echouee."
                else
                    bash ./installation_cvmatch_ai_linux.sh || echo "[WARN] Installation modeles IA echouee."
                fi
            else
                echo "[WARN] installation_cvmatch_ai_linux.sh introuvable."
            fi
        else
            echo "Installation modeles IA ignoree."
        fi
    else
        echo "[WARN] Verification modeles IA echouee."
    fi
fi

echo "Installation terminee!"
echo "Utilisez ./cvmatch.sh pour lancer l'application."
