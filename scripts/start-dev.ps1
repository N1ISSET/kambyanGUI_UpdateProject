$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$frontendRoot = Join-Path $projectRoot 'frontend'
$python = if ($env:KAMBYAN_PYTHON) {
    $env:KAMBYAN_PYTHON
} elseif (Test-Path 'E:\FYP_Env\myenv\python.exe') {
    # Conda environments keep python.exe at the environment root.
    'E:\FYP_Env\myenv\python.exe'
} else {
    # Standard venv environments keep it in Scripts.
    'E:\FYP_Env\myenv\Scripts\python.exe'
}

if (-not (Test-Path $python)) {
    throw "Python environment not found at '$python'. Set KAMBYAN_PYTHON to your virtual environment's python.exe path."
}

# Use a dedicated port so an old Django process on port 8000 cannot serve this app.
$backendPort = 8001
$backendAddress = "127.0.0.1:$backendPort"
$backendRunning = Test-NetConnection -ComputerName '127.0.0.1' -Port $backendPort -InformationLevel Quiet -WarningAction SilentlyContinue

if (-not $backendRunning) {
    $backendCommand = "Set-Location '$projectRoot'; & '$python' manage.py runserver $backendAddress"
    Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoExit', '-NoProfile', '-Command', $backendCommand)
    Write-Host "Started Django for this workspace at http://$backendAddress"
} else {
    Write-Host "A process is already listening on port $backendPort; reusing it."
}

Set-Location $frontendRoot
& npm.cmd run start:frontend
