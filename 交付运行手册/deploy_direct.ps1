$ErrorActionPreference = "Stop"

$DeployDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $DeployDir
$PythonPath = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

Set-Location $ProjectRoot

if (-not (Test-Path $PythonPath)) {
    & (Join-Path $DeployDir "setup_venv.ps1")
}

if (-not (Test-Path ".env")) {
    Copy-Item (Join-Path $DeployDir ".env.production.example") ".env"
    Write-Host "Created .env from production example. Please review it before real production use."
}

& $PythonPath scripts\init_db.py
& $PythonPath -m uvicorn main:app --host 0.0.0.0 --port 8000
