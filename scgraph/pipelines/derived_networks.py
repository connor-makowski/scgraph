"""Derive a network file from another network file, with no download.

WHAT IT ANSWERS

The network `world_multimodal` holds the roads, the railways, the sea lanes and the
flights of the world. `derive_network_file` takes a network file, the "parent file". It
writes a smaller network as a new network file, the "derived file". The node mode of a
node is the kind of place where the node is, such as `road` or `port`. The derived file
holds some node modes of the parent file, and its land networks inside a "bbox". A bbox
is a rectangle of latitudes and longitudes: `(south, west, north, east)`, in degrees. A
network release publishes `world_multimodal` and the networks derived from it.
`DERIVED_NETWORKS` names each derived network, with its node modes or its bbox.
`derive_network_release_files` writes all the derived files of a network release.

Each route of the derived file is a route of the parent file, with the same length.

WHAT IT READS

A pipeline with several node modes built the parent file, for example
`osm_world_multimodal`. The file holds the node mode of each node and the shape of each
edge. Its coordinates are int32 values, in units of 1e-7 degree. `derive_network_file`
maps the parent file, and copies into memory only the nodes and the edges that it keeps.

HOW A RUN GOES

1. Select the nodes. A node is selected when its node mode is one of `node_modes`. A
   node of a land node mode (`LAND_MODES`) must also be inside `bbox`. The bbox does not
   cut the other node modes: their nodes all stay. A `node_modes` of None keeps every
   node mode. A `bbox` of None cuts nothing.
2. Cut the graph. An edge stays when its two ends are selected.
3. Keep each strongly connected component of at least `min_component_nodes` nodes.
   An edge between two components is dropped. The chains are not contracted again: a
   junction that lost a road in step 2 stays as a node.
4. Write the derived file. Its nodes keep the order of the parent file: by node mode,
   then along a Hilbert curve. Its node modes table holds the kept node modes only,
   each with the count of its nodes. If the parent file has `edge_class_ids`, each kept edge keeps its class, and the derived
   file holds the whole list of classes. The derived file holds the lengths of the
   edges, and no other metric of the parent file.

Example: a two-way road joins the nodes 1, 2 and 3 along the equator, with 3 km
between two nodes. A second two-way road goes from node 2 to node 4, which is two
degrees north. Node 10 is a port, 1 km from node 3 and 11 km from the sea node 20. A
sea lane of 5550 km joins node 20 to the sea node 21, at 50 degrees east. The call
gives the bbox (-1, -1, 1, 1) and `min_component_nodes=1`.

- Step 1 selects the nodes 1, 2 and 3: they are road nodes inside the bbox. It selects
  the nodes 10, 20 and 21: the bbox does not cut their node modes, and node 21 is
  outside it. Node 4 is a road node outside the bbox, so it is not selected.
- Step 2 drops the two edges between the nodes 2 and 4.
- Step 3 keeps the six nodes. Every edge has an edge back, so they are one component.
  Node 2 stays between the nodes 1 and 3.

The derived file has 6 nodes and 10 edges. Its route from node 1 to node 21 is
3 + 3 + 1 + 11 + 5550 = 5568 km long, as in the parent file.

WHY THE RESULT IS RIGHT

The steps only remove nodes and edges. Each edge of the derived file is an edge of the
parent file, with its length. So each route of the derived file is a route of the
parent file, with the same length. The parent file can hold a shorter route between
the same two nodes. Such a route uses a node or an edge that the derived file does not
hold: for example an edge between two kept components, which step 3 drops.

WHAT THE HEADER OF A DERIVED FILE RECORDS

- `pipeline`: the pipeline of the parent file. The header has no `description`: the
  description of the parent file names networks that the derived file may not hold;
- `sources`: the sources of the parent file that serve the derived file. A node mode
  uses the source of its node ids, which the node modes table names. The node mode
  `airport` also uses the source `flights`, because a flight joins two airports. A
  source is removed when only removed node modes use it. A source that no node mode uses
  is kept, because the header does not record what uses it. For example, the land mask
  of the connectors uses Natural Earth;
- `software`: the software that derived the file;
- `derivation`: the `parent_content_sha256`, and the `node_modes`, the `bbox` and the
  `min_component_nodes` of the call.

HOW A DERIVED FILE IS VALIDATED

`validate_derived_network_file` reads the validation cases of the pipeline of the parent
file. It selects a case when two conditions hold. The two ends of the case are inside
the bbox. The derived file holds the node modes on which the kind of the case searches
its routes (`RULES` of `step4_validation_cases`). Some kinds search on every node mode:
the derived file must then hold every node mode of the parent file.

The derived file passes when it fails no selected case that the parent file passes.
A case that fails in both files does not show a defect of the derivation.

Example: `world_multimodal` has no road route from Kota Kinabalu to Pontianak, so it
fails the case `kota_kinabalu_mys`. The derived network `east_southeast_asia` fails
this case too, and it passes its validation.

THE COMMAND LINE

`python -m scgraph.pipelines.derived_networks WORLD_FILE OUTPUT_DIR` writes the derived files
of a network release into `OUTPUT_DIR`, and prints their paths. With names after
`OUTPUT_DIR`, it writes these derived networks only, for example `oceania`.
`--help` lists the options.
"""

import argparse
import importlib
import logging
import os
from array import array
from collections.abc import Sequence

from scgraph import network_assembly, network_file, pipelines
from scgraph.coordinates import encode_coordinate
from scgraph.geograph_networks import get_released_file_name
from scgraph.node_modes import build_node_mode_ids, list_node_mode_names
from scgraph.pipelines.steps.step4_validation_cases import (
    RULES,
    load_validation_cases,
    validate_network,
)
from scgraph.step_logs import log_step

logger = logging.getLogger(__name__)

__all__ = ["derive_network_file"]

# The node modes that a bbox cuts. The nodes of the other node modes (`sea`, `port`,
# `airport`) all stay. A route can then leave the bbox by sea or by air, and reach a
# port or an airport outside it.
LAND_MODES = ("road", "rail", "rail_terminal")
# The source of the edges of a node mode, when it is not the source of its node ids. A
# flight joins two airports: a file without the node mode `airport` holds no flight.
_EDGE_SOURCE_OF_MODE = {"airport": "flights"}
# The bbox of a call without a bbox: every point is inside it.
_WHOLE_GLOBE = (-90, -180, 90, 180)
# The networks that a network release derives from the file of `world_multimodal`.
# An entry gives the arguments of `derive_network_file` for one network. `node_modes`
# names the node modes to keep. `bbox` is the rectangle that cuts the land networks, as
# (south, west, north, east) in degrees.
DERIVED_NETWORKS: dict[str, dict] = {
    "world_sea": {"node_modes": ["sea", "port"]},
    "world_rail": {"node_modes": ["rail", "rail_terminal"]},
    "europe": {"bbox": (34, -25, 72, 45)},
    "north_america": {"bbox": (7, -170, 84, -50)},
    "south_america": {"bbox": (-57, -82, 13, -34)},
    "africa": {"bbox": (-35, -18, 38, 52)},
    "west_south_asia": {"bbox": (5, 25, 45, 98)},
    "east_southeast_asia": {"bbox": (-11, 92, 55, 150)},
    "north_asia": {"bbox": (40, 45, 78, 180)},
    "oceania": {"bbox": (-50, 110, 0, 180)},
}
# The description of each derived network that keeps some node modes of the world.
# `describe_derived_network` writes the sentence of a network with a bbox.
_MODE_NETWORK_DESCRIPTIONS = {
    "world_sea": "Sea lanes and ports of the world",
    "world_rail": "Railways and rail terminals of the world",
}


def describe_derived_network(name: str) -> str:
    """Return the sentence that describes a derived network in a network release.

    `GeoGraph.list_geographs` shows this sentence. It comes from the entry of the
    network in `DERIVED_NETWORKS`, so it always gives the bbox that cut the network.

    Args:
        name: The name of a network of `DERIVED_NETWORKS`.

    Returns:
        The description of the network, in one sentence.
    """
    bbox = DERIVED_NETWORKS[name].get("bbox")
    if bbox is None:
        return _MODE_NETWORK_DESCRIPTIONS[name]
    south, west, north, east = bbox
    return (
        f"The part of world_multimodal between latitudes {south} and {north} and "
        f"longitudes {west} and {east}, with every sea lane, port and airport of "
        "the world"
    )


def derive_network_file(
    parent_file: str | os.PathLike,
    derived_file: str | os.PathLike,
    node_modes: str | list[str] | None = None,
    bbox: Sequence[float] | None = None,
    *,
    save_intermediate_nodes: bool = True,
    min_component_nodes: int = 10,
) -> str:
    """Write a smaller network file from a network file: some of its node modes, and
    its land networks inside a bbox. The module docstring gives the steps.

    Args:
        parent_file: The network file to derive from. It holds several node modes, the
            shapes of its edges, and int32 coordinates.
        derived_file: The path of the network file to write.
        node_modes: The name of the node mode to keep, or a list of names. None
            keeps every node mode.
        bbox: `(south, west, north, east)`, in degrees. A node of `LAND_MODES`
            outside the bbox is removed. None removes no node.
        save_intermediate_nodes: False writes the same network without the
            intermediate nodes of its edges.
        min_component_nodes: The smallest number of nodes of a kept strongly
            connected component. The default removes a node that the cut left
            alone, and keeps the roads of a small island.

    Returns:
        The `content_sha256` of the derived file.

    Raises:
        ValueError: The south of the bbox is above its north, or its west is beyond
            its east. Or the parent file has one node mode only, no edge shapes, or
            float64 coordinates. Or `node_modes` names a node mode that the parent file
            does not have. Or the derived file would hold no node.
    """
    if isinstance(node_modes, str):
        node_modes = [node_modes]
    # The bbox takes the unit of the node points: 1e-7 degree
    south, west, north, east = (
        encode_coordinate(degrees) for degrees in bbox or _WHOLE_GLOBE
    )
    if south > north or west > east:
        raise ValueError(
            f"bbox {bbox} has its south above its north, or its west beyond "
            "its east: a bbox is (south, west, north, east)"
        )
    parent_arrays, parent_metadata = network_file.read(parent_file, mapped=True)
    if (
        len(parent_metadata.get("node_modes", ())) < 2
        or "shape_points" not in parent_arrays
        or network_file.get_coordinate_dtype(parent_arrays) != "int32"
    ):
        raise ValueError(
            f"{parent_file} has one node mode, no edge shapes or float64 coordinates: "
            "a parent file needs several node modes, edge shapes and int32 coordinates"
        )
    node_mode_names = list_node_mode_names(
        parent_metadata["node_modes"],
        node_modes or (),
        f"{parent_file}: node_modes",
    )
    # The graphs of the pipelines hold the node mode id of each node
    parent_arrays["node_mode_ids"] = build_node_mode_ids(
        parent_metadata["node_modes"]
    )
    # The ids of the node modes of the parent file that the derived file keeps
    kept_node_mode_ids = [
        node_mode_id
        for node_mode_id, name in enumerate(node_mode_names)
        if node_modes is None or name in node_modes
    ]
    with log_step(
        logger,
        "select the nodes",
        network_assembly.count_nodes_and_edges(parent_arrays),
    ) as counts:
        # 1. Select the nodes
        land_node_mode_ids = {
            node_mode_id
            for node_mode_id in kept_node_mode_ids
            if node_mode_names[node_mode_id] in LAND_MODES
        }
        node_points = parent_arrays["node_points"]
        latitudes, longitudes = node_points[0::2], node_points[1::2]
        selected = array(
            "i",
            (
                u
                for u, node_mode_id in enumerate(parent_arrays["node_mode_ids"])
                if node_mode_id in kept_node_mode_ids
                and (
                    node_mode_id not in land_node_mode_ids
                    or (
                        (south <= latitudes[u] <= north)
                        and (west <= longitudes[u] <= east)
                    )
                )
            ),
        )
        # 2. Cut the graph. Node `selected[i]` becomes node `i`.
        graph = network_assembly.renumber_nodes(parent_arrays, selected)
        counts.update(network_assembly.count_nodes_and_edges(graph, "kept_"))
    with log_step(
        logger,
        "keep the strongly connected components",
        network_assembly.count_nodes_and_edges(graph),
    ) as counts:
        # 3. Keep the strongly connected components. A junction with several
        # nodes keeps them all (`scgraph/turn_restrictions.py`).
        kept_nodes, component_of_node = network_assembly.keep_junctions_whole(
            graph,
            *network_assembly.keep_strongly_connected_components(
                graph["node_first_edge_ids"],
                graph["edge_destination_node_ids"],
                min_component_nodes,
            ),
        )
        if not len(kept_nodes):
            raise ValueError(
                f"{parent_file} has no component of {min_component_nodes} nodes "
                "or more with these node modes inside the bbox"
            )
        # An edge between two components is dropped
        graph = network_assembly.renumber_nodes(
            graph, kept_nodes, component_of_node
        )
        counts.update(network_assembly.count_nodes_and_edges(graph, "kept_"))
    # 4. Write the derived file. `selected` and `kept_nodes` are in rising order, so
    # two kept nodes are in the order that they have in the parent file.
    # A kept node mode takes its id in the new node modes table
    node_mode_id_translation = bytes.maketrans(
        bytes(kept_node_mode_ids), bytes(range(len(kept_node_mode_ids)))
    )
    node_mode_ids = graph.pop("node_mode_ids").tobytes()
    if not save_intermediate_nodes:
        del graph["edge_first_shape_point_ids"], graph["shape_points"]
    kept_modes = [
        {
            key: value
            for key, value in parent_metadata["node_modes"][
                node_mode_id
            ].items()
            if key != "node_count"
        }
        for node_mode_id in kept_node_mode_ids
    ]

    def find_used_sources(node_modes):
        return {mode.get("source") for mode in node_modes} | {
            _EDGE_SOURCE_OF_MODE.get(mode["name"]) for mode in node_modes
        }

    removed_sources = find_used_sources(
        parent_metadata["node_modes"]
    ) - find_used_sources(kept_modes)
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
        "node_modes": node_modes,
        "bbox": bbox,
        "min_component_nodes": min_component_nodes,
    }
    return network_file.write(
        derived_file,
        graph,
        network_file.build_header_metadata(
            metadata,
            node_modes=kept_modes,
            node_mode_ids=node_mode_ids.translate(node_mode_id_translation),
            # The derived file holds the lengths, and no other metric
            metrics=parent_metadata["metrics"][:1],
            classes=parent_metadata.get("classes"),
        ),
    )


def validate_derived_network_file(
    derived_file: str | os.PathLike, parent_file: str | os.PathLike
) -> None:
    """Check that a derived file fails no validation case that its parent file
    passes. The header of the derived file gives the pipeline, the node modes and the
    bbox. The module docstring gives the rule that selects a case.

    Args:
        derived_file: A network file that `derive_network_file` wrote.
        parent_file: The network file that `derived_file` was derived from.

    Raises:
        ValueError: The header of `derived_file` has no `derivation`. Or this version
            of scgraph does not have the pipeline that built the parent file.
        RuntimeError: The derived file fails a case that the parent file passes.
    """
    info = network_file.get_scgraph_info(derived_file)
    if "derivation" not in info:
        raise ValueError(
            f"{derived_file} has no derivation in its header: "
            "validate_derived_network_file needs a file that derive_network_file wrote"
        )
    parent_pipeline, derivation = info["pipeline"], info["derivation"]
    node_modes = derivation["node_modes"]
    south, west, north, east = derivation["bbox"] or _WHOLE_GLOBE

    def is_selected(case):
        # A kind without node modes searches its routes on every node mode
        case_modes = RULES[case["kind"]][0]
        has_the_modes = node_modes is None or (
            bool(case_modes) and set(case_modes) <= set(node_modes)
        )
        is_inside_the_bbox = all(
            (south <= latitude <= north) and (west <= longitude <= east)
            for latitude, longitude in (case["origin"], case["destination"])
        )
        return has_the_modes and is_inside_the_bbox

    try:
        pipeline = importlib.import_module(
            f"scgraph.pipelines.{parent_pipeline['name']}"
        )
    except ModuleNotFoundError:
        # The cases of a file are those of the pipeline that built its parent file
        raise ValueError(
            f"{parent_file} was built by the pipeline "
            f"'{parent_pipeline['name']}', which this version of scgraph does not "
            "have: its derived files cannot be validated (`run_validation_cases=False`, or "
            "`--no-validate` on the command line)"
        ) from None
    cases = [
        case
        for case in load_validation_cases(
            pipeline.VALIDATION, parent_pipeline["region"]
        )
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


def derive_network_release_files(
    world_file: str | os.PathLike,
    output_dir: str | os.PathLike,
    names: Sequence[str] | None = None,
    *,
    run_validation_cases: bool = True,
) -> list[str]:
    """Write the derived files of a network release into `output_dir`.

    A network release publishes each network as two files: `<name>.scgraph`, and
    `<name>.no_shapes.scgraph` without the shapes of the edges. The function writes
    these two files for each derived network. Without `names`, it also writes
    `world_multimodal.no_shapes.scgraph`, the world file without its shapes.

    Args:
        world_file: The network file of `world_multimodal`, with the shapes of its
            edges.
        output_dir: The folder of the derived files. It must exist.
        names: The names of the derived networks to write, among `DERIVED_NETWORKS`.
            None writes every derived network.
        run_validation_cases: Check each derived network with `validate_derived_network_file`. The two
            files of a network hold the same network, so the function checks only
            the file with shapes.

    Returns:
        The paths of the written files, in the order of their writing.

    Raises:
        ValueError: A name is not in `DERIVED_NETWORKS`, or a derived network is
            empty. Or `run_validation_cases` is on and this version of scgraph does not have
            the pipeline that built the world file.
        RuntimeError: A derived network fails a validation case that the world
            file passes.
    """
    selected = list(DERIVED_NETWORKS) if names is None else list(names)
    unknown = [name for name in selected if name not in DERIVED_NETWORKS]
    if unknown:
        raise ValueError(
            f"Unknown derived network {unknown[0]!r}: the derived networks are "
            f"{', '.join(DERIVED_NETWORKS)}"
        )
    written = []
    for name in selected:
        with_shapes = os.path.join(
            output_dir, get_released_file_name(name, has_shapes=True)
        )
        derive_network_file(world_file, with_shapes, **DERIVED_NETWORKS[name])
        if run_validation_cases:
            validate_derived_network_file(with_shapes, world_file)
        without_shapes = os.path.join(
            output_dir, get_released_file_name(name, has_shapes=False)
        )
        derive_network_file(
            world_file,
            without_shapes,
            **DERIVED_NETWORKS[name],
            save_intermediate_nodes=False,
        )
        written += [with_shapes, without_shapes]
    if names is None:
        world_without_shapes = os.path.join(
            output_dir,
            get_released_file_name("world_multimodal", has_shapes=False),
        )
        derive_network_file(
            world_file, world_without_shapes, save_intermediate_nodes=False
        )
        written.append(world_without_shapes)
    return written


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m scgraph.pipelines.derived_networks",
        description="Write the derived files of a network release from the file "
        "of osm_world_multimodal, with no download, and print their paths.",
    )
    parser.add_argument(
        "world_file", help="the network file of osm_world_multimodal"
    )
    parser.add_argument("output_dir", help="the folder of the derived files")
    parser.add_argument(
        "names",
        nargs="*",
        metavar="NAME",
        help="a derived network to write, for example oceania; without a name, "
        "every derived network and the world file without shapes",
    )
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="do not check that each derived network fails no validation case "
        "that the world file passes",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO)  # the count of validation cases
    try:
        paths = derive_network_release_files(
            args.world_file,
            args.output_dir,
            args.names or None,
            run_validation_cases=not args.no_validate,
        )
    except (
        ValueError,
        FileNotFoundError,
        RuntimeError,
    ) as error:  # the message says what to change: no traceback
        parser.exit(2, f"{error}\n")
    print("\n".join(paths))  # noqa: T201 (the output of the command)


if __name__ == "__main__":
    main()
