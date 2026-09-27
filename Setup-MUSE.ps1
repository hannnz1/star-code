param([string]$Python = 'python', [string]$Npm = 'npm.cmd')
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    if (!(Test-Path '.venv\Scripts\python.exe')) { & $Python -m venv .venv; if ($LASTEXITCODE -ne 0) { throw 'Python 3.12+ is required.' } }
    $localPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    & $localPython -m pip install uv
    if ($LASTEXITCODE -ne 0) { throw 'Could not install uv.' }
    & '.\.venv\Scripts\uv.exe' sync --locked --inexact --python $localPython
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
    $env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $PSScriptRoot 'work\browsers'
    & $localPython -m playwright install chromium
    if ($LASTEXITCODE -ne 0) { throw 'Chromium installation failed.' }
    Push-Location frontend
    try {
        & $Npm ci --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
        & $Npm run build
        if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
    } finally { Pop-Location }
    Write-Output 'Ready. Run Start-MUSE.ps1 -Config <your StarCode config.yaml>.'
} finally { Pop-Location }
