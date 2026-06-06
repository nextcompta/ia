@echo off
REM Installation du skill CFE impots.gouv.fr (Windows)

echo.
echo === Installation du skill CFE impots.gouv.fr ===
echo.

REM Verif Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERREUR] Python non trouve. Installez Python 3.9+ depuis https://python.org
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('python --version') do echo [OK] %%i detecte

echo.
echo Installation de Playwright...
python -m pip install --quiet playwright
if errorlevel 1 goto erreur

echo Installation de Chromium (peut prendre 1-2 minutes)...
python -m playwright install chromium
if errorlevel 1 goto erreur

echo.
echo [OK] Installation terminee.
echo.
echo === Lancement du skill ===
echo.

set /p IDENTIFIANT="Identifiant espace professionnel impots.gouv.fr : "
if "%IDENTIFIANT%"=="" (
    echo [ERREUR] Identifiant requis.
    pause
    exit /b 1
)

REM Lancement depuis la racine du projet
cd /d "%~dp0..\.."
python -m skills.cfe_impots.cli --identifiant "%IDENTIFIANT%"
goto fin

:erreur
echo [ERREUR] Installation echouee.
pause
exit /b 1

:fin
pause
