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

# Use fixed path matching install.ps1
$installDir = "C:\ProgramData\kiro-cli-history"
$binDir     = Join-Path $installDir "bin"
$venvDir    = Join-Path $installDir "venv"
$batPath    = Join-Path $binDir "kiro-cli-history.bat"

# Legacy path (before path change to avoid Korean encoding issues)
$legacyInstallDir = Join-Path $env:LOCALAPPDATA "kiro-cli-history"
$legacyBinDir     = Join-Path $legacyInstallDir "bin"

Write-Host ""
Write-Host "====================================================================" -ForegroundColor White
Write-Host "  kiro-cli-history uninstaller" -ForegroundColor White
Write-Host "====================================================================" -ForegroundColor White
Write-Host ""

# -- 1. Stop running kiro-cli-history processes --
$procs = Get-Process python* -ErrorAction SilentlyContinue | Where-Object { 
    $_.Path -and $_.Path -like "*kiro-cli-history*" 
}
if ($procs) {
    Write-Info "Stopping running kiro-cli-history processes..."
    $procs | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 300
}

# -- 2. Remove launcher bat --
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

# -- 3. Remove virtual environment --
if (Test-Path $venvDir) {
    Write-Info "Removing virtual environment: $venvDir"
}

# -- 4. Remove install directory (includes venv) --
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

# -- 4b. Remove legacy install directory (pre-path-change versions) --
if (Test-Path $legacyInstallDir) {
    Write-Info "Found legacy installation at $legacyInstallDir"
    try {
        Remove-Item $legacyInstallDir -Recurse -Force -ErrorAction Stop
        Write-OK "Removed legacy $legacyInstallDir"
    } catch {
        Write-Warn "Could not remove legacy ${legacyInstallDir}: $_"
    }
}

# -- 5. Remove User PATH entry --
try {
    $path    = [System.Environment]::GetEnvironmentVariable("Path", "User")
    # Remove both current and legacy bin directories
    $targets = @($binDir.TrimEnd('\'), $legacyBinDir.TrimEnd('\'))
    $elements = $path -split ';' | Where-Object { 
        $_ -and ($targets -notcontains $_.Trim().TrimEnd('\'))
    }
    $newPath  = $elements -join ';'
    if ($newPath -ne $path) {
        [System.Environment]::SetEnvironmentVariable("Path", $newPath, "User")
        Write-OK "Removed PATH entries"
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
