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
"$PYTHON_BIN" -m venv "$VENV_DIR"

# Activation environnement
source "$VENV_DIR/bin/activate" || {
    echo "ERREUR: Activation environnement"
    exit 1
}

# Mise a jour pip/setuptools/wheel (evite erreurs de build)
echo "Mise a jour pip/setuptools/wheel..."
"$VENV_DIR/bin/python" -m pip install --upgrade pip setuptools wheel

# Détection GPU pour PyTorch
TORCH_INDEX_URL="https://download.pytorch.org/whl/cpu"
TORCH_VARIANT="CPU"
if command -v nvidia-smi &> /dev/null && nvidia-smi &> /dev/null; then
    TORCH_INDEX_URL="https://download.pytorch.org/whl/cu121"
    TORCH_VARIANT="CUDA"
fi

echo "Installation PyTorch ($TORCH_VARIANT)..."
"$VENV_DIR/bin/python" -m pip install --upgrade --force-reinstall torch torchvision torchaudio --index-url "$TORCH_INDEX_URL"

"$VENV_DIR/bin/python" -m pip install --upgrade huggingface_hub transformers protobuf sentencepiece

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
"$VENV_DIR/bin/pip" install --no-build-isolation "${PIP_ARGS[@]}" -r "$REQ_TO_USE"

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
if "$VENV_DIR/bin/python" scripts/check_ai_models.py "${AI_CHECK_ARGS[@]}"; then
    echo "Modeles IA detectes."
else
    AI_STATUS=$?
    if [ "$AI_STATUS" -eq 2 ]; then
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
