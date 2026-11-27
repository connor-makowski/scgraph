import math
import os

import pytest

from scgraph.utils import hard_round

# The classes of the C++ extension, or None when the extension is not built.
try:
    from scgraph.cpp import CHGraph as CppCHGraph
    from scgraph.cpp import Graph as CppGraph
    from scgraph.cpp import TNRGraph as CppTNRGraph
except ImportError:
    CppGraph = CppCHGraph = CppTNRGraph = None

# The mark of a test that compares the C++ classes with the pure-Python ones,
# or that checks a behaviour of the C++ classes alone. Any other test takes
# the fixture graph_class, ch_class or tnr_class of conftest.py.
needs_the_cpp_extension = pytest.mark.skipif(
    CppGraph is None, reason="The C++ extension is not built"
)


def assert_result(realized, expected):
    # Every route has `metric_totals`, and the expected results of release
    # 3.6.0 do not have it: the comparison ignores it when they do not.
    if isinstance(realized, dict) and "metric_totals" not in expected:
        realized = {
            key: value
            for key, value in realized.items()
            if key != "metric_totals"
        }
    if isinstance(realized, dict) and "length" in realized:
        realized = {**realized, "length": hard_round(3, realized["length"])}
    if isinstance(expected, dict) and "length" in expected:
        expected = {**expected, "length": hard_round(3, expected["length"])}
    assert realized == expected


def great_circle_km(a, b):
    """Great-circle distance between [lat, lon] points (R = 6371 km), written apart from
    scgraph's own formula so that tests check it."""
    la1, lo1, la2, lo2 = map(math.radians, (*a, *b))
    h = (
        math.sin((la2 - la1) / 2) ** 2
        + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    )
    return 2 * 6371 * math.asin(math.sqrt(h))


def build_main_roads(files, *, work_dir=None):
    """Build the main roads and the vehicle ferries of the OSM file `files["roads"]`,
    as the arrays of a network file and a node modes table.

    The function is the `build` of a small pipeline for the tests. For the roads
    alone, it runs the steps that the pipeline `osm_region_multimodal` runs for each
    mode: read and cut the ways, store the pieces as a graph, assemble the arrays.
    Its select functions give no class.
    """
    from scgraph import network_assembly
    from scgraph.helpers import osm
    from scgraph.pipelines import osm_region_multimodal
    from scgraph.pipelines.steps import step1_osm_sources

    pieces = osm.build_way_pieces(
        step1_osm_sources.get_source(files["roads"]),
        {"road": {"ways": osm.select_main_roads}},
        ("highway", "route"),
        step1_osm_sources.MAX_KM_BETWEEN_NODES,
        os.path.join(work_dir, "ways") if work_dir else None,
        ferry_selects={"road": osm_region_multimodal.select_vehicle_ferries},
    )
    graph = network_assembly.build_graph_from_pieces(pieces["road"])
    arrays = network_assembly.assemble_network(
        graph,
        max_km_between_nodes=step1_osm_sources.MAX_KM_BETWEEN_NODES,
        min_component_nodes=None,  # only the largest component
    )
    return arrays, [{"name": None}]
