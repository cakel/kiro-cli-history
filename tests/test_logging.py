"""Regression tests for optional logging support."""

import builtins
import runpy
from pathlib import Path

import app_log


def test_app_warns_and_runs_with_logging_module_unavailable(monkeypatch, capsys):
    """A missing logging module must warn once while keeping the app usable."""
    original_import = builtins.__import__

    def import_without_app_log(name, *args, **kwargs):
        if name == "app_log":
            raise ImportError("simulated missing optional logging module")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_app_log)
    namespace = runpy.run_path(str(Path(__file__).parent.parent / "kiro_history.py"))

    assert "WARNING: app_log.py unavailable; debug logging disabled." in capsys.readouterr().err
    assert namespace["_CONFIG_DEFAULTS"]["debug"] is False
    namespace["init_logging"](debug=True)


def test_logging_creates_a_file_only_when_debug_is_enabled(tmp_path, monkeypatch):
    """Debug-off startup must remain side-effect free; debug-on writes logs."""
    app_log.close_logging()
    monkeypatch.setattr(app_log, "_get_data_dir", lambda: tmp_path)

    app_log.init_logging()
    assert not (tmp_path / app_log.LOG_FILENAME).exists()

    # close_logging resets _initialized, so a second call with debug=True works
    app_log.close_logging()
    app_log.init_logging(debug=True)
    app_log.log_perf("test_event")
    app_log.close_logging()

    assert "test_event" in (tmp_path / app_log.LOG_FILENAME).read_text(encoding="utf-8")
