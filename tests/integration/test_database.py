from code_index_mcp.storage.database import Database


def test_database_round_trip(tmp_path):
    database = Database(tmp_path / "index.db")

    database.initialize()

    connection = database.connection

    connection.execute(
        """
        INSERT INTO projects(
            project_id,
            canonical_root,
            schema_version,
            indexer_version,
            indexing_state,
            configuration_fingerprint
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "abc",
            str(tmp_path),
            1,
            "test",
            "idle",
            "test-config",
        ),
    )

    row = connection.execute(
        """
        SELECT project_id
        FROM projects
        """
    ).fetchone()

    assert row["project_id"] == "abc"

    database.close()
