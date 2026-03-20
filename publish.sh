python -m build --sdist
rm -r build 
python -m twine upload dist/*.tar.gz
