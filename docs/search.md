# Search

Search is designed around progressive retrieval.

## Code

Code search uses:

- exact symbol matching
- identifier matching
- path matching
- keyword search
- docstrings
- decorators
- AST metadata
- optional semantic search

Exact symbol matches receive the highest ranking.

## Markdown

Markdown search uses:

- headings
- section titles
- keywords
- section content
- file paths
- optional semantic search

## Unified search

`search_project` searches Python and Markdown together.

Results are compact and identify the smallest useful retrieval unit.

The expected workflow is:

1. Search.
2. Select an entity.
3. Retrieve the entity.
4. Find references.
5. Retrieve related code.
