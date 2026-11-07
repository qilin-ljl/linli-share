$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonExe = Join-Path $projectRoot 'backend\.venv\Scripts\python.exe'
$viteEntry = Join-Path $projectRoot 'frontend\node_modules\vite\bin\vite.js'
$backendEnv = Join-Path $projectRoot 'backend\.env'
$frontendEnv = Join-Path $projectRoot 'frontend\.env.local'
$database = Join-Path $projectRoot 'backend\neighloop.db'
$statePath = Join-Path $projectRoot '.local-run\processes.json'

function Test-RecordedProcess($State, [string]$Role) {
    $processId = [int]$State.("${Role}Id")
    $expectedTicks = [int64]$State.("${Role}StartTicks")
    $running = Get-Process -Id $processId -ErrorAction SilentlyContinue
    return $running -and [Math]::Abs(($running.StartTime.ToUniversalTime().Ticks - $expectedTicks) / 10000000) -lt 2
}

function Test-Ready([string]$Url) {
    try {
        return (Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200
    } catch {
        return $false
    }
}

function Test-ExistingApp {
    try {
        $api = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/bootstrap' -TimeoutSec 2
        $web = Invoke-WebRequest -Uri 'http://127.0.0.1:5173/' -UseBasicParsing -TimeoutSec 2
        return $null -ne $api.categories -and $null -ne $api.communities -and
               $web.StatusCode -eq 200 -and $web.Content -match '<title>NeighLoop'
    } catch {
        return $false
    }
}

try {
    $installed = (Test-Path -LiteralPath $pythonExe) -and
                 (Test-Path -LiteralPath $viteEntry) -and
                 (Test-Path -LiteralPath $backendEnv) -and
                 (Test-Path -LiteralPath $frontendEnv) -and
                 (Test-Path -LiteralPath $database)
    if (-not $installed) {
        Write-Host 'First run: setting up NeighLoop. This needs Python 3.12, Node.js and an internet connection.'
        & (Join-Path $projectRoot 'setup_local.ps1')
        if (-not $?) { throw 'Local setup failed.' }
    }

    & $pythonExe (Join-Path $projectRoot 'backend\refresh_demo_slots.py')
    if ($LASTEXITCODE -ne 0) { throw 'Refreshing local demo handover times failed.' }

    $alreadyRunning = $false
    if (Test-Path -LiteralPath $statePath) {
        try {
            $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
            $webPort = [int]$state.webPort
            $apiPort = [int]$state.apiPort
            $alreadyRunning = (Test-RecordedProcess $state 'apiServer') -and
                              (Test-RecordedProcess $state 'web') -and
                              (Test-Ready "http://127.0.0.1:$apiPort/api/bootstrap") -and
                              (Test-Ready "http://127.0.0.1:$webPort/")
        } catch {
            $alreadyRunning = $false
        }
    }

    if (-not $alreadyRunning -and (Test-ExistingApp)) {
        $alreadyRunning = $true
        $webPort = 5173
    }

    if (-not $alreadyRunning) {
        Write-Host 'Starting NeighLoop...'
        & (Join-Path $projectRoot 'start_local.ps1')
        if (-not $?) { throw 'Local startup failed.' }
        $webPort = 5173
    } else {
        Write-Host "NeighLoop is already running on port $webPort."
    }

    $url = "http://127.0.0.1:$webPort/"
    Start-Process $url
    Write-Host "Opened $url"
} catch {
    Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
