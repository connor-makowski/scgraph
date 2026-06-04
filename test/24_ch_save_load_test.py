import json
import pytest
from scgraph import CHGraph
from helpers import assert_result

_GRAPH_DATA = [
    {1: 5, 2: 1},
    {0: 5, 2: 2, 3: 1},
    {0: 1, 1: 2, 3: 4, 4: 8},
    {1: 1, 2: 4, 4: 3, 5: 6},
    {2: 8, 3: 3},
    {3: 6},
]


@pytest.fixture(scope="module")
def ch_graph_and_result():
    g = CHGraph(_GRAPH_DATA)
    return g, g.search(0, 5)


def test_save_load_ranks(tmp_path, ch_graph_and_result):
    original, expected = ch_graph_and_result
    path = str(tmp_path / "test.chjson")
    original.save_as_chjson(path)
    loaded = CHGraph.load_from_chjson(path)
    assert loaded.ranks == original.ranks


def test_save_load_search_result(tmp_path, ch_graph_and_result):
    original, expected = ch_graph_and_result
    path = str(tmp_path / "test.chjson")
    original.save_as_chjson(path)
    loaded = CHGraph.load_from_chjson(path)
    assert_result(loaded.search(0, 5), expected)


def test_load_without_original_graph(tmp_path, ch_graph_and_result):
    original, expected = ch_graph_and_result
    path = str(tmp_path / "test.chjson")
    original.save_as_chjson(path)
    no_orig_path = str(tmp_path / "test_no_orig.chjson")
    with open(path) as f:
        data = json.load(f)
    data["original_graph"] = None
    with open(no_orig_path, "w") as f:
        json.dump(data, f)
    loaded = CHGraph.load_from_chjson(no_orig_path)
    assert_result(loaded.search(0, 5), expected)
