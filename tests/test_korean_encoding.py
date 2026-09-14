"""test_korean_encoding.py — kiro_history.py 한글 처리 검증

Windows CP949 환경에서 UTF-8 세션 파일의 한글이 정상 처리되는지 테스트.
"""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

# 프로젝트 루트를 path에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from kiro_history import (
    extract_messages,
)
from session_store import (
    _fuzzy_match,
    _load_jsonl_sessions,
    SESSIONS_DIR,
)
import session_store as ss
import kiro_history as kh


def test_fuzzy_match_korean():
    """한글 fuzzy match 테스트"""
    cases = [
        ("한글", "한글 세션 테스트", True),
        ("세션", "한글 세션 테스트", True),
        ("없는단어", "한글 세션 테스트", False),
        ("한글 세션", "한글 세션 테스트", True),
        ("서울", "서울 날씨는 어때요?", True),
    ]
    for query, text, expected in cases:
        result = _fuzzy_match(query, text)
        assert result == expected, f"_fuzzy_match({query!r}, {text!r}) = {result}, expected {expected}"
    print("[OK] test_fuzzy_match_korean")


def test_extract_messages_korean():
    """한글 JSONL 메시지 추출 테스트"""
    tmpdir = tempfile.mkdtemp()
    try:
        jsonl_path = os.path.join(tmpdir, "test.jsonl")
        lines = [
            {"kind": "Prompt", "data": {"content": [{"kind": "text", "data": "안녕하세요, 한글 질문입니다."}]}},
            {"kind": "AssistantMessage", "data": {"content": [{"kind": "text", "data": "네, 한글 답변입니다."}]}},
        ]
        with open(jsonl_path, "w", encoding="utf-8") as f:
            for line in lines:
                f.write(json.dumps(line, ensure_ascii=False) + "\n")

        session = {"jsonl_path": jsonl_path}
        msgs = extract_messages(session)

        assert len(msgs) == 2, f"Expected 2 messages, got {len(msgs)}"
        assert msgs[0]["text"] == "안녕하세요, 한글 질문입니다.", f"Message corrupted: {msgs[0]['text']!r}"
        assert msgs[1]["text"] == "네, 한글 답변입니다.", f"Message corrupted: {msgs[1]['text']!r}"
        print("[OK] test_extract_messages_korean")
    finally:
        shutil.rmtree(tmpdir)


def test_load_jsonl_sessions_korean():
    """한글 title/cwd가 있는 세션 로드 테스트"""
    tmpdir = tempfile.mkdtemp()
    try:
        meta = {
            "session_id": "test-korean-001",
            "title": "한글 세션 제목",
            "cwd": "D:\\Work\\내프로젝트",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T01:00:00Z",
        }
        json_path = os.path.join(tmpdir, "test-korean-001.json")
        jsonl_path = os.path.join(tmpdir, "test-korean-001.jsonl")

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False)
        with open(jsonl_path, "w", encoding="utf-8") as f:
            f.write("{}\n")  # empty line

        # Patch SESSIONS_DIR temporarily
        orig_dir = ss.SESSIONS_DIR
        ss.SESSIONS_DIR = Path(tmpdir)
        try:
            sessions = ss._load_jsonl_sessions()
            assert len(sessions) == 1, f"Expected 1 session, got {len(sessions)}"
            s = sessions[0]
            assert s["title"] == "한글 세션 제목", f"Title corrupted: {s['title']!r}"
            assert s["cwd"] == "D:\\Work\\내프로젝트", f"CWD corrupted: {s['cwd']!r}"
            print("[OK] test_load_jsonl_sessions_korean")
        finally:
            ss.SESSIONS_DIR = orig_dir
    finally:
        shutil.rmtree(tmpdir)


def test_oem_roundtrip():
    """Windows OEM 코드페이지(CP949) 한글 roundtrip 테스트"""
    if sys.platform != "win32":
        print("[SKIP] test_oem_roundtrip (Windows only)")
        return

    import locale
    # Windows에서 OEM CP 확인
    try:
        import ctypes
        oemcp = ctypes.windll.kernel32.GetOEMCP()
    except Exception:
        oemcp = 949  # 한국어 Windows 기본값

    import codecs
    enc = codecs.lookup(f"cp{oemcp}")
    test_str = "홍길동"
    encoded = enc.encode(test_str)[0]
    decoded = enc.decode(encoded)[0]
    assert test_str == decoded, f"OEM roundtrip failed: {test_str!r} -> {decoded!r}"
    print(f"[OK] test_oem_roundtrip (CP{oemcp})")


if __name__ == "__main__":
    print(f"Python: {sys.version}")
    print(f"Preferred encoding: {__import__('locale').getpreferredencoding()}")
    print()

    test_fuzzy_match_korean()
    test_extract_messages_korean()
    test_load_jsonl_sessions_korean()
    test_oem_roundtrip()

    print()
    print("All tests passed.")
