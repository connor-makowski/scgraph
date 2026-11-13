from helpers import assert_result

_GRAPH_DATA = [
    {1: 5, 2: 1},
    {0: 5, 2: 2, 3: 1},
    {0: 1, 1: 2, 3: 4, 4: 8},
    {1: 1, 2: 4, 4: 3, 5: 6},
    {2: 8, 3: 3},
    {3: 6},
]


def test_ch_graph(graph_class):
    g = graph_class(_GRAPH_DATA)
    g.create_contraction_hierarchy()
    assert_result(
        g.contraction_hierarchy(origin_id=0, destination_id=5),
        {"path": [0, 2, 1, 3, 5], "length": 10},
    )
    assert_result(
        g.contraction_hierarchy(origin_id=5, destination_id=0),
        {"path": [5, 3, 1, 2, 0], "length": 10},
    )
    assert_result(
        g.contraction_hierarchy(origin_id=4, destination_id=0),
        {"path": [4, 3, 1, 2, 0], "length": 7},
    )
    assert_result(
        g.contraction_hierarchy(origin_id=2, destination_id=2),
        {"path": [2], "length": 0},
    )
