# Noor demo launcher (spec 001, T032).
# Starts NMIS on 127.0.0.1:5310 only, with the network guard on for NMIS and every child process.
# Refuses to start when any required variable is missing; there are no default secrets.
# Generate signing keys outside this repository: python -m noor_registry.keys generate --out-dir <absolute-external-directory>
#
# Usage (from the repository root, after setting the variables in your own session):
#   powershell -ExecutionPolicy Bypass -File launcher\noor-demo.ps1            # start NMIS
#   powershell -ExecutionPolicy Bypass -File launcher\noor-demo.ps1 -Seed      # create a fresh demo DB first

param(
    [switch]$Seed,
    [switch]$Reset
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot

$required = @(
    'NOOR_DATA_DIR', 'NOOR_EXCHANGE_DIR', 'NOOR_IDENTITY_DIR', 'NOOR_SECRET_KEY', 'NOOR_HOME_SIGNING_KEY_FILE',
    'NOOR_PW_PROPOSAL_MANAGER', 'NOOR_PW_REVIEW_APPROVER', 'NOOR_PW_MEMBER', 'NOOR_PW_VIEWER'
)
$missing = @($required | Where-Object { -not [Environment]::GetEnvironmentVariable($_) })
if ($missing.Count -gt 0) {
    [Console]::Error.WriteLine("Refusing to start. Missing environment variables: " + ($missing -join ', '))
    exit 2
}

$python = Join-Path $repo '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    [Console]::Error.WriteLine("Python virtual environment not found (.venv). See README.md (development section).")
    exit 2
}

# Network guard (T028): Python children load sitecustomize from this folder; Node children preload the .cjs.
$guard = Join-Path $repo 'tests\support\no_network'
$env:NOOR_NETGUARD = '1'
$env:PYTHONPATH = (@($guard, (Join-Path $repo 'platforms\nmis'), (Join-Path $repo 'packages\noor_identity'), (Join-Path $repo 'packages\noor_sso\python')) -join [IO.Path]::PathSeparator)
# Forward slashes: NODE_OPTIONS treats a backslash inside quotes as an escape.
$guardJs = (Join-Path $guard 'no_network.cjs').Replace('\', '/')
$env:NODE_OPTIONS = "--require `"$guardJs`""

& $python -m noor_identity build --identity-dir $env:NOOR_IDENTITY_DIR
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if ($Seed) {
    $seedArgs = @('-m', 'noor_registry.seed')
    if ($Reset) { $seedArgs += '--reset' }
    & $python @seedArgs
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

# config.py validates the variables again (absolute, outside the repository, key length) before binding.
& $python -m noor_registry.app
exit $LASTEXITCODE
