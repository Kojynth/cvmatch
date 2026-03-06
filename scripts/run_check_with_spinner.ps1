param(
    [string]$PythonExe = "",
    [string]$CommandLine = "",
    [string]$DisplayName = "",
    [string]$WorkingDirectory = "",
    [string]$StdoutPath = "",
    [string]$StderrPath = "",
    [int]$SoftTimeoutSec = 0
)

$ErrorActionPreference = "Stop"
$spinner = @("|", "/", "-", "\")
$start = Get-Date
$softNotified = $false
$idx = 0
$script:CurrentActivity = ""
$nextHeartbeat = 0
$heartbeatSec = 15

# Support env-driven configuration to avoid fragile batch quoting.
if ([string]::IsNullOrWhiteSpace($PythonExe)) { $PythonExe = $env:CVMATCH_CHECK_PYTHON }
if ([string]::IsNullOrWhiteSpace($CommandLine)) { $CommandLine = $env:CVMATCH_CHECK_CMD }
if ([string]::IsNullOrWhiteSpace($DisplayName)) { $DisplayName = $env:CVMATCH_CHECK_NAME }
if ([string]::IsNullOrWhiteSpace($WorkingDirectory)) { $WorkingDirectory = $env:CVMATCH_CHECK_WD }
if ([string]::IsNullOrWhiteSpace($StdoutPath)) { $StdoutPath = $env:CVMATCH_CHECK_OUT }
if ([string]::IsNullOrWhiteSpace($StderrPath)) { $StderrPath = $env:CVMATCH_CHECK_ERR }
if ($SoftTimeoutSec -le 0) {
    $rawSoft = $env:CVMATCH_CHECK_SOFT_TIMEOUT
    if ([int]::TryParse($rawSoft, [ref]$SoftTimeoutSec) -eq $false) { $SoftTimeoutSec = 20 }
}
$rawHeartbeat = $env:CVMATCH_CHECK_HEARTBEAT
$parsedHeartbeat = 0
if ([int]::TryParse($rawHeartbeat, [ref]$parsedHeartbeat) -and $parsedHeartbeat -gt 0) {
    $heartbeatSec = $parsedHeartbeat
}

if (
    [string]::IsNullOrWhiteSpace($PythonExe) -or
    [string]::IsNullOrWhiteSpace($CommandLine) -or
    [string]::IsNullOrWhiteSpace($DisplayName) -or
    [string]::IsNullOrWhiteSpace($WorkingDirectory) -or
    [string]::IsNullOrWhiteSpace($StdoutPath) -or
    [string]::IsNullOrWhiteSpace($StderrPath)
) {
    Write-Host "[ERROR] Spinner check config incomplete (python/cmd/name/wd/out/err)."
    exit 2
}

try {
    $proc = Start-Process `
        -FilePath $PythonExe `
        -ArgumentList $CommandLine `
        -WorkingDirectory $WorkingDirectory `
        -PassThru `
        -NoNewWindow `
        -RedirectStandardOutput $StdoutPath `
        -RedirectStandardError $StderrPath
}
catch {
    Write-Host ("[ERROR] {0}: impossible de lancer le check ({1})" -f $DisplayName, $_.Exception.Message)
    exit 1
}

$outSeen = 0
$errSeen = 0

function Drain-Lines {
    param(
        [string]$Path,
        [ref]$Seen,
        [string]$Prefix
    )

    if (-not (Test-Path $Path)) {
        return
    }

    $lines = @(Get-Content -Path $Path -ErrorAction SilentlyContinue)
    if ($lines.Count -eq 0) {
        return
    }

    $count = $lines.Count
    if ($count -le $Seen.Value) {
        return
    }

    Write-Host ""
    for ($i = $Seen.Value; $i -lt $count; $i++) {
        $line = $lines[$i]
        if (-not [string]::IsNullOrWhiteSpace($line)) {
            $trimmed = $line.Trim()
            if ($trimmed -match "^(Collecting)\s+(.+)$") {
                $script:CurrentActivity = "Collecting " + ($Matches[2].Trim())
            }
            elseif ($trimmed -match "^(Downloading)\s+(.+)$") {
                $script:CurrentActivity = "Downloading " + ($Matches[2].Trim())
            }
            elseif ($trimmed -match "^(Installing collected packages:?)\s*(.*)$") {
                $pkgPart = ($Matches[2] -as [string]).Trim()
                if ([string]::IsNullOrWhiteSpace($pkgPart)) {
                    $script:CurrentActivity = "Installing collected packages"
                } else {
                    $script:CurrentActivity = "Installing " + $pkgPart
                }
            }
            elseif ($trimmed -match "^(Building wheel for)\s+(.+)$") {
                $script:CurrentActivity = "Building wheel for " + ($Matches[2].Trim())
            }
            elseif ($trimmed -match "^(Preparing metadata)\s+(.+)$") {
                $script:CurrentActivity = "Preparing metadata " + ($Matches[2].Trim())
            }
            elseif ($trimmed -match "^(Requirement already satisfied:)\s+(.+)$") {
                $script:CurrentActivity = "Already satisfied: " + ($Matches[2].Trim())
            }
            elseif ($trimmed -match "^(Successfully installed)\s+(.+)$") {
                $script:CurrentActivity = "Installed: " + ($Matches[2].Trim())
            }
            elseif ($trimmed -match "^(Processing)\s+(.+)$") {
                $script:CurrentActivity = "Processing " + ($Matches[2].Trim())
            }
            elseif ($trimmed -match "^(Getting requirements to build wheel)\s*(.*)$") {
                $script:CurrentActivity = "Getting requirements to build wheel"
            }
            elseif ($trimmed -match "^(Building wheels for collected packages)\s*(.*)$") {
                $script:CurrentActivity = "Building wheels for collected packages"
            }
            elseif ($trimmed -match "^(Installing build dependencies)\s*(.*)$") {
                $script:CurrentActivity = "Installing build dependencies"
            }
        }
        if (-not [string]::IsNullOrWhiteSpace($line)) {
            Write-Host ("[{0}] {1}" -f $Prefix, $line)
        }
    }
    $Seen.Value = $count
}

while (-not $proc.HasExited) {
    Drain-Lines -Path $StdoutPath -Seen ([ref]$outSeen) -Prefix $DisplayName
    Drain-Lines -Path $StderrPath -Seen ([ref]$errSeen) -Prefix ($DisplayName + "/ERR")

    $elapsed = [int]((Get-Date) - $start).TotalSeconds
    $glyph = $spinner[$idx % $spinner.Count]
    $idx++
    $activitySuffix = ""
    if (-not [string]::IsNullOrWhiteSpace($script:CurrentActivity)) {
        $activity = $script:CurrentActivity
        if ($activity.Length -gt 110) {
            $activity = $activity.Substring(0, 110) + "..."
        }
        $activitySuffix = " | " + $activity
    }

    Write-Host -NoNewline ("`r[WAIT] {0} {1} {2}s{3} " -f $DisplayName, $glyph, $elapsed, $activitySuffix)
    Start-Sleep -Milliseconds 200

    if ((-not $softNotified) -and ($elapsed -ge $SoftTimeoutSec)) {
        Write-Host ""
        Write-Host ("[INFO] {0}: verification toujours en cours ({1}s), on continue..." -f $DisplayName, $elapsed)
        $softNotified = $true
        $nextHeartbeat = $elapsed + $heartbeatSec
    }
    elseif ($softNotified -and ($elapsed -ge $nextHeartbeat)) {
        Write-Host ""
        if (-not [string]::IsNullOrWhiteSpace($script:CurrentActivity)) {
            Write-Host ("[INFO] {0}: toujours en cours ({1}s) - {2}" -f $DisplayName, $elapsed, $script:CurrentActivity)
        } else {
            Write-Host ("[INFO] {0}: toujours en cours ({1}s), on continue..." -f $DisplayName, $elapsed)
        }
        $nextHeartbeat = $elapsed + $heartbeatSec
    }
}

$proc.WaitForExit()
Drain-Lines -Path $StdoutPath -Seen ([ref]$outSeen) -Prefix $DisplayName
Drain-Lines -Path $StderrPath -Seen ([ref]$errSeen) -Prefix ($DisplayName + "/ERR")

$total = [int]((Get-Date) - $start).TotalSeconds
Write-Host ("`r[DONE] {0} en {1}s.                        " -f $DisplayName, $total)
exit $proc.ExitCode
