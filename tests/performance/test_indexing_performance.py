from __future__ import annotations

import json
import time

SAMPLE_FILES = {
    "alpha.py": "import os\n\nclass Alpha:\n    def run(self):\n        return os.getcwd()\n",
    "beta.py": "from alpha import Alpha\n\ndef build():\n    return Alpha()\n",
    "gamma.py": "x = 1\n",
    "docs/readme.md": "# Guide\n\nIntro.\n\n## Install\n\nSteps.\n",
    "docs/api.md": "# API\n\n## build\n\nDocs.\n",
}


def _make_project(tmp_path):
    for relative, content in SAMPLE_FILES.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return tmp_path


def _count_calls(index_manager):
    counts = {"python": 0, "markdown": 0}

    original_python = index_manager.python_analyzer.analyze
    original_markdown = index_manager.markdown_analyzer.analyze

    def counted_python(*args, **kwargs):
        counts["python"] += 1
        return original_python(*args, **kwargs)

    def counted_markdown(*args, **kwargs):
        counts["markdown"] += 1
        return original_markdown(*args, **kwargs)

    index_manager.python_analyzer.analyze = counted_python
    index_manager.markdown_analyzer.analyze = counted_markdown
    return counts


def _trace_sql(connection):
    statements = {"SELECT": 0, "INSERT": 0, "UPDATE": 0, "DELETE": 0}

    def record(sql: str) -> None:
        verb = sql.strip().split(None, 1)[0].upper() if sql.strip() else ""
        if verb in statements:
            statements[verb] += 1

    connection.set_trace_callback(record)
    return statements


def test_indexing_performance_baseline(index_manager, tmp_path):
    project_root = _make_project(tmp_path)
    analyzer_calls = _count_calls(index_manager)
    sql_statements = _trace_sql(index_manager.db.connection)

    cold_started = time.perf_counter()
    cold = index_manager.index_project(project_root)
    cold_duration = time.perf_counter() - cold_started
    cold_calls = analyzer_calls.copy()
    cold_sql = sql_statements.copy()

    for key in sql_statements:
        sql_statements[key] = 0

    refresh_started = time.perf_counter()
    refresh = index_manager.index_project(project_root)
    refresh_duration = time.perf_counter() - refresh_started
    refresh_calls = analyzer_calls.copy()
    refresh_sql = sql_statements.copy()

    metrics = {
        "cold_duration_seconds": round(cold_duration, 6),
        "refresh_duration_seconds": round(refresh_duration, 6),
        "cold_analyzer_calls": cold_calls,
        "refresh_analyzer_calls": refresh_calls,
        "cold_sql": cold_sql,
        "refresh_sql": refresh_sql,
        "cold_files_parsed": cold["files_parsed"],
        "refresh_files_reused": refresh["files_reused"],
        "refresh_entities_reused": refresh["entities_reused"],
    }
    print(json.dumps(metrics, indent=2))

    assert cold["errors"] == []
    assert refresh["errors"] == []
    assert cold["files_seen"] == len(SAMPLE_FILES)
    assert cold_calls["python"] + cold_calls["markdown"] > 0

    assert refresh["files_reused"] == len(SAMPLE_FILES)
    assert refresh["files_parsed"] == 0
    assert refresh["entities_reused"] > 0
    assert analyzer_calls["python"] == cold_calls["python"]
    assert analyzer_calls["markdown"] == cold_calls["markdown"]
    assert refresh_sql["SELECT"] < cold_sql["SELECT"]
