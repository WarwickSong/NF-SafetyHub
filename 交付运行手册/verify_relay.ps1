$ErrorActionPreference = "Stop"

$DeployDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $DeployDir
$PythonPath = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

Set-Location $ProjectRoot

if (-not (Test-Path $PythonPath)) {
    & (Join-Path $DeployDir "setup_venv.ps1")
}

& $PythonPath -m pytest tests\test_fake_response.py tests\test_header_policy.py tests\test_relay.py tests\test_upstream_router.py
