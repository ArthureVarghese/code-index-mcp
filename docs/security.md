# Security

The server performs static analysis only.

It never executes indexed Python.

## Filesystem boundary

MCP paths must resolve inside the registered project root.

Parent traversal is rejected after canonicalization.

Symlinks are not followed during project discovery.

## Ignored files

The project ignore layer can exclude generated files, virtual environments,
build directories, dependency caches, and secret files.

## Secrets

Secret files should be excluded through configuration.

The server does not need to execute project code or import modules to index
them.
