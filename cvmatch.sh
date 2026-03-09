#!/bin/bash

# ================================================================
# CVMatch - Lanceur Linux/macOS avec gestion venv
# ================================================================
# Ce script gère automatiquement l'environnement virtuel,
# vérifie les dépendances et lance CVMatch de manière robuste.

if [ -z "${BASH_VERSION:-}" ]; then
    exec bash "$0" "$@"
fi

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

run_check_with_spinner() {
    local display_name="$1"
    local stdout_path="$2"
    local stderr_path="$3"
    local soft_timeout_sec="$4"
    shift 4
    local cmd=( "$@" )

    : > "$stdout_path"
    : > "$stderr_path"

    "${cmd[@]}" >"$stdout_path" 2>"$stderr_path" &
    local pid=$!
    local start_ts
    start_ts="$(date +%s)"
    local spinner='|/-\'
    local idx=0
    local soft_notified=0
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
            echo "[INFO] ${display_name}: verification toujours en cours (${elapsed}s), on continue..."
            soft_notified=1
        fi
    done

    set +e
    wait "$pid"
    local rc=$?
    set -e

    drain_stream_lines "$stdout_path" "$display_name" out_seen
    drain_stream_lines "$stderr_path" "${display_name}/ERR" err_seen

    local total=$(( $(date +%s) - start_ts ))
    printf '\r[DONE] %s en %ss.                        \n' "$display_name" "$total"
    return "$rc"
}

detect_python() {
    local candidate
    for candidate in python3.13 python3.12 python3.11 python3.10 python3.9 python3 python; do
        if command -v "$candidate" >/dev/null 2>&1; then
            if "$candidate" -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >/dev/null 2>&1; then
                echo "$candidate"
                return 0
            fi
        fi
    done

    for candidate in /usr/bin/python3.13 /usr/bin/python3.12 /usr/bin/python3.11 /usr/bin/python3.10 /usr/bin/python3.9 /usr/bin/python3 /usr/local/bin/python3 /opt/homebrew/bin/python3; do
        if [[ -x "$candidate" ]]; then
            if "$candidate" -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >/dev/null 2>&1; then
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

if [[ -z "${CVMATCH_AI_MODE:-}" ]]; then
    CVMATCH_AI_MODE="lite"
fi

if [[ -z "${PYTORCH_CUDA_ALLOC_CONF:-}" ]]; then
    export PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True"
fi

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
    log_error "Python 3.10+ introuvable dans le PATH"
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
if ! $PYTHON_BIN -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)"; then
    log_error "Python 3.10+ requis, version dÃ©tectÃ©e: $PYTHON_VERSION"
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
DEPS_OUT="$(mktemp)"
DEPS_ERR="$(mktemp)"
if ! run_check_with_spinner "Dependances critiques" "$DEPS_OUT" "$DEPS_ERR" 20 "$VENV_PYTHON" scripts/check_critical_deps.py; then
    cat "$DEPS_OUT" >> "$SESSION_LOG" 2>/dev/null || true
    cat "$DEPS_ERR" >> "$SESSION_LOG" 2>/dev/null || true
    rm -f "$DEPS_OUT" "$DEPS_ERR"
    echo
    echo "==============================================="
    echo "  INSTALLATION AUTOMATIQUE DES DÉPENDANCES"
    echo "==============================================="
    echo
    log_warning "[INFO] Des dépendances critiques manquantes ont été détectées"
    log_warning "[INFO] Installation automatique en cours..."
    echo

    if [[ -f "installation_cvmatch_linux.sh" ]]; then
        if [[ -n "${PYTHON_BIN:-}" ]]; then
            "$PYTHON_BIN" - <<'PY'
from pathlib import Path
path = Path("installation_cvmatch_linux.sh")
data = path.read_bytes()
if data.startswith(b"\xef\xbb\xbf"):
    path.write_bytes(data[3:])
PY
        fi
        log_info "[INSTALL] Execution de installation_cvmatch_linux.sh..."
        if ! bash "installation_cvmatch_linux.sh"; then
            log_error "[ERREUR] Installation automatique échouée"
            exit 1
        fi
    else
        log_error "[ERREUR] installation_cvmatch_linux.sh introuvable"
        echo "Solutions:"
        echo "1. Re-télécharger l'installateur Linux"
        echo "2. Installer manuellement les dépendances"
        exit 1
    fi

    # Réactiver le venv (l'installateur peut l'avoir recréé)
    if [[ -f "$VENV_DIR/bin/activate" ]]; then
        source "$VENV_DIR/bin/activate"
    else
        log_error "[ERREUR] Environnement virtuel introuvable après installation"
        exit 1
    fi

    # Test final simple
    echo "[VERIFY] Test final des imports..."
    if "$VENV_PYTHON" -c "import PySide6, torch, lmformatenforcer; print('Tests imports OK')" &>/dev/null; then
        log_success "[SUCCESS] Installation vérifiée avec succès"
        echo
    else
        log_error "[ERREUR] Vérification post-installation échouée"
        exit 1
    fi
else
    cat "$DEPS_OUT" >> "$SESSION_LOG" 2>/dev/null || true
    cat "$DEPS_ERR" >> "$SESSION_LOG" 2>/dev/null || true
    rm -f "$DEPS_OUT" "$DEPS_ERR"
    echo "[SUCCESS] Toutes les dependances sont presentes" >> "$SESSION_LOG"
    log_success "Toutes les dépendances sont présentes"
fi

# Verification CUDA PyTorch
echo "[CHECK] Verification CUDA PyTorch..." >> "$SESSION_LOG"
log_info "[CHECK] Verification CUDA PyTorch..."
CUDA_OUT="$(mktemp)"
CUDA_ERR="$(mktemp)"
if run_check_with_spinner "CUDA PyTorch" "$CUDA_OUT" "$CUDA_ERR" 12 "$VENV_PYTHON" scripts/check_cuda_runtime.py; then
    CUDA_STATUS=0
else
    CUDA_STATUS=$?
fi
cat "$CUDA_OUT" >> "$SESSION_LOG" 2>/dev/null || true
cat "$CUDA_ERR" >> "$SESSION_LOG" 2>/dev/null || true
rm -f "$CUDA_OUT" "$CUDA_ERR"
if [ "$CUDA_STATUS" -eq 0 ]; then
    echo "[SUCCESS] CUDA detected by PyTorch" >> "$SESSION_LOG"
    log_success "CUDA detected by PyTorch"
else
    if [ "$CUDA_STATUS" -eq 2 ]; then
        echo "[WARN] CUDA not detected by PyTorch (CPU mode)." >> "$SESSION_LOG"
        log_warning "CUDA not detected by PyTorch (CPU mode)."
    elif [ "$CUDA_STATUS" -eq 3 ]; then
        echo "[WARN] PyTorch non installe dans cet environnement." >> "$SESSION_LOG"
        echo "[INFO] Pour activer l'IA locale (LLM), lancez: installation_cvmatch_ai_linux.sh" >> "$SESSION_LOG"
        log_warning "PyTorch non installe dans cet environnement."
        log_info "Pour activer l'IA locale (LLM), lancez: installation_cvmatch_ai_linux.sh"
    else
        echo "[WARN] PyTorch CUDA check failed." >> "$SESSION_LOG"
        log_warning "PyTorch CUDA check failed."
    fi
fi

# Verification modeles IA
echo "[CHECK] Verification modeles IA..." >> "$SESSION_LOG"
log_info "[CHECK] Verification modeles IA..."
AI_MODE="${CVMATCH_AI_MODE:-lite}"
AI_CHECK_ARGS=(--mode "$AI_MODE" --include-llm)
if [ "${CVMATCH_SKIP_LLM:-}" = "1" ]; then
    AI_CHECK_ARGS=(--mode "$AI_MODE")
fi

AI_OK=0
AI_HAVE_LLM=1
AI_STATUS=0
AI_OUT="$(mktemp)"
AI_ERR="$(mktemp)"
if run_check_with_spinner "Modeles IA" "$AI_OUT" "$AI_ERR" 15 "$VENV_PYTHON" scripts/check_ai_models.py "${AI_CHECK_ARGS[@]}"; then
    AI_OK=1
else
    AI_STATUS=$?
    if [ "$AI_STATUS" -eq 2 ]; then
        if [[ " ${AI_CHECK_ARGS[*]} " == *"--include-llm"* ]]; then
            if "$VENV_PYTHON" scripts/check_ai_models.py --mode "$AI_MODE" >/dev/null 2>&1; then
                AI_OK=1
                AI_HAVE_LLM=0
            fi
        fi
        if [ "$AI_OK" -eq 0 ] && [ "$AI_MODE" != "full" ]; then
            if "$VENV_PYTHON" scripts/check_ai_models.py --mode full >/dev/null 2>&1; then
                AI_OK=1
                AI_HAVE_LLM=0
                CVMATCH_AI_MODE="full"
                AI_MODE="full"
            fi
        fi
    fi
fi
cat "$AI_OUT" >> "$SESSION_LOG" 2>/dev/null || true
cat "$AI_ERR" >> "$SESSION_LOG" 2>/dev/null || true
rm -f "$AI_OUT" "$AI_ERR"

if [ "$AI_OK" -eq 1 ]; then
    if [ "$AI_HAVE_LLM" -eq 1 ]; then
        echo "[SUCCESS] Modeles IA detectes (mode: $AI_MODE)" >> "$SESSION_LOG"
        log_success "Modeles IA detectes (mode: $AI_MODE)"
    else
        echo "[WARN] Modeles IA de base detectes (mode: $AI_MODE) - LLM manquant." >> "$SESSION_LOG"
        log_warning "Modeles IA de base detectes (mode: $AI_MODE) - LLM manquant."
    fi
else
    if [ "${AI_STATUS:-1}" -eq 3 ]; then
        echo "[WARN] Runtime IA incomplet (torch/transformers/huggingface_hub manquants)." >> "$SESSION_LOG"
        log_warning "Runtime IA incomplet (torch/transformers/huggingface_hub manquants)."
        read -r -p "Installer les dependances IA maintenant ? (O/n): " RUN_AI_INSTALL
        if [ -z "$RUN_AI_INSTALL" ] || [[ "$RUN_AI_INSTALL" =~ ^[OoYy]$ ]]; then
            if [ -f "installation_cvmatch_ai_linux.sh" ]; then
                if [ -x "installation_cvmatch_ai_linux.sh" ]; then
                    ./installation_cvmatch_ai_linux.sh || log_warning "Installation dependances IA echouee."
                else
                    bash installation_cvmatch_ai_linux.sh || log_warning "Installation dependances IA echouee."
                fi
            else
                echo "[WARN] installation_cvmatch_ai_linux.sh introuvable." >> "$SESSION_LOG"
                log_warning "installation_cvmatch_ai_linux.sh introuvable."
            fi
        else
            echo "[INFO] Installation dependances IA ignoree." >> "$SESSION_LOG"
            log_info "Installation dependances IA ignoree."
        fi
    elif [ "${AI_STATUS:-1}" -eq 2 ]; then
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
if ! "$VENV_PYTHON" - <<'PY'
import sys
try:
    import PySide6, torch, transformers, loguru, pypdf, sqlmodel, docx, psutil, lmformatenforcer
    print("Tests d'import: OK")
except ImportError as exc:
    print(f"Erreur import: {exc}")
    sys.exit(1)
PY
then
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
    "$VENV_PYTHON" - <<'PY'
import sys
try:
    import PySide6
    from PySide6.QtWidgets import QApplication
    print("PySide6: OK - Version", PySide6.__version__)
    print("QtWidgets: OK")
    print("Python executable:", sys.executable)
    print("Python path:", sys.path[0])
except Exception as exc:
    import traceback
    print("ERREUR Import:", repr(exc))
    traceback.print_exc()
PY
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
