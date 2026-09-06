param([string]$Python)
$ErrorActionPreference='Stop'
if(-not $Python){
 $pythonCommand=Get-Command python -ErrorAction SilentlyContinue
 if($pythonCommand){$Python=$pythonCommand.Source}else{$Python=Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'}
}
if(-not (Test-Path -LiteralPath $Python)){throw 'Python 3.10+ is required; pass -Python with an executable path.'}
& $Python -m pip install --target (Join-Path $PSScriptRoot '.work\python') -r (Join-Path $PSScriptRoot 'requirements-lock.txt')
if($LASTEXITCODE -ne 0){throw 'Python dependency installation failed'}
foreach($mode in @('mcp-loading','context-retention','multi-agent')){
 & (Join-Path $PSScriptRoot 'run.ps1') -Benchmark $mode -Python $Python
 if($LASTEXITCODE -ne 0){throw "Benchmark process failed: $mode"}
}
& $Python (Join-Path $PSScriptRoot 'report.py')
if($LASTEXITCODE -ne 0){throw 'Report generation failed'}
& $Python (Join-Path $PSScriptRoot 'write_report.py')
if($LASTEXITCODE -ne 0){throw 'Markdown report generation failed'}
Write-Output "RESULTS=$PSScriptRoot\results\summary\summary.json"