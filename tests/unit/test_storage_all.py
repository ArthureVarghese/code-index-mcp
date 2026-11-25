from __future__ import annotations

import pytest

from code_index_mcp.storage.database import Database


class TestDatabaseExtended:
    def test_context_manager(self, tmp_path):
        with Database(tmp_path / "ctx.db") as db:
            assert db.connection is not None

    def test_execute(self, tmp_path):
        db = Database(tmp_path / "exec.db")
        try:
            result = db.execute("SELECT 1").fetchone()
            assert result[0] == 1
        finally:
            db.close()

    def test_transaction_rollback(self, tmp_path):
        db = Database(tmp_path / "rollback.db")
        try:
            db.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
            try:
                with db.transaction():
                    db.connection.execute("INSERT INTO t VALUES (1)")
                    raise ValueError("force rollback")
            except ValueError:
                pass
            rows = db.execute("SELECT * FROM t").fetchall()
            assert len(rows) == 0
        finally:
            db.close()

    def test_transaction_commit(self, tmp_path):
        db = Database(tmp_path / "commit.db")
        try:
            db.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
            with db.transaction():
                db.connection.execute("INSERT INTO t VALUES (1)")
            rows = db.execute("SELECT * FROM t").fetchall()
            assert len(rows) == 1
        finally:
            db.close()

    def test_savepoint_rollback_isolation(self, tmp_path):
        db = Database(tmp_path / "savepoint.db")
        try:
            db.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")

            with db.transaction():
                db.execute("INSERT INTO t VALUES (1)")

                with pytest.raises(RuntimeError):
                    with db.savepoint():
                        db.execute("INSERT INTO t VALUES (2)")
                        raise RuntimeError("force savepoint rollback")

                db.execute("INSERT INTO t VALUES (3)")

            rows = db.execute("SELECT id FROM t ORDER BY id").fetchall()
            assert [row["id"] for row in rows] == [1, 3]
        finally:
            db.close()

    def test_initialize_schema(self, tmp_path):
        db = Database(tmp_path / "schema.db")
        try:
            # Tables should exist
            tables = db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            table_names = {t["name"] for t in tables}
            assert "projects" in table_names
            assert "files" in table_names
            assert "entities" in table_names
        finally:
            db.close()

    def test_schema_version_metadata(self, tmp_path):
        db = Database(tmp_path / "ver.db")
        try:
            row = db.execute(
                "SELECT value FROM code_index_schema_metadata WHERE key='schema_version'"
            ).fetchone()
            assert row is not None
            assert int(row["value"]) == 1
        finally:
            db.close()
