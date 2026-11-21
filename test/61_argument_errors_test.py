"""A call with a wrong argument raises a `ValueError` that names the argument."""

import pytest

from scgraph import GeoGraph

# Three nodes on a line, linked both ways.
_GRAPH = [{1: 1.0}, {0: 1.0, 2: 1.0}, {1: 1.0}]
_NODES = [[0, 0], [0, 1], [0, 2]]


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
    ],
)
def test_a_wrong_argument_of_a_change_raises_a_value_error(geograph, call):
    with pytest.raises(ValueError):
        call(geograph)
