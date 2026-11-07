import pytest
from helpers import great_circle_km

from scgraph import GeoGraph
from scgraph.helpers.hilbert import hilbert_order

pytest.importorskip("osmium")

# OSM ids -> (latitude, longitude)
_NODES = {
    1: (0.0, 0.0),
    2: (0.0, 0.01),
    3: (0.0, 0.02),
    4: (0.01, 0.01),
    5: (-0.005, 0.015),  # bridge over way 1, no shared node
    6: (0.005, 0.015),
    7: (0.01, 0.02),
    10: (1.0, 0.0),  # a long way without junctions
    11: (1.005, 0.01),
    12: (1.0, 0.02),
    13: (1.0, 0.03),
    20: (2.0, 0.0),  # way 7 runs through node 99, missing from the file
    21: (2.0, 0.02),
    30: (3.0, 0.0),  # one way, drawn against the traffic
    31: (3.0, 0.01),
    40: (4.0, 0.0),  # roundabout piece, one way without a oneway tag
    41: (4.0, 0.01),
    50: (5.0, 0.0),  # motorway, one way without a oneway tag
    51: (5.0, 0.01),
}
_WAYS = [
    (1, [1, 2, 3], {"highway": "primary"}),
    (2, [2, 4], {"highway": "primary"}),
    (3, [5, 6], {"highway": "primary", "bridge": "yes"}),
    (4, [3, 7], {"highway": "residential"}),
    (5, [4, 7], {"highway": "primary", "oneway": "yes"}),
    (6, [10, 11, 12, 13], {"highway": "trunk"}),
    (7, [20, 99, 21], {"highway": "primary"}),
    (8, [30, 31], {"highway": "primary", "oneway": "-1"}),
    (9, [40, 41], {"highway": "primary", "junction": "roundabout"}),
    (10, [50, 51], {"highway": "motorway"}),
]


def _write_osm(path):
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<osm version="0.6">']
    for ref, (lat, lon) in _NODES.items():
        lines.append(f'<node id="{ref}" version="1" lat="{lat}" lon="{lon}"/>')
    for ref, refs, tags in _WAYS:
        lines.append(f'<way id="{ref}" version="1">')
        lines += [f'<nd ref="{r}"/>' for r in refs]
        lines += [f'<tag k="{k}" v="{v}"/>' for k, v in tags.items()]
        lines.append("</way>")
    lines.append("</osm>")
    path.write_text("\n".join(lines))


def _km(a, b):
    return great_circle_km(_NODES[a], _NODES[b])


def _arcs(geo):
    """Arcs as {(osm id, osm id): length}, through the node coordinates."""

    def key(c):
        return (round(c[0], 7), round(c[1], 7))  # OSM stores 1e-7 degrees

    osm_id = {key(c): ref for ref, c in _NODES.items()}
    return {
        (osm_id[key(geo.nodes[u])], osm_id[key(geo.nodes[v])]): w
        for u, row in enumerate(geo.graph_object.graph)
        for v, w in row.items()
    }


@pytest.fixture(scope="module")
def osm_file(tmp_path_factory):
    path = tmp_path_factory.mktemp("osm") / "small.osm"
    _write_osm(path)
    return str(path)


@pytest.fixture(scope="module")
def arcs(osm_file):
    # Every part of the small file, not only its largest connected part
    return _arcs(GeoGraph.load_from_osm(osm_file, largest_component=False))


def test_load_from_osm_joins_ways_only_at_shared_nodes(arcs):
    # Ways 1 and 2 share node 2; the bridge (5-6) crosses way 1 without a shared node
    assert {(1, 2), (2, 3), (2, 4), (5, 6)} <= set(arcs)
    assert {arc for arc in arcs if 5 in arc} == {(5, 6), (6, 5)}


def test_load_from_osm_keeps_main_roads_by_default(arcs):
    # The residential way 4 (3-7) is left out; only the one-way primary way 5 reaches 7
    assert {arc for arc in arcs if 7 in arc} == {(4, 7)}


def test_load_from_osm_keeps_ways_by_tags(osm_file):
    # Primary roads without a bridge tag: way 3 (the bridge 5-6) is left out
    keep = {"highway": {"primary"}, "bridge": {None}}
    arcs = _arcs(
        GeoGraph.load_from_osm(osm_file, keep=keep, largest_component=False)
    )
    assert (1, 2) in arcs and not any(5 in arc for arc in arcs)


def test_load_from_osm_does_not_join_across_a_missing_node(arcs):
    # Way 7 runs 20 -> 99 -> 21, node 99 is missing from the file
    assert not any(20 in arc or 21 in arc for arc in arcs)


def test_load_from_osm_arc_lengths_follow_the_shape(arcs):
    assert arcs[(1, 2)] == pytest.approx(_km(1, 2))
    # Way 6 is cut at node 12, the first point 2 km or more from node 10
    assert arcs[(10, 12)] == pytest.approx(_km(10, 11) + _km(11, 12))
    assert arcs[(12, 13)] == pytest.approx(_km(12, 13))


_ONE_WAY = {(4, 7), (31, 30), (40, 41), (50, 51)}


@pytest.mark.parametrize(
    "directed, expected",
    [(True, _ONE_WAY), (False, _ONE_WAY | {(b, a) for a, b in _ONE_WAY})],
)
def test_load_from_osm_follows_one_way_streets(osm_file, directed, expected):
    arcs = _arcs(
        GeoGraph.load_from_osm(
            osm_file, directed=directed, largest_component=False
        )
    )
    one_way_nodes = {7, 30, 40, 50}
    assert {arc for arc in arcs if one_way_nodes & set(arc)} == expected


def test_load_from_osm_keeps_the_largest_strongly_connected_part(osm_file):
    # Ways 1 and 2 (nodes 1 to 4, two-way) are the largest part where every node
    # reaches every other; node 7 is only reached by a one-way street
    geo = GeoGraph.load_from_osm(osm_file)
    assert {node for arc in _arcs(geo) for node in arc} == {1, 2, 3, 4}
    assert dict(zip(geo.node_ids, map(tuple, geo.nodes))) == {
        ref: _NODES[ref] for ref in (1, 2, 3, 4)
    }


def test_load_from_osm_numbers_nodes_along_a_hilbert_curve_with_their_osm_ids(
    osm_file,
):
    geo = GeoGraph.load_from_osm(osm_file, largest_component=False)
    assert hilbert_order(geo.nodes) == list(range(len(geo.nodes)))
    assert geo.coordinate_dtype == "int32"  # OSM's own encoding
    assert all(
        _NODES[ref] == tuple(node) for ref, node in zip(geo.node_ids, geo.nodes)
    )
