param(
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 5173
)

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendPath = Join-Path $projectRoot "backend"
$frontendPath = Join-Path $projectRoot "frontend"
$backendPython = Join-Path $backendPath ".venv\Scripts\python.exe"

if (-not (Test-Path (Join-Path $frontendPath "node_modules"))) {
    Write-Error "Frontend dependencies are missing. Run: cd '$frontendPath'; npm install"
    exit 1
}
if (-not (Test-Path $backendPython)) {
    Write-Error "Backend virtual environment is missing. Run: cd '$backendPath'; py -3 -m venv .venv; .\.venv\Scripts\python.exe -m pip install -r requirements.txt"
    exit 1
}

Write-Host "Starting Boardroom API at http://localhost:$BackendPort"
Start-Process $backendPython -ArgumentList "-m", "uvicorn", "app.main:app", "--reload", "--port", "$BackendPort" -WorkingDirectory $backendPath -WindowStyle Hidden

Write-Host "Starting Boardroom UI at http://localhost:$FrontendPort"
Start-Process cmd.exe -ArgumentList "/c", "npm run dev -- --host 127.0.0.1 --port $FrontendPort" -WorkingDirectory $frontendPath -WindowStyle Hidden

Write-Host "Boardroom is starting. Open http://localhost:$FrontendPort and sign in with admin@boardroom.local / admin123."
