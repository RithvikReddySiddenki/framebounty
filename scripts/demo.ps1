<#
.SYNOPSIS
    Start, stop or inspect a local FrameBounty demo (API, media worker, chain worker, web).

.DESCRIPTION
    fixture mode: simulated listings and AI outcomes, no keys, no chain.
    testnet mode: live Arc testnet escrow + live Gemini. Every required setting
    must already be present (in .env or the terminal); the script refuses to
    start otherwise and lists only the missing names, never values.

    PIDs and logs are written to .local/demo/. 'stop' only stops processes that
    this script recorded in .local/demo/pids.json (and their child processes).

.EXAMPLE
    .\scripts\demo.ps1                          # fixture start
    .\scripts\demo.ps1 -Mode testnet -Action start
    .\scripts\demo.ps1 -Action status
    .\scripts\demo.ps1 -Action stop
    .\scripts\demo.ps1 -ListenHost 0.0.0.0      # phone/LAN demo (see docs/DEMO.md)
#>
param(
    [ValidateSet('fixture', 'testnet')][string]$Mode = 'fixture',
    [ValidateSet('start', 'stop', 'status')][string]$Action = 'start',
    [int]$ApiPort = 8000,
    [int]$WebPort = 3000,
    # 127.0.0.1 keeps the demo on this machine; 0.0.0.0 exposes it on the LAN.
    [string]$ListenHost = '127.0.0.1',
    # dev (default) reads NEXT_PUBLIC_* at startup. start serves an existing
    # production build, whose NEXT_PUBLIC_* values were fixed at build time.
    [ValidateSet('dev', 'start')][string]$WebMode = 'dev',
    [string]$EnvFile = '',
    [switch]$NoEnvFile
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$DemoDir = Join-Path $Root '.local\demo'
$PidFile = Join-Path $DemoDir 'pids.json'
$Python = Join-Path $Root '.venv\Scripts\python.exe'
$WebDir = Join-Path $Root 'apps\web'
$NextBin = Join-Path $WebDir 'node_modules\next\dist\bin\next'
if (-not $EnvFile) { $EnvFile = Join-Path $Root '.env' }

function Write-Step([string]$Message) { Write-Host "[demo] $Message" }
function Stop-Demo([string]$Message) { Write-Host "[demo] ERROR: $Message" -ForegroundColor Red; exit 1 }

# Windows PowerShell 5.1 joins -ArgumentList without quoting; quote by hand.
function ConvertTo-ArgumentString([string[]]$Arguments) {
    $parts = foreach ($a in $Arguments) {
        if ($a -match '[\s"]') { '"' + ($a -replace '"', '\"') + '"' } else { $a }
    }
    return ($parts -join ' ')
}

# Run a short prerequisite command, capture its output to a log, return exit code.
function Invoke-Checked([string]$Name, [string]$FilePath, [string[]]$Arguments) {
    $out = Join-Path $DemoDir "$Name.out.log"
    $err = Join-Path $DemoDir "$Name.err.log"
    $p = Start-Process -FilePath $FilePath -ArgumentList (ConvertTo-ArgumentString $Arguments) -WorkingDirectory $Root `
        -RedirectStandardOutput $out -RedirectStandardError $err -WindowStyle Hidden -PassThru -Wait
    return $p.ExitCode
}

function Read-PidFile {
    if (-not (Test-Path -LiteralPath $PidFile)) { return @() }
    $data = Get-Content -LiteralPath $PidFile -Raw | ConvertFrom-Json
    return @($data.processes)
}

# A recorded PID only counts if the same process (same start time) still runs,
# so a recycled PID belonging to something else is never touched.
function Get-RecordedProcess($Entry) {
    $proc = Get-Process -Id ([int]$Entry.pid) -ErrorAction SilentlyContinue
    if ($null -eq $proc) { return $null }
    try { $started = $proc.StartTime.ToUniversalTime().ToString('o') } catch { return $null }
    if ($started -ne $Entry.started) { return $null }
    return $proc
}

function Test-PortOpen([int]$Port) {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $task = $client.ConnectAsync('127.0.0.1', $Port)
        if ($task.Wait(1000)) { return $client.Connected }
        return $false
    } catch { return $false } finally { $client.Close() }
}

function Get-HttpStatus([string]$Url) {
    try {
        $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 10 -MaximumRedirection 0
        return [int]$r.StatusCode
    } catch {
        if ($_.Exception.Response) { return [int]$_.Exception.Response.StatusCode }
        return 0
    }
}

function Stop-Recorded {
    $entries = Read-PidFile
    if ($entries.Count -eq 0) { Write-Step 'No recorded demo processes.'; return }
    foreach ($entry in $entries) {
        $proc = Get-RecordedProcess $entry
        if ($null -eq $proc) { Write-Step "$($entry.name): not running (pid $($entry.pid))."; continue }
        # Stop the complete tree (venv/node may launch children). Never fall
        # back to stopping only the parent: that could orphan a server process
        # while reporting success and discarding the recovery record.
        # Windows PowerShell 5.1 turns a native program's stderr into an error
        # record under Stop, even when redirected. Capture the exit code so a
        # refusal reaches the explicit recovery-state path below.
        $previousErrorAction = $ErrorActionPreference
        try {
            $ErrorActionPreference = 'SilentlyContinue'
            & taskkill.exe /PID $proc.Id /T /F 2>$null | Out-Null
            $taskkillExit = $LASTEXITCODE
        } finally {
            $ErrorActionPreference = $previousErrorAction
        }
        if ($taskkillExit -ne 0) {
            Stop-Demo "$($entry.name) process tree could not be stopped; PID record was preserved."
        }
        Write-Step "$($entry.name): stopped (pid $($proc.Id))."
        [void]$proc.WaitForExit(5000)
        if ($null -ne (Get-RecordedProcess $entry)) {
            Stop-Demo "$($entry.name) did not stop (pid $($proc.Id)); PID record was preserved."
        }
    }
    Remove-Item -LiteralPath $PidFile -Force
}

function Show-Status {
    $entries = Read-PidFile
    if ($entries.Count -eq 0) { Write-Step 'No recorded demo processes.' }
    else {
        $data = Get-Content -LiteralPath $PidFile -Raw | ConvertFrom-Json
        Write-Step "Recorded mode: $($data.mode); started $($data.startedAt)"
        foreach ($entry in $entries) {
            $state = 'stopped'
            if ($null -ne (Get-RecordedProcess $entry)) { $state = 'running' }
            Write-Step ("{0,-13} pid {1,-7} {2}" -f $entry.name, $entry.pid, $state)
        }
        if ($data.apiPort) { $script:ApiPort = [int]$data.apiPort }
        if ($data.webPort) { $script:WebPort = [int]$data.webPort }
    }
    $health = Get-HttpStatus "http://127.0.0.1:$ApiPort/health"
    $web = Get-HttpStatus "http://127.0.0.1:$WebPort/"
    $healthText = "$health"; if ($health -eq 0) { $healthText = 'unreachable' }
    $webText = "$web"; if ($web -eq 0) { $webText = 'unreachable' }
    Write-Step "API  http://127.0.0.1:$ApiPort/health -> $healthText"
    Write-Step "Web  http://127.0.0.1:$WebPort/ -> $webText"
}

if ($Action -eq 'stop') { Stop-Recorded; exit 0 }
if ($Action -eq 'status') { Show-Status; exit 0 }

# ---------------------------------------------------------------- start
New-Item -ItemType Directory -Force -Path $DemoDir | Out-Null
foreach ($entry in (Read-PidFile)) {
    if ($null -ne (Get-RecordedProcess $entry)) {
        Stop-Demo "A recorded demo is already running ($($entry.name), pid $($entry.pid)). Run: .\scripts\demo.ps1 -Action stop"
    }
}

# Remember every documented setting so this terminal is restored afterwards;
# the started processes keep their own copy of the environment.
$settingNames = @()
foreach ($line in Get-Content -LiteralPath (Join-Path $Root '.env.example')) {
    if ($line -match '^([A-Z][A-Z0-9_]*)=') { $settingNames += $Matches[1] }
}
$savedEnv = @{}
foreach ($name in $settingNames) { $savedEnv[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }
function Restore-Env {
    foreach ($name in $savedEnv.Keys) { [Environment]::SetEnvironmentVariable($name, $savedEnv[$name], 'Process') }
}
function Get-Setting([string]$Name) { return [Environment]::GetEnvironmentVariable($Name, 'Process') }
function Set-Setting([string]$Name, [string]$Value) { [Environment]::SetEnvironmentVariable($Name, $Value, 'Process') }

$started = New-Object System.Collections.ArrayList
function Save-PidFile {
    $payload = [ordered]@{ mode = $Mode; startedAt = (Get-Date).ToString('o'); apiPort = $ApiPort; webPort = $WebPort; processes = @($started) }
    ($payload | ConvertTo-Json -Depth 4) | Set-Content -LiteralPath $PidFile -Encoding UTF8
}
function Start-DemoProcess([string]$Name, [string]$FilePath, [string[]]$Arguments, [string]$WorkingDirectory) {
    $out = Join-Path $DemoDir "$Name.out.log"
    $err = Join-Path $DemoDir "$Name.err.log"
    $p = Start-Process -FilePath $FilePath -ArgumentList (ConvertTo-ArgumentString $Arguments) -WorkingDirectory $WorkingDirectory `
        -RedirectStandardOutput $out -RedirectStandardError $err -WindowStyle Hidden -PassThru
    $entry = [ordered]@{ name = $Name; pid = $p.Id; started = $p.StartTime.ToUniversalTime().ToString('o'); log = $out; errorLog = $err }
    [void]$started.Add([pscustomobject]$entry)
    Save-PidFile
    Write-Step "$Name started (pid $($p.Id)); logs: $out"
    return $p
}
function Fail-Start([string]$Message) {
    if ($started.Count -gt 0) { Write-Step 'Stopping the processes started so far...'; Stop-Recorded }
    Restore-Env
    Stop-Demo $Message
}

try {
    # 1. Environment ------------------------------------------------------
    if (-not $NoEnvFile -and (Test-Path -LiteralPath $EnvFile)) {
        & (Join-Path $PSScriptRoot 'load-env.ps1') -Path $EnvFile
    } elseif (-not $NoEnvFile) {
        Write-Step 'No .env file found; using settings from this terminal.'
    }
    if (-not (Get-Setting 'AUTH_ORIGIN')) { Set-Setting 'AUTH_ORIGIN' "http://localhost:$WebPort" }
    if (-not (Get-Setting 'NEXT_PUBLIC_API_URL')) { Set-Setting 'NEXT_PUBLIC_API_URL' "http://localhost:$ApiPort" }
    if (-not (Get-Setting 'STORAGE_ROOT')) { Set-Setting 'STORAGE_ROOT' '.local/media' }

    if ($Mode -eq 'fixture') {
        # Force the safe, simulated configuration regardless of .env contents.
        Set-Setting 'APP_MODE' 'fixture'
        Set-Setting 'ALLOW_CHAIN_TRANSACTIONS' 'false'
        Set-Setting 'NEXT_PUBLIC_ENABLE_CHAIN_FUNDING' 'false'
        Set-Setting 'ALLOW_MODEL_TEXT' 'false'
        Set-Setting 'ALLOW_MODEL_MEDIA' 'false'
        Set-Setting 'ALLOW_LIVE_MODEL_SMOKE' 'false'
        Set-Setting 'GEMINI_FREE_TIER_CONFIRMED' 'false'
        # Fixture children do not need provider credentials or live chain
        # configuration. Remove them from the inherited environment even when
        # the local .env also contains a ready-to-use testnet profile.
        foreach ($name in @('GEMINI_API_KEY', 'GEMINI_MODEL', 'ARC_RPC_URL', 'ARC_USDC_ADDRESS',
                'ARC_ESCROW_ADDRESS', 'ARC_ALLOCATOR_ADDRESS', 'ARC_ALLOCATOR_PRIVATE_KEY')) {
            Set-Setting $name $null
        }
        foreach ($name in @('GEMINI_API_KEY', 'ARC_ALLOCATOR_PRIVATE_KEY', 'ARC_RPC_URL')) {
            if (Get-Setting $name) {
                Fail-Start "Fixture isolation failed to remove $name; no child process was started."
            }
        }
        # This launcher is for the complete simulated walkthrough. Override the
        # safe application default (uncertain) only in fixture mode; the caller's
        # original process setting is restored after the child processes start.
        Set-Setting 'FIXTURE_VERIFICATION_RESULT' 'pass'
        if (-not (Get-Setting 'DATABASE_URL')) {
            Write-Step 'DATABASE_URL not set; using the docker compose default (localhost:5432).'
            Set-Setting 'DATABASE_URL' 'postgresql+psycopg://framebounty:framebounty@localhost:5432/framebounty'
        }
    } else {
        $missing = @()
        $required = @('DATABASE_URL', 'AUTH_ORIGIN', 'NEXT_PUBLIC_API_URL', 'GEMINI_API_KEY', 'GEMINI_MODEL',
            'ARC_RPC_URL', 'ARC_ESCROW_ADDRESS', 'ARC_ALLOCATOR_ADDRESS', 'ARC_ALLOCATOR_PRIVATE_KEY')
        foreach ($name in $required) { if (-not (Get-Setting $name)) { $missing += $name } }
        $exact = [ordered]@{ APP_MODE = 'testnet'; ARC_CHAIN_ID = '5042002'; ALLOW_CHAIN_TRANSACTIONS = 'true'; NEXT_PUBLIC_ENABLE_CHAIN_FUNDING = 'true';
            ALLOW_MODEL_TEXT = 'true'; ALLOW_MODEL_MEDIA = 'true' }
        foreach ($name in $exact.Keys) { if ((Get-Setting $name) -ne $exact[$name]) { $missing += "$name=$($exact[$name])" } }
        if ($missing.Count -gt 0) {
            Restore-Env
            Write-Host '[demo] ERROR: testnet mode refused. Missing or incorrect settings (values not shown):' -ForegroundColor Red
            foreach ($m in $missing) { Write-Host "         - $m" -ForegroundColor Red }
            Write-Host '[demo] Put them in .env (see docs/DEMO.md, "Testnet mode") and retry.' -ForegroundColor Red
            exit 1
        }
        foreach ($publicName in @($settingNames | Where-Object { $_.StartsWith('NEXT_PUBLIC_') })) {
            $publicValue = Get-Setting $publicName
            if ($publicValue -and ($publicValue -eq (Get-Setting 'GEMINI_API_KEY') -or $publicValue -eq (Get-Setting 'ARC_ALLOCATOR_PRIVATE_KEY'))) {
                Fail-Start "$publicName contains a secret value. Secrets must never be in NEXT_PUBLIC_ variables."
            }
        }
        if ((Get-Setting 'GEMINI_MODEL') -ne 'gemini-3.5-flash-lite') {
            Write-Step 'Note: GEMINI_MODEL differs from the team choice (gemini-3.5-flash-lite).'
        }
    }

    # 2. Prerequisites ----------------------------------------------------
    if (-not (Test-Path -LiteralPath $Python)) { Fail-Start 'Python venv missing (.venv\Scripts\python.exe). See README "Local setup".' }
    if (-not (Test-Path -LiteralPath $NextBin)) { Fail-Start 'apps/web/node_modules missing. Run: cd apps/web; npm ci' }
    $node = Get-Command node -ErrorAction SilentlyContinue
    if ($null -eq $node) { Fail-Start 'Node.js was not found on PATH.' }
    if ($WebMode -eq 'start' -and -not (Test-Path -LiteralPath (Join-Path $WebDir '.next\BUILD_ID'))) {
        Fail-Start 'No production build found. Run: cd apps/web; npm run build (or use -WebMode dev).'
    }

    $fixtureChildCheck = ''
    if ($Mode -eq 'fixture') {
        $fixtureChildCheck = "import os; assert not any(os.getenv(n) for n in ('GEMINI_API_KEY','ARC_ALLOCATOR_PRIVATE_KEY','ARC_RPC_URL')), 'fixture child inherited live configuration'; "
    }
    $mediaCheck = $fixtureChildCheck + "import sys; from framebounty.media import media_executable as m; missing=[n for n in ('ffmpeg','ffprobe') if not m(n)]; print('missing: ' + ', '.join(missing) if missing else 'ok'); sys.exit(1 if missing else 0)"
    $code = Invoke-Checked 'check-ffmpeg' $Python @('-c', $mediaCheck)
    if ($code -ne 0) { Fail-Start 'FFmpeg/ffprobe not found. Run: .\.venv\Scripts\python.exe scripts/setup_media_tools.py (or set FFMPEG_BIN/FFPROBE_BIN).' }
    Write-Step 'FFmpeg and ffprobe found.'

    # Keep python -c on one line. Start-Process on Windows can truncate a quoted
    # multiline argument and return success after executing only the imports.
    $databaseCheck = "from sqlalchemy import text; from framebounty.db import engine; c=engine().connect(); c.execute(text('select 1')); c.close(); print('ok')"
    $code = Invoke-Checked 'check-db' $Python @('-c', $databaseCheck)
    if ($code -ne 0) { Fail-Start 'DATABASE_URL is not reachable. Start PostgreSQL (docker compose up -d postgres) or fix DATABASE_URL.' }
    Write-Step 'PostgreSQL reachable.'

    foreach ($port in @($ApiPort, $WebPort)) {
        if (Test-PortOpen $port) { Fail-Start "Port $port is already in use. Stop that server or pass -ApiPort/-WebPort (and match AUTH_ORIGIN/NEXT_PUBLIC_API_URL)." }
    }

    # 3. Migrations -------------------------------------------------------
    $code = Invoke-Checked 'migrate' $Python @('-m', 'alembic', '-c', 'services/api/alembic.ini', 'upgrade', 'head')
    if ($code -ne 0) { Fail-Start "Alembic migration failed; see $DemoDir\migrate.err.log" }
    Write-Step 'Migrations applied (alembic upgrade head).'

    # 4. Processes --------------------------------------------------------
    $api = Start-DemoProcess 'api' $Python @('-m', 'uvicorn', 'framebounty.main:app', '--host', $ListenHost, '--port', "$ApiPort") $Root
    [void](Start-DemoProcess 'media-worker' $Python @('-m', 'framebounty.worker') $Root)
    if ($Mode -eq 'testnet') {
        [void](Start-DemoProcess 'chain-worker' $Python @('-m', 'framebounty.chain_worker') $Root)
    }
    $web = Start-DemoProcess 'web' $node.Source @($NextBin, $WebMode, '--hostname', $ListenHost, '--port', "$WebPort") $WebDir

    # 5. Readiness --------------------------------------------------------
    $deadline = (Get-Date).AddSeconds(150)
    foreach ($target in @(@{ name = 'api'; url = "http://127.0.0.1:$ApiPort/health" }, @{ name = 'web'; url = "http://127.0.0.1:$WebPort/" })) {
        while ($true) {
            foreach ($entry in $started) {
                if ($null -eq (Get-RecordedProcess $entry)) { Fail-Start "$($entry.name) exited during startup; see $($entry.errorLog)" }
            }
            if ((Get-HttpStatus $target.url) -eq 200) { Write-Step "$($target.name) ready: $($target.url)"; break }
            if ((Get-Date) -gt $deadline) { Fail-Start "$($target.name) did not become ready; see logs in $DemoDir" }
            Start-Sleep -Milliseconds 1000
        }
    }
    Write-Step "Demo running in $Mode mode. Open $(Get-Setting 'AUTH_ORIGIN')"
    Write-Step 'Status: .\scripts\demo.ps1 -Action status    Stop: .\scripts\demo.ps1 -Action stop'
} finally {
    Restore-Env
}
