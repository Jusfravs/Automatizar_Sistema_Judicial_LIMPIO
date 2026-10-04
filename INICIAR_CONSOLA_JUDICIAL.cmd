@echo off
chcp 65001 >nul
cd /d "%~dp0"
python consola.py
if errorlevel 1 echo La consola termino con un error. Revisa el mensaje anterior.
echo.
pause
