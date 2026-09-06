param(
    [ValidateSet('Report','Verify','Run')][string]$Mode='Report',
    [string]$Python='python'
)
$ErrorActionPreference='Stop'
$benchDir=$PSScriptRoot
$projectDir=Split-Path $benchDir -Parent
if($Mode -ne 'Report') {
    Push-Location $projectDir
    try {
        & .\gradlew.bat test --tests 'com.starcode.context.*' --console=plain
        if($LASTEXITCODE -ne 0){throw 'Context tests failed; no paid benchmark launched.'}
    } finally { Pop-Location }
    # A separate PowerShell process prevents run.ps1's exit from exiting this runner.
    & powershell -NoProfile -File (Join-Path $benchDir 'run.ps1') -Benchmark compile
    if($LASTEXITCODE -ne 0){throw 'Compilation failed; no paid benchmark launched.'}
    if($Mode -eq 'Verify'){Write-Output 'VERIFY_PASS';return}
    $manifest=Join-Path $benchDir '.work\build-manifest.json'
    $manifestHash=(Get-FileHash -LiteralPath $manifest -Algorithm SHA256).Hash.ToLowerInvariant()
    $classes=Join-Path $benchDir ('.work\classes-'+$manifestHash.Substring(0,12))
    $jar=Join-Path $projectDir 'build\libs\star-code.jar'
    # Run explicitly requests a new ten-run paid batch; raw data is never overwritten.
    & java "-Dbench.root=$benchDir" "-Dbench.harness.sha=$manifestHash" '-Dbench.context.first=1' '-Dbench.context.last=10' -cp "$classes;$jar" bench.ReliabilityMain
    if($LASTEXITCODE -ne 0){throw 'Benchmark failed; inspect saved raw data before retrying.'}
}
& $Python (Join-Path $benchDir 'reliability-v1\evaluate.py')
if($LASTEXITCODE -ne 0){throw 'Offline evaluation failed.'}
& $Python (Join-Path $benchDir 'reliability-v1\write_report.py')
if($LASTEXITCODE -ne 0){throw 'Report generation failed.'}
