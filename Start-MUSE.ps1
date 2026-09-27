param(
    [string]$Config = 'C:\Users\Administrator\Desktop\project\star code\config.yaml',
    [int]$Port = 8765,
    [switch]$NoBrowser,
    [switch]$Quiet
)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$data = Join-Path $projectRoot '.muse'
if (!(Test-Path -LiteralPath $python)) { throw 'Run Setup-MUSE.ps1 first.' }
if (!(Test-Path -LiteralPath (Join-Path $projectRoot 'frontend\dist\index.html'))) { throw 'Frontend is missing. Run Setup-MUSE.ps1.' }
if (!(Test-Path -LiteralPath $Config)) { throw 'Specify an existing StarCode config.yaml using -Config.' }
New-Item -ItemType Directory -Force -Path $data | Out-Null
$processFile = Join-Path $data 'processes.json'
if (Test-Path -LiteralPath $processFile) {
    $saved = Get-Content -LiteralPath $processFile -Raw | ConvertFrom-Json
    foreach ($entry in $saved) {
        $running = Get-Process -Id $entry.pid -ErrorAction SilentlyContinue
        if ($running -and $running.StartTime.ToUniversalTime() -eq ([datetime]$entry.started).ToUniversalTime()) {
            throw 'MUSE is already running. Use Stop-MUSE.ps1 before starting another instance.'
        }
    }
}
$listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback,$Port)
try { $listener.Start() } finally { $listener.Stop() }
& $python -m muse doctor --config $Config --data-dir $data | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Configuration validation failed.' }
$records = @()
try {
    foreach ($role in @('api','worker')) {
        $arguments = @('-m','muse',$role,'--config',('"'+$Config+'"'),'--data-dir',('"'+$data+'"'),'--port',$Port)
        $process = Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $data "$role.out.log") -RedirectStandardError (Join-Path $data "$role.err.log")
        $records += @{pid=$process.Id;started=$process.StartTime.ToUniversalTime().ToString('o');role=$role}
    }
    $records | ConvertTo-Json | Set-Content -LiteralPath $processFile -Encoding utf8
    $ready = $false
    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        try { $health = Invoke-RestMethod "http://127.0.0.1:$Port/health" -TimeoutSec 1; if ($health.application -eq 'MUSE') { $ready=$true; break } } catch { Start-Sleep -Milliseconds 250 }
    }
    if (!$ready) { throw 'API did not become ready; inspect .muse/api.err.log.' }
    foreach ($entry in $records) { if (!(Get-Process -Id $entry.pid -ErrorAction SilentlyContinue)) { throw "$($entry.role) stopped; inspect its error log." } }
    Write-Output "MUSE is ready: http://127.0.0.1:$Port"
    if (!$Quiet) {
        Write-Output 'Local workspace access token (not your model API key):'
        Get-Content -LiteralPath (Join-Path $data 'access-token')
    }
    if (!$NoBrowser) { Start-Process "http://127.0.0.1:$Port" }
} catch {
    foreach ($entry in $records) {
        $running = Get-Process -Id $entry.pid -ErrorAction SilentlyContinue
        if ($running -and $running.StartTime.ToUniversalTime() -eq ([datetime]$entry.started).ToUniversalTime()) { & "$env:SystemRoot\System32\taskkill.exe" /PID $entry.pid /T /F | Out-Null }
    }
    throw
}
