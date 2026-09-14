#Requires -Version 5.1
<#
.SYNOPSIS
  kiro-cli-history installer (Windows).
.DESCRIPTION
  Installs kiro_history.py under C:\ProgramData\kiro-cli-history,
  creates a virtual environment (prefers uv, falls back to venv),
  generates a launcher .bat, and registers the bin directory in the
  User PATH.
  No admin rights required (standard users have write access to C:\ProgramData).
#>

$ErrorActionPreference = "Stop"
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path

function Write-OK   { param($m) Write-Host "[OK]    $m" -ForegroundColor Green }
function Write-Info { param($m) Write-Host "[INFO]  $m" -ForegroundColor Cyan }
function Write-Warn { param($m) Write-Host "[WARN]  $m" -ForegroundColor Yellow }
function Write-Err  { param($m) Write-Host "[ERROR] $m" -ForegroundColor Red; throw $m }

Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "   kiro-cli-history installer - Windows" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host ""

# -- 1. Python check --
Write-Info "Checking Python..."
$pyCmd = $null
foreach ($candidate in @("python", "python3", "py")) {
    if (Get-Command $candidate -ErrorAction SilentlyContinue) {
        try {
            & $candidate -c "import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)" 2>$null
            if ($LASTEXITCODE -eq 0) { $pyCmd = $candidate; break }
        } catch {}
    }
}
if (-not $pyCmd) {
    Write-Err "Python 3.9+ is required but not found.`n  Install from: https://www.python.org/downloads/`n  or: winget install Python.Python.3"
}
$pyVer = (& $pyCmd --version) 2>&1
Write-OK "Python: $pyVer"

# -- 2. Install dirs --
# Use a fixed path without potential Korean/Unicode characters in username
# C:\ProgramData is system-wide and ASCII-only
$installDir = "C:\ProgramData\kiro-cli-history"
$binDir     = Join-Path $installDir "bin"
$venvDir    = Join-Path $installDir "venv"

Write-Info "Installing to $installDir ..."
if (-not (Test-Path $installDir)) { New-Item -ItemType Directory -Path $installDir -Force | Out-Null }
if (-not (Test-Path $binDir))     { New-Item -ItemType Directory -Path $binDir     -Force | Out-Null }

# -- 3. Create virtual environment (prefer uv, fallback to venv) --
# Remove existing venv first to avoid lock conflicts on reinstall
if (Test-Path $venvDir) {
    Write-Info "Removing existing virtual environment..."
    # Kill any running kiro-cli-history processes holding the venv
    $blocked = Get-Process python* -ErrorAction SilentlyContinue |
               Where-Object { $_.Path -like "*kiro-cli-history*" }
    if ($blocked) {
        foreach ($p in $blocked) {
            Write-Info "Stopping running instance (PID $($p.Id))..."
            Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
        }
        Start-Sleep -Milliseconds 500
    }
    try {
        Remove-Item $venvDir -Recurse -Force -ErrorAction Stop
        Write-OK "Removed existing venv"
    } catch {
        Write-Err "Could not remove existing venv: $_`n  Try closing all terminals and retry."
    }
}

if (Get-Command uv -ErrorAction SilentlyContinue) {
    Write-Info "Using uv (fast mode)..."
    & uv venv $venvDir
    if ($LASTEXITCODE -ne 0) { Write-Err "Failed to create venv with uv" }
    & uv pip install textual --python "$venvDir\Scripts\python.exe"
    if ($LASTEXITCODE -ne 0) { Write-Err "Failed to install textual with uv" }
    Write-OK "Virtual environment created with uv"
} else {
    Write-Info "Using standard venv..."
    & $pyCmd -m venv $venvDir
    if ($LASTEXITCODE -ne 0) { Write-Err "Failed to create venv" }
    & "$venvDir\Scripts\pip.exe" install --upgrade pip --quiet
    & "$venvDir\Scripts\pip.exe" install textual --quiet
    if ($LASTEXITCODE -ne 0) { Write-Err "Failed to install textual" }
    Write-OK "Virtual environment created with venv"
}

# -- 4. Copy main scripts and inject git hash --
$srcScript = Join-Path $SCRIPT_DIR "kiro_history.py"
if (-not (Test-Path $srcScript)) {
    Write-Err "kiro_history.py not found in $SCRIPT_DIR"
}
Copy-Item -LiteralPath $srcScript -Destination (Join-Path $installDir "kiro_history.py") -Force

# Copy session_store.py (data/search layer required by kiro_history.py)
$srcStore = Join-Path $SCRIPT_DIR "session_store.py"
if (-not (Test-Path $srcStore)) {
    Write-Err "session_store.py not found in $SCRIPT_DIR"
}
Copy-Item -LiteralPath $srcStore -Destination (Join-Path $installDir "session_store.py") -Force
Write-OK "Copied session_store.py -> $installDir"

# Inject current git version and hash into installed script
$destScript = Join-Path $installDir "kiro_history.py"
try {
    $gitHash = & git -C $SCRIPT_DIR rev-parse --short HEAD 2>$null
    $gitTag = & git -C $SCRIPT_DIR describe --tags --abbrev=0 2>$null
    if ($LASTEXITCODE -eq 0 -and $gitHash) {
        $content = Get-Content $destScript -Raw -Encoding UTF8
        $content = $content -replace '_BUILT_HASH = ""', "_BUILT_HASH = `"$($gitHash.Trim())`""
        if ($gitTag) {
            $content = $content -replace '_BUILT_VERSION = ""', "_BUILT_VERSION = `"$($gitTag.Trim())`""
            Write-OK "Injected git version: $($gitTag.Trim())"
        }
        [System.IO.File]::WriteAllText($destScript, $content, [System.Text.UTF8Encoding]::new($false))
        Write-OK "Injected git hash: $($gitHash.Trim())"
    }
} catch {
    Write-Info "Could not inject git version/hash (git not available)"
}
Write-OK "Copied kiro_history.py -> $installDir"

# -- 5. Generate kiro-cli-history.bat using venv python --
$batPath = Join-Path $binDir "kiro-cli-history.bat"
$venvPython = Join-Path $venvDir "Scripts\python.exe"
$mainScript = Join-Path $installDir "kiro_history.py"

$batBody = @"
@echo off
rem kiro-cli-history - global launcher (generated by install.ps1).
setlocal
"$venvPython" "$mainScript" %*
endlocal & exit /b %ERRORLEVEL%
"@

# Write in UTF-8 without BOM - cmd.exe does not handle UTF-8 BOM
# C:\ProgramData path is ASCII-only so encoding is not an issue
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($batPath, $batBody, $utf8NoBom)
Write-OK "Wrote launcher bat: $batPath"

# -- 6. Register bin dir in User PATH (idempotent) --
Write-Info "Registering PATH..."

$currentUserPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
$normalizedCurrent = ($currentUserPath -split ';') | Where-Object { $_ } |
    ForEach-Object { $_.Trim().TrimEnd('\') }

if ($normalizedCurrent -notcontains $binDir.TrimEnd('\')) {
    try {
        $newPath = if ($currentUserPath) { "$currentUserPath;$binDir" } else { $binDir }
        [System.Environment]::SetEnvironmentVariable("Path", $newPath, "User")
        Write-OK "Added $binDir to User PATH"
    } catch {
        Write-Warn "Failed to update PATH: $_"
        Write-Host "  Manual: Add the following to your User PATH:" -ForegroundColor Yellow
        Write-Host "    $binDir" -ForegroundColor Yellow
    }
} else {
    Write-OK "kiro-cli-history already in PATH"
}

# Update current session PATH
$env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
            [System.Environment]::GetEnvironmentVariable("Path", "User")
Write-OK "Current session PATH updated"

# -- Done --
Write-Host ""
Write-OK "Installation complete!"
Write-Host ""
Write-Host "  Run from any directory:" -ForegroundColor White
Write-Host "    kiro-cli-history" -ForegroundColor Gray
Write-Host ""
Write-Host "  Note: Open a new terminal for PATH to take effect." -ForegroundColor Yellow
Write-Host ""
