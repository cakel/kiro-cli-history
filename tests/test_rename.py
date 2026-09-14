"""Tests for session rename functionality."""
import json
import os
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


class TestJSONLRename:
    """Test JSONL session rename - atomic file write."""

    def test_rename_creates_valid_json(self, tmp_path):
        """Basic rename updates title in JSON metadata."""
        # Setup
        json_file = tmp_path / "test.json"
        jsonl_file = tmp_path / "test.jsonl"
        json_file.write_text('{"title": "old title", "other": "data"}', encoding="utf-8")
        jsonl_file.write_text('{"kind": "Prompt"}\n', encoding="utf-8")
        
        session = {
            "source": "jsonl",
            "jsonl_path": str(jsonl_file),
        }
        
        # Import after setup to avoid import errors during collection
        from kiro_history import KiroHistory
        
        app = KiroHistory()
        result = app._update_session_title(session, "new title")
        
        assert result is True
        data = json.loads(json_file.read_text(encoding="utf-8"))
        assert data["title"] == "new title"
        assert data["other"] == "data"  # Other fields preserved

    def test_rename_atomic_no_corruption_on_replace_error(self, tmp_path):
        """If os.replace fails, original file should remain intact."""
        json_file = tmp_path / "test.json"
        jsonl_file = tmp_path / "test.jsonl"
        original_content = '{"title": "original", "data": "important"}'
        json_file.write_text(original_content, encoding="utf-8")
        jsonl_file.write_text('{"kind": "Prompt"}\n', encoding="utf-8")
        
        session = {
            "source": "jsonl",
            "jsonl_path": str(jsonl_file),
        }
        
        from kiro_history import KiroHistory
        
        app = KiroHistory()
        
        # Simulate os.replace failing (e.g., cross-device move)
        with patch("os.replace", side_effect=OSError("simulated replace error")):
            result = app._update_session_title(session, "new title")
        
        # Original file should be unchanged
        assert json_file.read_text(encoding="utf-8") == original_content
        assert result is False
        
        # Temp file should be cleaned up
        temp_files = list(tmp_path.glob("*.json"))
        assert len(temp_files) == 1  # Only original file remains

    def test_rename_nonexistent_file_returns_false(self, tmp_path):
        """Rename of non-existent file should return False gracefully."""
        session = {
            "source": "jsonl",
            "jsonl_path": str(tmp_path / "nonexistent.jsonl"),
        }
        
        from kiro_history import KiroHistory
        
        app = KiroHistory()
        result = app._update_session_title(session, "new title")
        
        assert result is False


class TestSQLiteRename:
    """Test SQLite session rename."""

    def test_rename_v2_updates_correct_column(self, tmp_path):
        """V2 rename should update title in value JSON."""
        db_path = tmp_path / "test.sqlite3"
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE conversations_v2 (
                key TEXT,
                conversation_id TEXT PRIMARY KEY,
                value TEXT,
                created_at INTEGER,
                updated_at INTEGER
            )
        """)
        # V2 stores data as JSON in value column
        v2_data = json.dumps({
            "title": "old title",
            "history": []
        })
        conn.execute(
            "INSERT INTO conversations_v2 VALUES (?, ?, ?, ?, ?)",
            ("/path", "sess-123", v2_data, 0, 0)
        )
        conn.commit()
        conn.close()
        
        session = {
            "source": "sqlite_v2",
            "session_id": "sess-123",
        }
        
        from kiro_history import KiroHistory
        
        with patch("kiro_history._sqlite_db_path", return_value=str(db_path)):
            app = KiroHistory()
            result = app._update_session_title(session, "new title")
        
        assert result is True
        
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT value FROM conversations_v2 WHERE conversation_id = ?",
            ("sess-123",)
        ).fetchone()
        conn.close()
        
        data = json.loads(row[0])
        assert data["title"] == "new title"

    def test_rename_v1_key_value_structure(self, tmp_path):
        """V1 uses key-value structure: key=cwd, value=JSON in conversations table."""
        db_path = tmp_path / "test.sqlite3"
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE conversations (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        # V1 stores data as JSON in value column, key is cwd
        cwd = "/path/to/project"
        v1_data = json.dumps({
            "conversation_id": "conv-456",
            "title": "old title",
            "cwd": cwd
        })
        conn.execute(
            "INSERT INTO conversations VALUES (?, ?)",
            (cwd, v1_data)
        )
        conn.commit()
        conn.close()
        
        session = {
            "source": "sqlite_v1",
            "session_id": "conv-456",
            "cwd": cwd,  # V1 rename uses cwd as lookup key
        }
        
        from kiro_history import KiroHistory
        
        with patch("kiro_history._sqlite_db_path", return_value=str(db_path)):
            app = KiroHistory()
            result = app._update_session_title(session, "new title")
        
        assert result is True
        
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT value FROM conversations WHERE key = ?",
            (cwd,)
        ).fetchone()
        conn.close()
        
        data = json.loads(row[0])
        assert data["title"] == "new title"

    def test_rename_invalid_source_returns_false(self):
        """Unknown source type should return False."""
        session = {
            "source": "unknown_source",
            "session_id": "test-123",
        }
        
        from kiro_history import KiroHistory
        
        app = KiroHistory()
        result = app._update_session_title(session, "new title")
        
        assert result is False


class TestSQLTableNameAllowlist:
    """Test that SQL table names are validated against allowlist."""

    def test_only_allowed_tables_are_used(self, tmp_path):
        """SQL should only use tables from allowlist, not f-string injection."""
        db_path = tmp_path / "test.sqlite3"
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE conversations_v2 (
                conversation_id TEXT PRIMARY KEY,
                title TEXT
            )
        """)
        conn.execute("INSERT INTO conversations_v2 VALUES ('test', 'old')")
        conn.commit()
        conn.close()
        
        # Try with a malicious source name
        session = {
            "source": "sqlite_v2; DROP TABLE conversations_v2;--",
            "session_id": "test",
        }
        
        from kiro_history import KiroHistory
        
        with patch("kiro_history._sqlite_db_path", return_value=str(db_path)):
            app = KiroHistory()
            result = app._update_session_title(session, "hacked")
        
        # Should return False for invalid source
        assert result is False
        
        # Table should still exist
        conn = sqlite3.connect(db_path)
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        conn.close()
        
        assert ("conversations_v2",) in tables
