$ErrorActionPreference = 'Stop'
$processFile = Join-Path $PSScriptRoot '.muse\processes.json'
if (!(Test-Path -LiteralPath $processFile)) { Write-Output 'No managed MUSE processes.'; exit 0 }
$saved = Get-Content -LiteralPath $processFile -Raw | ConvertFrom-Json
foreach ($entry in $saved) {
    $running = Get-Process -Id $entry.pid -ErrorAction SilentlyContinue
    if ($running -and $running.StartTime.ToUniversalTime() -eq ([datetime]$entry.started).ToUniversalTime()) {
        & "$env:SystemRoot\System32\taskkill.exe" /PID $entry.pid /T /F | Out-Null
        if ($LASTEXITCODE -ne 0) {
            $remaining = Get-Process -Id $entry.pid -ErrorAction SilentlyContinue
            if ($remaining -and $remaining.StartTime.ToUniversalTime() -eq ([datetime]$entry.started).ToUniversalTime()) {
                throw "Could not stop MUSE $($entry.role); the process may still be running."
            }
        }
        Write-Output "Stopped MUSE $($entry.role)."
    }
}
Write-Output 'Task records remain on disk. Active tasks recover after their lease expires; uncertain writes require reconciliation.'
