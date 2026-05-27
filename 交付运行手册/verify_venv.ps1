$ErrorActionPreference = "Stop"

$DeployDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $DeployDir
$PythonPath = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

Set-Location $ProjectRoot

if (-not (Test-Path $PythonPath)) {
    & (Join-Path $DeployDir "setup_venv.ps1")
}

& $PythonPath -m compileall main.py config.py dependencies.py proxy engine governance file_security observability storage admin notify middleware scripts tests
& $PythonPath -m pytest
