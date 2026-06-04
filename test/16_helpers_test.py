from scgraph.helpers.visvalingam import visvalingam


def test_visvalingam_basic():
    data = [[1, 1], [2, 2], [3, 2], [4, 1], [5, 1]]
    expected = [[1, 1], [3, 2], [4, 1], [5, 1]]
    assert visvalingam(data, pct_to_keep=50, min_points=3) == expected
