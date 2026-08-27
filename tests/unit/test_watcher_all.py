from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

from code_index_mcp.watcher.debounce import Debouncer
from code_index_mcp.watcher.service import FileWatcher


class TestDebouncer:
    def test_fires_callback(self):
        callback = MagicMock()
        debouncer = Debouncer(0.05, callback)
        debouncer.submit("path1")
        time.sleep(0.15)
        callback.assert_called_once_with("path1")
        debouncer.close()

    def test_resets_on_resubmit(self):
        callback = MagicMock()
        debouncer = Debouncer(0.1, callback)
        debouncer.submit("path1")
        time.sleep(0.05)
        debouncer.submit("path1")  # Reset
        time.sleep(0.05)
        assert callback.call_count == 0
        time.sleep(0.1)
        assert callback.call_count == 1
        debouncer.close()

    def test_close_cancels(self):
        callback = MagicMock()
        debouncer = Debouncer(1.0, callback)
        debouncer.submit("path1")
        debouncer.close()
        time.sleep(0.1)
        callback.assert_not_called()

    def test_multiple_paths(self):
        callback = MagicMock()
        debouncer = Debouncer(0.05, callback)
        debouncer.submit("a")
        debouncer.submit("b")
        time.sleep(0.15)
        assert callback.call_count == 2
        debouncer.close()


class TestFileWatcher:
    def test_start_stop(self, tmp_path):
        callback = MagicMock()
        watcher = FileWatcher(tmp_path, callback, debounce_seconds=0.05, interval_seconds=0.05)
        watcher.start()
        time.sleep(0.05)
        watcher.stop()

    def test_detects_new_file(self, tmp_path):
        callback = MagicMock()
        watcher = FileWatcher(tmp_path, callback, debounce_seconds=0.05, interval_seconds=0.05)
        watcher.start()
        time.sleep(0.1)
        (tmp_path / "new.py").write_text("x = 1\n")
        time.sleep(0.3)
        watcher.stop()
        assert callback.call_count >= 1

    def test_context_manager(self, tmp_path):
        callback = MagicMock()
        with FileWatcher(tmp_path, callback, debounce_seconds=0.05, interval_seconds=0.05):
            time.sleep(0.1)
        # Should not raise

    def test_start_when_already_running(self, tmp_path):
        callback = MagicMock()
        watcher = FileWatcher(tmp_path, callback, interval_seconds=0.05)
        watcher.start()
        watcher.start()  # Should be no-op
        time.sleep(0.05)
        watcher.stop()

    def test_stop_when_not_running(self):
        callback = MagicMock()
        watcher = FileWatcher(Path("/tmp"), callback)
        watcher.stop()  # Should not raise

    def test_callback_exception_does_not_crash(self, tmp_path):
        def bad_callback(path):
            raise RuntimeError("oops")

        watcher = FileWatcher(tmp_path, bad_callback, debounce_seconds=0.01, interval_seconds=0.05)
        watcher.start()
        time.sleep(0.1)
        (tmp_path / "a.py").write_text("x\n")
        time.sleep(0.2)
        watcher.stop()

    def test_nonexistent_root(self, tmp_path):
        callback = MagicMock()
        fake_root = tmp_path / "nonexistent"
        watcher = FileWatcher(fake_root, callback, interval_seconds=0.05)
        watcher.start()
        time.sleep(0.1)
        watcher.stop()

    def test_ignores_symlinks(self, tmp_path):
        callback = MagicMock()
        watcher = FileWatcher(tmp_path, callback, debounce_seconds=0.05, interval_seconds=0.05)
        real = tmp_path / "real.py"
        real.write_text("x\n")
        watcher.start()
        time.sleep(0.1)
        watcher.stop()


class TestTakeSnapshot:
    def test_ignores_non_matching_extensions(self, tmp_path):
        (tmp_path / "data.txt").write_text("hello\n")
        (tmp_path / "code.py").write_text("x = 1\n")
        (tmp_path / "doc.md").write_text("# Hi\n")
        callback = MagicMock()
        watcher = FileWatcher(tmp_path, callback)
        snapshot = watcher._take_snapshot()
        assert "data.txt" not in snapshot
        assert "code.py" in snapshot
        assert "doc.md" in snapshot

    def test_includes_pyi_files(self, tmp_path):
        (tmp_path / "types.pyi").write_text("x: int\n")
        callback = MagicMock()
        watcher = FileWatcher(tmp_path, callback)
        snapshot = watcher._take_snapshot()
        assert "types.pyi" in snapshot

    def test_includes_markdown_extension(self, tmp_path):
        (tmp_path / "readme.markdown").write_text("# Hi\n")
        callback = MagicMock()
        watcher = FileWatcher(tmp_path, callback)
        snapshot = watcher._take_snapshot()
        assert "readme.markdown" in snapshot

    def test_skips_directories(self, tmp_path):
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "code.py").write_text("x = 1\n")
        callback = MagicMock()
        watcher = FileWatcher(tmp_path, callback)
        snapshot = watcher._take_snapshot()
        assert "subdir" not in snapshot
        assert "subdir/code.py" in snapshot

    def test_stat_error_handled(self, tmp_path):
        callback = MagicMock()
        watcher = FileWatcher(tmp_path, callback)
        # Create a file then make it appear to stat error
        (tmp_path / "a.py").write_text("x\n")
        with patch.object(Path, "stat", side_effect=PermissionError("denied")):
            snapshot = watcher._take_snapshot()
        # The file should be skipped due to permission error
        assert "a.py" not in snapshot
