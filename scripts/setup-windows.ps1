param([string]$NetworkProxy = '')
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$root = 'C:\AI\MOSS-TTSD'
$python = "$root\.venv\Scripts\python.exe"
if ($NetworkProxy) { $env:HTTPS_PROXY = $NetworkProxy }
Set-Location $root
try {
    & $python -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw 'pip upgrade failed' }
    $wheel = "$root\wheelhouse\torch-2.6.0+cu124-cp311-cp311-win_amd64.whl"
    if (Test-Path $wheel) {
        & $python -m pip install --no-deps $wheel
        if ($LASTEXITCODE -ne 0) { throw 'Local PyTorch wheel installation failed' }
    }
    & $python -m pip install -r requirements-v100.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
    & $python -m pip check
    if ($LASTEXITCODE -ne 0) { throw 'Dependency validation failed' }
    'complete' | Set-Content "$root\setup-status.txt"
} catch {
    $_ | Out-String | Set-Content "$root\setup-status.txt"
    throw
}
