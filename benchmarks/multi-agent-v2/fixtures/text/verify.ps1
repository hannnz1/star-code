$ErrorActionPreference='Stop'
New-Item -ItemType Directory -Force -Path (Join-Path $PSScriptRoot 'build') | Out-Null
$sources=@(Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot 'src') -Recurse -Filter '*.java' | ForEach-Object {$_.FullName})
& javac -d (Join-Path $PSScriptRoot 'build') @sources (Join-Path $PSScriptRoot 'tests\GateTest.java')
if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
& java -cp (Join-Path $PSScriptRoot 'build') GateTest
exit $LASTEXITCODE
