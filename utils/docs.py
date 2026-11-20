import json
import os
import subprocess
import sys
from pathlib import Path

root = Path(__file__).parent.parent
scgraph = root / "scgraph" / "__init__.py"

VERSION = "3.6.0"
OLD_DOC_VERSIONS = ["2.15.0", "1.5.2", "0.3.0"]


def update_versions_manifest():
    """Write all available documentation versions to docs/versions.json and docs/versions.js."""
    versions = [VERSION] + OLD_DOC_VERSIONS
    versions_json = root / "docs" / "versions.json"
    versions_json.write_text(json.dumps(versions, indent=2) + "\n")

    versions_js = root / "docs" / "versions.js"
    versions_js.write_text(
        f"window.DOC_VERSIONS = {json.dumps(versions, indent=2)};\n"
    )


def generate_docs(version):
    out_dir = str(root / "docs" / version)
    template_dir = str(root / "doc_template")

    if version != "./" and version != VERSION:
        # One-time rebuild of older versions from dist/ tarballs
        tarball = str(root / "dist" / f"scgraph-{version}.tar.gz")
        subprocess.run(
            [
                "uv",
                "run",
                "--isolated",
                "--with",
                tarball,
                "--with",
                "pdoc",
                "pdoc",
                "-o",
                out_dir,
                "-t",
                template_dir,
                "scgraph",
            ],
            check=True,
            cwd=str(root),
        )
    else:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pdoc",
                "-o",
                out_dir,
                "-t",
                template_dir,
                "./scgraph",
            ],
            check=True,
        )


# Build __init__.py from README
readme = (root / "README.md").read_text()

init_setup = """
from scgraph.graph_reducer import algorithm

try:
    from scgraph.cpp import Graph, CHGraph
    # Assign the python algorithm function to the cpp graph class
    Graph.algorithm = staticmethod(algorithm)
except ImportError:
    from scgraph.graph import Graph
    from scgraph.contraction_hierarchies import CHGraph

from scgraph.geograph import GeoGraph
from scgraph.grid import GridGraph
"""

scgraph.write_text(
    f'r"""\n{readme}\n"""\n\n{init_setup}'
)

# Update the versions manifest loaded dynamically by client-side JS
update_versions_manifest()

# Generate current docs
print(f"Generating docs for current version ({VERSION}) and root...")
generate_docs("./")
generate_docs(VERSION)

# Rebuild old versions if '--rebuild-old' is passed or when executed
if "--rebuild-old" in sys.argv or "--all" in sys.argv:
    for version in OLD_DOC_VERSIONS:
        print(f"Rebuilding docs for version {version}...")
        generate_docs(version)
