# Caslu SysCare — pytest (UI offscreen)
# Uso: .\scripts\test.ps1
#      .\scripts\test.ps1 tests/test_core.py -v
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PytestArgs
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    & (Join-Path $PSScriptRoot "setup-dev.ps1")
}

$py = Join-Path $Root ".venv\Scripts\python.exe"
$prev = $env:QT_QPA_PLATFORM
$env:QT_QPA_PLATFORM = "offscreen"
try {
    if ($PytestArgs.Count -gt 0) {
        & $py -m pytest @PytestArgs
    } else {
        & $py -m pytest -q
    }
} finally {
    if ($null -eq $prev) {
        Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
    } else {
        $env:QT_QPA_PLATFORM = $prev
    }
}
