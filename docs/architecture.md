# Architecture

Code Index MCP is divided into six primary layers.

## MCP

The MCP layer exposes agent-facing tools and translates requests into
application operations.

It does not own persistence or indexing logic.

## Project

The project layer identifies projects, manages project metadata, and selects
the appropriate local SQLite index.

## Indexing

The indexing layer discovers files, calculates hashes, parses Python and
Markdown, matches entities against previous versions, and performs incremental
updates.

## Cache

The cache layer tracks derived information and invalidation dependencies.

Cache keys are based on stable content hashes rather than timestamps.

## Search

Search combines symbol matching, SQLite FTS/keyword matching, ranking, and
optional semantic search.

## Retrieval

Retrieval converts a search result into bounded context.

The default behavior is entity-level retrieval rather than complete-file
retrieval.

## Storage

SQLite is the persistence boundary.

The storage interface is intentionally independent from MCP, allowing a future
search or storage implementation to replace SQLite without changing MCP tools.
