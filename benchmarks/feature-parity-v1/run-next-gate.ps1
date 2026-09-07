param([string]$AcceptedRun='2026-09-07T14-59-12Z')
$ErrorActionPreference='Stop'
$projectPath=Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$pythonPath=Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
if(-not(Test-Path -LiteralPath $pythonPath)){$pythonPath=(Get-Command python -ErrorAction Stop).Source}
Push-Location $projectPath
try {
    & $pythonPath (Join-Path $PSScriptRoot 'verify-accepted-run.py') --run $AcceptedRun
    if($LASTEXITCODE -ne 0){throw 'Accepted source/package verification failed; no commit created.'}
    $gitArgs=@('-c',"safe.directory=$($projectPath.Replace('\','/'))")
    $staged=@(& git @gitArgs diff --cached --name-only)
    if($LASTEXITCODE -ne 0){throw 'Cannot inspect Git index.'}
    if($staged.Count -gt 0){throw 'Existing staged changes detected; preserve them and inspect before freezing.'}
    $paths=@('src','config.example.yaml','README.md','benchmarks/STAR_CODE_CURRENT_STATUS.md',
        'benchmarks/feature-parity-v1','benchmarks/results/feature-parity-accepted.json',
        'benchmarks/results/feature-parity-session-environment.json')
    & git @gitArgs add -- @paths
    if($LASTEXITCODE -ne 0){throw 'Git staging failed; no model experiment started.'}
    & git @gitArgs diff --cached --quiet
    $diffExit=$LASTEXITCODE
    if($diffExit -gt 1){throw 'Git staged comparison failed.'}
    if($diffExit -eq 1){
        & git @gitArgs commit -m 'Add tested protocol compatibility, checkpoints and platform shell policies'
        if($LASTEXITCODE -ne 0){throw 'Git commit failed; retain staged changes for inspection.'}
    }
    $frozenCommit=(& git @gitArgs rev-parse HEAD)
    if($LASTEXITCODE -ne 0){throw 'Cannot read frozen commit.'}
    Write-Output "FROZEN_COMMIT=$frozenCommit"
    # Original benchmark-baseline-v1 is never moved or replaced.
    $freezePath=Join-Path $projectPath 'benchmarks/results/raw/feature-parity-v1'
    @{commit=$frozenCommit;accepted_run=$AcceptedRun;timestamp=[DateTime]::UtcNow.ToString('o')} |
        ConvertTo-Json | Set-Content -LiteralPath (Join-Path $freezePath 'feature-parity-freeze.json') -Encoding UTF8
    & $pythonPath (Join-Path $PSScriptRoot 'run-session-e2e.py')
    if($LASTEXITCODE -ne 0){throw 'Session integration gate did not pass; retain the RESULTS directory.'}
} finally {Pop-Location}
