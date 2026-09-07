param([ValidateRange(1,3)][int]$FirstRepeat=1, [ValidateRange(1,3)][int]$LastRepeat=3)
$ErrorActionPreference='Stop'
if($FirstRepeat -gt $LastRepeat){throw 'FirstRepeat must not exceed LastRepeat.'}
if($PSVersionTable.PSVersion.Major -lt 7){throw 'Run with PowerShell 7 (pwsh).'}
$benchPath=Split-Path $PSScriptRoot -Parent
$projectPath=Split-Path $benchPath -Parent
$stamp=(Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH-mm-ssZ')
Push-Location $projectPath
try {
    $shellPath=(Get-Process -Id $PID).Path
    & $shellPath -NoProfile -File (Join-Path $benchPath 'run.ps1') compile *> (Join-Path $benchPath "results/long-context-compile-$stamp.log")
    if($LASTEXITCODE -ne 0){throw 'Compilation failed.'}
    $hash=(Get-FileHash (Join-Path $benchPath '.work/build-manifest.json') -Algorithm SHA256).Hash.ToLowerInvariant()
    $classes=Join-Path $benchPath ('.work/classes-'+$hash.Substring(0,12))
    $jar=Join-Path $projectPath 'build/libs/star-code.jar'
    & java "-Dbench.root=$benchPath" "-Dbench.harness.sha=$hash" -cp "$classes;$jar" bench.LongContextBench $FirstRepeat $LastRepeat *>&1 |
        Tee-Object -FilePath (Join-Path $benchPath "results/long-context-console-$stamp.log")
    if($LASTEXITCODE -ne 0){throw 'Benchmark invocation failed; preserve all raw output.'}
    Write-Output 'Process finished. Workflow and retrieval results must be read from raw data, not the exit code.'
    Get-Content (Join-Path $benchPath 'results/long-context-v1-latest.txt')
} finally {Pop-Location}
