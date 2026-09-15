"""app_log.py — Logging for kiro-cli-history.

Writes to kiro-cli-history.log with rotation (2MB gz) and retention (60 days).
Designed for debugging and performance analysis, not verbose runtime logging.

Public API:
    init_logging()              -> None (call once at app start)
    log_perf(event, **kwargs)   -> None
    log_warn(event, **kwargs)   -> None  
    log_error(event, **kwargs)  -> None

Log levels:
    PERF  — Performance measurements (app start, search, load times)
    WARN  — Abnormal but recoverable (cache failure, fallback used)
    ERROR — Failures and exceptions
"""

import gzip
import os
import shutil
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LOG_FILENAME = "kiro-cli-history.log"
MAX_LOG_BYTES = 2 * 1024 * 1024  # 2 MB
MAX_AGE_DAYS = 60
MAX_ROTATED_FILES = 10  # Safety cap on number of .gz files

# Module state
_log_file = None
_app_version = "unknown"
_log_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Path resolution (reuse from config if available, else standalone)
# ---------------------------------------------------------------------------

def _get_data_dir() -> Path:
    """Get the data directory. Creates if needed."""
    try:
        from config import get_data_dir
        return get_data_dir()
    except ImportError:
        # Fallback: same directory as this file
        data_dir = Path(__file__).parent / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir


def _get_log_path() -> Path:
    """Get the full path to the log file."""
    return _get_data_dir() / LOG_FILENAME


def _get_app_version() -> str:
    """Get the current app version string."""
    try:
        from kiro_history import VERSION
        return VERSION
    except ImportError:
        return "unknown"


# ---------------------------------------------------------------------------
# Rotation and cleanup
# ---------------------------------------------------------------------------

def _rotate_logs() -> None:
    """Rotate log file if over size limit. Called once at app start."""
    log_path = _get_log_path()
    
    if not log_path.exists():
        return
    
    try:
        if log_path.stat().st_size < MAX_LOG_BYTES:
            return
    except OSError:
        return
    
    # Find next available rotation number
    data_dir = _get_data_dir()
    existing = sorted(data_dir.glob(f"{LOG_FILENAME}.*.gz"))
    
    # Shift existing files: .2.gz -> .3.gz, .1.gz -> .2.gz
    for gz_path in reversed(existing):
        try:
            # Extract number from filename
            num_str = gz_path.stem.split(".")[-1]  # "kiro-cli-history.log.1" -> "1"
            num = int(num_str)
            if num >= MAX_ROTATED_FILES:
                gz_path.unlink()  # Delete if exceeds max
                continue
            new_path = data_dir / f"{LOG_FILENAME}.{num + 1}.gz"
            gz_path.rename(new_path)
        except (ValueError, OSError):
            pass
    
    # Compress current log to .1.gz
    gz_path = data_dir / f"{LOG_FILENAME}.1.gz"
    try:
        with open(log_path, "rb") as f_in:
            with gzip.open(gz_path, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
        # Truncate original log
        log_path.write_text("")
    except OSError:
        pass


def _cleanup_old_logs() -> None:
    """Delete rotated logs older than MAX_AGE_DAYS. Called once at app start."""
    data_dir = _get_data_dir()
    cutoff = time.time() - (MAX_AGE_DAYS * 24 * 60 * 60)
    
    for gz_path in data_dir.glob(f"{LOG_FILENAME}.*.gz"):
        try:
            if gz_path.stat().st_mtime < cutoff:
                gz_path.unlink()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

def init_logging() -> None:
    """Initialize logging system. Call once at app start.
    
    - Performs log rotation if needed
    - Cleans up old log files
    - Opens log file for appending
    
    Safe to call multiple times — subsequent calls are no-ops.
    """
    global _log_file, _app_version
    
    # Already initialized — skip
    if _log_file is not None:
        return
    
    _app_version = _get_app_version()
    
    # Rotate and cleanup first
    _rotate_logs()
    _cleanup_old_logs()
    
    # Open log file (line-buffered for crash safety)
    try:
        log_path = _get_log_path()
        _log_file = open(log_path, "a", encoding="utf-8", buffering=1)
    except OSError as e:
        _log_file = None
        print(f"[kiro-cli-history] Warning: could not open log file: {e}", file=sys.stderr)


def close_logging() -> None:
    """Close log file. Optional — called at app exit."""
    global _log_file
    if _log_file:
        try:
            _log_file.close()
        except OSError:
            pass
        _log_file = None


# ---------------------------------------------------------------------------
# Log writing
# ---------------------------------------------------------------------------

def _format_timestamp() -> str:
    """Get current timestamp in ISO 8601 format with timezone (RFC 3339)."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _format_kwargs(kwargs: dict) -> str:
    """Format kwargs as key=value pairs."""
    parts = []
    for k, v in kwargs.items():
        if isinstance(v, str) and (" " in v or "=" in v or '"' in v):
            escaped = v.replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")
            parts.append(f'{k}="{escaped}"')
        elif isinstance(v, float):
            parts.append(f"{k}={v:.3f}")
        else:
            parts.append(f"{k}={v}")
    return " ".join(parts)


def _write_log(level: str, event: str, **kwargs) -> None:
    """Write a log entry. Thread-safe."""
    if _log_file is None:
        return
    
    timestamp = _format_timestamp()
    kwargs_str = _format_kwargs(kwargs) if kwargs else ""
    
    if kwargs_str:
        line = f"{timestamp} [{level}] {event} {kwargs_str}\n"
    else:
        line = f"{timestamp} [{level}] {event}\n"
    
    try:
        with _log_lock:
            _log_file.write(line)
            _log_file.flush()
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def log_perf(event: str, **kwargs) -> None:
    """Log a performance measurement.
    
    Example:
        log_perf("app_start", sessions=150, load_time=0.234)
        log_perf("search", query="test", results=5, time=0.012, cache="warm")
    """
    _write_log("PERF", event, **kwargs)


def log_warn(event: str, **kwargs) -> None:
    """Log a warning (abnormal but recoverable).
    
    Example:
        log_warn("cache_build_failed", session_id="abc123", reason="OSError")
    """
    _write_log("WARN", event, **kwargs)


def log_error(event: str, **kwargs) -> None:
    """Log an error (failure).
    
    Example:
        log_error("resume_failed", session_id="abc123", error="FileNotFoundError")
    """
    _write_log("ERROR", event, **kwargs)


# ---------------------------------------------------------------------------
# CLI self-check
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== app_log.py self-check ===\n")
    
    print(f"Data dir: {_get_data_dir()}")
    print(f"Log path: {_get_log_path()}")
    print(f"App version: {_get_app_version()}")
    print()
    
    print("Initializing logging...")
    init_logging()
    
    print("Writing test entries...")
    log_perf("self_check_start", version=_app_version)
    log_perf("search", query="test query", results=42, time=0.123, cache="warm")
    log_warn("test_warning", reason="just testing")
    log_error("test_error", error="simulated error")
    log_perf("self_check_end")
    
    close_logging()
    
    print("\nLog contents:")
    print("-" * 60)
    log_path = _get_log_path()
    if log_path.exists():
        print(log_path.read_text())
    else:
        print("(log file not found)")
    print("-" * 60)
    
    print("\n=== OK ===")
