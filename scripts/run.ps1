# Caslu SysCare — abre a interface grafica
# Uso: .\scripts\run.ps1
$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    & (Join-Path $PSScriptRoot "setup-dev.ps1")
}

# test.ps1 usa offscreen; se ficar no terminal, a janela nao aparece.
Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue

$py = Join-Path $Root ".venv\Scripts\python.exe"
# python -m mantem o terminal aberto ate fechar o app e mostra erros de startup
& $py -m syscare
exit $LASTEXITCODE
