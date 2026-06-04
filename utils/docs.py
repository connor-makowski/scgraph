import os
import subprocess
import sys
from pathlib import Path

root = Path(__file__).parent.parent
scgraph = root / "scgraph" / "__init__.py"


VERSION = "3.4.0"
OLD_DOC_VERSIONS = ["2.15.0", "1.5.2", "0.3.0"]

env = {
    **os.environ,
    "version_options": " ".join([VERSION] + OLD_DOC_VERSIONS),
}


def generate_docs(version):
    out_dir = str(root / "docs" / version)
    template_dir = str(root / "doc_template")

    if version != "./" and version != VERSION:
        # Use an isolated environment per old version so their (older)
        # dependencies don't clobber the current venv.
        tarball = str(root / "dist" / f"scgraph-{version}.tar.gz")
        subprocess.run(
            [
                "uv", "run", "--isolated",
                "--with", tarball,
                "--with", "pdoc",
                "pdoc", "-o", out_dir, "-t", template_dir, "scgraph",
            ],
            check=True,
            env=env,
            cwd=str(root),
        )
    else:
        subprocess.run(
            [sys.executable, "-m", "pdoc", "-o", out_dir, "-t", template_dir, "scgraph"],
            check=True,
            env=env,
        )


# Build __init__.py from README
readme = (root / "README.md").read_text().replace("\\","\\\\")

init_setup = """
try:
    from scgraph.cpp import Graph, CHGraph
except ImportError:
    from scgraph.graph import Graph
    from scgraph.contraction_hierarchies import CHGraph
    
from scgraph.geograph import GeoGraph
from scgraph.grid import GridGraph
"""

scgraph.write_text(f'"""\n{readme}\n"""\n{init_setup}\n')

generate_docs("./")
generate_docs(VERSION)
for version in OLD_DOC_VERSIONS:
    generate_docs(version)

# Update Jupyter Notebook
# jupyter nbconvert --execute example.ipynb --to notebook --inplace
# jupyter nbconvert --execute example_making_modificaitons --to notebook --inplace
# rm '=2.0.0'