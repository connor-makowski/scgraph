#!/bin/bash
cd /app/
# Lint and Autoformat the code in place
# Remove unused imports
autoflake --in-place --remove-all-unused-imports --ignore-init-module-imports -r ./scgraph
# Perform all other steps
black --config pyproject.toml ./scgraph
black --config pyproject.toml ./test
