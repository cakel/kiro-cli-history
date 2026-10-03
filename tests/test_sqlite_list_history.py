"""tests/test_sqlite_list_history.py — Guard against nested-list history entries.

Some SQLite v2 sessions store history as a list of lists
([[{...}, {...}], ...]) rather than a list of dicts ([{user:..., assistant:...}, ...]).
All four history-iterating functions must skip non-dict entries instead of raising
AttributeError.

Ref: upstream issue prabhugr/kiro-cli-history#2
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from session_store import (
    _extract_messages_from_history,
    _get_first_prompt_from_history,
    _is_sqlite_subagent,
    _search_history,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

NORMAL_HISTORY = [
    {
        "user": {"content": {"Prompt": {"prompt": "hello world"}}},
        "assistant": {"content": {"Text": "hi there"}},
    },
    {
        "user": {"content": {"Prompt": {"prompt": "second turn"}}},
        "assistant": {"content": {"Text": "response two"}},
    },
]

# The problematic format: history entries are lists, not dicts
NESTED_LIST_HISTORY = [
    [{"user": {"content": {"Prompt": {"prompt": "nested entry"}}}}, {}],
    [{"assistant": {"content": {"Text": "nested reply"}}}],
]

# Mixed: some entries are dicts, some are lists
MIXED_HISTORY = [
    {
        "user": {"content": {"Prompt": {"prompt": "valid entry"}}},
        "assistant": {"content": {"Text": "valid reply"}},
    },
    ["not", "a", "dict"],
    {
        "user": {"content": {"Prompt": {"prompt": "another valid"}}},
        "assistant": {"content": {"Text": "another reply"}},
    },
]


# ---------------------------------------------------------------------------
# _extract_messages_from_history
# ---------------------------------------------------------------------------

class TestExtractMessagesFromHistory:

    def test_normal_history_works(self):
        msgs = _extract_messages_from_history(NORMAL_HISTORY)
        assert len(msgs) == 4
        assert msgs[0] == {"role": "you", "text": "hello world"}
        assert msgs[1] == {"role": "kiro", "text": "hi there"}

    def test_nested_list_history_no_crash(self):
        """Must not raise AttributeError when entries are lists."""
        msgs = _extract_messages_from_history(NESTED_LIST_HISTORY)
        assert msgs == []

    def test_mixed_history_skips_lists(self):
        """List entries skipped; dict entries still extracted."""
        msgs = _extract_messages_from_history(MIXED_HISTORY)
        roles = [m["role"] for m in msgs]
        texts = [m["text"] for m in msgs]
        assert "valid entry" in texts
        assert "another valid" in texts
        # No content from the list entry
        assert all(r in ("you", "kiro") for r in roles)

    def test_empty_history(self):
        assert _extract_messages_from_history([]) == []


# ---------------------------------------------------------------------------
# _get_first_prompt_from_history
# ---------------------------------------------------------------------------

class TestGetFirstPromptFromHistory:

    def test_normal_history_returns_prompt(self):
        result = _get_first_prompt_from_history(NORMAL_HISTORY)
        assert result == "hello world"

    def test_nested_list_history_returns_untitled(self):
        """Must not raise; returns '(untitled)' when no dict entries found."""
        result = _get_first_prompt_from_history(NESTED_LIST_HISTORY)
        assert result == "(untitled)"

    def test_mixed_history_returns_first_valid_prompt(self):
        result = _get_first_prompt_from_history(MIXED_HISTORY)
        assert result == "valid entry"

    def test_empty_history_returns_untitled(self):
        assert _get_first_prompt_from_history([]) == "(untitled)"


# ---------------------------------------------------------------------------
# _is_sqlite_subagent
# ---------------------------------------------------------------------------

class TestIsSqliteSubagent:

    def test_normal_non_subagent(self):
        assert _is_sqlite_subagent(NORMAL_HISTORY) is False

    def test_nested_list_history_no_crash(self):
        """Must not raise; returns False when no dict entries found."""
        result = _is_sqlite_subagent(NESTED_LIST_HISTORY)
        assert result is False

    def test_mixed_history_no_crash(self):
        result = _is_sqlite_subagent(MIXED_HISTORY)
        assert isinstance(result, bool)

    def test_empty_history(self):
        assert _is_sqlite_subagent([]) is False


# ---------------------------------------------------------------------------
# _search_history
# ---------------------------------------------------------------------------

class TestSearchHistory:

    def test_normal_history_matches(self):
        assert _search_history("hello", NORMAL_HISTORY) is True

    def test_normal_history_no_match(self):
        assert _search_history("xyz_no_match", NORMAL_HISTORY) is False

    def test_nested_list_history_no_crash(self):
        """Must not raise; returns False when no dict entries."""
        result = _search_history("nested", NESTED_LIST_HISTORY)
        assert result is False

    def test_mixed_history_matches_dict_entries(self):
        assert _search_history("valid entry", MIXED_HISTORY) is True

    def test_mixed_history_no_crash_on_list_entry(self):
        # Key guarantee: must not raise AttributeError when a list entry is present.
        # The return value (True/False) depends only on the dict entries in the list.
        result = _search_history("xyz_guaranteed_no_match_12345", MIXED_HISTORY)
        assert result is False

    def test_empty_history(self):
        assert _search_history("anything", []) is False
