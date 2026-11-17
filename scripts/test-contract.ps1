param([string]$Distro = 'Ubuntu')
$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path -LiteralPath "$PSScriptRoot/..").Path
if (-not (Test-Path -LiteralPath "$repoRoot/.local/arc-foundry/forge")) {
    throw 'Run .venv/Scripts/python.exe scripts/setup_arc_tools.py first.'
}
$linuxRoot = (& wsl.exe -d $Distro --exec wslpath -a $repoRoot).Trim()
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& wsl.exe -d $Distro --exec "$linuxRoot/.local/arc-foundry/forge" test --root "$linuxRoot/contracts" --use "$linuxRoot/.local/arc-foundry/solc-0.8.24" --offline -vv
exit $LASTEXITCODE
