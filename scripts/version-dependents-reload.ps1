[CmdletBinding()]
param(
    [Parameter(Mandatory=$false)][ValidateSet('Check','Start','Resume','Stop','Status')][string]$Action = 'Check',
    [string]$Config = 'data/vd-db-reload-ready-20260912-01/config.json',
    [string]$Python = 'C:\Users\SSAFY\miniforge3\python.exe'
)

$ErrorActionPreference = 'Stop'
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if ($Config.IndexOfAny([char[]]('"', "`r", "`n")) -ge 0) { throw 'Config path contains an unsafe quote or newline' }
$configCandidate = if ([System.IO.Path]::IsPathRooted($Config)) { $Config } else { Join-Path $repoRoot $Config }
$configPath = (Resolve-Path -LiteralPath $configCandidate).Path
$jobConfig = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
$jobOutput = [string]$jobConfig.output
if ([string]::IsNullOrWhiteSpace($jobOutput)) { throw 'Config output is required' }
$jobRoot = if ([System.IO.Path]::IsPathRooted($jobOutput)) { [System.IO.Path]::GetFullPath($jobOutput) } else { [System.IO.Path]::GetFullPath((Join-Path $repoRoot $jobOutput)) }
$repoPrefix = $repoRoot.TrimEnd('\') + '\'
if (-not $jobRoot.StartsWith($repoPrefix, [System.StringComparison]::OrdinalIgnoreCase)) { throw 'Config output must be inside the repository' }
New-Item -ItemType Directory -Force -Path $jobRoot | Out-Null

function Quote-WindowsArgument([string]$Value) {
    if ($Value.IndexOfAny([char[]]('"', "`r", "`n")) -ge 0) { throw 'Argument contains an unsafe quote or newline' }
    if ($Value -notmatch '[\s"]') { return $Value }
    return '"' + $Value + '"'
}

$sitePackages = Join-Path $repoRoot '.venv-bq\Lib\site-packages'
$pythonPath = @($repoRoot, $sitePackages) -join ';'
$env:PYTHONPATH = if ($env:PYTHONPATH) { "$pythonPath;$env:PYTHONPATH" } else { $pythonPath }
$arguments = @('-u', '-m', 'pipeline.version_dependents.historical_db_reload', '--config', $configPath)
switch ($Action) {
    'Start'  { $arguments += '--publish' }
    'Resume' { $arguments += @('--publish', '--resume') }
    'Stop'   { $arguments += '--stop' }
    'Status' { $arguments += '--status' }
}

if ($Action -in @('Start','Resume')) {
    $pidPath = Join-Path $jobRoot 'runner-process.json'
    if (Test-Path -LiteralPath $pidPath) {
        $prior = Get-Content -LiteralPath $pidPath -Raw | ConvertFrom-Json
        $priorProcess = Get-Process -Id ([int]$prior.pid) -ErrorAction SilentlyContinue
        if ($priorProcess -and ([string]$priorProcess.StartTime.ToUniversalTime().Ticks -eq [string]$prior.started_ticks)) {
            throw "reload process is already running: PID $($prior.pid)"
        }
    }
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmssfff'
    $stdout = Join-Path $jobRoot "runner-$stamp.stdout.log"
    $stderr = Join-Path $jobRoot "runner-$stamp.stderr.log"
    $quotedArguments = $arguments | ForEach-Object { Quote-WindowsArgument $_ }
    $job = Start-Process -FilePath $Python -ArgumentList $quotedArguments -WorkingDirectory $repoRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    @{pid=$job.Id; started_ticks=[string]$job.StartTime.ToUniversalTime().Ticks} | ConvertTo-Json | Set-Content -LiteralPath $pidPath -Encoding ascii
    Start-Sleep -Milliseconds 2000
    if ($job.HasExited) {
        $errorText = if (Test-Path -LiteralPath $stderr) { Get-Content -LiteralPath $stderr -Raw } else { '' }
        throw "reload process exited immediately with code $($job.ExitCode): $errorText"
    }
    Write-Output ("reload process started: PID {0}; logs: {1}, {2}" -f $job.Id, $stdout, $stderr)
} else {
    & $Python @arguments
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
