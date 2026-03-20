rm -r dist/*
python -m build --sdist
python -m twine upload dist/*.tar.gz
