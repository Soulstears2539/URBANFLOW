@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo No se encontro .venv\Scripts\python.exe
  exit /b 1
)
echo Iniciando UrbanFlow en http://127.0.0.1:5052/
".venv\Scripts\python.exe" run.py
