"""SQLite persistence layer."""

from code_index_mcp.storage.database import Database
from code_index_mcp.storage.schema import SCHEMA_VERSION

__all__ = ["Database", "SCHEMA_VERSION"]
