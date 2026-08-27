def test_function_only_change_reuses_unmodified_entities(
    tmp_path,
    index_manager,
):
    source = """class Service:
    def a(self):
        return 1

    def b(self):
        return 2

    def c(self):
        return 3
"""

    file = tmp_path / "service.py"
    file.write_text(source)

    first = index_manager.index_project(tmp_path)

    assert first["entities_recomputed"] >= 4

    file.write_text(source.replace("return 2", "return 20"))

    second = index_manager.refresh_index(tmp_path)

    assert second["entities_recomputed"] == 1
    assert second["entities_reused"] >= 3


def test_added_method_preserves_existing_entities(
    tmp_path,
    index_manager,
):
    file = tmp_path / "service.py"

    file.write_text(
        """class Service:
    def a(self):
        return 1
"""
    )

    index_manager.index_project(tmp_path)

    file.write_text(
        """class Service:
    def a(self):
        return 1

    def b(self):
        return 2
"""
    )

    result = index_manager.refresh_index(tmp_path)

    assert result["entities_recomputed"] == 1
    assert result["entities_reused"] >= 2
