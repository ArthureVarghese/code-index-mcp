from code_index_mcp.retrieval.context import ContextBuilder


class Repository:
    def get_parent(self, entity_id):
        return {"entity_id": "parent"}

    def get_relationships(self, entity_id):
        return [{"type": "calls", "target": "x"}]

    def get_children(self, entity_id):
        return []


def test_minimal_context_is_bounded():
    builder = ContextBuilder(Repository())

    result = builder.build(
        {
            "entity_id": "x",
            "path": "a.py",
            "entity_type": "function",
            "name": "f",
            "start_line": 1,
            "end_line": 2,
            "source": "def f(): pass",
            "large_internal_field": "unused",
        },
        depth="minimal",
    )

    assert "large_internal_field" not in result
    assert "source" not in result
    assert result["name"] == "f"
