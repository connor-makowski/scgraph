uv run python3 -m build --sdist
uv run python3 -m twine upload dist/*.tar.gz
