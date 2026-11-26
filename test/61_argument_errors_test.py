"""A call with a wrong argument raises a `ValueError` that names the argument, or a
`TypeError` for a value of the wrong type. Both builds raise the same type."""

import numbers
from array import array
from decimal import Decimal

import pytest

from scgraph import GeoGraph

# Three nodes on a line, linked both ways.
_GRAPH = [{1: 1.0}, {0: 1.0, 2: 1.0}, {1: 1.0}]
_NODES = [[0, 0], [0, 1], [0, 2]]


# An integer that is not an `int`, as a numpy integer is. The tests do not import numpy.
class _NodeId:
    def __init__(self, value):
        self.value = value

    def __index__(self):
        return self.value


numbers.Integral.register(_NodeId)


@pytest.fixture
def geograph():
    return GeoGraph(graph=_GRAPH, nodes=_NODES)


@pytest.mark.parametrize(
    "method, filename",
    [
        ("save_as_graphjson", "network.json"),
        ("load_from_graphjson", "network.json"),
        ("save_as_scgraph", "network.bin"),
        ("load_from_scgraph", "network.bin"),
    ],
)
def test_a_geograph_file_with_another_suffix_raises(
    geograph, tmp_path, method, filename
):
    with pytest.raises(ValueError, match="Filename must end with"):
        getattr(geograph, method)(str(tmp_path / filename))


def test_a_ch_file_with_another_suffix_raises(ch_class, tmp_path):
    hierarchy = ch_class(_GRAPH)

    with pytest.raises(ValueError, match=".chjson"):
        hierarchy.save_as_chjson(str(tmp_path / "hierarchy.json"))
    with pytest.raises(ValueError, match=".chjson"):
        ch_class.load_from_chjson(str(tmp_path / "hierarchy.json"))


def test_a_tnr_file_with_another_suffix_raises(tnr_class, tmp_path):
    hierarchy = tnr_class(_GRAPH)

    with pytest.raises(ValueError, match=".tnrjson"):
        hierarchy.save_as_tnrjson(str(tmp_path / "hierarchy.json"))
    with pytest.raises(ValueError, match=".tnrjson"):
        tnr_class.load_from_tnrjson(str(tmp_path / "hierarchy.json"))


@pytest.mark.parametrize(
    "option",
    [
        {"node_addition_type": "nearest"},
        {"algorithm_fn": "no_such_algorithm"},
        {"algorithm_fn": 5},
        {"output_coordinate_path": "no_such_format"},
    ],
)
def test_an_unknown_option_of_get_shortest_path_raises(geograph, option):
    with pytest.raises(ValueError):
        geograph.get_shortest_path(
            origin_node={"latitude": 0, "longitude": 0},
            destination_node={"latitude": 0, "longitude": 2},
            **option,
        )


# The optional arguments of a hierarchy are passed by keyword, so that a call means
# the same with the C++ extension and in pure Python.
def test_a_hierarchy_class_refuses_an_option_passed_by_position(
    ch_class, tnr_class
):
    with pytest.raises(TypeError):
        ch_class(_GRAPH, 50)
    with pytest.raises(TypeError):
        tnr_class(_GRAPH, 2)


def test_a_graph_refuses_a_hierarchy_option_passed_by_position(graph_class):
    graph = graph_class(_GRAPH)

    with pytest.raises(TypeError):
        graph.create_contraction_hierarchy(None)
    with pytest.raises(TypeError):
        graph.create_tnr_hierarchy(2)


def test_tnr_class_takes_the_same_options_in_both_builds(tnr_class):
    hierarchy = tnr_class(
        _GRAPH,
        num_transit_nodes=2,
        settled_limit=10,
        heuristic_fn=lambda hierarchy, node_id: node_id,
    )

    assert hierarchy.get_shortest_path(0, 2)["length"] == 2.0


@pytest.mark.parametrize(
    "method, extra_arguments",
    [
        ("create_contraction_hierarchy", "ch_graph_kwargs"),
        ("create_tnr_hierarchy", "tnr_graph_kwargs"),
    ],
)
def test_the_dict_of_extra_hierarchy_arguments_is_deprecated(
    graph_class, method, extra_arguments
):
    graph = graph_class(_GRAPH)

    with pytest.warns(DeprecationWarning, match=extra_arguments):
        getattr(graph, method)(**{extra_arguments: {}})


def test_get_shortest_path_refuses_an_option_passed_by_position(geograph):
    with pytest.raises(TypeError):
        geograph.get_shortest_path(
            {"latitude": 0, "longitude": 0},
            {"latitude": 0, "longitude": 2},
            "km",
        )


def test_length_only_is_deprecated(geograph):
    with pytest.warns(DeprecationWarning, match="totals_only"):
        geograph.get_shortest_path(
            origin_node={"latitude": 0, "longitude": 0},
            destination_node={"latitude": 0, "longitude": 2},
            length_only=True,
        )


def test_an_alias_of_a_node_addition_type_is_deprecated(geograph):
    with pytest.warns(DeprecationWarning, match="Use 'closest'"):
        geograph.get_shortest_path(
            origin_node={"latitude": 0, "longitude": 0},
            destination_node={"latitude": 0, "longitude": 2},
            node_addition_type="kdclosest",
        )


@pytest.mark.parametrize(
    "call",
    [
        lambda geograph: geograph.add_coord_node(coord_dict={"latitude": 91}),
        lambda geograph: geograph.add_coord_node(coord_dict=[0, 0]),
        lambda geograph: geograph.add_haversine_edge(
            origin_idx=0, destination_idx=9
        ),
        lambda geograph: geograph.add_edge(0, 2, float("nan")),
        # The south of this bounding box is above its north
        lambda geograph: geograph.get_nodes(bbox=(1, 0, 0, 1)),
        lambda geograph: geograph.get_nodes(bbox=(float("nan"), 0, 1, 1)),
    ],
)
def test_a_wrong_argument_of_a_change_raises_a_value_error(geograph, call):
    with pytest.raises(ValueError):
        call(geograph)


@pytest.mark.parametrize(
    "call",
    [
        lambda geograph: geograph.get_path_edges([0, 1.0]),
        # A set has no order: it is not a path
        lambda geograph: geograph.get_path_edges({0, 1}),
        lambda geograph: geograph.get_path_edges(bytearray([0, 1])),
        lambda geograph: geograph.list_geographs(geograph_url=5),
        lambda geograph: geograph.save_as_scgraph(
            "network.scgraph", metadata=5
        ),
    ],
)
def test_a_value_of_the_wrong_type_raises_a_type_error(geograph, call):
    with pytest.raises(TypeError):
        call(geograph)


def test_save_as_scgraph_refuses_a_metadata_string_other_than_auto(geograph):
    with pytest.raises(ValueError, match="metadata"):
        geograph.save_as_scgraph("network.scgraph", metadata="bad")


# A path may be any sequence of integer node ids, such as a range or a numpy array.
@pytest.mark.parametrize(
    "path", [range(3), (0, 1, 2), [_NodeId(0), _NodeId(1), _NodeId(2)]]
)
def test_get_path_edges_takes_a_sequence_of_integers(geograph, path):
    assert geograph.get_path_edges(path) == geograph.get_path_edges([0, 1, 2])


# A search checks its origin and its destination before it reads the graph.
@pytest.mark.parametrize(
    "algorithm", ["dijkstra", "contraction_hierarchy", "tnr"]
)
@pytest.mark.parametrize("origin_id, destination_id", [(0, 99), (-1, 2)])
def test_a_search_refuses_a_node_that_is_not_in_the_graph(
    graph_class, algorithm, origin_id, destination_id
):
    graph = graph_class(_GRAPH)

    with pytest.raises(ValueError, match="is not in this graph"):
        getattr(graph, algorithm)(origin_id, destination_id)


# An origin is a node id, a set of node ids, or a dict of node ids and start
# distances. A dict is never read as the set of its node ids.
@pytest.mark.parametrize("algorithm", ["dijkstra", "contraction_hierarchy"])
@pytest.mark.parametrize(
    "origin_id", ["a", 1.5, [0], None, {"a": 1.0}, {0: "x"}]
)
def test_a_search_refuses_an_origin_of_the_wrong_type(
    graph_class, algorithm, origin_id
):
    graph = graph_class(_GRAPH)

    with pytest.raises(TypeError):
        getattr(graph, algorithm)(origin_id, 2)


# A node id may be an integer that is not an `int`, such as a numpy integer, and a
# set of node ids may be a frozenset, as in release 3.6 with the C++ extension.
@pytest.mark.parametrize(
    "origin_id",
    [_NodeId(0), {_NodeId(0)}, frozenset({0}), {_NodeId(0): 0.0}],
)
def test_a_search_takes_a_node_id_from_a_numpy_array_and_a_frozenset(
    graph_class, origin_id
):
    graph = graph_class(_GRAPH)

    assert graph.dijkstra(origin_id, _NodeId(2)) == {
        "path": [0, 1, 2],
        "length": 2.0,
    }


@pytest.mark.parametrize("algorithm", ["dijkstra", "contraction_hierarchy"])
@pytest.mark.parametrize("start_distance", [-5, float("nan"), Decimal("NaN")])
def test_a_search_refuses_a_negative_or_nan_start_distance(
    graph_class, algorithm, start_distance
):
    graph = graph_class(_GRAPH)

    with pytest.raises(ValueError, match="non-negative"):
        getattr(graph, algorithm)({0: start_distance}, 2)


def test_validate_refuses_a_nan_distance(graph_class):
    graph = graph_class([{1: float("nan")}, {0: 1.0}])

    with pytest.raises(ValueError):
        graph.validate()


def test_a_graph_refuses_node_first_edge_ids_that_decrease(graph_class):
    # Node 0 would own the edges 0 and 1, and node 1 the edges from 2 to 1.
    node_first_edge_ids = array("i", [0, 2, 1, 2])

    with pytest.raises(ValueError):
        graph_class.from_edge_arrays(
            node_first_edge_ids, array("i", [1, 0]), array("d", [1.0, 1.0])
        )


@pytest.mark.parametrize("iterations", [1.5, "a", None])
def test_reduce_refuses_iterations_of_the_wrong_type(graph_class, iterations):
    graph = graph_class(_GRAPH)

    with pytest.raises(TypeError):
        graph.reduce(iterations)


def test_reduce_refuses_iterations_below_minus_one(graph_class):
    graph = graph_class(_GRAPH)

    with pytest.raises(ValueError, match="-5"):
        graph.reduce(-5)


@pytest.mark.parametrize(
    "name", ["reduced_graph_connections", "reduced_inverse_graph_connections"]
)
def test_the_connections_of_a_reduced_graph_are_read_only(graph_class, name):
    graph = graph_class(_GRAPH)

    with pytest.raises(AttributeError):
        setattr(graph, name, [])


@pytest.mark.parametrize(
    "origin_id, distance", [("a", 1.0), (None, 1.0), (0, "x"), (0, None)]
)
def test_add_edge_refuses_a_value_of_the_wrong_type(
    graph_class, origin_id, distance
):
    graph = graph_class(_GRAPH)

    with pytest.raises(TypeError):
        graph.add_edge(origin_id, 2, distance)


def test_add_edge_takes_a_node_id_from_a_numpy_array(graph_class):
    # A copy: the pure-Python class keeps the rows that it is given
    graph = graph_class([dict(row) for row in _GRAPH])

    graph.add_edge(_NodeId(0), _NodeId(2), 1.0)

    assert graph.dijkstra(0, 2) == {"path": [0, 2], "length": 1.0}


# A distance is any number with `__float__`, not only an `int` or a `float`.
def test_a_search_takes_a_decimal_start_distance(graph_class):
    graph = graph_class(_GRAPH)

    result = graph.dijkstra({0: Decimal("1.5")}, 2)

    # 1.5 at node 0, then the edges 0-1 and 1-2 of length 1
    assert result == {"path": [0, 1, 2], "length": 3.5}


def test_add_edge_takes_a_decimal_distance(graph_class):
    # A copy: the pure-Python class keeps the rows that it is given
    graph = graph_class([dict(row) for row in _GRAPH])

    graph.add_edge(0, 2, Decimal("1.5"))

    assert graph.dijkstra(0, 2) == {"path": [0, 2], "length": 1.5}


def test_add_edge_refuses_a_nan_distance(graph_class):
    graph = graph_class(_GRAPH)

    with pytest.raises(ValueError):
        graph.add_edge(0, 2, float("nan"))
