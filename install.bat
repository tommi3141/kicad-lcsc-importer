@echo off
setlocal enabledelayedexpansion
for /f "usebackq delims=" %%D in (`powershell -NoProfile -Command "[Environment]::GetFolderPath('MyDocuments')"`) do set DOCS=%%D
set FOUND=0
for %%V in (9.0 10.0) do (
  if exist "%DOCS%\KiCad\%%V" (
    mkdir "%DOCS%\KiCad\%%V\plugins" 2>nul
    robocopy "%~dp0lcsc-importer" "%DOCS%\KiCad\%%V\plugins\lcsc-importer" /E /XD __pycache__ /NFL /NDL /NJH /NJS /NP >nul
    echo Installiert nach %DOCS%\KiCad\%%V\plugins\lcsc-importer
    set FOUND=1
  )
)
if "%FOUND%"=="0" echo Kein KiCad 9.0/10.0 Ordner in "%DOCS%\KiCad" gefunden.
echo.
echo Fertig. In KiCad: Einstellungen ^> Plugins ^> "KiCad-API aktivieren", dann KiCad neu starten.
echo Beim ersten Start legt KiCad die Python-Umgebung des Plugins an (Internet noetig, dauert kurz).
pause
