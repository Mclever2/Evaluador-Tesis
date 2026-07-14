# ECM — script de desarrollo para Windows (PowerShell)
# Uso:  .\scripts\dev.ps1 setup    # crea .venv e instala dependencias del backend
#       .\scripts\dev.ps1 rubrics  # regenera los JSON de rúbricas desde docs/
#       .\scripts\dev.ps1 test     # corre pytest del backend
#       .\scripts\dev.ps1 api      # levanta FastAPI en http://localhost:8000
#       .\scripts\dev.ps1 web      # levanta el frontend (Vite) en http://localhost:5173

param([Parameter(Position = 0)][string]$Cmd = "help")

$Root = Split-Path -Parent $PSScriptRoot
$Venv = Join-Path $Root ".venv"
$Py = Join-Path $Venv "Scripts\python.exe"

function Ensure-Venv {
    if (-not (Test-Path $Py)) {
        Write-Host "Creando entorno virtual (.venv) con Python 3.11…"
        py -3.11 -m venv $Venv
        if (-not (Test-Path $Py)) { throw "No se pudo crear .venv. ¿Está instalado Python 3.11?" }
    }
}

switch ($Cmd) {
    "setup" {
        Ensure-Venv
        & $Py -m pip install --upgrade pip
        & $Py -m pip install -r (Join-Path $Root "backend\requirements.txt")
    }
    "rubrics" {
        Ensure-Venv
        Push-Location (Join-Path $Root "backend")
        & $Py -m cli.build_rubrics
        Pop-Location
    }
    "test" {
        Ensure-Venv
        Push-Location (Join-Path $Root "backend")
        & $Py -m pytest
        Pop-Location
    }
    "api" {
        Ensure-Venv
        Push-Location (Join-Path $Root "backend")
        & $Py -m uvicorn app.main:app --reload --port 8000
        Pop-Location
    }
    "web" {
        Push-Location (Join-Path $Root "web")
        npm run dev
        Pop-Location
    }
    default {
        Write-Host "Comandos: setup | rubrics | test | api | web"
    }
}
