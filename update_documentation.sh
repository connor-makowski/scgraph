pdoc scgraph/ --force --html -o docs
mv ./docs/scgraph/* ./docs
rm -r ./docs/scgraph
# Update Jupyter Notebook
jupyter nbconvert --execute example.ipynb --to notebook --inplace
rm '=1.0.0'