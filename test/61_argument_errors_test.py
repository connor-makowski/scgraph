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
