@echo off
setlocal EnableExtensions EnableDelayedExpansion
rem ================================================================
rem CVMatch - Lanceur Windows avec gestion venv
rem ================================================================
rem Ce script gere automatiquement l'environnement virtuel,
rem verifie les dependances et lance CVMatch de maniere robuste.

chcp 65001 >nul

rem Definir les couleurs pour Windows (avec powershell)
set "COLOR_INFO=Write-Host -ForegroundColor Cyan"
set "COLOR_SUCCESS=Write-Host -ForegroundColor Green"
set "COLOR_WARNING=Write-Host -ForegroundColor Yellow"
set "COLOR_ERROR=Write-Host -ForegroundColor Red"
set "COLOR_TITLE=Write-Host -ForegroundColor Magenta"

echo.
powershell -Command "%COLOR_TITLE% '========================================'"
powershell -Command "%COLOR_TITLE% 'CVMatch - lanceur'"
powershell -Command "%COLOR_TITLE% '========================================'"

set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%"
cd /d "%PROJECT_ROOT%"

rem Hugging Face cache (shared by NER, zero-shot, and LLM)
set "HF_CACHE_DIR=%PROJECT_ROOT%.hf_cache"
set "HUGGINGFACE_HUB_CACHE=%HF_CACHE_DIR%"
set "HF_HUB_CACHE=%HF_CACHE_DIR%"
set "TRANSFORMERS_CACHE=%HF_CACHE_DIR%"
set "HF_HUB_DISABLE_SYMLINKS=1"
set "HF_HUB_DISABLE_SYMLINKS_WARNING=1"
if "%CVMATCH_AI_MODE%"=="" set "CVMATCH_AI_MODE=lite"

rem Creer log de session avec timestamp des le debut
for /f "tokens=1-3 delims=/" %%a in ("%date%") do set "session_date=%%c-%%a-%%b"
for /f "tokens=1-3 delims=:" %%a in ("%time%") do set "session_time=%%a-%%b-%%c"
set "session_time=%session_time: =0%"
set "session_time=%session_time:,=%"
set "SESSION_TIMESTAMP=%session_date%_%session_time%"
set "SESSION_LOG=logs\sessionlog\cvmatch_session_%SESSION_TIMESTAMP%.log"

mkdir logs 2>nul
mkdir logs\sessionlog 2>nul

rem Nettoyage des anciens logs (garde les 20 plus recents)
for /f "skip=20 delims=" %%f in ('dir /b /o-d "logs\sessionlog\cvmatch_session_*.log" 2^>nul') do (
    del "logs\sessionlog\%%f" >nul 2>&1
)

rem Definir le repertoire de l'environnement virtuel d'abord
set "VENV_DIR=%PROJECT_ROOT%cvmatch_env"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
set "VENV_PIP=%VENV_DIR%\Scripts\pip.exe"

rem Initialiser le log de session avec encodage UTF-8
chcp 65001 > nul
echo ============================================== > "%SESSION_LOG%"
echo CVMatch - Session Log >> "%SESSION_LOG%"
echo ============================================== >> "%SESSION_LOG%"
echo Date/Heure: %date% %time% >> "%SESSION_LOG%"
echo Session ID: %SESSION_TIMESTAMP% >> "%SESSION_LOG%"
echo Python: "%VENV_PYTHON%" >> "%SESSION_LOG%"
echo Repertoire: %CD% >> "%SESSION_LOG%"
echo Utilisateur: %USERNAME% >> "%SESSION_LOG%"
echo ============================================== >> "%SESSION_LOG%"
echo CVMatch - lanceur >> "%SESSION_LOG%"
echo ==============================================

rem ================================================================
rem ETAPE 1: Verifications pre-vol
rem ================================================================
echo [1/6] Verifications systeme... >> "%SESSION_LOG%"
powershell -Command "%COLOR_INFO% '[1/6] Verifications systeme...'"

rem Test Python
python --version >nul 2>&1 || (
    powershell -Command "%COLOR_ERROR% 'ERREUR: Python n''est pas installe ou pas dans le PATH'"
    echo.
    powershell -Command "%COLOR_WARNING% 'Solutions:'"
    powershell -Command "%COLOR_WARNING% '1. Installer Python depuis https://python.org'"
    powershell -Command "%COLOR_WARNING% '2. Cocher Add Python to PATH lors de l''installation'"
    powershell -Command "%COLOR_WARNING% '3. Redemarrer le terminal apres installation'"
    pause
    exit /b 1
)

python --version 2>&1 | findstr /c:"3." >nul || (
    powershell -Command "%COLOR_ERROR% 'ERREUR: Python 3.x requis'"
    python --version
    pause
    exit /b 1
)

powershell -Command "%COLOR_SUCCESS% 'Python OK:'"
echo Python OK: >> "%SESSION_LOG%"
python --version
python --version >> "%SESSION_LOG%" 2>&1

rem ================================================================
rem ETAPE 2: Gestion intelligente de l'environnement virtuel
rem ================================================================
echo [2/6] Gestion environnement virtuel... >> "%SESSION_LOG%"
powershell -Command "%COLOR_INFO% '[2/6] Gestion environnement virtuel...'"

if exist "%VENV_DIR%" (
    echo Environnement virtuel trouve: %VENV_DIR% >> "%SESSION_LOG%"
    powershell -Command "%COLOR_SUCCESS% 'Environnement virtuel trouve: %VENV_DIR%'"

    rem Verifier que l'environnement virtuel est fonctionnel
    "%VENV_PYTHON%" --version >nul 2>&1 || (
        echo Environnement virtuel corrompu, recreation... >> "%SESSION_LOG%"
        powershell -Command "%COLOR_WARNING% 'Environnement virtuel corrompu, recreation...'"
        echo Suppression ancien environnement virtuel... >> "%SESSION_LOG%"
        powershell -Command "%COLOR_INFO% 'Suppression ancien environnement...'"
        rmdir /s /q "%VENV_DIR%" 2>nul
        goto CREATE_VENV
    )

    powershell -Command "%COLOR_INFO% 'Test environnement virtuel...'"
    echo Test environnement virtuel... >> "%SESSION_LOG%"
    call :TEST_VENV
    if errorlevel 1 (
        powershell -Command "%COLOR_WARNING% 'Environnement virtuel defaillant, recreation...'"
        rmdir /s /q "%VENV_DIR%" 2>nul
        goto CREATE_VENV
    )

    if not exist "%VENV_DIR%\Scripts\activate.bat" (
        echo Environnement virtuel incomplet, recreation... >> "%SESSION_LOG%"
        powershell -Command "%COLOR_WARNING% 'Environnement virtuel incomplet, recreation...'"
        rmdir /s /q "%VENV_DIR%" 2>nul
        goto CREATE_VENV
    )
    if not exist "%VENV_DIR%\Scripts\pip.exe" (
        echo Environnement virtuel incomplet - pip manquant, recreation... >> "%SESSION_LOG%"
        powershell -Command "%COLOR_WARNING% 'Environnement virtuel incomplet - pip manquant, recreation...'"
        rmdir /s /q "%VENV_DIR%" 2>nul
        goto CREATE_VENV
    )

    goto ACTIVATE_VENV
) else (
    powershell -Command "%COLOR_INFO% 'Environnement virtuel non trouve, creation...'"
)

:CREATE_VENV
echo Creation environnement virtuel... >> "%SESSION_LOG%"
powershell -Command "%COLOR_INFO% 'Creation environnement virtuel...'"
echo Execution: python -m venv "%VENV_DIR%" >> "%SESSION_LOG%"
powershell -Command "%COLOR_WARNING% 'Cette operation peut prendre plusieurs minutes...'"
echo Cette operation peut prendre plusieurs minutes... >> "%SESSION_LOG%"
python -m venv "%VENV_DIR%" || (
    echo ERREUR: Impossible de creer l'environnement virtuel
    echo.
    echo Solutions:
    echo 1. Verifier que le module venv est installe: python -m venv --help
    echo 2. Installer avec: python -m pip install virtualenv
    echo 3. Utiliser: python -m virtualenv cvmatch_env
    pause
    exit /b 1
)

echo Environnement virtuel cree avec succes >> "%SESSION_LOG%"
powershell -Command "%COLOR_SUCCESS% 'Environnement virtuel cree avec succes'"

:ACTIVATE_VENV
powershell -Command "%COLOR_INFO% 'Activation environnement virtuel...'"
call "%VENV_DIR%\Scripts\activate.bat" || (
    echo ERREUR: Impossible d'activer l'environnement virtuel
    pause
    exit /b 1
)

echo Environnement virtuel active >> "%SESSION_LOG%"
powershell -Command "%COLOR_SUCCESS% 'Environnement virtuel active'"

rem ================================================================
rem ETAPE 3: Verification des dependances
rem ================================================================
echo [3/5] Verification dependances... >> "%SESSION_LOG%"
powershell -Command "%COLOR_INFO% '[3/5] Verification dependances...'"

rem Test rapide des packages critiques
echo Test des dependances critiques... >> "%SESSION_LOG%"
powershell -Command "%COLOR_INFO% 'Test des dependances critiques...'"
"%VENV_PYTHON%" -c "import PySide6, loguru, sqlmodel, pandas, numpy, requests, dateutil, pydantic, pypdf, docx, bs4, fitz, PIL, jinja2, psutil, selenium" >nul 2>&1
if errorlevel 1 goto DEPS_MISSING
echo [SUCCESS] Toutes les dependances sont presentes >> "%SESSION_LOG%"
powershell -Command "%COLOR_SUCCESS% '[SUCCESS] Toutes les dependances sont presentes'"
goto DEPS_DONE

:DEPS_MISSING
    echo.
    powershell -Command "%COLOR_WARNING% '==============================================='"
    powershell -Command "%COLOR_WARNING% '  DEPENDANCES MANQUANTES DETECTEES'"
    powershell -Command "%COLOR_WARNING% '==============================================='"
    echo.
    powershell -Command "%COLOR_INFO% '[INFO] Des dependances critiques sont manquantes'"
    powershell -Command "%COLOR_INFO% '[INFO] Lancement de l''installateur automatique...'"
    echo.

    rem Lancer l'installateur Windows
    if exist "installation_cvmatch_windows.bat" (
        powershell -Command "%COLOR_INFO% 'Execution de installation_cvmatch_windows.bat...'"
        call installation_cvmatch_windows.bat
        if errorlevel 1 (
            powershell -Command "%COLOR_ERROR% 'ERREUR: L''installation a echoue'"
            echo Consultez les logs d'installation pour plus de details
            pause
            exit /b 1
        )
    ) else (
        powershell -Command "%COLOR_ERROR% 'ERREUR: installation_cvmatch_windows.bat introuvable'"
        echo.
        echo Solutions:
        echo 1. Telecharger et executer installation_cvmatch_windows.bat
        echo 2. Installer manuellement les dependances
        pause
        exit /b 1
    )

    echo.
    powershell -Command "%COLOR_SUCCESS% '==============================================='"
    powershell -Command "%COLOR_SUCCESS% '  INSTALLATION TERMINEE - REDEMARRAGE CVMATCH'"
    powershell -Command "%COLOR_SUCCESS% '==============================================='"
    echo.

:DEPS_DONE

rem Verification CUDA PyTorch (optionnel)
echo [CHECK] Verification CUDA PyTorch... >> "%SESSION_LOG%"
powershell -Command "%COLOR_INFO% '[CHECK] Verification CUDA PyTorch...'"
"%VENV_PYTHON%" -c "import torch" >nul 2>&1
if errorlevel 1 goto TORCH_MISSING
"%VENV_PYTHON%" -c "import torch, sys; print('torch', torch.__version__, 'cuda_available', torch.cuda.is_available(), 'cuda', torch.version.cuda); sys.exit(0 if torch.cuda.is_available() else 2)" >> "%SESSION_LOG%" 2>&1
set "CUDA_CHECK_RESULT=%ERRORLEVEL%"
if "%CUDA_CHECK_RESULT%"=="0" (
    echo [SUCCESS] CUDA detectee par PyTorch >> "%SESSION_LOG%"
    powershell -Command "%COLOR_SUCCESS% 'CUDA detectee par PyTorch'"
) else if "%CUDA_CHECK_RESULT%"=="2" (
    echo [WARN] CUDA non detectee par PyTorch - mode CPU. >> "%SESSION_LOG%"
    powershell -Command "%COLOR_WARNING% 'CUDA non detectee par PyTorch - mode CPU.'"
) else (
    echo [WARN] Verification CUDA PyTorch echouee - torch indisponible? >> "%SESSION_LOG%"
    powershell -Command "%COLOR_WARNING% 'Verification CUDA PyTorch echouee - torch indisponible?'"
)
goto TORCH_CHECK_DONE

:TORCH_MISSING
echo [INFO] PyTorch non installe - verification CUDA ignoree. >> "%SESSION_LOG%"
powershell -Command "%COLOR_INFO% 'PyTorch non installe - verification CUDA ignoree.'"

:TORCH_CHECK_DONE

rem Verification modeles IA
echo [CHECK] Verification modeles IA... >> "%SESSION_LOG%"
powershell -Command "%COLOR_INFO% '[CHECK] Verification modeles IA...'"
set "AI_CHECK_ARGS=--include-llm"
if not "%CVMATCH_AI_MODE%"=="" set "AI_CHECK_ARGS=%AI_CHECK_ARGS% --mode %CVMATCH_AI_MODE%"
"%VENV_PYTHON%" scripts\check_ai_models.py %AI_CHECK_ARGS% >nul 2>&1
set "AI_CHECK_RESULT=%ERRORLEVEL%"
if "%AI_CHECK_RESULT%"=="0" (
    echo [SUCCESS] Modeles IA detectes >> "%SESSION_LOG%"
    powershell -Command "%COLOR_SUCCESS% 'Modeles IA detectes'"
) else if "%AI_CHECK_RESULT%"=="2" (
    echo [WARN] Modeles IA manquants. >> "%SESSION_LOG%"
    powershell -Command "%COLOR_WARNING% 'Modeles IA manquants. Installation optionnelle.'"
    set "RUN_AI_INSTALL="
    set /p "RUN_AI_INSTALL=Installer les modeles IA maintenant ? ^(O/n^): "
    set "SKIP_AI_INSTALL="
    if /i "!RUN_AI_INSTALL!"=="n" set "SKIP_AI_INSTALL=1"
    if /i "!RUN_AI_INSTALL!"=="non" set "SKIP_AI_INSTALL=1"
    if not defined SKIP_AI_INSTALL (
        if exist "installation_cvmatch_ai_windows.bat" (
            call installation_cvmatch_ai_windows.bat
        ) else (
            echo [WARN] installation_cvmatch_ai_windows.bat introuvable >> "%SESSION_LOG%"
            powershell -Command "%COLOR_WARNING% 'installation_cvmatch_ai_windows.bat introuvable'"
        )
    ) else (
        echo [INFO] Installation modeles IA ignoree. >> "%SESSION_LOG%"
        powershell -Command "%COLOR_INFO% 'Installation modeles IA ignoree.'"
    )
    set "SKIP_AI_INSTALL="
) else (
    echo [WARN] Verification modeles IA echouee. >> "%SESSION_LOG%"
    powershell -Command "%COLOR_WARNING% 'Verification modeles IA echouee.'"
)

rem ================================================================
rem ETAPE 4: Tests de sante pre-lancement
rem ================================================================
echo [4/5] Tests de sante... >> "%SESSION_LOG%"
powershell -Command "%COLOR_INFO% '[4/5] Tests de sante...'"

rem Test presence fichier principal
if not exist "main.py" (
    powershell -Command "%COLOR_ERROR% 'ERREUR: main.py non trouve dans %PROJECT_ROOT%'"
    echo.
    echo Verifiez que vous etes dans le bon repertoire CVMatch
    pause
    exit /b 1
)

echo Tests de sante: OK >> "%SESSION_LOG%"
powershell -Command "%COLOR_SUCCESS% 'Tests de sante: OK'"

rem ================================================================
rem ETAPE 5: Lancement CVMatch
rem ================================================================
echo [5/5] Lancement CVMatch... >> "%SESSION_LOG%"
powershell -Command "%COLOR_INFO% '[5/5] Lancement CVMatch...'"
echo. >> "%SESSION_LOG%"
echo ======================================== >> "%SESSION_LOG%"
echo Demarrage de l'interface CVMatch... >> "%SESSION_LOG%"
echo ======================================== >> "%SESSION_LOG%"
echo.
echo ========================================
echo Demarrage de l'interface CVMatch...
echo ========================================

rem Variables d'environnement pour PySide6 et interface graphique
set "QT_QPA_PLATFORM_PLUGIN_PATH=%VENV_DIR%\Lib\site-packages\PySide6\plugins"
set "QT_PLUGIN_PATH=%VENV_DIR%\Lib\site-packages\PySide6\plugins"

rem Lancer avec plus de debugging et gestion d'erreurs
echo Lancement: "%VENV_PYTHON%" main.py >> "%SESSION_LOG%"
echo Environnement Python: %VIRTUAL_ENV% >> "%SESSION_LOG%"
echo Lancement: "%VENV_PYTHON%" main.py
echo Environnement Python: %VIRTUAL_ENV%
echo.


echo Creation log de session: %SESSION_LOG%
echo. >> "%SESSION_LOG%"
echo === DEBUT SESSION CVMATCH === >> "%SESSION_LOG%"

rem Lancement avec redirection vers fichier ET console (Windows)
echo [DEBUT MAIN.PY] >> "%SESSION_LOG%"

rem Definir variables d'environnement pour eviter les codes ANSI dans le fichier
set "PYTHONIOENCODING=utf-8"
set "PYTHONUNBUFFERED=1"

rem Lancer main.py avec le log de session unifie
set "CVMATCH_SESSION_LOG=%SESSION_LOG%"
"%VENV_PYTHON%" main.py

set "EXIT_CODE=%ERRORLEVEL%"

echo. >> "%SESSION_LOG%"
echo === FIN SESSION CVMATCH === >> "%SESSION_LOG%"
echo Heure de fin: %date% %time% >> "%SESSION_LOG%"
echo Code de sortie: %EXIT_CODE% >> "%SESSION_LOG%"
echo ============================================== >> "%SESSION_LOG%"

echo.
powershell -Command "%COLOR_TITLE% '========================================'"

if %EXIT_CODE% equ 0 (
    powershell -Command "%COLOR_SUCCESS% 'CVMatch ferme normalement'"
) else (
    powershell -Command "%COLOR_ERROR% 'CVMatch ferme avec erreur ^(code %EXIT_CODE%^)'"
    call :RUN_DIAGNOSTIC
    pause
)

powershell -Command "%COLOR_TITLE% '========================================'"
powershell -Command "%COLOR_SUCCESS% 'Fin du lanceur CVMatch'"
powershell -Command "%COLOR_SUCCESS% 'Merci d''avoir utilise CVMatch!'"
powershell -Command "%COLOR_TITLE% '========================================'"

rem Desactiver l'environnement virtuel
deactivate 2>nul

exit /b %EXIT_CODE%

:TEST_VENV
"%VENV_PYTHON%" -c "import sys" >> "%SESSION_LOG%" 2>&1
exit /b %ERRORLEVEL%

:RUN_DIAGNOSTIC
echo.
echo === DIAGNOSTIC DETAILLE ===
echo.
echo Environnement virtuel: %VENV_DIR%
echo Python utilise: "%VENV_PYTHON%"
echo Version Python:
"%VENV_PYTHON%" --version
echo.
echo Test imports critiques et diagnostics:
if exist "scripts\diagnostic.py" (
    "%VENV_PYTHON%" scripts\diagnostic.py
) else (
    call :DIAGNOSTIC_RAPIDE
)
echo.
if exist "logs" (
    echo === DERNIERS LOGS ===
    if exist "logs\app.log" (
        echo Fichier logs\app.log:
        call :TAIL_APP_LOG
    ) else (
        echo Fichier logs\app.log non trouve
    )
) else (
    echo Dossier logs non trouve
)
echo.
echo === SOLUTIONS ===
echo 1. Verifier que l'environnement virtuel est correct
echo 2. Reinstaller les dependances: "%VENV_PIP%" install --force-reinstall PySide6
echo 3. Tester directement: "%VENV_PYTHON%" -c "from PySide6.QtWidgets import QApplication; print('OK')"
echo.
exit /b 0

:DIAGNOSTIC_RAPIDE
echo Diagnostic rapide:
"%VENV_PYTHON%" --version
"%VENV_PYTHON%" -c "import PySide6" 2>nul && echo PySide6: OK || echo ERREUR: PySide6 non disponible
"%VENV_PYTHON%" -c "from PySide6.QtWidgets import QApplication" 2>nul && echo QtWidgets: OK || echo ERREUR: QtWidgets non disponible
exit /b 0

:TAIL_APP_LOG
powershell -Command "Get-Content 'logs\\app.log' -Tail 10"
exit /b 0
