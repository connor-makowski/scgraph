"""Check that the modules of `scgraph` import only from their own layer or a lower one.

`LAYERS` gives the layer of each module (DEVELOPMENT.md and the rework brief, decision D1).
The script reads every `import` of every module under `scgraph/` with `ast`, at the top
of the file and inside functions. It prints each import that goes to a higher layer, and
exits with 1 if one of them is not in `ALLOWED`.

Run it from the root of the repository: `python utils/check_import_layers.py`.
"""

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "scgraph"

# The layer of a module: the dotted name below `scgraph`, or its first part for a
# package (`helpers` holds every module of `scgraph/helpers/`). A module imports only
# from its own layer or a lower one. The package `scgraph` itself is the highest layer.
LAYERS = {
    "deprecations": 0,
    "step_logs": 0,
    "array_checks": 0,
    "utils": 0,
    "errors": 0,
    "files": 0,
    "helpers": 1,
    "network_file": 1,
    "array_views": 1,
    "graph_utils": 2,
    "graph_reducer": 2,
    "graph": 2,
    "contraction_hierarchies": 2,
    "transit_node_routing": 2,
    "grid": 2,
    "edge_classes": 3,
    "metrics": 3,
    "node_snapping": 3,
    "geograph": 4,
    "geograph_files": 4,
    "geograph_edits": 4,
    "geograph_edges": 4,
    "geograph_routing": 4,
    "network_release": 5,
    "networks": 5,
    "built_in_geographs": 5,
    "pipelines": 6,
    "": 7,  # `scgraph/__init__.py`
}

# The imports that go to a higher layer and stay: (importing module, imported module,
# reason). The imported module is the one of the import statement, below `scgraph`
# (an empty string is the package).
ALLOWED = [
    (
        "grid",
        "",
        "`GridGraph` extends the `Graph` that the package chooses: the C++ one when it is built.",
    ),
    (
        "geograph",
        "",
        "`GeoGraph` builds on the `Graph` that the package chooses, and raises its errors.",
    ),
    (
        "geograph_files",
        "",
        "`GeoGraphIO` builds the `Graph` that the package chooses: the C++ one when it is built.",
    ),
    (
        "geograph_edits",
        "",
        "`GeoGraphModifiers` builds the `Graph` that the package chooses: the C++ one when it is built.",
    ),
    (
        "geograph_edges",
        "",
        "`GeoGraphEdges` builds the `Graph` that the package chooses: the C++ one when it is built.",
    ),
    (
        "geograph_files",
        "built_in_geographs",
        "The default of `geograph_url` in the signatures of `load_geograph` and "
        "`list_geographs` is `built_in_geographs.GEOGRAPH_URL`, and a default is "
        "read when the module loads.",
    ),
    (
        "geograph_files",
        "networks",
        "The static methods of `GeoGraph` that release 3.6.0 exposes (`load_geograph` "
        "and the like) import the work from a higher layer inside the function (D1).",
    ),
    (
        "networks",
        "pipelines.network_builder",
        "`build_network` runs the build of a network, and "
        "`list_buildable_networks` reads which pipelines need a region. The "
        "pipelines import `networks` at the top, so these imports are inside the "
        "functions.",
    ),
]


def get_layer(module: str) -> int | None:
    """Return the layer of a module given below `scgraph`, or None if it is unknown."""
    return LAYERS.get(module.split(".")[0] if module else "")


def list_imports(tree: ast.AST) -> list[tuple[int, str, bool]]:
    """Return `(line, module below scgraph, is_inside_function)` of each import of the
    package `scgraph`, other than its C++ extension."""
    found = []

    def visit(node, in_function):
        for child in ast.iter_child_nodes(node):
            if (
                isinstance(child, ast.If)
                and isinstance(child.test, ast.Name)
                and child.test.id == "TYPE_CHECKING"
            ):
                continue  # an import for an annotation: it does not run
            inside = in_function or isinstance(
                child, (ast.FunctionDef, ast.AsyncFunctionDef)
            )
            names = []
            if isinstance(child, ast.Import):
                names = [alias.name for alias in child.names]
            elif isinstance(child, ast.ImportFrom) and child.level == 0:
                base = child.module or ""
                if base == "scgraph":
                    # `from scgraph import X` is the module X, or a name of the package
                    names = [
                        (
                            f"scgraph.{alias.name}"
                            if (ROOT / f"{alias.name}.py").is_file()
                            or (ROOT / alias.name).is_dir()
                            else "scgraph"
                        )
                        for alias in child.names
                    ]
                else:
                    names = [base]
            for name in names:
                if name == "scgraph" or name.startswith("scgraph."):
                    module = name.removeprefix("scgraph").removeprefix(".")
                    if module.split(".")[0] != "cpp":
                        found.append((child.lineno, module, inside))
            visit(child, inside)

    visit(tree, False)
    return found


def main() -> int:
    allowed = {(a, b) for a, b, _ in ALLOWED}
    failures = 0
    for path in sorted(ROOT.rglob("*.py")):
        relative = path.relative_to(ROOT).with_suffix("")
        parts = [part for part in relative.parts if part != "__init__"]
        module = ".".join(parts)
        layer = get_layer(module)
        tree = ast.parse(path.read_text(), filename=str(path))
        if layer is None:
            print(f"{path}: the module `{module}` has no layer in LAYERS")
            failures += 1
            continue
        for line, imported, in_function in list_imports(tree):
            imported_layer = get_layer(imported)
            if imported_layer is None:
                print(f"{path}:{line}: `{imported}` has no layer in LAYERS")
                failures += 1
            elif imported_layer > layer:
                key = (module.split(".")[0], imported)
                is_allowed = key in allowed or (module, imported) in allowed
                where = "inside a function" if in_function else "at the top"
                print(
                    f"{path.relative_to(ROOT.parent)}:{line}: `{module or 'scgraph'}` "
                    f"(layer {layer}) imports `{imported or 'scgraph'}` "
                    f"(layer {imported_layer}) {where}"
                    + ("  [allowed]" if is_allowed else "")
                )
                failures += not is_allowed
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
