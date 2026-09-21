param([switch]$Watch, [string]$Root = $PSScriptRoot)
$ErrorActionPreference = 'Stop'

function Read-JsonSafe([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    for ($attempt = 0; $attempt -lt 3; $attempt++) {
        try { return (Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json) } catch {
            if ($attempt -eq 2) { return $null }
            Start-Sleep -Milliseconds 100
        }
    }
    return $null
}

function Format-Bytes([object]$Bytes) {
    if ($null -eq $Bytes) { return '-' }
    $n = [double]$Bytes
    if ($n -ge 1GB) { return ('{0:N2} GiB' -f ($n / 1GB)) }
    if ($n -ge 1MB) { return ('{0:N1} MiB' -f ($n / 1MB)) }
    return ('{0:N0} B' -f $n)
}

function Show-Parallel([string]$RunRoot) {
    $dependents = Join-Path $RunRoot 'dependents'
    if (-not (Test-Path -LiteralPath $dependents -PathType Container)) { return }
    $parallelPath = Join-Path $dependents 'parallel-attempt/parallel-run'
    if (-not (Test-Path -LiteralPath $parallelPath)) {
        Write-Host '  Parallel: preparing or verifying input shards; workers have not started.'
        return
    }
    $run = Get-Item -LiteralPath $parallelPath
    $plan = Read-JsonSafe (Join-Path $run.FullName 'run_plan.json')
    $execution = @(Get-ChildItem -LiteralPath $run.FullName -Filter 'execution-*.json' -File -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1 | ForEach-Object { Read-JsonSafe $_.FullName })[0]
    $eventsPath = Join-Path $run.FullName 'progress.jsonl'
    $events = @()
    if (Test-Path -LiteralPath $eventsPath) {
        foreach ($line in (Get-Content -LiteralPath $eventsPath -Tail 10 -ErrorAction SilentlyContinue)) {
            try { $events += ($line | ConvertFrom-Json) } catch { }
        }
    }
    $last = $events | Select-Object -Last 1
    $reused = $events | Where-Object { $_.phase -eq 'REUSED_ALL_PARTITIONS' } | Select-Object -Last 1
    $pointers = @(Get-ChildItem -LiteralPath (Join-Path $run.FullName 'partitions') -Directory -ErrorAction SilentlyContinue |
        ForEach-Object { Join-Path $_.FullName 'complete.json' } |
        Where-Object { Test-Path -LiteralPath $_ -PathType Leaf })
    $total = if ($plan -and $plan.partitions) { @($plan.partitions.PSObject.Properties).Count } else { 0 }
    $receipts = @()
    foreach ($pointerPath in $pointers) {
        $pointer = Read-JsonSafe $pointerPath
        if ($pointer -and $pointer.attempt) {
            $attemptPath = Join-Path (Split-Path $pointerPath -Parent) $pointer.attempt
            $receiptPath = Join-Path $attemptPath 'receipt.json'
            $receipt = Read-JsonSafe $receiptPath
            if ($receipt) { $receipts += $receipt }
        }
    }
    $maxMemory = $null
    if ($receipts.Count -gt 0) {
        $values = @($receipts | ForEach-Object {
            if ($_.memory -and $null -ne $_.memory.rss_bytes) { [double]$_.memory.rss_bytes }
            elseif ($_.memory -and $null -ne $_.memory.working_set_bytes) { [double]$_.memory.working_set_bytes }
        } | Where-Object { $null -ne $_ })
        if ($values.Count -gt 0) { $maxMemory = ($values | Measure-Object -Maximum).Maximum }
    }
    $progress = if ($total -gt 0) { "{0}/{1}" -f $pointers.Count, $total } else { "{0}/?" -f $pointers.Count }
    Write-Host ("  Parallel: {0} | accepted partitions: {1} | last event: {2}" -f $run.FullName, $progress, $(if ($last) { $last.phase } else { '-' }))
    if ($reused) {
        Write-Host ("    Reusing {0} partitions; finalization: {1} threads, {2} DuckDB memory" -f $reused.partitions, $reused.settings.threads, $reused.settings.memory_limit)
    }
    if ($last -and $last.at_unix) { Write-Host ("    event time: {0}" -f ([DateTimeOffset]::FromUnixTimeSeconds([int64]$last.at_unix).ToLocalTime().ToString('yyyy-MM-dd HH:mm:ss zzz'))) }
    if (-not $reused -and $execution -and $execution.worker_settings) {
        Write-Host ("    workers: {0}, threads/worker: {1}, memory/worker: {2}, temp/worker: {3}" -f $execution.workers, $execution.worker_settings.threads, $execution.worker_settings.memory_limit, $execution.worker_settings.max_temp_size)
        if ($execution.coordinator_pid) { Write-Host ("    coordinator PID: {0}" -f $execution.coordinator_pid) }
    }
    if ($maxMemory) { Write-Host ("    max recorded worker RSS: {0}" -f (Format-Bytes $maxMemory)) }
}

do {
    if ($Watch) { Clear-Host }
    $statusPath = Join-Path $Root 'status.json'
    if (Test-Path -LiteralPath $statusPath) {
        $state = Read-JsonSafe $statusPath
        if ($null -eq $state) { Write-Host 'Status file is being updated; retrying.'; if ($Watch) { Start-Sleep -Seconds 2; continue } else { return } }
        $alive = $null -ne (Get-Process -Id $state.pid -ErrorAction SilentlyContinue)
        $elapsed = [Math]::Round(([datetimeoffset]::UtcNow - [datetimeoffset]::Parse($state.started_at)).TotalMinutes, 1)
        Write-Host "Status: $($state.status) | Process alive: $alive | Elapsed: $elapsed min"
        $phaseElapsed = '-'
        if ($state.phase_started_at) { $phaseElapsed = "{0:N1} min" -f (([datetimeoffset]::UtcNow - [datetimeoffset]::Parse($state.phase_started_at)).TotalMinutes) }
        Write-Host "Phase: $($state.phase) | Phase elapsed: $phaseElapsed | Heartbeat: $($state.heartbeat_at)"
        Write-Host "Free disk: $($state.free_gib) GiB"
        if ($state.phase -like '*COPY_RAW') {
            $doneGiB = [Math]::Round($state.copy_bytes_done / 1GB, 3)
            $totalGiB = [Math]::Round($state.copy_bytes_total / 1GB, 3)
            Write-Host "Copy: $($state.copy_objects_done)/$($state.copy_objects_total) objects, $doneGiB/$totalGiB GiB"
            Write-Host $state.current_object
        }
        if ($state.error) { Write-Host "Error: $($state.error)" -ForegroundColor Red }
        $config = Get-Content -LiteralPath (Join-Path $Root 'config.json') -Raw | ConvertFrom-Json
        $ids = if ($config.baseline_run_id) { @($config.baseline_run_id, $config.weekly_run_id) } else { @('b831', 'w914') }
        foreach ($id in $ids) {
            $stagePath = Join-Path $Root "w/$id/status.json"
            if (Test-Path -LiteralPath $stagePath) {
                $stage = Read-JsonSafe $stagePath
                if ($null -eq $stage) { continue }
                Write-Host "`n$id : $($stage.status) / $($stage.phase)"
                $stage.stages.PSObject.Properties | ForEach-Object {
                    Write-Host "  $($_.Name): $($_.Value.status)"
                }
                Show-Parallel (Join-Path $Root "w/$id")
            }
        }
        foreach ($label in @('baseline', 'weekly')) {
            $dbPath = Join-Path $Root "run/db-$label/last-run.json"
            if (Test-Path -LiteralPath $dbPath) {
                $db = Get-Content -LiteralPath $dbPath -Raw | ConvertFrom-Json
                Write-Host "DB $label : $($db.status)"
            }
        }
        if ($state.status -eq 'RUNNING' -and -not $alive) {
            Write-Host 'Process stopped unexpectedly. Inspect logs before restarting.' -ForegroundColor Red
        }
    } else { Write-Host 'Not started' }
    $launch = Read-JsonSafe (Join-Path $Root 'launch.json')
    if ($launch -and $launch.stdout -and (Test-Path -LiteralPath $launch.stdout)) {
        Write-Host "`nCurrent run log: $($launch.stdout)"
        Get-Content -LiteralPath $launch.stdout -Tail 5 | ForEach-Object { Write-Host $_ }
    }
    $timings = Join-Path $Root 'timings.json'
    if (Test-Path -LiteralPath $timings) {
        Write-Host "`nTiming history (includes previous attempts):"
        Get-Content -LiteralPath $timings -Raw | ConvertFrom-Json | Select-Object -Last 15 | Format-Table phase, status, seconds -AutoSize
    }
    if ($Watch) { Start-Sleep -Seconds 5 }
} while ($Watch)
