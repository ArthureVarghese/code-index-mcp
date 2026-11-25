# Indexing

Python is parsed using the standard library AST.

Supported entities include modules, classes, functions, async functions,
methods, nested functions, decorators, imports, annotations and structural
metadata.

Markdown is indexed by document section.

## Incremental workflow

1. Discover candidate files.
2. Calculate exact source hash.
3. Reuse unchanged files.
4. Parse changed files.
5. Extract entities.
6. Match logical identities against previous entities.
7. Compare content hashes.
8. Reuse unchanged entities.
9. Recompute changed entities.
10. Remove deleted entities.
11. Update search units.
12. Update relationships.
13. Commit atomically.

A syntax error in one Python file does not invalidate other files.

