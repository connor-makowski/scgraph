#!/bin/bash
cd /app/

# Make a temp init.py that only has the content below
cp README.md scgraph/__init__.py
sed -i '1s/^/\"\"\"\n/' scgraph/__init__.py
echo "\"\"\"" >> scgraph/__init__.py
echo "" >> scgraph/__init__.py

# Read through the file and replace all \ with \\ (for windows path issues in python docstrings)
sed -i 's|\\|\\\\|g' scgraph/__init__.py

# Add the following import statements to the end of the file:
echo "try:" >> scgraph/__init__.py
echo "    from scgraph.cpp import Graph, CHGraph" >> scgraph/__init__.py
echo "except ImportError:" >> scgraph/__init__.py
echo "    from scgraph.graph import Graph" >> scgraph/__init__.py
echo "    from scgraph.contraction_hierarchies import CHGraph" >> scgraph/__init__.py

echo "from scgraph.geograph import GeoGraph" >> scgraph/__init__.py
echo "from scgraph.grid import GridGraph" >> scgraph/__init__.py



# Specify versions for documentation purposes
VERSION="3.2.1"
OLD_DOC_VERSIONS="2.15.0 1.5.2 0.3.0"
export version_options="$VERSION $OLD_DOC_VERSIONS"

# generate the docs for a version function:
function generate_docs() {
    INPUT_VERSION=$1
    if [ $INPUT_VERSION != "./" ]; then
        if [ $INPUT_VERSION != $VERSION ]; then
            pip install "./dist/scgraph-$INPUT_VERSION.tar.gz"
        fi
    fi
    pdoc -o ./docs/$INPUT_VERSION -t ./doc_template scgraph !scgraph.geographs
}

# Generate the docs for the current version
generate_docs ./
generate_docs $VERSION

# Generate the docs for all the old versions
for version in $OLD_DOC_VERSIONS; do
    generate_docs $version
done;

# Reinstall the current package as an egg
pip install -e .


# Update Jupyter Notebook
# jupyter nbconvert --execute example.ipynb --to notebook --inplace
# jupyter nbconvert --execute example_making_modificaitons --to notebook --inplace
# rm '=2.0.0'