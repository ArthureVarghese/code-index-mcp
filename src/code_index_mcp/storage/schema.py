from __future__ import annotations

SCHEMA_VERSION = 1


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS projects (
    project_id TEXT PRIMARY KEY,
    canonical_root TEXT NOT NULL UNIQUE,
    schema_version INTEGER NOT NULL,
    indexer_version TEXT NOT NULL,
    indexing_state TEXT NOT NULL,
    configuration_fingerprint TEXT NOT NULL,
    last_indexed_at TEXT,
    indexed_files INTEGER NOT NULL DEFAULT 0,
    indexed_entities INTEGER NOT NULL DEFAULT 0,
    indexed_markdown_sections INTEGER NOT NULL DEFAULT 0,
    health TEXT NOT NULL DEFAULT 'unknown',
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS files (
    file_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    canonical_path TEXT NOT NULL,
    source_kind TEXT NOT NULL,
    exact_hash TEXT NOT NULL,
    semantic_hash TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    mtime_ns INTEGER NOT NULL,
    encoding TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    ignored INTEGER NOT NULL DEFAULT 0,
    parse_status TEXT NOT NULL DEFAULT 'pending',
    parse_error TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(project_id, relative_path),
    FOREIGN KEY(project_id) REFERENCES projects(project_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_files_project
    ON files(project_id);

CREATE INDEX IF NOT EXISTS idx_files_hash
    ON files(project_id, exact_hash);

CREATE INDEX IF NOT EXISTS idx_files_relative_path
    ON files(relative_path);

CREATE TABLE IF NOT EXISTS entities (
    entity_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    file_id TEXT NOT NULL,
    source_kind TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    name TEXT NOT NULL,
    qualified_name TEXT NOT NULL,
    parent_id TEXT,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    start_column INTEGER NOT NULL,
    end_column INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    exact_source_hash TEXT NOT NULL,
    semantic_hash TEXT NOT NULL,
    structural_hash TEXT NOT NULL,
    source TEXT NOT NULL,
    docstring TEXT,
    signature TEXT,
    decorators_json TEXT NOT NULL DEFAULT '[]',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
    FOREIGN KEY(file_id) REFERENCES files(file_id) ON DELETE CASCADE,
    FOREIGN KEY(parent_id) REFERENCES entities(entity_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_entities_project
    ON entities(project_id);

CREATE INDEX IF NOT EXISTS idx_entities_file
    ON entities(file_id);

CREATE INDEX IF NOT EXISTS idx_entities_parent
    ON entities(parent_id);

CREATE INDEX IF NOT EXISTS idx_entities_name
    ON entities(project_id, name);

CREATE INDEX IF NOT EXISTS idx_entities_qualified_name
    ON entities(project_id, qualified_name);

CREATE INDEX IF NOT EXISTS idx_entities_content_hash
    ON entities(project_id, content_hash);

CREATE INDEX IF NOT EXISTS idx_entities_file_order
    ON entities(file_id, start_line, start_column, end_line);

CREATE TABLE IF NOT EXISTS entity_versions (
    entity_id TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    exact_source_hash TEXT NOT NULL,
    semantic_hash TEXT NOT NULL,
    structural_hash TEXT NOT NULL,
    indexer_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY(entity_id, content_hash),
    FOREIGN KEY(entity_id) REFERENCES entities(entity_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS relationships (
    relationship_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    source_entity_id TEXT NOT NULL,
    target_entity_id TEXT,
    relationship_kind TEXT NOT NULL,
    confidence TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(
        project_id,
        source_entity_id,
        target_entity_id,
        relationship_kind
    ),
    FOREIGN KEY(project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
    FOREIGN KEY(source_entity_id) REFERENCES entities(entity_id) ON DELETE CASCADE,
    FOREIGN KEY(target_entity_id) REFERENCES entities(entity_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_relationships_source
    ON relationships(source_entity_id);

CREATE INDEX IF NOT EXISTS idx_relationships_target
    ON relationships(target_entity_id);

CREATE TABLE IF NOT EXISTS markdown_sections (
    section_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    file_id TEXT NOT NULL,
    parent_section_id TEXT,
    heading TEXT NOT NULL,
    heading_level INTEGER NOT NULL,
    heading_path TEXT NOT NULL,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    exact_source_hash TEXT NOT NULL,
    semantic_hash TEXT NOT NULL,
    source TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
    FOREIGN KEY(file_id) REFERENCES files(file_id) ON DELETE CASCADE,
    FOREIGN KEY(parent_section_id)
        REFERENCES markdown_sections(section_id)
        ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_markdown_sections_project
    ON markdown_sections(project_id);

CREATE INDEX IF NOT EXISTS idx_markdown_sections_file
    ON markdown_sections(file_id);

CREATE INDEX IF NOT EXISTS idx_markdown_sections_hash
    ON markdown_sections(project_id, content_hash);

CREATE INDEX IF NOT EXISTS idx_markdown_sections_heading_path
    ON markdown_sections(project_id, heading_path);

CREATE TABLE IF NOT EXISTS search_documents (
    document_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    entity_id TEXT,
    section_id TEXT,
    source_kind TEXT NOT NULL,
    title TEXT NOT NULL,
    path TEXT NOT NULL,
    content TEXT NOT NULL,
    keywords TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
    FOREIGN KEY(entity_id) REFERENCES entities(entity_id) ON DELETE CASCADE,
    FOREIGN KEY(section_id) REFERENCES markdown_sections(section_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_search_documents_project
    ON search_documents(project_id);

CREATE INDEX IF NOT EXISTS idx_search_documents_entity
    ON search_documents(entity_id);

CREATE INDEX IF NOT EXISTS idx_search_documents_section
    ON search_documents(section_id);

CREATE VIRTUAL TABLE IF NOT EXISTS search_fts USING fts5(
    document_id UNINDEXED,
    project_id UNINDEXED,
    title,
    path,
    content,
    keywords,
    tokenize='unicode61'
);

CREATE TABLE IF NOT EXISTS embeddings (
    cache_key TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    semantic_hash TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    representation_version TEXT NOT NULL,
    vector_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
    FOREIGN KEY(document_id) REFERENCES search_documents(document_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_embeddings_document
    ON embeddings(document_id);

CREATE INDEX IF NOT EXISTS idx_embeddings_lookup
    ON embeddings(semantic_hash, provider, model, representation_version);

CREATE TABLE IF NOT EXISTS summaries (
    cache_key TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    semantic_hash TEXT NOT NULL,
    metadata_hash TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    summary TEXT NOT NULL,
    created_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
    FOREIGN KEY(document_id) REFERENCES search_documents(document_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_summaries_document
    ON summaries(document_id);

CREATE INDEX IF NOT EXISTS idx_summaries_lookup
    ON summaries(semantic_hash, metadata_hash, provider, model, prompt_version);

CREATE TABLE IF NOT EXISTS cache_metadata (
    cache_key TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    cache_layer TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    dependency_hash TEXT,
    implementation_version TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(project_id) REFERENCES projects(project_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_cache_metadata_project
    ON cache_metadata(project_id);

CREATE TABLE IF NOT EXISTS index_jobs (
    job_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    state TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    files_seen INTEGER NOT NULL DEFAULT 0,
    files_changed INTEGER NOT NULL DEFAULT 0,
    files_reused INTEGER NOT NULL DEFAULT 0,
    files_parsed INTEGER NOT NULL DEFAULT 0,
    entities_reused INTEGER NOT NULL DEFAULT 0,
    entities_recomputed INTEGER NOT NULL DEFAULT 0,
    embeddings_reused INTEGER NOT NULL DEFAULT 0,
    embeddings_recomputed INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(project_id) REFERENCES projects(project_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_index_jobs_project
    ON index_jobs(project_id);
"""


def schema_statements() -> list[str]:
    """Return executable schema statements."""
    return [statement.strip() for statement in SCHEMA_SQL.split(";") if statement.strip()]
