$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
  Write-Error "No se encontro el interprete en .venv\Scripts\python.exe"
}

Write-Host "Iniciando UrbanFlow en http://127.0.0.1:5052/"
& $python run.py
