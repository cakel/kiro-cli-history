"""_version.py — Single source of truth for version information.

All modules (kiro_history, config, app_log) import from here.
Prevents circular imports: config/app_log no longer need to import kiro_history.

Injected at install time by install.sh / install.ps1:
  _BUILT_VERSION  <- git describe --tags --abbrev=0
  _BUILT_HASH     <- git rev-parse --short HEAD
"""

# Fallback version when git is not available or not injected at install
VERSION = "v0.1.0-cakel.6"

# Injected at install time — empty string means "not installed, use git/fallback"
_BUILT_VERSION = ""
_BUILT_HASH = ""
