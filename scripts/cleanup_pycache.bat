@echo off
REM Script de nettoyage des caches Python (.pyc et __pycache__)
REM Généré par Claude Code pour résoudre le bug TypeError signaux Qt

echo ========================================
echo  Nettoyage des caches Python
echo ========================================
echo.

echo [1/3] Suppression des dossiers __pycache__...
FOR /d /r . %%d IN (__pycache__) DO @IF EXIST "%%d" (
    echo   - Suppression de %%d
    rd /s /q "%%d"
)

echo.
echo [2/3] Suppression des fichiers .pyc individuels...
FOR /r . %%f IN (*.pyc) DO @IF EXIST "%%f" (
    echo   - Suppression de %%f
    del /q "%%f"
)

echo.
echo [3/3] Suppression des fichiers .pyo (optimisés)...
FOR /r . %%f IN (*.pyo) DO @IF EXIST "%%f" (
    echo   - Suppression de %%f
    del /q "%%f"
)

echo.
echo ========================================
echo  Nettoyage terminé !
echo ========================================
echo.
echo Vous pouvez maintenant relancer l'application :
echo   - python main.py
echo   - ou cvmatch.bat
echo.
echo Python va automatiquement recompiler les fichiers .py
echo avec les nouvelles modifications (including on_data_changed signature).
echo.
pause
