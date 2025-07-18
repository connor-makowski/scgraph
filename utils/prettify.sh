#!/bin/bash
cd /app/
# Lint and Autoformat the code in place
# Remove unused imports
autoflake --in-place --remove-all-unused-imports --ignore-init-module-imports -r ./scgraph --exclude=core.py
# Perform all other steps
black --config pyproject.toml ./scgraph
black --config pyproject.toml ./test
