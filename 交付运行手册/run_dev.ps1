$ErrorActionPreference = "Stop"

$DeployDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $DeployDir
$PythonPath = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

Set-Location $ProjectRoot

if (-not (Test-Path $PythonPath)) {
    & (Join-Path $DeployDir "setup_venv.ps1")
}

if (-not (Test-Path ".env")) {
    Copy-Item (Join-Path $DeployDir ".env.local.example") ".env"
}

& $PythonPath -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
