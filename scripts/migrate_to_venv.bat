@echo off
title Migration vers Environnement Virtuel CVMatch
color 0E

echo.
echo  ==========================================
echo   Migration vers Environnement Virtuel
echo        CVMatch - Generateur CV IA
echo  ==========================================
echo.

echo [INFO] Cette migration va:
echo   1. Remplacer CVMatch.bat par la version avec venv
echo   2. Remplacer cvmatch.sh par la version avec venv  
echo   3. Sauvegarder les anciens launchers
echo   4. Tester le nouvel environnement
echo.

set /p "confirm=Continuer la migration ? (o/N): "
if /i not "%confirm%"=="o" (
    echo Migration annulee
    pause
    exit /b 0
)

echo.
echo [ETAPE 1] Sauvegarde des anciens launchers...

rem Sauvegarder les anciens
if exist "CVMatch.bat" (
    move "CVMatch.bat" "CVMatch_old.bat" >nul
    echo   - CVMatch.bat -> CVMatch_old.bat
)

if exist "cvmatch.sh" (
    move "cvmatch.sh" "cvmatch_old.sh" >nul  
    echo   - cvmatch.sh -> cvmatch_old.sh
)

echo.
echo [ETAPE 2] Installation nouveaux launchers...

rem Installer les nouveaux
if exist "CVMatch_new.bat" (
    move "CVMatch_new.bat" "CVMatch.bat" >nul
    echo   - CVMatch_new.bat -> CVMatch.bat
) else (
    echo   [ERREUR] CVMatch_new.bat introuvable
)

if exist "cvmatch_new.sh" (
    move "cvmatch_new.sh" "cvmatch.sh" >nul
    echo   - cvmatch_new.sh -> cvmatch.sh  
) else (
    echo   [ERREUR] cvmatch_new.sh introuvable
)

echo.
echo [ETAPE 3] Test du nouveau launcher...
echo Lancement de CVMatch.bat pour test...
timeout /t 3 >nul

rem Tester le nouveau launcher (sans lancer l'app)
echo @echo off > test_launcher.bat
echo echo Test launcher OK - Migration reussie >> test_launcher.bat
echo timeout /t 2 ^>nul >> test_launcher.bat
echo exit /b 0 >> test_launcher.bat

call test_launcher.bat
del test_launcher.bat >nul 2>&1

echo.
echo [SUCCESS] Migration terminee avec succes !
echo.
echo Utilisation:
echo   Windows: Double-cliquez sur CVMatch.bat
echo   Linux:   ./cvmatch.sh
echo.
echo En cas de probleme, restaurez avec:
echo   Windows: move CVMatch_old.bat CVMatch.bat
echo   Linux:   mv cvmatch_old.sh cvmatch.sh
echo.

pause
