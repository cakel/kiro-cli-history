"""tests/fixtures/__init__.py — In-memory fixture data for unit tests.

Creates a self-contained fake session store in a temp directory:
  <tmp>/
    kiro/sessions/cli/
      <uuid>.json   (metadata)
      <uuid>.jsonl  (messages)
    kiro-cli/
      data.sqlite3  (v2 table)

The fixture covers:
  - 6 JSONL sessions (various sizes, one Korean "에이스플레이어" session)
  - 2 SQLite v2 sessions
  - 1 JSONL session with parent_session_id (subagent / single-turn)
  - 1 untitled JSONL session
  - Known search results for test assertions

All files are tiny (<1KB each) — entire fixture builds in <10ms.
"""

import json
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple


# ---------------------------------------------------------------------------
# Fixture session specs
# ---------------------------------------------------------------------------

class _Spec(NamedTuple):
    session_id: str
    title: str
    cwd: str
    prompts: list[str]   # user turns
    replies: list[str]   # assistant turns (same length)
    is_subagent: bool = False
    parent_session_id: str | None = None
    created_at: str = "2026-01-01T10:00:00Z"
    updated_at: str = "2026-01-01T11:00:00Z"


FIXTURE_SESSIONS: list[_Spec] = [
    _Spec(
        session_id="aaaaaaaa-0001-0001-0001-000000000001",
        title="에이스플레이어 설정 방법",
        cwd="D:/Work/acme-player",
        prompts=["에이스플레이어 설정하는 방법을 알려주세요",
                 "네트워크 설정은 어떻게 하나요?"],
        replies=["에이스플레이어는 다음과 같이 설정합니다...",
                 "네트워크 설정은 AcmeConsole에서 합니다..."],
    ),
    _Spec(
        session_id="aaaaaaaa-0002-0002-0002-000000000002",
        title="session_store 검색 성능 개선",
        cwd="D:/Work/kiro-cli-history",
        prompts=["session_store 검색이 느립니다",
                 "prebuild_cache는 어떻게 동작하나요?"],
        replies=["cold search가 느린 이유는 JSONL 파일을 처음 읽기 때문입니다",
                 "prebuild_cache는 백그라운드 스레드에서 실행됩니다"],
    ),
    _Spec(
        session_id="aaaaaaaa-0003-0003-0003-000000000003",
        title="Python import 오류 해결",
        cwd="D:/Work/myproject",
        prompts=["ModuleNotFoundError: No module named 'foo'"],
        replies=["pip install foo 로 설치하세요"],
    ),
    _Spec(
        session_id="aaaaaaaa-0004-0004-0004-000000000004",
        title="def 함수 작성 방법",
        cwd="D:/Work/tutorial",
        prompts=["def 키워드로 함수를 어떻게 정의하나요?",
                 "return 값이 없는 경우는?"],
        replies=["def 함수명(매개변수): 형태로 작성합니다",
                 "return 없이 None을 반환합니다"],
    ),
    _Spec(
        session_id="aaaaaaaa-0005-0005-0005-000000000005",
        title="Docker 컨테이너 실행",
        cwd="D:/Work/docker-project",
        prompts=["docker run 명령어 사용법을 알려주세요"],
        replies=["docker run [OPTIONS] IMAGE [COMMAND] 형태입니다"],
    ),
    _Spec(
        session_id="aaaaaaaa-0006-0006-0006-000000000006",
        title="",  # untitled
        cwd="",
        prompts=["안녕"],
        replies=["안녕하세요"],
    ),
    _Spec(
        session_id="aaaaaaaa-0007-0007-0007-000000000007",
        title="subagent 작업",
        cwd="D:/Work/subagent",
        prompts=["subagent 지시사항"],
        replies=["완료했습니다"],
        is_subagent=True,
        parent_session_id="aaaaaaaa-0001-0001-0001-000000000001",
    ),
]

# SQLite v2 fixture sessions (stored in DB, not files)
SQLITE_SESSIONS: list[dict] = [
    {
        "session_id": "bbbbbbbb-0001-0001-0001-000000000001",
        "title": "SQLite 세션 - 에이스플레이어 네트워크",
        "cwd": "D:/Work/sqlite-session-1",
        "prompts": ["에이스플레이어 네트워크 문제가 생겼습니다"],
        "replies": ["네트워크 설정을 확인해보세요"],
        "created_ms": 1704067200000,  # 2024-01-01
        "updated_ms": 1704070800000,
    },
    {
        "session_id": "bbbbbbbb-0002-0002-0002-000000000002",
        "title": "SQLite 세션 - Python 디버깅",
        "cwd": "D:/Work/sqlite-session-2",
        "prompts": ["Python 디버깅 방법을 알려주세요"],
        "replies": ["pdb를 사용하면 됩니다"],
        "created_ms": 1704153600000,
        "updated_ms": 1704157200000,
    },
]

# Expected search results (session_ids) — ground truth for assertions
EXPECTED: dict[str, set[str]] = {
    "에이스플레이어": {
        "aaaaaaaa-0001-0001-0001-000000000001",
        "bbbbbbbb-0001-0001-0001-000000000001",
    },
    "session_store": {
        "aaaaaaaa-0002-0002-0002-000000000002",
    },
    "python": {
        "aaaaaaaa-0003-0003-0003-000000000003",
        "bbbbbbbb-0002-0002-0002-000000000002",
    },
    "def ": {
        "aaaaaaaa-0004-0004-0004-000000000004",
    },
    "docker": {
        "aaaaaaaa-0005-0005-0005-000000000005",
    },
}


# ---------------------------------------------------------------------------
# Fixture builder
# ---------------------------------------------------------------------------

def _make_jsonl_line(kind: str, text: str) -> str:
    obj = {
        "kind": kind,
        "data": {
            "content": [{"kind": "text", "data": text}]
        }
    }
    # No spaces after separators — matches how kiro-cli writes JSONL
    # so the byte-search msg_count heuristic (b'"kind":"Prompt"') works
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def build_fixture_dir(tmp_path: Path) -> Path:
    """Create a complete fake session store under tmp_path.

    Returns tmp_path (the KIRO_DEMO_DIR root).
    Layout:
      tmp_path/kiro/sessions/cli/   ← JSONL sessions
      tmp_path/kiro-cli/data.sqlite3 ← SQLite sessions
    """
    sessions_dir = tmp_path / "kiro" / "sessions" / "cli"
    sessions_dir.mkdir(parents=True)
    db_dir = tmp_path / "kiro-cli"
    db_dir.mkdir(parents=True)

    # --- JSONL sessions ---
    for spec in FIXTURE_SESSIONS:
        sid = spec.session_id
        meta = {
            "session_id": sid,
            "title": spec.title,
            "cwd": spec.cwd,
            "created_at": spec.created_at,
            "updated_at": spec.updated_at,
            "session_created_reason": "subagent" if spec.is_subagent else "user",
            "parent_session_id": spec.parent_session_id,
        }
        (sessions_dir / f"{sid}.json").write_text(
            json.dumps(meta, ensure_ascii=False), encoding="utf-8"
        )
        lines = []
        for prompt, reply in zip(spec.prompts, spec.replies):
            lines.append(_make_jsonl_line("Prompt", prompt))
            lines.append(_make_jsonl_line("AssistantMessage", reply))
        (sessions_dir / f"{sid}.jsonl").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )

    # --- SQLite v2 sessions ---
    db_path = db_dir / "data.sqlite3"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE conversations_v2 "
        "(key TEXT, conversation_id TEXT PRIMARY KEY, value TEXT, "
        " created_at INTEGER, updated_at INTEGER)"
    )
    for s in SQLITE_SESSIONS:
        history = []
        for prompt, reply in zip(s["prompts"], s["replies"]):
            history.append({
                "user": {"content": {"Prompt": {"prompt": prompt}}},
                "assistant": {"content": {"Text": reply}},
            })
        value = json.dumps({
            "title": s["title"],
            "history": history,
            "conversation_id": s["session_id"],
        }, ensure_ascii=False)
        conn.execute(
            "INSERT INTO conversations_v2 VALUES (?,?,?,?,?)",
            (s["cwd"], s["session_id"], value, s["created_ms"], s["updated_ms"])
        )
    conn.commit()
    conn.close()

    return tmp_path
