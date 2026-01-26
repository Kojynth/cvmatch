#!/bin/bash
# ================================================================
# CVMatch - Installateur Linux (recrÃ©e automatiquement)
# ================================================================
set -e

echo "CVMatch - Installateur Linux"
echo "===================================="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
cd "$PROJECT_ROOT"

# VÃ©rification Python
PYTHON_BIN="$(command -v python3 || true)"
if [[ -z "$PYTHON_BIN" ]]; then
    echo "ERREUR: Python 3.10+ requis"
    echo "Installez Python avec: sudo apt install python3 python3-venv python3-pip"
    exit 1
fi
if [[ "$PYTHON_BIN" == "$PROJECT_ROOT/"* ]]; then
    echo "ERROR: Refusing to run python from project directory."
    exit 1
fi
if ! "$PYTHON_BIN" -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)"; then
    echo "ERREUR: Python 3.10+ requis"
    exit 1
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
"$VENV_DIR/bin/pip" install "${PIP_ARGS[@]}" -r "$REQ_TARGET"

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


# Installation modèles IA interactifs
echo
echo "=============================================="
echo "Configuration des modèles IA pour CVMatch"
echo "=============================================="
echo
echo "CVMatch peut fonctionner avec ou sans modèles IA :"
echo "- Avec IA : Extraction précise, classification automatique"
echo "- Sans IA : Fonctionnement basique avec règles prédéfinies"
echo

read -p "Souhaitez-vous installer les modèles IA ? (O/n): " INSTALL_AI

if [[ "$INSTALL_AI" =~ ^[Nn]$ ]] || [[ "$INSTALL_AI" =~ ^[Nn][Oo][Nn]$ ]]; then
    echo
    echo "Modèles IA ignorés - CVMatch fonctionnera en mode règles uniquement."
else
    echo
    echo "Lancement de l'installateur interactif des modèles..."
    "$VENV_DIR/bin/python" scripts/interactive_model_installer.py

    if [ $? -eq 0 ]; then
        echo
        echo "✅ Modèles IA installés avec succès!"
        if [ -f "./installation_cvmatch_ai_linux.sh" ]; then
            ./installation_cvmatch_ai_linux.sh || echo "[WARN] Préinstallation des modèles IA impossible (mode règles fallback)."
        else
            echo "[WARN] installation_cvmatch_ai_linux.sh introuvable (mode regles fallback)."
        fi
    else
        echo
        echo "⚠️ Installation des modèles incomplète ou annulée."
        echo "CVMatch fonctionnera en mode règles uniquement."
    fi
fi

echo
echo "Installation terminée!"
echo "Utilisez ./cvmatch.sh pour lancer l'application."
