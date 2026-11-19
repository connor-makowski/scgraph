"""Derive a network file from another network file, with no download.

WHAT IT ANSWERS

The network `world_multimodal` holds the roads, the railways, the sea lanes and the
flights of the world. `derive_file` takes a network file, the "parent file". It
writes a smaller network as a new network file, the "derived file". The derived file
holds some modes of the parent file, and its land networks inside a "bbox". A bbox
is a rectangle of latitudes and longitudes: `(south, west, north, east)`, in degrees.
A "view" is a named choice of modes and of bbox. `VIEWS` lists the views of
`world_multimodal` for a data release.

Each route of the derived file is a route of the parent file, with the same length.

WHAT IT READS

A pipeline with several modes built the parent file, for example `world_multimodal`.
The file holds the mode of each node and the shape of each arc. Its coordinates are
int32 values, in units of 1e-7 degree. `derive_file` maps the parent file, and
copies into memory only the nodes and the arcs that it keeps.

HOW A RUN GOES

1. Select the nodes. A node is selected when its mode is one of `modes`. A node of a
   land mode (`LAND_MODES`) must also be inside `bbox`. The bbox does not cut the
   other modes: their nodes all stay. A `modes` of None keeps every mode. A `bbox`
   of None cuts nothing.
2. Cut the graph. An arc stays when its two ends are selected.
3. Keep each strongly connected component of at least `min_component_nodes` nodes.
   An arc between two components is dropped. The chains are not contracted again: a
   junction that lost a road in step 2 stays as a node.
4. Write the derived file. Its nodes keep the order of the parent file: by mode, then
   along a Hilbert curve. Its modes table holds the kept modes only. As in every
   network file, a derived file with one mode has no `node_modes`.

Example: a two-way road joins the nodes 1, 2 and 3 along the equator, with 3 km
between two nodes. A second two-way road goes from node 2 to node 4, which is two
degrees north. Node 10 is a port, 1 km from node 3 and 11 km from the sea node 20. A
sea lane of 5550 km joins node 20 to the sea node 21, at 50 degrees east. The call
gives the bbox (-1, -1, 1, 1) and `min_component_nodes=1`.

- Step 1 selects the nodes 1, 2 and 3: they are road nodes inside the bbox. It
  selects the nodes 10, 20 and 21: the bbox does not cut their modes, and node 21 is
  outside it. Node 4 is a road node outside the bbox, so it is not selected.
- Step 2 drops the two arcs between the nodes 2 and 4.
- Step 3 keeps the six nodes. Every arc has an arc back, so they are one component.
  Node 2 stays between the nodes 1 and 3.

The derived file has 6 nodes and 10 arcs. Its route from node 1 to node 21 is
3 + 3 + 1 + 11 + 5550 = 5568 km long, as in the parent file.

WHY THE RESULT IS RIGHT

The steps only remove nodes and arcs. Each arc of the derived file is an arc of the
parent file, with its length. So each route of the derived file is a route of the
parent file, with the same length. The parent file can hold a shorter route between
the same two nodes. Such a route uses a node or an arc that the derived file does not
hold: for example an arc between two kept components, which step 3 drops.

WHAT THE HEADER OF A DERIVED FILE RECORDS

- `pipeline`: the pipeline of the parent file. The header has no `description`: the
  description of the parent file names modes that the derived file may not hold;
- `sources`: the sources of the parent file that serve the derived file. A mode cites
  the source of its node ids in the modes table. A source is removed when only
  removed modes cite it. A source that no mode cites is kept, because the header
  does not record the modes that use it;
- `software`: the software that derived the file;
- `derivation`: the `parent_content_sha256`, and the `modes`, the `bbox` and the
  `min_component_nodes` of the call.

HOW A DERIVED FILE IS VALIDATED

`validate_derived_file` reads the validation cases of the pipeline of the parent
file. It selects a case when two conditions hold. The two ends of the case are inside
the bbox. The derived file holds the modes on which the kind of the case searches its
routes (`RULES` of `stage4_validation`). Some kinds search on every mode: the derived
file must then hold every mode of the parent file.

The derived file passes when it fails no selected case that the parent file passes.
A case that fails in both files does not show a defect of the derivation.

Example: `world_multimodal` has no road route from Kota Kinabalu to Pontianak, so it
fails the case `kota_kinabalu_mys`. The view `east_southeast_asia` fails this case
too, and it passes its validation.

THE COMMAND LINE

`python -m scgraph.pipelines.derive PARENT_FILE VIEW OUTPUT_DIR` writes
`OUTPUT_DIR/VIEW.scgraph` and prints its path. `--help` lists the options.
"""

import argparse
import importlib
import logging
import os
from array import array
from collections.abc import Sequence

from scgraph import network_file, pipelines
from scgraph.pipelines.steps.stage3_assembly import assembly
from scgraph.pipelines.steps.stage4_validation import (
    RULES,
    load_cases,
    validate_network,
)
from scgraph.utils import _log_step

logger = logging.getLogger(__name__)

# The modes that a bbox cuts. The nodes of the other modes (`sea`, `port`,
# `airport`) all stay. A route can then leave the bbox by sea or by air, and reach a
# port or an airport outside it.
LAND_MODES = ("road", "rail", "rail_terminal")
# The bbox of a call without a bbox: every point is inside it.
_WHOLE_GLOBE = (-90, -180, 90, 180)
# The views of `world_multimodal` for a data release, as `name: (modes, bbox)`.
# These are the arguments of `derive_file`. A `modes` of None keeps every mode. A
# bbox is (south, west, north, east), in degrees.
VIEWS: dict[str, tuple[list[str] | None, Sequence[float] | None]] = {
    "world_sea": (["sea", "port"], None),
    "world_rail": (["rail", "rail_terminal"], None),
    "europe": (None, (34, -25, 72, 45)),
    "north_america": (None, (7, -170, 84, -50)),
    "south_america": (None, (-57, -82, 13, -34)),
    "africa": (None, (-35, -18, 38, 52)),
    "west_south_asia": (None, (5, 25, 45, 98)),
    "east_southeast_asia": (None, (-11, 92, 55, 150)),
    "north_asia": (None, (40, 45, 78, 180)),
    "oceania": (None, (-50, 110, 0, 180)),
}


def derive_file(
    parent_file: str | os.PathLike,
    derived_file: str | os.PathLike,
    modes: list[str] | None = None,
    bbox: Sequence[float] | None = None,
    *,
    keep_shapes: bool = True,
    min_component_nodes: int = 10,
) -> str:
    """Write a smaller network from a network file as a new network file: some of its
    modes, and its land networks inside a bbox. The module docstring gives the steps.

    Args:
        parent_file: The network file to derive from. It holds several modes, the
            shapes of its arcs, and int32 coordinates.
        derived_file: The path of the network file to write.
        modes: The names of the modes to keep. None keeps every mode.
        bbox: `(south, west, north, east)`, in degrees. A node of `LAND_MODES`
            outside the bbox is removed. None removes no node.
        keep_shapes: False writes the same network without the shapes of its arcs.
        min_component_nodes: The smallest number of nodes of a kept strongly
            connected component. The default removes a node that the cut left
            alone, and keeps the roads of a small island.

    Returns:
        The `content_sha256` of the derived file.

    Raises:
        ValueError: The south of the bbox is above its north, or its west is beyond
            its east. Or the parent file has one mode only, no arc shapes, or
            float64 coordinates. Or `modes` names a mode that the parent file does
            not have. Or the derived file would hold no node.
    """
    # The bbox takes the unit of the node points: 1e-7 degree
    south, west, north, east = (
        round(degrees * 1e7) for degrees in bbox or _WHOLE_GLOBE
    )
    if south > north or west > east:
        raise ValueError(
            f"bbox {bbox} has its south above its north, or its west beyond "
            "its east: a bbox is (south, west, north, east)"
        )
    parent_arrays, parent_metadata = network_file.read(parent_file, mapped=True)
    if (
        not {"node_modes", "shape_points"} <= set(parent_arrays)
        or network_file.coordinate_dtype(parent_arrays) != "int32"
    ):
        raise ValueError(
            f"{parent_file} has one mode, no arc shapes or float64 coordinates: "
            "a parent file needs several modes, arc shapes and int32 coordinates"
        )
    mode_names = [mode["name"] for mode in parent_metadata["modes"]]
    unknown = sorted(set(modes or ()) - set(mode_names))
    if unknown:
        raise ValueError(f"{parent_file} has no mode named {unknown}")
    # The rows of the modes table of the parent file that the derived file keeps
    kept_mode_rows = [
        row
        for row, name in enumerate(mode_names)
        if modes is None or name in modes
    ]
    with _log_step(
        logger,
        "select the nodes",
        assembly._count_nodes_and_arcs(parent_arrays),
    ) as counts:
        # 1. Select the nodes
        land_rows = {
            row for row in kept_mode_rows if mode_names[row] in LAND_MODES
        }
        node_points = parent_arrays["node_points"]
        latitudes, longitudes = node_points[0::2], node_points[1::2]
        selected = array(
            "i",
            (
                u
                for u, row in enumerate(parent_arrays["node_modes"])
                if row in kept_mode_rows
                and (
                    row not in land_rows
                    or (
                        (south <= latitudes[u] <= north)
                        and (west <= longitudes[u] <= east)
                    )
                )
            ),
        )
        # 2. Cut the graph. Node `selected[i]` becomes node `i`.
        graph = assembly._renumbered(parent_arrays, selected)
        counts.update(assembly._count_nodes_and_arcs(graph, "kept_"))
    with _log_step(
        logger,
        "keep the strongly connected components",
        assembly._count_nodes_and_arcs(graph),
    ) as counts:
        # 3. Keep the strongly connected components
        kept_nodes, component_of_node = (
            assembly.keep_strongly_connected_components(
                graph["offsets"], graph["heads"], min_component_nodes
            )
        )
        if not len(kept_nodes):
            raise ValueError(
                f"{parent_file} has no component of {min_component_nodes} nodes "
                "or more with these modes inside the bbox"
            )
        # An arc between two components is dropped
        graph = assembly._renumbered(graph, kept_nodes, component_of_node)
        counts.update(assembly._count_nodes_and_arcs(graph, "kept_"))
    # 4. Write the derived file. `selected` and `kept_nodes` are in rising order, so
    # two kept nodes are in the order that they have in the parent file.
    if len(kept_mode_rows) == 1:
        del graph["node_modes"]  # a network file with one mode has none
    else:  # a kept mode takes its row in the new modes table
        row_translation = bytes.maketrans(
            bytes(kept_mode_rows), bytes(range(len(kept_mode_rows)))
        )
        graph["node_modes"] = array(
            "B", graph["node_modes"].tobytes().translate(row_translation)
        )
    if not keep_shapes:
        del graph["shape_offsets"], graph["shape_points"]
    kept_modes = [parent_metadata["modes"][row] for row in kept_mode_rows]
    removed_sources = {
        mode.get("source") for mode in parent_metadata["modes"]
    } - {mode.get("source") for mode in kept_modes}
    metadata = pipelines.build_metadata(
        **parent_metadata["pipeline"],
        sources=[
            source
            for source in parent_metadata["sources"]
            if source["name"] not in removed_sources
        ],
    )
    metadata["derivation"] = {
        "parent_content_sha256": parent_metadata["content_sha256"],
        "modes": modes,
        "bbox": bbox,
        "min_component_nodes": min_component_nodes,
    }
    return network_file.write(
        derived_file,
        graph,
        network_file.header_metadata(
            metadata, units=parent_metadata["units"], modes=kept_modes
        ),
    )


def validate_derived_file(
    derived_file: str | os.PathLike, parent_file: str | os.PathLike
) -> None:
    """Check that a derived file fails no validation case that its parent file
    passes. The header of the derived file gives the pipeline, the modes and the
    bbox. The module docstring says which cases are selected.

    Args:
        derived_file: A network file that `derive_file` wrote.
        parent_file: The network file that `derived_file` was derived from.

    Raises:
        ValueError: The header of `derived_file` has no `derivation`.
        RuntimeError: The derived file fails a case that the parent file passes.
    """
    info = network_file.get_scgraph_info(derived_file)
    if "derivation" not in info:
        raise ValueError(
            f"{derived_file} has no derivation in its header: "
            "validate_derived_file needs a file that derive_file wrote"
        )
    parent_pipeline, derivation = info["pipeline"], info["derivation"]
    modes = derivation["modes"]
    south, west, north, east = derivation["bbox"] or _WHOLE_GLOBE

    def is_selected(case):
        # A kind with an empty tuple of modes searches its routes on every mode
        case_modes = RULES[case["kind"]][0]
        has_the_modes = modes is None or (
            bool(case_modes) and set(case_modes) <= set(modes)
        )
        is_inside_the_bbox = all(
            (south <= latitude <= north) and (west <= longitude <= east)
            for latitude, longitude in (case["origin"], case["destination"])
        )
        return has_the_modes and is_inside_the_bbox

    pipeline = importlib.import_module(
        f"scgraph.pipelines.{parent_pipeline['name']}"
    )
    cases = [
        case
        for case in load_cases(pipeline.VALIDATION, parent_pipeline["region"])
        if is_selected(case)
    ]

    def find_failed_cases(file):
        return {
            failure["id"] for failure in validate_network(file, cases).failures
        }

    failed = find_failed_cases(derived_file)
    if failed:  # the parent file can be the world file: it is loaded only then
        failed -= find_failed_cases(parent_file)
    logger.info(
        "%s: %d selected case(s), %d failed in this file only",
        derived_file,
        len(cases),
        len(failed),
    )
    if failed:
        raise RuntimeError(
            f"{derived_file} fails {len(failed)} case(s) that its parent file "
            f"passes: {', '.join(sorted(failed))}"
        )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m scgraph.pipelines.derive",
        description="Derive a view from a network file, with no download, and "
        "print the path of the derived file.",
    )
    parser.add_argument("parent_file", help="the network file to derive from")
    parser.add_argument("view", choices=VIEWS, help="the view to derive")
    parser.add_argument("output_dir", help="the folder of the derived file")
    parser.add_argument(
        "--no-shapes",
        action="store_true",
        help="write VIEW.no_shapes.scgraph: the same network without the shapes "
        "of its arcs",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="check that the derived file fails no validation case that the "
        "parent file passes; a file that fails stays in the folder",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO)  # the count of validation cases
    suffix = ".no_shapes" if args.no_shapes else ""
    path = os.path.join(args.output_dir, f"{args.view}{suffix}.scgraph")
    try:
        derive_file(
            args.parent_file,
            path,
            *VIEWS[args.view],
            keep_shapes=not args.no_shapes,
        )
        if args.validate:
            validate_derived_file(path, args.parent_file)
        print(path)  # noqa: T201 (the output of the command)
    except (
        ValueError,
        FileNotFoundError,
        RuntimeError,
    ) as error:  # the message says what to change: no traceback
        parser.exit(2, f"{error}\n")


if __name__ == "__main__":
    main()
