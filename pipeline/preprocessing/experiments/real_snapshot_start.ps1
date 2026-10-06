param(
    [string]$Root = $PSScriptRoot,
    [string]$Python = '',
    [switch]$AllowExistingProcess
)
$ErrorActionPreference = 'Stop'
$Root = [IO.Path]::GetFullPath($Root)
$configPath = Join-Path $Root 'config.json'
$config = if (Test-Path -LiteralPath $configPath) {
    Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
} else { $null }
if ([string]::IsNullOrWhiteSpace($Python) -and $config -and $config.python) { $Python = [string]$config.python }
if ([string]::IsNullOrWhiteSpace($Python)) {
    $Python = 'C:/Users/SSAFY/workspace/S15P21A506/.venv-bq/Scripts/python.exe'
}
$python = [IO.Path]::GetFullPath($Python)
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw "Python executable not found: $python" }
$statusPath = Join-Path $Root 'status.json'
if (-not $AllowExistingProcess -and (Test-Path -LiteralPath $statusPath)) {
    try {
        $old = Get-Content -LiteralPath $statusPath -Raw | ConvertFrom-Json
        if ($old.pid -and (Get-Process -Id ([int]$old.pid) -ErrorAction SilentlyContinue)) {
            throw "An experiment process is already running (PID $($old.pid))."
        }
    } catch [System.Management.Automation.RuntimeException] { throw }
    catch { }
}
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$stdout = Join-Path $Root "run-$stamp.log"
$stderr = Join-Path $Root "error-$stamp.log"
$quotedRoot = '"' + $Root.TrimEnd('\') + '"'
$process = Start-Process -FilePath $python -ArgumentList @('-u', '-m', 'pipeline.preprocessing.experiments.real_snapshot_run', '--root', $quotedRoot) -WorkingDirectory (Join-Path $Root 'src') -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
@{pid=$process.Id; python=$python; root=$Root; stdout=$stdout; stderr=$stderr; launched_at=(Get-Date).ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $Root 'launch.json') -Encoding utf8
Write-Host "Started PID $($process.Id)."
Write-Host "Status: powershell -ExecutionPolicy Bypass -File `"$(Join-Path $Root 'status.ps1')`" -Root `"$Root`" -Watch"
