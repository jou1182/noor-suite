param(
    [string]$SourceRepo,
    [string]$Ref,
    [string]$Stamp,
    [string]$ApprovalList,
    [string]$SourceLabel,
    [string]$ReviewedBy,
    [string[]]$Exposure = @(),
    [switch]$Finish
)

$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$python = Join-Path $repo '.venv\Scripts\python.exe'
$env:PYTHONIOENCODING = 'utf-8'

foreach ($name in @('NOOR_STAGING_DIR', 'NOOR_PRIVATE_REPORTS_DIR', 'NOOR_BLOCKLIST_FILE', 'NOOR_IDENTITY_DIR')) {
    if (-not [Environment]::GetEnvironmentVariable($name)) {
        [Console]::Error.WriteLine("$name is not set")
        exit 2
    }
}

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    [Console]::Error.WriteLine('repository Python unavailable')
    exit 2
}

function Invoke-Snapshot {
    param([string[]]$Arguments)
    # PowerShell 5.1 turns native stderr into error records; 'Stop' would abort before the exit code is read.
    $ErrorActionPreference = 'Continue'
    $output = & $python -m tools.snapshot @Arguments 2>&1
    $code = $LASTEXITCODE
    foreach ($line in $output) { Write-Output ([string]$line) }
    if ($code -ne 0) { exit $code }
}

Push-Location $repo
try {
    if ($Finish) {
        if (-not $Stamp -or -not $ApprovalList -or -not $SourceLabel -or -not $ReviewedBy) {
            [Console]::Error.WriteLine('Mode B requires Stamp, ApprovalList, SourceLabel, and ReviewedBy')
            exit 2
        }
        Invoke-Snapshot -Arguments @('mark-sanitized', '--platform', 'nmis_full', '--stamp', $Stamp, '--list', $ApprovalList)
        # Approvals take effect only through a fresh scan; fingerprint requires the 'scanned' state.
        Invoke-Snapshot -Arguments @('scan', '--platform', 'nmis_full', '--stamp', $Stamp)
        $fingerprintArgs = @('fingerprint', '--platform', 'nmis_full', '--stamp', $Stamp,
                             '--source-label', $SourceLabel, '--reviewed-by', $ReviewedBy)
        foreach ($item in $Exposure) { $fingerprintArgs += @('--exposure', $item) }
        Invoke-Snapshot -Arguments $fingerprintArgs
    } else {
        if (-not $SourceRepo -or -not $Ref) {
            [Console]::Error.WriteLine('Mode A requires SourceRepo and Ref')
            exit 2
        }
        $ErrorActionPreference = 'Continue'
        $stageOutput = & $python -m tools.snapshot stage --platform nmis_full --from-git $SourceRepo --commit $Ref 2>&1
        $stageCode = $LASTEXITCODE
        $stageOutput | ForEach-Object { Write-Output ([string]$_) }
        $ErrorActionPreference = 'Stop'
        if ($stageCode -ne 0) { exit $stageCode }
        $stampLine = @($stageOutput | Where-Object { $_ -match '^stamp: (\d{8}-\d{4})$' })
        if ($stampLine.Count -ne 1) {
            [Console]::Error.WriteLine('stage stamp unavailable')
            exit 2
        }
        $currentStamp = [regex]::Match([string]$stampLine[0], '^stamp: (\d{8}-\d{4})$').Groups[1].Value
        Invoke-Snapshot -Arguments @('select', '--platform', 'nmis_full', '--stamp', $currentStamp)
        Invoke-Snapshot -Arguments @('sanitize', '--platform', 'nmis_full', '--stamp', $currentStamp)
        Invoke-Snapshot -Arguments @('scan', '--platform', 'nmis_full', '--stamp', $currentStamp)
        Write-Output "stamp: $currentStamp"
        Write-Output 'Next: review private reports; build the approval list; run mode B with -Finish.'
    }
} finally {
    Pop-Location
}
