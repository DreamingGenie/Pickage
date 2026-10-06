param(
    [string]$Python = 'python',
    [string]$SourceContainer = 'pickage-267-validation',
    [string]$SourceDb = 'pickage_267_full_defaulted',
    [string]$Output = ('data/service-data-migration/pilot-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
)
$ErrorActionPreference = 'Stop'
$previousClasspath341 = $env:PICKAGE_341_JAVA_CLASSPATH
try {
    if (-not $previousClasspath341) {
        # Same versions used in the recorded pilot; no network/install step.
        $cacheRoot341 = Join-Path $env:USERPROFILE '.gradle/caches/modules-2/files-2.1'
        $artifacts341 = @(
            'org.flywaydb/flyway-core/11.14.1',
            'org.flywaydb/flyway-database-postgresql/11.14.1',
            'org.postgresql/postgresql/42.7.11',
            'com.fasterxml.jackson.core/jackson-annotations/2.21',
            'com.fasterxml.jackson.core/jackson-core/2.21.4',
            'com.fasterxml.jackson.core/jackson-databind/2.21.4'
        )
        $jars341 = foreach ($artifact341 in $artifacts341) {
            $matches341 = @(Get-ChildItem (Join-Path $cacheRoot341 $artifact341) -Recurse -Filter '*.jar' |
                Where-Object Name -NotMatch 'sources|javadoc')
            if ($matches341.Count -ne 1) {
                throw "Missing/ambiguous runtime jar: $artifact341. Set PICKAGE_341_JAVA_CLASSPATH explicitly."
            }
            $matches341[0].FullName
        }
        $env:PICKAGE_341_JAVA_CLASSPATH = $jars341 -join [IO.Path]::PathSeparator
    }
    & $Python (Join-Path $PSScriptRoot 'test_integration.py') --source-container $SourceContainer --source-db $SourceDb --output $Output
    if ($LASTEXITCODE -ne 0) { throw "Local pilot failed (exit $LASTEXITCODE). See $Output/result.json." }
} finally {
    $env:PICKAGE_341_JAVA_CLASSPATH = $previousClasspath341
}
