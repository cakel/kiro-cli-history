"""tests/fixtures/integration_sessions/__init__.py

Synthetic integration test sessions with known search patterns.
These are designed to be portable across any machine.
"""

import json
from datetime import datetime, timezone
from pathlib import Path


def _generate_large_session():
    """Generate a large session with known matches for '두 가지'."""
    msgs = []
    # Add 12 messages with "두 가지"
    for i in range(12):
        msgs.append({"kind": "Prompt", "text": f"두 가지 방법이 있습니다 - 옵션 {i+1}"})
        msgs.append({"kind": "AssistantMessage", "text": f"옵션 {i+1}을 설명하겠습니다"})
    
    # Pad with non-matching messages to reach ~800
    for i in range(400):
        msgs.append({"kind": "Prompt", "text": f"질문 {i+1}: 이것은 테스트입니다"})
        msgs.append({"kind": "AssistantMessage", "text": f"답변 {i+1}: 확인했습니다"})
    
    return msgs


def _generate_search_session():
    """Generate a session for search performance testing."""
    msgs = []
    # Add 20 messages with "전체"
    for i in range(20):
        msgs.append({"kind": "Prompt", "text": f"전체 목록을 보여주세요 - 요청 {i+1}"})
        msgs.append({"kind": "AssistantMessage", "text": f"전체 {i+1}개 항목입니다"})
    
    # Pad with non-matching messages to reach ~950
    for i in range(450):
        msgs.append({"kind": "Prompt", "text": f"다른 질문 {i+1}"})
        msgs.append({"kind": "AssistantMessage", "text": f"다른 답변 {i+1}"})
    
    return msgs


def _generate_highlight_session():
    """Generate session with known matches for 'example.com'."""
    base_msgs = [
        # 13 messages containing "example.com"
        {"kind": "Prompt", "text": "Visit https://example.com for documentation"},
        {"kind": "AssistantMessage", "text": "The example.com site has API docs"},
        {"kind": "Prompt", "text": "Can I use example.com/api?"},
        {"kind": "AssistantMessage", "text": "Yes, example.com/api is public"},
        {"kind": "Prompt", "text": "What about example.com/auth?"},
        {"kind": "AssistantMessage", "text": "example.com/auth requires login"},
        {"kind": "Prompt", "text": "Send request to example.com"},
        {"kind": "AssistantMessage", "text": "Request sent to example.com"},
        {"kind": "Prompt", "text": "Check example.com status"},
        {"kind": "AssistantMessage", "text": "example.com is online"},
        {"kind": "Prompt", "text": "Download from example.com"},
        {"kind": "AssistantMessage", "text": "Downloaded from example.com"},
        {"kind": "Prompt", "text": "Final check on example.com"},
        # Non-matching messages
        {"kind": "AssistantMessage", "text": "All checks complete"},
        {"kind": "Prompt", "text": "What else can you help with?"},
        {"kind": "AssistantMessage", "text": "I can help with many things"},
    ]
    # Repeat to get ~112 messages
    msgs = base_msgs * 7
    return msgs


# Fixture session specs for integration tests
INTEGRATION_SESSIONS = {
    "int-highlight": {
        "session_id": "int-highlight-aaaa-bbbb-cccc-ddddeeee0001",
        "title": "Integration Test - Highlight Search",
        "cwd": "D:/Work/test-project",
        "search_term": "example.com",
        "expected_matches": 13 * 7,  # 91 matches (13 per repeat * 7)
        "messages": _generate_highlight_session(),
    },
    "int-large": {
        "session_id": "int-large-aaaa-bbbb-cccc-ddddeeee0002",
        "title": "Integration Test - Large Session",
        "cwd": "D:/Work/large-project",
        "search_term": "두 가지",
        "expected_matches": 12,
        "messages": _generate_large_session(),
    },
    "int-search": {
        "session_id": "int-search-aaaa-bbbb-cccc-ddddeeee0003",
        "title": "Integration Test - Search Performance",
        "cwd": "D:/Work/search-project",
        "search_term": "전체",
        "expected_matches": 40,  # 20 prompts + 20 responses
        "messages": _generate_search_session(),
    },
}


def build_integration_fixtures(output_dir: Path):
    """Build JSONL fixture files for integration tests."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    for name, spec in INTEGRATION_SESSIONS.items():
        jsonl_path = output_dir / f"{spec['session_id']}.jsonl"
        json_path = output_dir / f"{spec['session_id']}.json"
        
        # Session header/metadata
        header = {
            "session_id": spec["session_id"],
            "cwd": spec["cwd"],
            "title": spec["title"],
            "model": "test-model",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        
        # Write JSON sidecar (metadata)
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(header, f, ensure_ascii=False, indent=2)
        
        # Write JSONL (messages only, no header) - no spaces for msg_count detection
        with open(jsonl_path, 'w', encoding='utf-8') as f:
            for msg in spec["messages"]:
                obj = {
                    "version": "1",
                    "kind": msg["kind"],
                    "data": {
                        "content": [{"kind": "text", "data": msg["text"]}]
                    }
                }
                f.write(json.dumps(obj, ensure_ascii=False, separators=(',', ':')) + "\n")
        
        size_kb = jsonl_path.stat().st_size / 1024
        print(f"  {name}: {len(spec['messages'])} msgs -> {jsonl_path.name} ({size_kb:.1f} KB)")
    
    return INTEGRATION_SESSIONS


if __name__ == "__main__":
    output = Path(__file__).parent
    build_integration_fixtures(output)
