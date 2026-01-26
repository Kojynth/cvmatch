@echo off
setlocal enabledelayedexpansion

set "project_root=%~dp0"
for %%I in ("%project_root%.") do set "project_root=%%~fI"



REM Créer fichier de log avec timestamp
set logfile="%project_root%\reset_cleanup.log"
echo [%date% %time%] === DEBUT NETTOYAGE CVMATCH === > "%logfile%"
echo Nettoyage post-fermeture CVMatch...
echo [%date% %time%] Script de nettoyage lancé >> "%logfile%"

REM Attendre 2 secondes que l'application se ferme complètement
echo Attente fermeture application...
echo [%date% %time%] Attente fermeture application (2s)... >> "%logfile%"
timeout /t 2 /nobreak >nul

REM Supprimer base de données
echo Suppression bases de données...
echo [%date% %time%] Suppression bases de données >> "%logfile%"
if exist "%USERPROFILE%\.cvmatch\cvmatch.db" (
    del /f /q "%USERPROFILE%\.cvmatch\cvmatch.db" 2>nul
    echo [%date% %time%] - cvmatch.db utilisateur supprimée >> "%logfile%"
) else (
    echo [%date% %time%] - cvmatch.db utilisateur inexistante >> "%logfile%"
)

if exist "%project_root%\cvmatch.db" (
    del /f /q "%project_root%\cvmatch.db" 2>nul
    echo [%date% %time%] - cvmatch.db projet supprimée >> "%logfile%"
) else (
    echo [%date% %time%] - cvmatch.db projet inexistante >> "%logfile%"
)

if exist "%project_root%\data\cvmatch.db" (
    del /f /q "%project_root%\data\cvmatch.db" 2>nul
    echo [%date% %time%] - cvmatch.db data supprimée >> "%logfile%"
) else (
    echo [%date% %time%] - cvmatch.db data inexistante >> "%logfile%"
)

REM Nettoyage SÉLECTIF des logs (préserver logs système)
echo Nettoyage sélectif dossier logs...
echo [%date% %time%] Nettoyage sélectif dossier logs >> "%logfile%"
REM Supprimer SEULEMENT les logs utilisateur, pas les logs système
if exist "%project_root%\logs" (
    REM PROTECTION ÉTENDUE: Préserver TOUS les logs système critiques
    for %%f in (install* setup* system* crash* emergency* crash_resistant* emergency_backup* errors_* diagnostic* debug_system* startup* init*) do (
        if exist "%project_root%\logs\%%f" (
            echo [%date% %time%] - PRÉSERVÉ: %%f (log système critique) >> "%logfile%"
        )
    )
    
    REM SUPPRESSION SÉCURISÉE: Supprimer SEULEMENT les logs utilisateur identifiés
    del /f /q "%project_root%\logs\cv_extraction_*.log" 2>nul
    del /f /q "%project_root%\logs\session_*.log" 2>nul
    del /f /q "%project_root%\logs\extraction_*.log" 2>nul
    del /f /q "%project_root%\logs\user_*.log" 2>nul
    del /f /q "%project_root%\logs\profile_*.log" 2>nul
    del /f /q "%project_root%\logs\upload_*.log" 2>nul
    rmdir /s /q "%project_root%\logs\extraction" 2>nul
    
    REM SUPPRIMÉ: cvmatch.log et app.log - TROP DANGEREUX à supprimer automatiquement
    REM Ces logs peuvent contenir des informations système importantes
    echo [%date% %time%] - Logs utilisateur supprimés (logs système préservés) >> "%logfile%"
) else (
    echo [%date% %time%] - Dossier logs inexistant >> "%logfile%"
)
REM S'assurer que le dossier logs existe
if not exist "%project_root%\logs" (
    mkdir "%project_root%\logs" 2>nul
)
echo. > "%project_root%\logs\.gitkeep" 2>nul
echo [%date% %time%] - Structure dossier logs préservée >> "%logfile%"

REM Supprimer autres dossiers de données
echo Nettoyage dossiers de données...
echo [%date% %time%] Nettoyage dossiers de données >> "%logfile%"
REM CRITIQUE: Liste exhaustive des dossiers avec données utilisateur
for %%d in (exports cache models data archive output "généré" config gold) do (
    echo Nettoyage %%d...
    if exist "%project_root%\%%d" (
        rmdir /s /q "%project_root%\%%d" 2>nul
        echo [%date% %time%] - Dossier %%d supprimé >> "%logfile%"
    ) else (
        echo [%date% %time%] - Dossier %%d inexistant >> "%logfile%"
    )
    mkdir "%project_root%\%%d" 2>nul
    echo. > "%project_root%\%%d\.gitkeep" 2>nul
    echo [%date% %time%] - Dossier %%d recréé >> "%logfile%"
)

REM Nettoyage spécial pour dossier CV avec sous-dossiers
echo Nettoyage CV...
if exist "%project_root%\CV" (
    rmdir /s /q "%project_root%\CV" 2>nul
    echo [%date% %time%] - Dossier CV supprimé >> "%logfile%"
)
mkdir "%project_root%\CV" 2>nul
mkdir "%project_root%\CV\importés" 2>nul
mkdir "%project_root%\CV\générés" 2>nul
echo. > "%project_root%\CV\.gitkeep" 2>nul
echo. > "%project_root%\CV\importés\.gitkeep" 2>nul
echo. > "%project_root%\CV\générés\.gitkeep" 2>nul
echo [%date% %time%] - Dossier CV recréé avec sous-dossiers >> "%logfile%"

REM Supprimer dossiers datasets  
echo Nettoyage datasets...
echo [%date% %time%] Nettoyage datasets >> "%logfile%"
if exist "%project_root%\datasets\user_learning" (
    rmdir /s /q "%project_root%\datasets\user_learning" 2>nul
    echo [%date% %time%] - user_learning supprimé >> "%logfile%"
)
if exist "%project_root%\datasets\training_ready" (
    rmdir /s /q "%project_root%\datasets\training_ready" 2>nul
    echo [%date% %time%] - training_ready supprimé >> "%logfile%"
)
mkdir "%project_root%\datasets\user_learning" 2>nul
mkdir "%project_root%\datasets\training_ready" 2>nul
echo [%date% %time%] - Dossiers datasets recréés >> "%logfile%"

REM Supprimer dossier utilisateur complet
echo Suppression dossier utilisateur...
echo [%date% %time%] Suppression dossier utilisateur >> "%logfile%"
if exist "%USERPROFILE%\.cvmatch" (
    rmdir /s /q "%USERPROFILE%\.cvmatch" 2>nul
    echo [%date% %time%] - Dossier utilisateur .cvmatch supprimé >> "%logfile%"
) else (
    echo [%date% %time%] - Dossier utilisateur .cvmatch inexistant >> "%logfile%"
)

REM CRITIQUE: Supprimer fichiers sensibles par patterns - VERSION SÉCURISÉE
echo Suppression fichiers sensibles...
echo [%date% %time%] Suppression fichiers sensibles >> "%logfile%"
REM PROTECTION: Ne pas utiliser de patterns trop larges qui suppriment les fichiers système
del /f /q "%project_root%\*.bak" 2>nul
del /f /q "%project_root%\*historique*" 2>nul
del /f /q "%project_root%\*rapport*" 2>nul
del /f /q "%project_root%\*export*" 2>nul
del /f /q "%project_root%\*généré*" 2>nul
del /f /q "%project_root%\fix_*" 2>nul
del /f /q "%project_root%\validate_*" 2>nul
REM SUPPRESSION SPÉCIFIQUE ET SÉCURISÉE des fichiers de test (éviter test.*)
del /f /q "%project_root%\test_extraction_*.py" 2>nul
del /f /q "%project_root%\test_logging_*.py" 2>nul
del /f /q "%project_root%\test_persistent_*.py" 2>nul
del /f /q "%project_root%\debug_*.py" 2>nul
REM SUPPRIMÉ: "*.log", "*cv*", "*CV*", "test_*" - trop dangereux
echo [%date% %time%] - Fichiers sensibles supprimés (protection activée) >> "%logfile%"

REM VÉRIFICATION CRITIQUE: S'assurer que les fichiers de lancement existent
echo Vérification fichiers de lancement...
echo [%date% %time%] Vérification fichiers de lancement >> "%logfile%"
if not exist "%project_root%\cvmatch.bat" (
    echo [%date% %time%] ALERTE: cvmatch.bat manquant - recréation automatique >> "%logfile%"
    echo FICHIER CRITIQUE MANQUANT: cvmatch.bat sera recréé au prochain démarrage
)
if not exist "%project_root%\cvmatch.sh" (
    echo [%date% %time%] ALERTE: cvmatch.sh manquant - recréation automatique >> "%logfile%"
    echo FICHIER CRITIQUE MANQUANT: cvmatch.sh sera recréé au prochain démarrage
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

REM Supprimer dossier généré avec encodage corrompu (si existant)
if exist "%project_root%\généré" (
    rmdir /s /q "%project_root%\généré" 2>nul
    echo [%date% %time%] - Dossier encodage corrompu supprimé >> "%logfile%"
)

REM Supprimer dossier tests/fixtures avec CV sensibles
if exist "%project_root%\tests\fixtures" (
    rmdir /s /q "%project_root%\tests\fixtures" 2>nul
    echo [%date% %time%] - Fixtures tests supprimées >> "%logfile%"
)

echo [%date% %time%] Nettoyage terminé avec succès >> "%logfile%"
echo Nettoyage terminé.

REM Redémarrer CVMatch
echo Redémarrage de CVMatch...
echo [%date% %time%] Redémarrage de CVMatch >> "%logfile%"
cd /d "%project_root%"
if exist "CVMatch.bat" (
    start "" "CVMatch.bat"
    echo [%date% %time%] Redémarrage via CVMatch.bat >> "%logfile%"
) else (
    start "" python main.py
    echo [%date% %time%] Redémarrage via python main.py >> "%logfile%"
)

echo [%date% %time%] === FIN NETTOYAGE CVMATCH === >> "%logfile%"

REM Auto-supprimer ce script (après un délai pour laisser le log se finir)
timeout /t 1 /nobreak >nul
del "%~f0" 2>nul
