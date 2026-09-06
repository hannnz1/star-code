param([switch]$RunE2E)
$ErrorActionPreference='Stop'
$benchDir=$PSScriptRoot
$projectDir=Split-Path $benchDir -Parent
$previousCache=$env:GRADLE_USER_HOME
$env:GRADLE_USER_HOME=Join-Path $env:USERPROFILE '.gradle'
$runDir=Join-Path $benchDir ('results\raw\agent-budget-local\'+(Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH-mm-ssZ'))
New-Item -ItemType Directory -Path $runDir -Force | Out-Null
Push-Location $projectDir
try {
    # Use PowerShell7 for javac output; Windows PowerShell5 can promote benign javac notes to errors.
    $pwshCommand=Get-Command pwsh -ErrorAction SilentlyContinue
    if($pwshCommand){$pwshPath=$pwshCommand.Source}
    else {$pwshPath=Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\native\powershell\pwsh.exe'}
    if(-not(Test-Path -LiteralPath $pwshPath)){throw 'PowerShell7 is required to compile the benchmark harness.'}
    & $pwshPath -NoProfile -Command '$env:GRADLE_USER_HOME=Join-Path $env:USERPROFILE ''.gradle''; & .\gradlew.bat test --no-daemon --rerun-tasks --console=plain; exit $LASTEXITCODE' *> (Join-Path $runDir 'tests.log')
    if($LASTEXITCODE -ne 0){throw "Tests failed. See $runDir\tests.log"}
    $counts=[ordered]@{suites=0;tests=0;failures=0;errors=0;skipped=0}
    foreach($file in Get-ChildItem -LiteralPath 'build\test-results\test' -Filter 'TEST-*.xml'){
        [xml]$xml=Get-Content -LiteralPath $file.FullName
        $counts.suites++
        foreach($field in @('tests','failures','errors','skipped')){$counts[$field]+=[int]$xml.testsuite.$field}
    }
    if($counts.tests -eq 0 -or $counts.failures -gt 0 -or $counts.errors -gt 0){throw 'No valid passing full suite.'}
    $counts|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $runDir 'tests.json') -Encoding UTF8
    & $pwshPath -NoProfile -File (Join-Path $benchDir 'run.ps1') compile *> (Join-Path $runDir 'compile.log')
    if($LASTEXITCODE -ne 0){throw "Harness compilation failed. See $runDir\compile.log"}
    $jar=Join-Path $projectDir 'build\libs\star-code.jar'
    $archiveDir=Join-Path $benchDir '.work\dependency-jars'
    New-Item -ItemType Directory -Path $archiveDir -Force|Out-Null
    $oldHash=(Get-FileHash -LiteralPath $jar -Algorithm SHA256).Hash.ToLowerInvariant()
    $archived=Join-Path $archiveDir ($oldHash+'.jar')
    if(-not(Test-Path -LiteralPath $archived)){Copy-Item -LiteralPath $jar -Destination $archived}
    # Preserve the exact compiled harness dependency; packaging changes the distribution JAR.
    if($RunE2E){
        $manifestHash=(Get-FileHash -LiteralPath (Join-Path $benchDir '.work\build-manifest.json') -Algorithm SHA256).Hash.ToLowerInvariant()
        $classes=Join-Path $benchDir ('.work\classes-'+$manifestHash.Substring(0,12))
        & java "-Dbench.root=$benchDir" "-Dbench.harness.sha=$manifestHash" -cp "$classes;$jar" bench.GateSuiteCurrent *> (Join-Path $runDir 'e2e.log')
        if($LASTEXITCODE -ne 0){throw "E2E invocation failed. See $runDir\e2e.log"}
        Get-Content -LiteralPath (Join-Path $runDir 'e2e.log') -Tail 3
    }
    & $pwshPath -NoProfile -Command '$env:GRADLE_USER_HOME=Join-Path $env:USERPROFILE ''.gradle''; & .\gradlew.bat shadowJar --console=plain; exit $LASTEXITCODE' *> (Join-Path $runDir 'package.log')
    if($LASTEXITCODE -ne 0){throw "Packaging failed. See $runDir\package.log"}
    $commit=& git -c "safe.directory=$($projectDir.Replace('\','/'))" rev-parse HEAD
    [ordered]@{timestamp=(Get-Date).ToUniversalTime().ToString('o');git_commit=$commit;tests=$counts;
        e2e_requested=[bool]$RunE2E;jar_sha256=(Get-FileHash -LiteralPath $jar -Algorithm SHA256).Hash;
        warning='E2E PASS is determined by the preserved strict gate, not this script exit code.'}|
        ConvertTo-Json -Depth 4|Set-Content -LiteralPath (Join-Path $runDir 'validation.json') -Encoding UTF8
    Write-Output "VALIDATION_RESULTS=$runDir"
    Write-Output "FULL_TESTS_PASS=$($counts.tests)"
    Write-Output "JAR=$jar"
} finally {Pop-Location; $env:GRADLE_USER_HOME=$previousCache}
