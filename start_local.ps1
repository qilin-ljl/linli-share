param(
    [ValidateRange(1024,65535)][int]$ApiPort = 8000,
    [ValidateRange(1024,65535)][int]$WebPort = 5173
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Join-Path $projectRoot 'backend'
$frontendDir = Join-Path $projectRoot 'frontend'
$pythonExe = Join-Path $backendDir '.venv\Scripts\python.exe'
$viteEntry = Join-Path $frontendDir 'node_modules\vite\bin\vite.js'
$runDir = Join-Path $projectRoot '.local-run'
$statePath = Join-Path $runDir 'processes.json'

if (-not (Test-Path -LiteralPath $pythonExe) -or -not (Test-Path -LiteralPath $viteEntry)) {
    throw 'Dependencies are missing. Run .\setup_local.ps1 first.'
}
if ($ApiPort -eq $WebPort) { throw 'API and frontend ports must be different.' }
if (Get-NetTCPConnection -State Listen -LocalPort $ApiPort,$WebPort -ErrorAction SilentlyContinue) {
    throw "Port $ApiPort or $WebPort is already in use. Stop the existing service or choose different ports."
}

New-Item -ItemType Directory -Path $runDir -Force | Out-Null
$nodeExe = (Get-Command node.exe -ErrorAction Stop).Source
$previousCors = [Environment]::GetEnvironmentVariable('CORS_ORIGINS', 'Process')
$previousApiUrl = [Environment]::GetEnvironmentVariable('VITE_API_URL', 'Process')
$env:CORS_ORIGINS = "http://127.0.0.1:$WebPort,http://localhost:$WebPort"
$env:VITE_API_URL = "http://127.0.0.1:$ApiPort"
try {
    $apiProcess = Start-Process -FilePath $pythonExe -ArgumentList @('-m','uvicorn','main:app','--host','127.0.0.1','--port',"$ApiPort") -WorkingDirectory $backendDir -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runDir 'api.out.log') -RedirectStandardError (Join-Path $runDir 'api.err.log') -PassThru
    $quotedViteEntry = '"' + $viteEntry + '"'
    $webProcess = Start-Process -FilePath $nodeExe -ArgumentList @($quotedViteEntry,'--host','127.0.0.1','--port',"$WebPort",'--strictPort') -WorkingDirectory $frontendDir -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runDir 'web.out.log') -RedirectStandardError (Join-Path $runDir 'web.err.log') -PassThru
} catch {
    if ($apiProcess) { Stop-Process -Id $apiProcess.Id -ErrorAction SilentlyContinue }
    throw
} finally {
    [Environment]::SetEnvironmentVariable('CORS_ORIGINS', $previousCors, 'Process')
    [Environment]::SetEnvironmentVariable('VITE_API_URL', $previousApiUrl, 'Process')
}

function Wait-ForUrl([string]$Url) {
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -eq 200) { return $true }
        } catch { Start-Sleep -Milliseconds 800 }
    }
    return $false
}

if (-not (Wait-ForUrl "http://127.0.0.1:$ApiPort/api/bootstrap") -or -not (Wait-ForUrl "http://127.0.0.1:$WebPort/")) {
    $apiListener = Get-NetTCPConnection -State Listen -LocalPort $ApiPort -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($apiListener) { Stop-Process -Id $apiListener.OwningProcess -ErrorAction SilentlyContinue }
    Stop-Process -Id $apiProcess.Id,$webProcess.Id -ErrorAction SilentlyContinue
    throw "Startup failed. Check logs in $runDir"
}

$apiListener = Get-NetTCPConnection -State Listen -LocalPort $ApiPort -ErrorAction Stop | Select-Object -First 1
$apiServerProcess = Get-Process -Id $apiListener.OwningProcess -ErrorAction Stop
@{
    apiLauncherId = $apiProcess.Id
    apiLauncherStartTicks = [string]$apiProcess.StartTime.ToUniversalTime().Ticks
    apiServerId = $apiServerProcess.Id
    apiServerStartTicks = [string]$apiServerProcess.StartTime.ToUniversalTime().Ticks
    webId = $webProcess.Id
    webStartTicks = [string]$webProcess.StartTime.ToUniversalTime().Ticks
    apiPort = $ApiPort
    webPort = $WebPort
} | ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding UTF8

Write-Host "NeighLoop is running at http://127.0.0.1:$WebPort/"
Write-Host "API docs: http://127.0.0.1:$ApiPort/docs"
Write-Host 'Run .\stop_local.ps1 to stop these background processes.'
