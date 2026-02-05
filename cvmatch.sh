#!/bin/bash

# ================================================================
# CVMatch - Lanceur Linux/macOS avec gestion venv
# ================================================================
# Ce script gère automatiquement l'environnement virtuel,
# vérifie les dépendances et lance CVMatch de manière robuste.

set -e  # Arrêter en cas d'erreur

# Couleurs pour l'affichage
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

detect_python() {
    local candidate
    for candidate in python3 python; do
        if command -v "$candidate" >/dev/null 2>&1; then
            if "$candidate" -c "import sys; sys.exit(0 if sys.version_info >= (3,8) else 1)" >/dev/null 2>&1; then
                echo "$candidate"
                return 0
            fi
        fi
    done

    for candidate in /usr/bin/python3 /usr/local/bin/python3 /opt/homebrew/bin/python3; do
        if [[ -x "$candidate" ]]; then
            if "$candidate" -c "import sys; sys.exit(0 if sys.version_info >= (3,8) else 1)" >/dev/null 2>&1; then
                echo "$candidate"
                return 0
            fi
        fi
    done
    return 1
}

echo ""
echo "========================================"
echo "CVMatch - lanceur"
echo "========================================"

# Variables de chemin
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
cd "$PROJECT_ROOT"

VENV_DIR="$PROJECT_ROOT/cvmatch_env"
VENV_PYTHON="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"

# Créer log de session avec timestamp dès le début
SESSION_TIMESTAMP=$(date +"%Y-%d-%m_%H-%M-%S%3N")
SESSION_LOG="logs/sessionlog/cvmatch_session_$SESSION_TIMESTAMP.log"

mkdir -p logs/sessionlog

# Nettoyage des anciens logs (garde les 20 plus récents)
if ls logs/sessionlog/cvmatch_session_*.log >/dev/null 2>&1; then
    ls -t logs/sessionlog/cvmatch_session_*.log | tail -n +21 | xargs -r rm -f
fi

# Initialiser le log de session avec encodage UTF-8
echo "==============================================" > "$SESSION_LOG"
echo "CVMatch - Session Log" >> "$SESSION_LOG"
echo "==============================================" >> "$SESSION_LOG"
echo "Date/Heure: $(date)" >> "$SESSION_LOG"
echo "Session ID: $SESSION_TIMESTAMP" >> "$SESSION_LOG"
echo "Python: $VENV_PYTHON" >> "$SESSION_LOG"
echo "Repertoire: $(pwd)" >> "$SESSION_LOG"
echo "Utilisateur: $USER" >> "$SESSION_LOG"
echo "==============================================" >> "$SESSION_LOG"
echo "CVMatch - lanceur" >> "$SESSION_LOG"
echo "=============================================="

# ================================================================
# ÉTAPE 1: Vérifications pré-vol
# ================================================================
echo "[1/6] Verifications systeme..." >> "$SESSION_LOG"
log_info "[1/6] Vérifications système..."

# Test Python
PYTHON_BIN="$(detect_python || true)"
if [[ -z "$PYTHON_BIN" ]]; then
    log_error "Python 3.8+ introuvable dans le PATH"
    echo ""
    echo "Diagnostic:"
    echo "PATH=$PATH"
    echo "python3: $(command -v python3 2>/dev/null || echo 'not found')"
    echo "python:  $(command -v python 2>/dev/null || echo 'not found')"
    echo ""
    echo "Solutions selon votre distribution:"
    echo "â€¢ Ubuntu/Debian: sudo apt update && sudo apt install python3 python3-venv python3-pip"
    echo "â€¢ CentOS/RHEL:   sudo yum install python3 python3-venv python3-pip"
    echo "â€¢ Arch/Manjaro:  sudo pacman -S python python-virtualenv python-pip"
    echo "â€¢ macOS:         brew install python3"
    exit 1
fi

PYTHON_VERSION=$($PYTHON_BIN -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
if ! $PYTHON_BIN -c "import sys; sys.exit(0 if sys.version_info >= (3,8) else 1)"; then
    log_error "Python 3.8+ requis, version dÃ©tectÃ©e: $PYTHON_VERSION"
    exit 1
fi

echo "Python OK: $($PYTHON_BIN --version) ($PYTHON_BIN)" >> "$SESSION_LOG"
log_success "Python OK: $($PYTHON_BIN --version) ($PYTHON_BIN)"

# ================================================================
# ÉTAPE 2: Gestion intelligente de l'environnement virtuel  
# ================================================================
echo "[2/6] Gestion environnement virtuel..." >> "$SESSION_LOG"
log_info "[2/6] Gestion environnement virtuel..."

if [[ -d "$VENV_DIR" ]]; then
    echo "Environnement virtuel trouve: $VENV_DIR" >> "$SESSION_LOG"
    log_info "Environnement virtuel trouvé: $VENV_DIR"
    
    # Vérifier que l'environnement virtuel est fonctionnel
    if ! "$VENV_PYTHON" --version &>/dev/null; then
        log_warning "Environnement virtuel corrompu, recréation..."
        rm -rf "$VENV_DIR"
    elif ! "$VENV_PYTHON" -c "import sys; print('Environnement virtuel OK:', sys.prefix)" &>/dev/null; then
        log_warning "Environnement virtuel défaillant, recréation..."
        rm -rf "$VENV_DIR"  
    else
        log_success "Environnement virtuel fonctionnel"
    fi
fi

if [[ ! -d "$VENV_DIR" ]]; then
    log_info "Création environnement virtuel..."
    
    if ! "$PYTHON_BIN" -m venv "$VENV_DIR"; then
        log_error "Impossible de créer l'environnement virtuel"
        echo ""
        echo "Solutions:"
        echo "1. Installer python3-venv: sudo apt install python3-venv (Ubuntu/Debian)"
        echo "2. Ou utiliser virtualenv: pip3 install virtualenv && python3 -m virtualenv cvmatch_env"
        exit 1
    fi
    
    log_success "Environnement virtuel créé avec succès"
fi

# Activation de l'environnement virtuel
log_info "Activation environnement virtuel..."
source "$VENV_DIR/bin/activate" || {
    log_error "Impossible d'activer l'environnement virtuel"
    exit 1
}

log_success "Environnement virtuel activé"

# ================================================================
# ÉTAPE 3: Mise à jour pip et outils de base
# ================================================================
log_info "[3/5] Mise à jour outils de base..."

"$VENV_PIP" install --upgrade pip setuptools wheel --quiet || {
    log_warning "Mise à jour pip partiellement échouée, continuation..."
}

# ================================================================
# ÉTAPE 4: Vérification et installation des dépendances
# ================================================================
echo "[4/6] Verification dependances..." >> "$SESSION_LOG"
log_info "[4/6] Vérification et installation dépendances..."

# Test rapide des packages critiques
echo "Test des dépendances critiques..."
echo "Test des dependances critiques..." >> "$SESSION_LOG"
if ! "$VENV_PYTHON" -c "import PySide6, torch, transformers, loguru, pypdf, sqlmodel, docx, psutil; print('Toutes les dependances sont presentes')" &>/dev/null; then
    echo
    echo "==============================================="
    echo "  INSTALLATION AUTOMATIQUE DES DÉPENDANCES"
    echo "==============================================="
    echo
    log_warning "[INFO] Des dépendances critiques manquantes ont été détectées"
    log_warning "[INFO] Installation automatique en cours..."
    echo
    
    # Détection GPU pour PyTorch
    echo "[CHECK] Détection GPU pour PyTorch optimisé..."
    if command -v nvidia-smi &> /dev/null && nvidia-smi &> /dev/null; then
        log_success "[GPU] GPU CUDA détecté - Installation version CUDA"
        TORCH_INDEX="--index-url https://download.pytorch.org/whl/cu121"
    else
        log_info "[CPU] Mode CPU - Installation version CPU"
        TORCH_INDEX="--index-url https://download.pytorch.org/whl/cpu"
    fi
    
    echo "[INSTALL] Installation depuis requirements_linux.txt..."
    echo "[INSTALL] Ceci peut prendre plusieurs minutes..."
    echo
    
    # Installation depuis requirements_linux.txt (source unique de vérité)
    if [[ -f "requirements_linux.txt" ]]; then
        log_info "Installation complète depuis requirements_linux.txt"
        if ! "$VENV_PIP" install -r requirements_linux.txt $TORCH_INDEX --quiet --disable-pip-version-check; then
            log_error "[ERREUR] Installation requirements_linux.txt échouée"
            exit 1
        fi
        log_success "[OK] Installation requirements terminée"
    else
        log_warning "[FALLBACK] requirements_linux.txt non trouvé, installation de base..."
        # Installation minimale de secours
        if ! "$VENV_PIP" install PySide6 torch transformers loguru pypdf sqlmodel --quiet --disable-pip-version-check; then
            log_error "[ERREUR] Installation de base échouée"
            exit 1
        fi
        log_success "[OK] Installation de base terminée"
    fi
    
    echo
    echo "==============================================="
    echo "  INSTALLATION TERMINÉE AVEC SUCCÈS"
    echo "==============================================="
    echo
    
    # Test final simple
    echo "[VERIFY] Test final des imports..."
    if "$VENV_PYTHON" -c "import PySide6, torch; print('Tests imports OK')" &>/dev/null; then
        log_success "[SUCCESS] Installation vérifiée avec succès"
        echo
    else
        log_error "[ERREUR] Vérification post-installation échouée"
        exit 1
    fi
else
    echo "[SUCCESS] Toutes les dependances sont presentes" >> "$SESSION_LOG"
    log_success "Toutes les dépendances sont présentes"
fi

# Verification CUDA PyTorch
echo "[CHECK] Verification CUDA PyTorch..." >> "$SESSION_LOG"
log_info "[CHECK] Verification CUDA PyTorch..."
if "$VENV_PYTHON" -c "import torch, sys; print('torch', torch.__version__, 'cuda_available', torch.cuda.is_available(), 'cuda', torch.version.cuda); sys.exit(0 if torch.cuda.is_available() else 2)"; then
    echo "[SUCCESS] CUDA detected by PyTorch" >> "$SESSION_LOG"
    log_success "CUDA detected by PyTorch"
else
    CUDA_STATUS=$?
    if [ "$CUDA_STATUS" -eq 2 ]; then
        echo "[WARN] CUDA not detected by PyTorch (CPU mode)." >> "$SESSION_LOG"
        log_warning "CUDA not detected by PyTorch (CPU mode)."
    else
        echo "[WARN] PyTorch CUDA check failed." >> "$SESSION_LOG"
        log_warning "PyTorch CUDA check failed."
    fi
fi

# Verification modeles IA
echo "[CHECK] Verification modeles IA..." >> "$SESSION_LOG"
log_info "[CHECK] Verification modeles IA..."
if "$VENV_PYTHON" scripts/check_ai_models.py >/dev/null 2>&1; then
    echo "[SUCCESS] Modeles IA detectes" >> "$SESSION_LOG"
    log_success "Modeles IA detectes"
else
    AI_STATUS=$?
    if [ "$AI_STATUS" -eq 2 ]; then
        echo "[WARN] Modeles IA manquants. Installation optionnelle." >> "$SESSION_LOG"
        log_warning "Modeles IA manquants. Installation optionnelle."
        read -r -p "Installer les modeles IA maintenant ? (O/n): " RUN_AI_INSTALL
        if [ -z "$RUN_AI_INSTALL" ] || [[ "$RUN_AI_INSTALL" =~ ^[OoYy]$ ]]; then
            if [ -f "installation_cvmatch_ai_linux.sh" ]; then
                if [ -x "installation_cvmatch_ai_linux.sh" ]; then
                    ./installation_cvmatch_ai_linux.sh || log_warning "Installation modeles IA echouee."
                else
                    bash installation_cvmatch_ai_linux.sh || log_warning "Installation modeles IA echouee."
                fi
            else
                echo "[WARN] installation_cvmatch_ai_linux.sh introuvable." >> "$SESSION_LOG"
                log_warning "installation_cvmatch_ai_linux.sh introuvable."
            fi
        else
            echo "[INFO] Installation modeles IA ignoree." >> "$SESSION_LOG"
            log_info "Installation modeles IA ignoree."
        fi
    else
        echo "[WARN] Verification modeles IA echouee." >> "$SESSION_LOG"
        log_warning "Verification modeles IA echouee."
    fi
fi

# ================================================================
# ÉTAPE 5: Tests de santé pré-lancement
# ================================================================
echo "[5/6] Tests de sante..." >> "$SESSION_LOG"
log_info "[5/6] Tests de santé..."

# Test imports critiques
if ! "$VENV_PYTHON" -c "try: import PySide6, torch, transformers, loguru, pypdf, sqlmodel, docx, psutil; print('Tests d\\'import: OK'); except ImportError as e: print(f'Erreur import: {e}'); exit(1)"; then
    log_error "Tests d'import échoués"
    echo ""
    echo "Diagnostic:"
    "$VENV_PYTHON" -c "import sys; print('Python:', sys.executable); print('Packages path:', sys.path[:3])"
    exit 1
fi

# Test présence fichier principal
if [[ ! -f "main.py" ]]; then
    log_error "main.py non trouvé dans $PROJECT_ROOT"
    echo ""
    echo "Vérifiez que vous êtes dans le bon répertoire CVMatch"
    exit 1
fi

echo "Tests de sante: OK" >> "$SESSION_LOG"
log_success "Tests de santé: OK"

echo "[6/6] Lancement CVMatch..." >> "$SESSION_LOG"
log_info "[6/6] Lancement CVMatch..."
echo ""
echo "========================================"
echo "Démarrage de l'interface CVMatch..."
echo "========================================"

# Variables d'environnement pour Qt/PySide6
export QT_QPA_PLATFORM_PLUGIN_PATH="$VENV_DIR/lib/python*/site-packages/PySide6/Qt/plugins"
export QT_PLUGIN_PATH="$VENV_DIR/lib/python*/site-packages/PySide6/Qt/plugins"

# Créer répertoire logs si inexistant
mkdir -p logs

# Lancer main.py avec le log de session unifié
echo "Lancement: $VENV_PYTHON main.py" >> "$SESSION_LOG"
echo "Environnement Python: $VIRTUAL_ENV" >> "$SESSION_LOG"
echo "Lancement: $VENV_PYTHON main.py"
echo "Environnement Python: $VIRTUAL_ENV"
echo ""

echo "" >> "$SESSION_LOG"
echo "=== DEBUT SESSION CVMATCH ===" >> "$SESSION_LOG"
echo "[DEBUT MAIN.PY]" >> "$SESSION_LOG"

export CVMATCH_SESSION_LOG="$SESSION_LOG"
"$VENV_PYTHON" main.py
EXIT_CODE=$?

echo "" >> "$SESSION_LOG"
echo "=== FIN SESSION CVMATCH ===" >> "$SESSION_LOG"
echo "Heure de fin: $(date)" >> "$SESSION_LOG"
echo "Code de sortie: $EXIT_CODE" >> "$SESSION_LOG"
echo "==============================================" >> "$SESSION_LOG"

echo ""
echo "========================================"

if [[ $EXIT_CODE -eq 0 ]]; then
    log_success "CVMatch fermé normalement"
else
    log_error "CVMatch fermé avec erreur (code $EXIT_CODE)"
    echo ""
    echo "=== DIAGNOSTIC DÉTAILLÉ ==="
    echo ""
    echo "Environnement virtuel: $VENV_DIR"
    echo "Python utilisé: $VENV_PYTHON"
    echo "Version Python:"
    "$VENV_PYTHON" --version
    echo ""
    echo "Test imports critiques:"
    "$VENV_PYTHON" -c "try: import PySide6; from PySide6.QtWidgets import QApplication; import sys; print('PySide6: OK - Version', PySide6.__version__); print('QtWidgets: OK'); print('Python executable:', sys.executable); print('Python path:', sys.path[0]); except Exception as e: import traceback; print('ERREUR Import:', repr(e)); traceback.print_exc()"
    echo ""
    
    if [[ -d "logs" ]] && [[ -f "logs/app.log" ]]; then
        echo "=== DERNIERS LOGS ==="
        echo "Fichier logs/app.log:"
        tail -n 10 "logs/app.log" 2>/dev/null || echo "Impossible de lire logs/app.log"
    else
        echo "Dossier logs non trouvé"
    fi
    
    echo ""
    echo "=== SOLUTIONS ==="
    echo "1. Vérifier l'environnement virtuel: source $VENV_DIR/bin/activate"
    echo "2. Réinstaller PySide6: $VENV_PIP install --force-reinstall PySide6"
    echo "3. Tester imports: $VENV_PYTHON -c \"from PySide6.QtWidgets import QApplication; print('OK')\""
    echo "4. Relancer avec: ./cvmatch.sh"
    echo ""
fi

echo "========================================"
echo "Fin du lanceur CVMatch"
echo "Merci d'avoir utilisé CVMatch!"
echo "========================================"

# Désactiver l'environnement virtuel
deactivate 2>/dev/null || true

exit $EXIT_CODE
