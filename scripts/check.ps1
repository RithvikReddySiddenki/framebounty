$ErrorActionPreference = 'Stop'
& "$PSScriptRoot/../.venv/Scripts/python.exe" -m pytest "$PSScriptRoot/../services/api/tests" -q
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Push-Location "$PSScriptRoot/../apps/web"
try {
    npm.cmd run typecheck
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    npm.cmd run build
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally { Pop-Location }
