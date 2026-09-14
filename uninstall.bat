@echo off
rem kiro-cli-history uninstaller (Windows)
rem Delegates to uninstall.ps1 - prefers pwsh (7+), falls back to powershell (5.1).

set "PS=powershell"
where pwsh >nul 2>nul && set "PS=pwsh"

"%PS%" -NoProfile -ExecutionPolicy Bypass -File "%~dp0uninstall.ps1" %*
exit /b %ERRORLEVEL%
