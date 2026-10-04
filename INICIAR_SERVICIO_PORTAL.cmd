@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist config_supabase.json (
  echo Falta config_supabase.json. Copia config_supabase.example.json y completa los datos.
  pause
  exit /b 1
)
:inicio
python consola.py servicio --config config_supabase.json
echo El servicio se detuvo. Se reinicia en 30 segundos. Cierra esta ventana para no reiniciarlo.
timeout /t 30 /nobreak >nul
goto inicio
