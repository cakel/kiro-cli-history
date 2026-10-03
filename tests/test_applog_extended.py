"""Extended tests for app_log.py.

Covers:
  1.  debug=False 시 log_perf/log_warn 파일 미기록
  2.  debug=False 시 log_error lazy-open 후 기록
  3.  init_logging 두 번 호출 no-op
  4.  _format_kwargs — 공백 없는 값
  5.  _format_kwargs — 공백 있는 값 (quoted)
  6.  _format_kwargs — float 값 (.3f)
  7.  _format_kwargs — 빈 dict
  8.  log_perf 라인에 [PERF] 포함
  9.  log_warn 라인에 [WARN] 포함
  10. log_error 라인에 [ERROR] 포함 + ts= 자동 삽입
  11. close_logging 후 재초기화 가능
  12. 로그 로테이션: 2MB 초과 파일 → .1.gz 생성
  13. 오래된 gz 파일 cleanup
"""

import gzip
import time
from pathlib import Path

import pytest

import app_log


# ---------------------------------------------------------------------------
# Fixture: 각 테스트마다 app_log 모듈 상태를 깨끗하게 초기화
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_app_log(tmp_path, monkeypatch):
    """테스트 전후로 app_log 상태를 완전히 리셋하고 data_dir을 tmp_path로 패치."""
    # 테스트 시작 전 리셋
    app_log.close_logging()
    app_log._log_file = None
    app_log._logging_enabled = False

    # _get_data_dir을 tmp_path로 패치
    monkeypatch.setattr(app_log, "_get_data_dir", lambda: tmp_path)

    yield tmp_path

    # 테스트 종료 후 리셋 (다음 테스트를 위해)
    app_log.close_logging()
    app_log._log_file = None
    app_log._logging_enabled = False


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _log_path(tmp_path: Path) -> Path:
    return tmp_path / app_log.LOG_FILENAME


# ---------------------------------------------------------------------------
# 1. debug=False 시 log_perf / log_warn 는 파일에 기록 안 됨
# ---------------------------------------------------------------------------

def test_perf_and_warn_not_written_in_non_debug_mode(reset_app_log):
    tmp_path = reset_app_log

    app_log.init_logging(debug=False)
    app_log.log_perf("perf_event", val=1)
    app_log.log_warn("warn_event", val=2)
    app_log.close_logging()

    log_file = _log_path(tmp_path)
    # 파일이 아예 생성되지 않거나, 생성됐더라도 PERF/WARN 내용 없어야 함
    if log_file.exists():
        content = log_file.read_text(encoding="utf-8")
        assert "perf_event" not in content
        assert "warn_event" not in content
    # 파일이 없으면 그것 자체로 통과


# ---------------------------------------------------------------------------
# 2. debug=False 시 log_error 는 파일 lazy-open 후 기록됨
# ---------------------------------------------------------------------------

def test_error_lazy_opens_file_in_non_debug_mode(reset_app_log):
    tmp_path = reset_app_log

    app_log.init_logging(debug=False)
    # 이 시점에 파일이 없어야 함
    assert not _log_path(tmp_path).exists()

    app_log.log_error("something_broke", detail="oops")
    app_log.close_logging()

    log_file = _log_path(tmp_path)
    assert log_file.exists(), "log_error should lazy-open the file"
    content = log_file.read_text(encoding="utf-8")
    assert "something_broke" in content
    assert "[ERROR]" in content


# ---------------------------------------------------------------------------
# 3. init_logging 두 번 호출해도 no-op (두 번째 호출 무시)
# ---------------------------------------------------------------------------

def test_init_logging_second_call_is_noop(reset_app_log):
    tmp_path = reset_app_log

    app_log.init_logging(debug=True)
    first_file_obj = app_log._log_file

    # 두 번째 호출 — 상태 변경 없어야 함
    app_log.init_logging(debug=True)
    assert app_log._log_file is first_file_obj, (
        "Second init_logging call must be a no-op (same file object)"
    )


def test_init_logging_debug_true_then_false_noop(reset_app_log):
    """첫 호출이 debug=True면 두 번째 debug=False도 무시되어야 함 (no-op).

    no-op 조건: _log_file is not None OR _logging_enabled is True.
    debug=True 첫 호출 후에는 _log_file이 열리고 _logging_enabled=True이므로
    이후 호출은 no-op.
    """
    app_log.init_logging(debug=True)
    assert app_log._logging_enabled is True
    first_file_obj = app_log._log_file

    app_log.init_logging(debug=False)
    # 여전히 enabled 상태이고 파일 객체도 변하지 않아야 함
    assert app_log._logging_enabled is True
    assert app_log._log_file is first_file_obj


# ---------------------------------------------------------------------------
# 4. _format_kwargs — 공백 없는 값: key=value
# ---------------------------------------------------------------------------

def test_format_kwargs_simple_value():
    result = app_log._format_kwargs({"event": "search", "count": 42})
    assert "event=search" in result
    assert "count=42" in result


# ---------------------------------------------------------------------------
# 5. _format_kwargs — 공백 있는 값: key="value with space"
# ---------------------------------------------------------------------------

def test_format_kwargs_value_with_space():
    result = app_log._format_kwargs({"msg": "hello world"})
    assert result == 'msg="hello world"'


def test_format_kwargs_value_with_equals():
    """'=' 포함 문자열도 quoted 처리."""
    result = app_log._format_kwargs({"expr": "a=b"})
    assert result == 'expr="a=b"'


# ---------------------------------------------------------------------------
# 6. _format_kwargs — float 값: key=0.123
# ---------------------------------------------------------------------------

def test_format_kwargs_float_three_decimal_places():
    result = app_log._format_kwargs({"duration": 0.123456})
    assert result == "duration=0.123"


def test_format_kwargs_float_rounds_correctly():
    result = app_log._format_kwargs({"ratio": 1.9999})
    assert result == "ratio=2.000"


# ---------------------------------------------------------------------------
# 7. _format_kwargs — 빈 dict: 빈 문자열
# ---------------------------------------------------------------------------

def test_format_kwargs_empty_dict():
    result = app_log._format_kwargs({})
    assert result == ""


# ---------------------------------------------------------------------------
# 8. log_perf 로그 라인에 [PERF] 포함 확인
# ---------------------------------------------------------------------------

def test_log_perf_contains_perf_tag(reset_app_log):
    tmp_path = reset_app_log

    app_log.init_logging(debug=True)
    app_log.log_perf("app_start", sessions=10)
    app_log.close_logging()

    content = _log_path(tmp_path).read_text(encoding="utf-8")
    assert "[PERF]" in content
    assert "app_start" in content


# ---------------------------------------------------------------------------
# 9. log_warn 로그 라인에 [WARN] 포함 확인
# ---------------------------------------------------------------------------

def test_log_warn_contains_warn_tag(reset_app_log):
    tmp_path = reset_app_log

    app_log.init_logging(debug=True)
    app_log.log_warn("cache_miss", reason="cold")
    app_log.close_logging()

    content = _log_path(tmp_path).read_text(encoding="utf-8")
    assert "[WARN]" in content
    assert "cache_miss" in content


# ---------------------------------------------------------------------------
# 10. log_error 라인에 [ERROR] 포함 및 ts= 필드 자동 포함 확인
# ---------------------------------------------------------------------------

def test_log_error_contains_error_tag_and_ts(reset_app_log):
    tmp_path = reset_app_log

    app_log.init_logging(debug=True)
    app_log.log_error("db_fail", error="timeout")
    app_log.close_logging()

    content = _log_path(tmp_path).read_text(encoding="utf-8")
    assert "[ERROR]" in content
    assert "db_fail" in content
    assert "ts=" in content, "ERROR entries must auto-inject ts= field"


def test_log_error_ts_is_numeric(reset_app_log):
    tmp_path = reset_app_log

    app_log.init_logging(debug=True)
    before = int(time.time() * 1000)
    app_log.log_error("ts_check")
    after = int(time.time() * 1000)
    app_log.close_logging()

    content = _log_path(tmp_path).read_text(encoding="utf-8")
    # ts=<number> 형태 파싱
    import re
    match = re.search(r"ts=(\d+)", content)
    assert match, "ts= value should be an integer"
    ts_value = int(match.group(1))
    assert before <= ts_value <= after


# ---------------------------------------------------------------------------
# 11. close_logging 후 재초기화 가능
# ---------------------------------------------------------------------------

def test_reinitialize_after_close(reset_app_log):
    tmp_path = reset_app_log

    # 첫 번째 세션
    app_log.init_logging(debug=True)
    app_log.log_perf("first_session")
    app_log.close_logging()

    # 수동 리셋 (close_logging이 _logging_enabled만 False로 만들지만
    # _log_file은 이미 None이므로 추가로 리셋)
    app_log._log_file = None
    app_log._logging_enabled = False

    # 두 번째 세션
    app_log.init_logging(debug=True)
    app_log.log_perf("second_session")
    app_log.close_logging()

    content = _log_path(tmp_path).read_text(encoding="utf-8")
    assert "first_session" in content
    assert "second_session" in content


# ---------------------------------------------------------------------------
# 12. 로그 로테이션: 2MB 초과 파일 있으면 .1.gz 생성
# ---------------------------------------------------------------------------

def test_log_rotation_creates_gz_when_over_size_limit(reset_app_log):
    tmp_path = reset_app_log

    log_file = _log_path(tmp_path)
    # 2MB + 1 byte 짜리 더미 로그 파일 생성
    log_file.write_bytes(b"x" * (app_log.MAX_LOG_BYTES + 1))

    app_log._rotate_logs()

    gz_path = tmp_path / f"{app_log.LOG_FILENAME}.1.gz"
    assert gz_path.exists(), "rotation should produce .1.gz"

    # gz 내용이 원본과 일치하는지 확인
    with gzip.open(gz_path, "rb") as f:
        data = f.read()
    assert data == b"x" * (app_log.MAX_LOG_BYTES + 1)

    # 원본 파일은 빈 상태로 truncate
    assert log_file.read_bytes() == b""


def test_log_rotation_skipped_when_under_size_limit(reset_app_log):
    tmp_path = reset_app_log

    log_file = _log_path(tmp_path)
    log_file.write_bytes(b"small log")

    app_log._rotate_logs()

    gz_path = tmp_path / f"{app_log.LOG_FILENAME}.1.gz"
    assert not gz_path.exists(), "no rotation when file is under size limit"


# ---------------------------------------------------------------------------
# 13. 오래된 gz 파일 cleanup
# ---------------------------------------------------------------------------

def test_cleanup_old_logs_removes_expired_gz(reset_app_log):
    tmp_path = reset_app_log

    # MAX_AGE_DAYS + 1일 전 mtime을 가진 gz 파일 생성
    old_gz = tmp_path / f"{app_log.LOG_FILENAME}.1.gz"
    old_gz.write_bytes(b"old compressed log")
    old_mtime = time.time() - (app_log.MAX_AGE_DAYS + 1) * 24 * 60 * 60
    import os
    os.utime(old_gz, (old_mtime, old_mtime))

    app_log._cleanup_old_logs()

    assert not old_gz.exists(), "expired gz file should be deleted"


def test_cleanup_old_logs_keeps_recent_gz(reset_app_log):
    tmp_path = reset_app_log

    # 최근 파일은 유지되어야 함
    recent_gz = tmp_path / f"{app_log.LOG_FILENAME}.1.gz"
    recent_gz.write_bytes(b"recent compressed log")
    # mtime을 현재로 (기본값)

    app_log._cleanup_old_logs()

    assert recent_gz.exists(), "recent gz file should not be deleted"
