param([switch]$Package)
$ErrorActionPreference='Stop'
$projectPath=Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$stamp=(Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH-mm-ssZ')
$outputPath=Join-Path $projectPath "benchmarks/results/raw/feature-parity-v1/$stamp"
New-Item -ItemType Directory -Path $outputPath -Force | Out-Null
$record=[ordered]@{benchmark='feature-parity-local';run_id=$stamp;status='FAILURE';model='NONE';network_model_calls=0;package_requested=[bool]$Package}
$oldCache=$env:GRADLE_USER_HOME
$env:GRADLE_USER_HOME=Join-Path $env:USERPROFILE '.gradle'
Push-Location $projectPath
try {
    $record.git_commit=(& git -c "safe.directory=$($projectPath.Replace('\','/'))" rev-parse HEAD)
    $record.os=[Environment]::OSVersion.VersionString
    $ErrorActionPreference='Continue'
    $record.java=(& java --version 2>&1 | Out-String).Trim()
    $javaExit=$LASTEXITCODE
    $ErrorActionPreference='Stop'
    if($javaExit -ne 0){throw 'Java runtime is unavailable.'}
    $manifest=[ordered]@{}
    foreach($file in Get-ChildItem -LiteralPath src -File -Recurse){
        $manifest[$file.FullName.Substring($projectPath.Length+1)]=(Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash
    }
    $manifest|ConvertTo-Json -Depth 3|Set-Content -LiteralPath (Join-Path $outputPath 'source-manifest.json') -Encoding UTF8
    $watch=[Diagnostics.Stopwatch]::StartNew()
    $testStartedUtc=[DateTime]::UtcNow
    $ErrorActionPreference='Continue'
    & .\gradlew.bat test --no-daemon --rerun-tasks *> (Join-Path $outputPath 'tests.log')
    $testExit=$LASTEXITCODE
    $ErrorActionPreference='Stop'
    $counts=[ordered]@{tests=0;failures=0;errors=0;skipped=0}
    $failedTests=@()
    $testFiles=@(Get-ChildItem -LiteralPath build/test-results/test -Filter 'TEST-*.xml' -ErrorAction SilentlyContinue | Where-Object {$_.LastWriteTimeUtc -ge $testStartedUtc})
    $xmlPath=Join-Path $outputPath 'test-results'
    if($testFiles.Count -gt 0){New-Item -ItemType Directory -Path $xmlPath -Force|Out-Null}
    foreach($file in $testFiles){
        Copy-Item -LiteralPath $file.FullName -Destination $xmlPath
        [xml]$doc=Get-Content -LiteralPath $file.FullName
        foreach($key in @('tests','failures','errors','skipped')){$counts[$key]+=[int]$doc.testsuite.$key}
        foreach($case in @($doc.testsuite.testcase)){
            if($case.failure -or $case.error){
                $detail=if($case.failure){$case.failure.message}else{$case.error.message}
                $failedTests+=@([ordered]@{class=[string]$case.classname;name=[string]$case.name;message=[string]$detail})
            }
        }
    }
    $record.tests=$counts
    $record.failed_tests=$failedTests
    $record.test_results_available=($testFiles.Count -gt 0)
    if($testExit -ne 0){throw 'Gradle test failed; retain tests.log and test-results XML.'}
    if(Select-String -LiteralPath (Join-Path $outputPath 'tests.log') -Pattern 'AccessDeniedException|An exception has occurred in the compiler|java\.lang\.[A-Za-z]+Error' -Quiet){throw 'Compiler/environment error despite exit code; do not accept this run.'}
    if($counts.tests -lt 233 -or $counts.failures -or $counts.errors -or $counts.skipped){throw 'Full passing suite is required.'}
    foreach($entry in $manifest.GetEnumerator()){
        if((Get-FileHash -LiteralPath $entry.Key -Algorithm SHA256).Hash -ne $entry.Value){throw 'Source changed during validation.'}
    }
    if($Package){
        $jar=Join-Path $projectPath 'build/libs/star-code.jar'
        if(Test-Path -LiteralPath $jar){
            $oldHash=(Get-FileHash -LiteralPath $jar -Algorithm SHA256).Hash
            $archive=Join-Path $projectPath "benchmarks/.work/dependency-jars/$oldHash.jar"
            New-Item -ItemType Directory -Path (Split-Path $archive -Parent) -Force|Out-Null
            if(-not(Test-Path -LiteralPath $archive)){Copy-Item -LiteralPath $jar -Destination $archive}
        }
        $ErrorActionPreference='Continue'
        & .\gradlew.bat shadowJar --no-daemon *> (Join-Path $outputPath 'package.log')
        $packageExit=$LASTEXITCODE
        $ErrorActionPreference='Stop'
        if($packageExit -ne 0){throw 'Packaging failed.'}
        if(Select-String -LiteralPath (Join-Path $outputPath 'package.log') -Pattern 'AccessDeniedException|An exception has occurred in the compiler' -Quiet){throw 'Packaging environment error.'}
        $record.jar_sha256=(Get-FileHash -LiteralPath $jar -Algorithm SHA256).Hash
    }
    $record.status='PASS'
} catch {$record.exception=$_.Exception.Message}
finally {
    if($watch){$record.wall_clock_seconds=$watch.Elapsed.TotalSeconds}
    $record|ConvertTo-Json -Depth 6|Set-Content -LiteralPath (Join-Path $outputPath 'validation.json') -Encoding UTF8
    Pop-Location;$env:GRADLE_USER_HOME=$oldCache
}
Write-Output "STATUS=$($record.status)"
Write-Output "RESULTS=$outputPath"
foreach($failure in @($record.failed_tests)){
    if($failure){Write-Output "FAILED_TEST=$($failure.class).$($failure.name)";Write-Output "FAILURE_DETAIL=$($failure.message)"}
}
if($record.status -ne 'PASS'){Write-Output $record.exception;exit 1}
