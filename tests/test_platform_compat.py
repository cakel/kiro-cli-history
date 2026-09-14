"""test_platform_compat.py — 크로스플랫폼 호환성 테스트

Python 3.9+ 호환성 및 Windows/macOS/Linux 플랫폼별 경로 처리 검증.
"""
import os
import sqlite3
import sys
import tempfile
import shutil
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from session_store import _sqlite_db_path, SESSIONS_DIR


def test_sqlite_db_path():
    """플랫폼별 SQLite DB 경로 반환 테스트"""
    path = _sqlite_db_path()
    assert isinstance(path, Path), f"Expected Path, got {type(path)}"

    if sys.platform == "win32":
        assert "kiro-cli" in str(path), f"Windows path should contain 'kiro-cli': {path}"
        # LOCALAPPDATA 또는 AppData\Local 포함
        path_str = str(path).lower()
        assert "appdata" in path_str or "local" in path_str, f"Unexpected Windows path: {path}"
    elif sys.platform == "darwin":
        assert "Application Support" in str(path), f"macOS path should contain 'Application Support': {path}"
    else:
        # Linux
        assert ".local/share" in str(path) or "XDG_DATA_HOME" in os.environ, f"Unexpected Linux path: {path}"

    print(f"[OK] test_sqlite_db_path: {path}")


def test_sqlite_uri_mode():
    """SQLite URI 모드 (read-only) 테스트"""
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = Path(tmpdir) / "test.sqlite3"

        # Create DB
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE t (x TEXT)")
        conn.execute("INSERT INTO t VALUES (?)", ("test",))
        conn.commit()
        conn.close()

        # Read via URI mode (kiro_history.py 방식)
        uri = f"file:{db_path}?mode=ro"
        conn2 = sqlite3.connect(uri, uri=True)
        rows = conn2.execute("SELECT * FROM t").fetchall()
        conn2.close()

        assert rows == [("test",)], f"Unexpected data: {rows}"
        print("[OK] test_sqlite_uri_mode")
    finally:
        shutil.rmtree(tmpdir)


def test_sqlite_uri_with_spaces():
    """SQLite URI 경로에 공백 포함 시 테스트"""
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = Path(tmpdir) / "path with spaces" / "test.sqlite3"
        db_path.parent.mkdir(parents=True)

        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE t (x TEXT)")
        conn.commit()
        conn.close()

        uri = f"file:{db_path}?mode=ro"
        conn2 = sqlite3.connect(uri, uri=True)
        conn2.close()

        print("[OK] test_sqlite_uri_with_spaces")
    finally:
        shutil.rmtree(tmpdir)


def test_datetime_fromisoformat():
    """datetime.fromisoformat() Z suffix 처리 테스트 (3.9 호환)"""
    # kiro_history.py에서 사용하는 방식: .replace("Z", "+00:00")
    ts = "2026-01-01T12:00:00Z"
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    assert dt.year == 2026
    assert dt.month == 1
    assert dt.hour == 12
    print("[OK] test_datetime_fromisoformat")


def test_strftime_day_no_padding():
    """strftime 날짜 패딩 제거 테스트 (%-d는 Windows 미지원)"""
    # kiro_history.py 방식: dt.day로 직접 접근
    dt = datetime(2026, 1, 5)
    result = f"{dt.day} {dt.strftime('%b %Y')}"
    assert result == "5 Jan 2026", f"Unexpected format: {result}"
    print("[OK] test_strftime_day_no_padding")


def test_path_home():
    """Path.home() 동작 테스트"""
    home = Path.home()
    assert home.exists(), f"Home does not exist: {home}"
    assert home.is_dir(), f"Home is not a directory: {home}"
    print(f"[OK] test_path_home: {home}")


if __name__ == "__main__":
    print(f"Python: {sys.version}")
    print(f"Platform: {sys.platform}")
    print()

    test_sqlite_db_path()
    test_sqlite_uri_mode()
    test_sqlite_uri_with_spaces()
    test_datetime_fromisoformat()
    test_strftime_day_no_padding()
    test_path_home()

    print()
    print("All tests passed.")
