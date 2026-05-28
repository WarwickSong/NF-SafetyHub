$ErrorActionPreference = "Stop"

$DeployDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $DeployDir
$PythonPath = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

Set-Location $ProjectRoot

if (-not (Test-Path $PythonPath)) {
    & (Join-Path $DeployDir "setup_venv.ps1")
}

& $PythonPath -m pytest tests\test_keyword.py tests\test_regex.py tests\test_scanner.py tests\test_rules_config.py
