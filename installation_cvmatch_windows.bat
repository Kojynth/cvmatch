@echo off
setlocal EnableExtensions
rem ================================================================
rem CVMatch - Installateur Windows (minimum)
rem ================================================================
chcp 65001 >nul

echo CVMatch - Installateur Windows
echo ==================================

set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%"
cd /d "%PROJECT_ROOT%"

rem Logging (in logs/ directory)
set "LOG_DIR=%PROJECT_ROOT%logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%" >nul 2>&1
set "LOG_STAMP="
for /f %%a in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HH-mm-ss"') do set "LOG_STAMP=%%a"
if "%LOG_STAMP%"=="" goto :fallback_stamp
goto :stamp_done
:fallback_stamp
set "LOG_STAMP=%date%_%time%"
set "LOG_STAMP=%LOG_STAMP:/=-%"
set "LOG_STAMP=%LOG_STAMP::=-%"
set "LOG_STAMP=%LOG_STAMP:,=-%"
set "LOG_STAMP=%LOG_STAMP:.=-%"
set "LOG_STAMP=%LOG_STAMP: =0%"
:stamp_done
set "INSTALL_LOG=%LOG_DIR%\\installation_cvmatch_windows_%LOG_STAMP%.log"
echo CVMatch - Installateur Windows (minimum) > "%INSTALL_LOG%"
echo Logs: %INSTALL_LOG% >> "%INSTALL_LOG%"
echo Logs: %INSTALL_LOG%

for %%I in ("%PROJECT_ROOT%") do (
    set "PROJECT_ROOT_PATH=%%~pI"
)
if "%PROJECT_ROOT_PATH%"=="\" goto :unsafe_project_root

rem Verification Python
if exist "%PROJECT_ROOT%python.exe" goto :python_hijack
if exist "%PROJECT_ROOT%python.bat" goto :python_hijack
if exist "%PROJECT_ROOT%python.cmd" goto :python_hijack
set "PYTHON_EXE="
set "PYTHON_ARGS="
set "PYTHON_BAD_VERSION="
set "PYTHON_BAD_ARCH="
set "HAS_PY_LAUNCHER="
where py >nul 2>&1
if not errorlevel 1 set "HAS_PY_LAUNCHER=1"
if not "%CVMATCH_PYTHON%"=="" (
    call :validate_python "%CVMATCH_PYTHON%"
    if not defined PYTHON_EXE (
        echo [WARN] CVMATCH_PYTHON invalide - detection automatique. >> "%INSTALL_LOG%"
        echo [WARN] CVMATCH_PYTHON invalide - detection automatique.
    )
)
if not defined PYTHON_EXE (
    call :find_python_from_py "3.13"
    call :find_python_from_py "3.12"
    call :find_python_from_py "3.11"
    call :find_python_from_py "3.10"
    call :find_python_from_py "3.14"
)
if not defined PYTHON_EXE (
    for /f "delims=" %%a in ('where python 2^>nul') do call :validate_python "%%a"
)
if not defined PYTHON_EXE (
    if defined PYTHON_BAD_VERSION goto :python_version
    if defined PYTHON_BAD_ARCH goto :python_arch
    goto :no_python
)
echo Using Python: %PYTHON_EXE% %PYTHON_ARGS% >> "%INSTALL_LOG%"
"%PYTHON_EXE%" %PYTHON_ARGS% --version >> "%INSTALL_LOG%" 2>&1

rem Creation environnement virtuel
echo Creation environnement virtuel...
echo Creation environnement virtuel... >> "%INSTALL_LOG%"
set "VENV_DIR=%PROJECT_ROOT%cvmatch_env"
if exist "%VENV_DIR%" (
    if /I not "%VENV_DIR%"=="%PROJECT_ROOT%cvmatch_env" goto :unsafe_venv
    rmdir /s /q "%VENV_DIR%"
)
"%PYTHON_EXE%" %PYTHON_ARGS% -m venv "%VENV_DIR%" >> "%INSTALL_LOG%" 2>&1
if errorlevel 1 goto :venv_failed

rem Activation environnement
call "%VENV_DIR%\Scripts\activate.bat"
if errorlevel 1 goto :activate_failed

rem Installation dependances minimales
set "REQ_FILE=%PROJECT_ROOT%requirements_windows.txt"
set "REQ_LOCK=%PROJECT_ROOT%requirements_windows.lock"
set "REQ_TO_USE="
set "REQ_HASH_ARGS="
if exist "%REQ_LOCK%" (
    set "REQ_TO_USE=%REQ_LOCK%"
    set "REQ_HASH_ARGS=--require-hashes"
    echo Using locked requirements file. >> "%INSTALL_LOG%"
) else (
    if not exist "%REQ_FILE%" goto :req_missing
    set "REQ_TO_USE=%REQ_FILE%"
    echo [WARN] Using unpinned requirements file. >> "%INSTALL_LOG%"
    echo [WARN] Consider creating requirements_windows.lock with hashes.
)
echo Installation dependances minimales...
echo Installation dependances minimales... >> "%INSTALL_LOG%"
"%VENV_DIR%\Scripts\pip.exe" install %REQ_HASH_ARGS% -r "%REQ_TO_USE%" >> "%INSTALL_LOG%" 2>&1
if errorlevel 1 goto :pip_failed

echo Installation minimale terminee.
echo Installation minimale terminee. >> "%INSTALL_LOG%"

echo.
echo Installation terminee!
echo Utilisez cvmatch.bat pour lancer l'application.
echo Pour activer l'IA, lancez installation_cvmatch_ai_windows.bat.
echo Installation terminee! >> "%INSTALL_LOG%"
echo Utilisez cvmatch.bat pour lancer l'application. >> "%INSTALL_LOG%"
echo Pour activer l'IA, lancez installation_cvmatch_ai_windows.bat. >> "%INSTALL_LOG%"
pause
exit /b 0

:find_python_from_py
if defined PYTHON_EXE exit /b 0
if not defined HAS_PY_LAUNCHER exit /b 0
set "PY_TAG=%~1"
py -%PY_TAG% -c "import struct, sys; sys.exit(0 if struct.calcsize('P')*8 >= 64 else 1)" >nul 2>&1
if errorlevel 1 exit /b 0
set "PYTHON_EXE=py"
set "PYTHON_ARGS=-%PY_TAG%"
exit /b 0

:validate_python
if defined PYTHON_EXE exit /b 0
set "CANDIDATE=%~1"
if "%CANDIDATE%"=="" exit /b 0
if not exist "%CANDIDATE%" exit /b 0
echo("%CANDIDATE%" | findstr /I /L /C:"WindowsApps" >nul
if not errorlevel 1 exit /b 0
"%CANDIDATE%" -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if errorlevel 1 (
    set "PYTHON_BAD_VERSION=1"
    exit /b 0
)
"%CANDIDATE%" -c "import struct; sys.exit(0 if struct.calcsize('P')*8 >= 64 else 1)" >nul 2>&1
if errorlevel 1 (
    set "PYTHON_BAD_ARCH=1"
    exit /b 0
)
set "PYTHON_EXE=%CANDIDATE%"
set "PYTHON_ARGS="
exit /b 0

:unsafe_project_root
echo ERREUR: Repertoire projet non securise (racine du disque).
echo ERREUR: Repertoire projet non securise (racine du disque). >> "%INSTALL_LOG%"
pause
exit /b 1

:python_hijack
echo ERREUR: Python local detecte dans le dossier projet.
echo ERREUR: Python local detecte dans le dossier projet. >> "%INSTALL_LOG%"
echo Supprimez python.exe/python.bat/python.cmd puis relancez.
echo Supprimez python.exe/python.bat/python.cmd puis relancez. >> "%INSTALL_LOG%"
pause
exit /b 1

:python_version
echo ERREUR: Version Python insuffisante (3.10+ requis).
echo ERREUR: Version Python insuffisante (3.10+ requis). >> "%INSTALL_LOG%"
pause
exit /b 1

:python_arch
echo ERREUR: Python 64-bit requis.
echo ERREUR: Python 64-bit requis. >> "%INSTALL_LOG%"
pause
exit /b 1

:no_python
echo ERREUR: Python 3.10+ requis
echo Telechargez Python depuis https://python.org
echo ERREUR: Python 3.10+ requis >> "%INSTALL_LOG%"
pause
exit /b 1

:venv_failed
echo ERREUR: Creation environnement virtuel
echo ERREUR: Creation environnement virtuel >> "%INSTALL_LOG%"
pause
exit /b 1

:activate_failed
echo ERREUR: Activation environnement
echo ERREUR: Activation environnement >> "%INSTALL_LOG%"
pause
exit /b 1

:req_missing
echo ERREUR: requirements_windows.txt manquant
echo ERREUR: requirements_windows.txt manquant >> "%INSTALL_LOG%"
pause
exit /b 1

:unsafe_venv
echo ERREUR: Chemin environnement virtuel non securise.
echo ERREUR: Chemin environnement virtuel non securise. >> "%INSTALL_LOG%"
pause
exit /b 1

:pip_failed
echo [ERREUR] Installation dependances minimales echouee.
echo [ERREUR] Installation dependances minimales echouee. >> "%INSTALL_LOG%"
pause
exit /b 1
