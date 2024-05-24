rm -r ./docs
pdoc -o ./docs scgraph
# Update Jupyter Notebook
# jupyter nbconvert --execute example.ipynb --to notebook --inplace
# jupyter nbconvert --execute example_making_modificaitons --to notebook --inplace
# rm '=2.0.0'