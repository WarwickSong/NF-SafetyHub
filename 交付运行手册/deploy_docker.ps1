$ErrorActionPreference = "Stop"

$DeployDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $DeployDir

Set-Location $ProjectRoot

if (-not (Test-Path ".env")) {
    Copy-Item (Join-Path $DeployDir ".env.production.example") ".env"
    Write-Host "Created .env from production example. Please review it before real production use."
}

docker compose up --build -d
docker compose ps
