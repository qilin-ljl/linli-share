param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Join-Path $projectRoot 'backend'
$frontendDir = Join-Path $projectRoot 'frontend'
$pythonExe = Join-Path $backendDir '.venv\Scripts\python.exe'
$envPath = Join-Path $backendDir '.env'
$frontendEnvPath = Join-Path $frontendDir '.env.local'

function Invoke-Checked([string]$Executable, [string[]]$CommandArguments) {
    & $Executable @CommandArguments
    if ($LASTEXITCODE -ne 0) { throw "$Executable exited with code $LASTEXITCODE" }
}

try { Invoke-Checked 'py' @('-3.12', '--version') }
catch { throw 'Python 3.12 is required. Install it from python.org, then rerun setup_local.ps1.' }

try { $nodeVersion = [Version]((& node --version).TrimStart('v')) }
catch { throw 'Node.js 20.19+ or 22.12+ is required.' }
if (-not (($nodeVersion.Major -eq 20 -and $nodeVersion -ge [Version]'20.19.0') -or $nodeVersion -ge [Version]'22.12.0')) {
    throw "Node.js $nodeVersion is too old. Use 20.19+ or 22.12+."
}
$npmCommand = Get-Command npm.cmd -ErrorAction Stop

if (-not (Test-Path -LiteralPath $pythonExe)) {
    Write-Host 'Creating Python virtual environment...'
    Invoke-Checked 'py' @('-3.12', '-m', 'venv', (Join-Path $backendDir '.venv'))
}

Write-Host 'Installing Python dependencies...'
Invoke-Checked $pythonExe @('-m', 'pip', 'install', '-r', (Join-Path $backendDir 'requirements.txt'))

if (-not (Test-Path -LiteralPath $envPath)) {
    $template = [System.IO.File]::ReadAllText((Join-Path $backendDir '.env.example'))
    $randomBytes = New-Object byte[] 48
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generator.GetBytes($randomBytes) } finally { $generator.Dispose() }
    $jwtSecret = [Convert]::ToBase64String($randomBytes).Replace('+', '-').Replace('/', '_').TrimEnd('=')
    $template = [regex]::Replace($template, '(?m)^JWT_SECRET_KEY=.*$', "JWT_SECRET_KEY=$jwtSecret")
    $template = [regex]::Replace($template, '(?m)^NEIGHLOOP_DEMO_MODE=.*$', 'NEIGHLOOP_DEMO_MODE=true')
    [System.IO.File]::WriteAllText($envPath, $template, (New-Object System.Text.UTF8Encoding($false)))
    Write-Host 'Created backend/.env with a local JWT secret. Add your own DEEPSEEK_API_KEY there for AI features.'
}

if (-not (Test-Path -LiteralPath $frontendEnvPath)) {
    [System.IO.File]::WriteAllText($frontendEnvPath, "VITE_DEMO_MODE=true`n", (New-Object System.Text.UTF8Encoding($false)))
}

Push-Location $frontendDir
try {
    Write-Host 'Installing frontend dependencies...'
    Invoke-Checked $npmCommand.Source @('ci', '--no-audit', '--no-fund')
    Write-Host 'Checking frontend build...'
    Invoke-Checked $npmCommand.Source @('run', 'build')
} finally { Pop-Location }

Push-Location $backendDir
try {
    Write-Host 'Initializing demo database...'
    Invoke-Checked $pythonExe @('seed.py')
} finally { Pop-Location }

Write-Host ''
Write-Host 'Setup complete. Run .\start_local.ps1, then open http://127.0.0.1:5173/'
Write-Host 'DeepSeek features need DEEPSEEK_API_KEY in backend/.env. Never put it in frontend/.env.local.'
