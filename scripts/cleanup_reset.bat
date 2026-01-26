@echo off
setlocal enabledelayedexpansion

set "project_root=%~dp0"
for %%I in ("%project_root%.") do set "project_root=%%~fI"



REM CrÃ©er fichier de log avec timestamp
set logfile="%project_root%\reset_cleanup.log"
echo [%date% %time%] === DEBUT NETTOYAGE CVMATCH === > "%logfile%"
echo Nettoyage post-fermeture CVMatch...
echo [%date% %time%] Script de nettoyage lancÃ© >> "%logfile%"

REM Attendre 2 secondes que l'application se ferme complÃ¨tement
echo Attente fermeture application...
echo [%date% %time%] Attente fermeture application (2s)... >> "%logfile%"
timeout /t 2 /nobreak >nul

REM Supprimer base de donnÃ©es
echo Suppression bases de donnÃ©es...
echo [%date% %time%] Suppression bases de donnÃ©es >> "%logfile%"
if exist "%USERPROFILE%\.cvmatch\cvmatch.db" (
    del /f /q "%USERPROFILE%\.cvmatch\cvmatch.db" 2>nul
    echo [%date% %time%] - cvmatch.db utilisateur supprimÃ©e >> "%logfile%"
) else (
    echo [%date% %time%] - cvmatch.db utilisateur inexistante >> "%logfile%"
)

if exist "%project_root%\cvmatch.db" (
    del /f /q "%project_root%\cvmatch.db" 2>nul
    echo [%date% %time%] - cvmatch.db projet supprimÃ©e >> "%logfile%"
) else (
    echo [%date% %time%] - cvmatch.db projet inexistante >> "%logfile%"
)

if exist "%project_root%\data\cvmatch.db" (
    del /f /q "%project_root%\data\cvmatch.db" 2>nul
    echo [%date% %time%] - cvmatch.db data supprimÃ©e >> "%logfile%"
) else (
    echo [%date% %time%] - cvmatch.db data inexistante >> "%logfile%"
)

REM Nettoyage SÃ‰LECTIF des logs (prÃ©server logs systÃ¨me)
echo Nettoyage sÃ©lectif dossier logs...
echo [%date% %time%] Nettoyage sÃ©lectif dossier logs >> "%logfile%"
REM Supprimer SEULEMENT les logs utilisateur, pas les logs systÃ¨me
if exist "%project_root%\logs" (
    REM PROTECTION Ã‰TENDUE: PrÃ©server TOUS les logs systÃ¨me critiques
    for %%f in (install* setup* system* crash* emergency* crash_resistant* emergency_backup* errors_* diagnostic* debug_system* startup* init*) do (
        if exist "%project_root%\logs\%%f" (
            echo [%date% %time%] - PRÃ‰SERVÃ‰: %%f (log systÃ¨me critique) >> "%logfile%"
        )
    )
    
    REM SUPPRESSION SÃ‰CURISÃ‰E: Supprimer SEULEMENT les logs utilisateur identifiÃ©s
    del /f /q "%project_root%\logs\cv_extraction_*.log" 2>nul
    del /f /q "%project_root%\logs\session_*.log" 2>nul
    del /f /q "%project_root%\logs\extraction_*.log" 2>nul
    del /f /q "%project_root%\logs\user_*.log" 2>nul
    del /f /q "%project_root%\logs\profile_*.log" 2>nul
    del /f /q "%project_root%\logs\upload_*.log" 2>nul
    rmdir /s /q "%project_root%\logs\extraction" 2>nul
    
    REM SUPPRIMÃ‰: cvmatch.log et app.log - TROP DANGEREUX Ã  supprimer automatiquement
    REM Ces logs peuvent contenir des informations systÃ¨me importantes
    echo [%date% %time%] - Logs utilisateur supprimÃ©s (logs systÃ¨me prÃ©servÃ©s) >> "%logfile%"
) else (
    echo [%date% %time%] - Dossier logs inexistant >> "%logfile%"
)
REM S'assurer que le dossier logs existe
if not exist "%project_root%\logs" (
    mkdir "%project_root%\logs" 2>nul
)
echo. > "%project_root%\logs\.gitkeep" 2>nul
echo [%date% %time%] - Structure dossier logs prÃ©servÃ©e >> "%logfile%"

REM Supprimer autres dossiers de donnÃ©es
echo Nettoyage dossiers de donnÃ©es...
echo [%date% %time%] Nettoyage dossiers de donnÃ©es >> "%logfile%"
REM CRITIQUE: Liste exhaustive des dossiers avec donnÃ©es utilisateur
for %%d in (exports cache models data archive output "gÃ©nÃ©rÃ©" config gold) do (
    echo Nettoyage %%d...
    if exist "%project_root%\%%d" (
        rmdir /s /q "%project_root%\%%d" 2>nul
        echo [%date% %time%] - Dossier %%d supprimÃ© >> "%logfile%"
    ) else (
        echo [%date% %time%] - Dossier %%d inexistant >> "%logfile%"
    )
    mkdir "%project_root%\%%d" 2>nul
    echo. > "%project_root%\%%d\.gitkeep" 2>nul
    echo [%date% %time%] - Dossier %%d recrÃ©Ã© >> "%logfile%"
)

REM Nettoyage spÃ©cial pour dossier CV avec sous-dossiers
echo Nettoyage CV...
if exist "%project_root%\CV" (
    rmdir /s /q "%project_root%\CV" 2>nul
    echo [%date% %time%] - Dossier CV supprimÃ© >> "%logfile%"
)
mkdir "%project_root%\CV" 2>nul
mkdir "%project_root%\CV\importÃ©s" 2>nul
mkdir "%project_root%\CV\gÃ©nÃ©rÃ©s" 2>nul
echo. > "%project_root%\CV\.gitkeep" 2>nul
echo. > "%project_root%\CV\importÃ©s\.gitkeep" 2>nul
echo. > "%project_root%\CV\gÃ©nÃ©rÃ©s\.gitkeep" 2>nul
echo [%date% %time%] - Dossier CV recrÃ©Ã© avec sous-dossiers >> "%logfile%"

REM Supprimer dossiers datasets  
echo Nettoyage datasets...
echo [%date% %time%] Nettoyage datasets >> "%logfile%"
if exist "%project_root%\datasets\user_learning" (
    rmdir /s /q "%project_root%\datasets\user_learning" 2>nul
    echo [%date% %time%] - user_learning supprimÃ© >> "%logfile%"
)
if exist "%project_root%\datasets\training_ready" (
    rmdir /s /q "%project_root%\datasets\training_ready" 2>nul
    echo [%date% %time%] - training_ready supprimÃ© >> "%logfile%"
)
mkdir "%project_root%\datasets\user_learning" 2>nul
mkdir "%project_root%\datasets\training_ready" 2>nul
echo [%date% %time%] - Dossiers datasets recrÃ©Ã©s >> "%logfile%"

REM Supprimer dossier utilisateur complet
echo Suppression dossier utilisateur...
echo [%date% %time%] Suppression dossier utilisateur >> "%logfile%"
if exist "%USERPROFILE%\.cvmatch" (
    rmdir /s /q "%USERPROFILE%\.cvmatch" 2>nul
    echo [%date% %time%] - Dossier utilisateur .cvmatch supprimÃ© >> "%logfile%"
) else (
    echo [%date% %time%] - Dossier utilisateur .cvmatch inexistant >> "%logfile%"
)

REM CRITIQUE: Supprimer fichiers sensibles par patterns - VERSION SÃ‰CURISÃ‰E
echo Suppression fichiers sensibles...
echo [%date% %time%] Suppression fichiers sensibles >> "%logfile%"
REM PROTECTION: Ne pas utiliser de patterns trop larges qui suppriment les fichiers systÃ¨me
del /f /q "%project_root%\*.bak" 2>nul
del /f /q "%project_root%\*historique*" 2>nul
del /f /q "%project_root%\*rapport*" 2>nul
del /f /q "%project_root%\*export*" 2>nul
del /f /q "%project_root%\*gÃ©nÃ©rÃ©*" 2>nul
del /f /q "%project_root%\fix_*" 2>nul
del /f /q "%project_root%\validate_*" 2>nul
REM SUPPRESSION SPÃ‰CIFIQUE ET SÃ‰CURISÃ‰E des fichiers de test (Ã©viter test.*)
del /f /q "%project_root%\test_extraction_*.py" 2>nul
del /f /q "%project_root%\test_logging_*.py" 2>nul
del /f /q "%project_root%\test_persistent_*.py" 2>nul
del /f /q "%project_root%\debug_*.py" 2>nul
REM SUPPRIMÃ‰: "*.log", "*cv*", "*CV*", "test_*" - trop dangereux
echo [%date% %time%] - Fichiers sensibles supprimÃ©s (protection activÃ©e) >> "%logfile%"

REM VÃ‰RIFICATION CRITIQUE: S'assurer que les fichiers de lancement existent
echo VÃ©rification fichiers de lancement...
echo [%date% %time%] VÃ©rification fichiers de lancement >> "%logfile%"
if not exist "%project_root%\cvmatch.bat" (
    echo [%date% %time%] ALERTE: cvmatch.bat manquant - recrÃ©ation automatique >> "%logfile%"
    echo FICHIER CRITIQUE MANQUANT: cvmatch.bat sera recrÃ©Ã© au prochain dÃ©marrage
)
if not exist "%project_root%\cvmatch.sh" (
    echo [%date% %time%] ALERTE: cvmatch.sh manquant - recrÃ©ation automatique >> "%logfile%"
    echo FICHIER CRITIQUE MANQUANT: cvmatch.sh sera recrÃ©Ã© au prochain dÃ©marrage
)
if not exist "%project_root%\installation_cvmatch_windows.bat" (
    echo [%date% %time%] ALERTE: installation_cvmatch_windows.bat manquant >> "%logfile%"
)
if not exist "%project_root%\installation_cvmatch_ai_windows.bat" (
    echo [%date% %time%] ALERTE: installation_cvmatch_ai_windows.bat manquant >> "%logfile%"
)
if not exist "%project_root%\installation_cvmatch_linux.sh" (
    echo [%date% %time%] ALERTE: installation_cvmatch_linux.sh manquant >> "%logfile%"
)
if not exist "%project_root%\installation_cvmatch_ai_linux.sh" (
    echo [%date% %time%] ALERTE: installation_cvmatch_ai_linux.sh manquant >> "%logfile%"
)

REM Supprimer dossier gâ”œÂ®nâ”œÂ®râ”œÂ® avec encodage corrompu
if exist "%project_root%\gâ”œÂ®nâ”œÂ®râ”œÂ®" (
    rmdir /s /q "%project_root%\gâ”œÂ®nâ”œÂ®râ”œÂ®" 2>nul
    echo [%date% %time%] - Dossier encodage corrompu supprimÃ© >> "%logfile%"
)

REM Supprimer dossier tests/fixtures avec CV sensibles
if exist "%project_root%\tests\fixtures" (
    rmdir /s /q "%project_root%\tests\fixtures" 2>nul
    echo [%date% %time%] - Fixtures tests supprimÃ©es >> "%logfile%"
)

echo [%date% %time%] Nettoyage terminÃ© avec succÃ¨s >> "%logfile%"
echo Nettoyage terminÃ©.

REM RedÃ©marrer CVMatch
echo RedÃ©marrage de CVMatch...
echo [%date% %time%] RedÃ©marrage de CVMatch >> "%logfile%"
cd /d "%project_root%"
if exist "CVMatch.bat" (
    start "" "CVMatch.bat"
    echo [%date% %time%] RedÃ©marrage via CVMatch.bat >> "%logfile%"
) else (
    start "" python main.py
    echo [%date% %time%] RedÃ©marrage via python main.py >> "%logfile%"
)

echo [%date% %time%] === FIN NETTOYAGE CVMATCH === >> "%logfile%"

REM Auto-supprimer ce script (aprÃ¨s un dÃ©lai pour laisser le log se finir)
timeout /t 1 /nobreak >nul
del "%~f0" 2>nul
