"""tests/helpers.py — Shared test utilities (importable from test files)."""


def reset_cache(sessions: list) -> list:
    """Clear _search_text/_lock on all JSONL sessions in-place."""
    for s in sessions:
        if s.get("source") == "jsonl":
            s.pop("_search_text", None)
            s.pop("_lock", None)
    return sessions


def result_ids(sessions: list) -> set:
    return {s.get("session_id") or s.get("cwd") or id(s) for s in sessions}
