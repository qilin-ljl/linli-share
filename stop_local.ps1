param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$statePath = Join-Path $projectRoot '.local-run\processes.json'
if (-not (Test-Path -LiteralPath $statePath)) {
    Write-Host 'No package-managed NeighLoop processes were recorded.'
    return
}

$state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
foreach ($role in @('apiServer', 'apiLauncher', 'web')) {
    $processId = [int]$state.("${role}Id")
    $expectedTicks = [int64]$state.("${role}StartTicks")
    $running = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if ($running -and [Math]::Abs(($running.StartTime.ToUniversalTime().Ticks - $expectedTicks) / 10000000) -lt 2) {
        Stop-Process -Id $processId -ErrorAction Stop
        Write-Host "Stopped process $processId"
    } elseif ($running) {
        Write-Warning "Skipped process $processId because its start time does not match the package record."
    }
}
Remove-Item -LiteralPath $statePath -Force
