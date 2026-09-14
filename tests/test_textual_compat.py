"""Test Textual app initialization and widget compatibility."""
import sys
import unittest

sys.path.insert(0, r'D:\Work\kiro-cli-history')


class TestTextualWidgets(unittest.TestCase):
    """Test that Textual widgets initialize correctly."""

    def test_richlog_init(self):
        """RichLog should initialize with our parameters."""
        from textual.widgets import RichLog
        # These are the params we use in compose()
        log = RichLog(wrap=True, highlight=True, markup=True)
        self.assertIsNotNone(log)

    def test_listview_init(self):
        """ListView should initialize."""
        from textual.widgets import ListView
        lv = ListView()
        self.assertIsNotNone(lv)

    def test_input_init(self):
        """Input should initialize with placeholder."""
        from textual.widgets import Input
        inp = Input(placeholder="Search sessions...")
        self.assertIsNotNone(inp)

    def test_static_init(self):
        """Static should initialize."""
        from textual.widgets import Static
        st = Static("")
        self.assertIsNotNone(st)

    def test_footer_init(self):
        """Footer should initialize."""
        from textual.widgets import Footer
        ft = Footer()
        self.assertIsNotNone(ft)


class TestAppImport(unittest.TestCase):
    """Test that KiroHistory app can be imported and instantiated."""

    def test_import_kirohistory(self):
        """KiroHistory class should import."""
        from kiro_history import KiroHistory
        self.assertIsNotNone(KiroHistory)

    def test_instantiate_kirohistory(self):
        """KiroHistory should instantiate without error."""
        from kiro_history import KiroHistory
        app = KiroHistory()
        self.assertIsNotNone(app)
        self.assertTrue(app.title.startswith("kiro-cli-history"))

    def test_bindings_exist(self):
        """App should have expected key bindings."""
        from kiro_history import KiroHistory
        app = KiroHistory()
        binding_keys = [b.key for b in app.BINDINGS]
        # Check critical bindings exist
        self.assertIn("ctrl+r", binding_keys)
        self.assertIn("ctrl+y", binding_keys)
        self.assertIn("ctrl+n", binding_keys)
        self.assertIn("escape", binding_keys)


class TestCoreFunctions(unittest.TestCase):
    """Test core utility functions."""

    def test_get_sessions_returns_list(self):
        """get_sessions should return a list."""
        from kiro_history import get_sessions
        sessions = get_sessions()
        self.assertIsInstance(sessions, list)

    def test_extract_messages_with_limit(self):
        """extract_messages should respect limit parameter."""
        from kiro_history import get_sessions, extract_messages
        sessions = get_sessions()
        if sessions:
            # Find a session with messages
            for s in sessions:
                if s.get('msg_count', 0) > 30:
                    msgs = extract_messages(s, limit=10)
                    self.assertLessEqual(len(msgs), 10)
                    break

    def test_extract_messages_message_format(self):
        """Extracted messages should have role and text keys."""
        from kiro_history import get_sessions, extract_messages
        sessions = get_sessions()
        if sessions:
            for s in sessions:
                msgs = extract_messages(s, limit=5)
                if msgs:
                    for msg in msgs:
                        self.assertIn('role', msg)
                        self.assertIn('text', msg)
                        self.assertIn(msg['role'], ['you', 'kiro'])
                    break


class TestLazyLoadingState(unittest.TestCase):
    """Test lazy loading state variables."""

    def test_app_has_lazy_loading_attrs(self):
        """KiroHistory should have lazy loading state attributes."""
        from kiro_history import KiroHistory
        app = KiroHistory()
        self.assertTrue(hasattr(app, '_preview_messages'))
        self.assertTrue(hasattr(app, '_preview_batch_size'))
        self.assertTrue(hasattr(app, '_preview_all_loaded'))

    def test_batch_size_reasonable(self):
        """Batch size should be reasonable (10-100)."""
        from kiro_history import KiroHistory
        app = KiroHistory()
        self.assertGreaterEqual(app._preview_batch_size, 10)
        self.assertLessEqual(app._preview_batch_size, 100)


if __name__ == "__main__":
    unittest.main(verbosity=2)
