param([ValidateSet('compile','mcp-loading','context-retention','multi-agent')][string]$Benchmark='compile',[string]$Python)
$ErrorActionPreference='Stop'
$benchDir=$PSScriptRoot
$projectDir=Split-Path $benchDir -Parent
$jar=Join-Path $projectDir 'build\libs\star-code.jar'
if(-not (Test-Path -LiteralPath $jar)){throw 'Build dependency jar absent. Run the normal project build first.'}
$sources=@(Get-ChildItem -LiteralPath (Join-Path $projectDir 'src\main\java') -Filter '*.java' -Recurse)+@(Get-ChildItem -LiteralPath (Join-Path $benchDir 'src') -Filter '*.java' -Recurse)
$manifest=[ordered]@{baseline='014808a0b0942f25bc4f1c3f415fa63262f98176';dependency_jar_sha256=(Get-FileHash -LiteralPath $jar -Algorithm SHA256).Hash;sources=[ordered]@{}}
foreach($f in $sources){$manifest.sources[$f.FullName.Substring($projectDir.Length+1)]=(Get-FileHash -LiteralPath $f.FullName -Algorithm SHA256).Hash}
New-Item -ItemType Directory -Path (Join-Path $benchDir '.work') -Force | Out-Null
$manifestFile=Join-Path $benchDir '.work\build-manifest.json';[IO.File]::WriteAllText($manifestFile,($manifest|ConvertTo-Json -Depth 5),[Text.UTF8Encoding]::new($false))
$manifestHash=(Get-FileHash -LiteralPath $manifestFile -Algorithm SHA256).Hash.ToLowerInvariant()
$classes=Join-Path $benchDir ('.work\classes-'+$manifestHash.Substring(0,12));New-Item -ItemType Directory -Path $classes -Force|Out-Null
$argumentsFile=Join-Path $benchDir '.work\javac.args'
$arguments=@('--release','21','-encoding','UTF-8','-cp',('"'+$jar.Replace('\','/')+'"'),'-d',('"'+$classes.Replace('\','/')+'"'))+$($sources|ForEach-Object {'"'+$_.FullName.Replace('\','/')+'"'})
[IO.File]::WriteAllLines($argumentsFile,$arguments,[Text.UTF8Encoding]::new($false))
$compileLog=Join-Path $benchDir '.work\compile.log'; & javac ('@'+$argumentsFile) 2>&1|Tee-Object -FilePath $compileLog
if($LASTEXITCODE -ne 0){throw "Compilation failed: $LASTEXITCODE"}
if(Select-String -LiteralPath $compileLog -Pattern 'AccessDeniedException|An exception has occurred in the compiler|java\.lang\.[A-Za-z]+Error' -Quiet){throw 'Compiler environment failure. See .work\compile.log; no benchmark will be launched.'}
Copy-Item -Path (Join-Path $projectDir 'src\main\resources\*') -Destination $classes -Recurse -Force
if($Benchmark -eq 'compile'){Write-Output "COMPILE_PASS=$classes";exit 0}
& java "-Dbench.root=$benchDir" "-Dbench.harness.sha=$manifestHash" -cp "$classes;$jar" bench.BenchMain $Benchmark
if($LASTEXITCODE -ne 0){throw "Benchmark process failed: $LASTEXITCODE"}