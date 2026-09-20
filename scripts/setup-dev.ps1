# Caslu SysCare — ambiente de desenvolvimento (Windows PowerShell)
# Uso: .\scripts\setup-dev.ps1
#      .\scripts\setup-dev.ps1 -Recreate   # apaga e recria o .venv
param(
    [switch]$Recreate
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

if ($Recreate -and (Test-Path ".venv")) {
    Write-Host "Removendo .venv..."
    Remove-Item -Recurse -Force ".venv"
}

if (-not (Test-Path ".venv")) {
    Write-Host "Criando venv..."
    python -m venv .venv
}

$py = Join-Path $Root ".venv\Scripts\python.exe"
$pip = Join-Path $Root ".venv\Scripts\pip.exe"

& $py -m pip install --upgrade pip
& $pip install -e ".[dev]"

Write-Host ""
Write-Host "Pronto. Proximos passos:"
Write-Host "  Testes:  .\scripts\test.ps1"
Write-Host "  App GUI: .\scripts\run.ps1"
Write-Host "  Exe:     .\build_exe.ps1"
