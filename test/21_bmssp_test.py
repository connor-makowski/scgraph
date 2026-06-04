from helpers import assert_result


def test_bmssp_marnet_0_5(marnet):
    graph = marnet.graph_object
    assert_result(graph.bmssp(0, 5), graph.dijkstra(0, 5))


def test_bmssp_marnet_100_7999(marnet):
    graph = marnet.graph_object
    assert_result(graph.bmssp(100, 7999), graph.dijkstra(100, 7999))


def test_bmssp_marnet_4022_8342(marnet):
    graph = marnet.graph_object
    assert_result(graph.bmssp(4022, 8342), graph.dijkstra(4022, 8342))


def test_bmssp_us_freeway_0_5(us_freeway):
    graph = us_freeway.graph_object
    assert_result(graph.bmssp(0, 5), graph.dijkstra(0, 5))


def test_bmssp_us_freeway_4022_8342(us_freeway):
    graph = us_freeway.graph_object
    assert_result(graph.bmssp(4022, 8342), graph.dijkstra(4022, 8342))
