# Cache Architecture

Caching is content-addressed and hierarchical.

## Hash levels

Each source unit can have:

- exact source hash
- semantic hash
- structural hash
- derived-data version

Entity identity is separate from entity content hash.

Example:

`python:src/auth.py:AuthService.validate_token`

is an identity.

Its SHA-256 content hash identifies a particular version.

## Incremental invalidation

Changing one method invalidates the method's source-derived data.

It does not invalidate unrelated methods.

Parent structural data is invalidated only when the parent's structure changes.

Examples:

- implementation-only change: method cache changes
- signature change: method structural cache changes
- new method: method cache and class outline change
- unrelated Markdown section: unaffected

## Derived caches

Embeddings and summaries use their own versioned cache keys.

Embedding cache keys contain:

- semantic hash
- provider
- model
- representation version

Summary cache keys additionally contain:

- metadata hash
- prompt version

## Recovery

Index updates occur transactionally.

The last committed state remains usable if an indexing operation fails.
