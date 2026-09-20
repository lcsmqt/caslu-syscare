# Run in PowerShell, from the project root. Produces dist\CasluSysCare.exe
param(
    [switch]$RecreateVenv
)

$ErrorActionPreference = "Stop"

if ($RecreateVenv -and (Test-Path .venv)) {
    Remove-Item -Recurse -Force .venv
}

if (-not (Test-Path .venv)) {
    python -m venv .venv
}

.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pyinstaller --noconfirm --onefile --windowed --name CasluSysCare `
  --paths src --collect-submodules syscare src\syscare\__main__.py
Write-Host "Done: dist\CasluSysCare.exe"
