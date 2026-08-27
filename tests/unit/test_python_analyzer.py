from code_index_mcp.indexing.python.analyzer import PythonAnalyzer


def test_extracts_nested_and_async_entities():
    source = """
class Service:
    def method(self, value: int) -> str:
        def nested() -> str:
            return "x"
        return nested()

    async def run(self) -> None:
        pass
"""

    result = PythonAnalyzer().analyze(source, "service.py")

    ids = {entity.entity_id for entity in result.entities}

    assert "python:service.py:Service" in ids
    assert "python:service.py:Service.method" in ids
    assert "python:service.py:Service.run" in ids
    assert any("nested" in entity.entity_id for entity in result.entities)


def test_syntax_error_does_not_raise():
    result = PythonAnalyzer().analyze(
        "def broken(:\n",
        "broken.py",
    )

    assert result.errors
    assert result.entities == []
