#Requires -Version 5.1
<#
.SYNOPSIS
  kiro-cli-history uninstaller (Windows).
.DESCRIPTION
  Reverses install.ps1: removes the launcher bat, install directory
  (including venv), and the User PATH entry.
  Project files (kiro_history.py in the repo) are NOT touched.
#>

$ErrorActionPreference = "Stop"

function Write-OK   { param($m) Write-Host "[OK]    $m" -ForegroundColor Green }
function Write-Info { param($m) Write-Host "[INFO]  $m" -ForegroundColor Cyan }
function Write-Warn { param($m) Write-Host "[WARN]  $m" -ForegroundColor Yellow }

$installDir = Join-Path $env:LOCALAPPDATA "kiro-cli-history"
$binDir     = Join-Path $installDir "bin"
$venvDir    = Join-Path $installDir "venv"
$batPath    = Join-Path $binDir "kiro-cli-history.bat"

Write-Host ""
Write-Host "====================================================================" -ForegroundColor White
Write-Host "  kiro-cli-history uninstaller" -ForegroundColor White
Write-Host "====================================================================" -ForegroundColor White
Write-Host ""

# -- 1. Remove launcher bat --
if (Test-Path $batPath) {
    try {
        Remove-Item $batPath -Force -ErrorAction Stop
        Write-OK "Removed $batPath"
    } catch {
        Write-Warn "Could not remove ${batPath}: $_"
    }
} else {
    Write-Info "kiro-cli-history.bat not found (already removed?)"
}

# -- 2. Remove virtual environment --
if (Test-Path $venvDir) {
    Write-Info "Removing virtual environment: $venvDir"
}

# -- 3. Remove install directory (includes venv) --
if (Test-Path $installDir) {
    try {
        Remove-Item $installDir -Recurse -Force -ErrorAction Stop
        Write-OK "Removed $installDir"
    } catch {
        Write-Warn "Could not remove ${installDir}: $_"
    }
} else {
    Write-Info "$installDir not found (already removed?)"
}

# -- 4. Remove User PATH entry --
try {
    $path    = [System.Environment]::GetEnvironmentVariable("Path", "User")
    $target  = $binDir.TrimEnd('\')
    $elements = $path -split ';' | Where-Object { $_ -and ($_.Trim().TrimEnd('\') -ne $target) }
    $newPath  = $elements -join ';'
    if ($newPath -ne $path) {
        [System.Environment]::SetEnvironmentVariable("Path", $newPath, "User")
        Write-OK "Removed PATH entry: $binDir"
    } else {
        Write-Info "PATH entry not found (already removed?)"
    }
} catch {
    Write-Warn "Could not update PATH: $_"
    Write-Host "  Manual: remove '$binDir' from your User PATH (sysdm.cpl)." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "====================================================================" -ForegroundColor White
Write-Host "  Uninstall complete." -ForegroundColor White
Write-Host "====================================================================" -ForegroundColor White
Write-Host ""
Write-Host "  Repo files (kiro_history.py, install.ps1, etc.) are NOT affected." -ForegroundColor Gray
Write-Host "  Open a new terminal for the PATH change to take effect." -ForegroundColor Yellow
Write-Host ""
exit 0
