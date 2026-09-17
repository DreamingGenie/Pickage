# Run from any directory. This script builds locally; it never submits a Spark job.
$ErrorActionPreference = 'Stop'
$endpoint = docker --context desktop-linux context inspect desktop-linux --format '{{.Endpoints.docker.Host}}'
if ($LASTEXITCODE -ne 0 -or $endpoint.Trim() -ne 'npipe:////./pipe/dockerDesktopLinuxEngine') {
    throw 'Expected the local Docker Desktop Linux named pipe; refusing to build.'
}
$lock = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'images.lock.json') -Raw | ConvertFrom-Json
$dockerfile = Join-Path $PSScriptRoot '../Dockerfile'
# This Dockerfile copies only from base images. An empty context keeps repository
# data, credentials and unrelated files out of the build context.
$buildContext = Join-Path ([IO.Path]::GetTempPath()) ('pickage-spark-build-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $buildContext | Out-Null
try {
    docker --context desktop-linux build --platform $lock.platform `
        --build-arg "SPARK_IMAGE=$($lock.build_args.SPARK_IMAGE)" `
        --build-arg "NODE_IMAGE=$($lock.build_args.NODE_IMAGE)" `
        --build-arg "PYTHON_IMAGE=$($lock.build_args.PYTHON_IMAGE)" `
        --tag $lock.tag --file $dockerfile $buildContext
    if ($LASTEXITCODE -ne 0) { throw 'Local experiment image build failed.' }
    docker --context desktop-linux image inspect $lock.tag --format '{{.Id}}'
    if ($LASTEXITCODE -ne 0) { throw 'Built image identity could not be read.' }
} finally {
    # Remove only the empty directory created above, without recursive deletion.
    Remove-Item -LiteralPath $buildContext
}
