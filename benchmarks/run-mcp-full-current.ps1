param()
$ErrorActionPreference = 'Stop'
$benchPath = $PSScriptRoot
$projectPath = Split-Path $benchPath -Parent
Push-Location $projectPath
try {
    # Run in a child shell because the frozen compile script terminates with exit.
    $compileLog = Join-Path $benchPath 'results/mcp-full-current-compile.log'
    $compileShell = (Get-Process -Id $PID).Path
    & $compileShell -NoProfile -File (Join-Path $benchPath 'run.ps1') compile *> $compileLog
    if ($LASTEXITCODE -ne 0) { throw "Compilation failed; see $compileLog" }
    $manifest = Join-Path $benchPath '.work/build-manifest.json'
    $buildHash = (Get-FileHash -LiteralPath $manifest -Algorithm SHA256).Hash.ToLowerInvariant()
    $classes = Join-Path $benchPath ('.work/classes-' + $buildHash.Substring(0,12))
    $dependencyJar = Join-Path $projectPath 'build/libs/star-code.jar'
    & java "-Dbench.root=$benchPath" "-Dbench.harness.sha=$buildHash" -cp "$classes;$dependencyJar" bench.McpFullCurrent
    if ($LASTEXITCODE -ne 0) { throw 'Full loading baseline failed; preserve raw output and inspect the error.' }
} finally { Pop-Location }
