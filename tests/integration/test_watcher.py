import time

from code_index_mcp.watcher.service import FileWatcher


def test_watcher_detects_change(tmp_path):
    target = tmp_path / "test.py"
    target.write_text("x = 1")

    events = []

    watcher = FileWatcher(
        tmp_path,
        lambda root: events.append(root),
        debounce_seconds=0.05,
        interval_seconds=0.02,
    )

    watcher.start()

    try:
        target.write_text("x = 2")
        time.sleep(0.2)
    finally:
        watcher.stop()

    assert events
