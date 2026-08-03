import pytest
from scgraph.graph import Graph as PyGraph

try:
    from scgraph.cpp import Graph as CppGraph

    HAS_CPP = True
except ImportError:
    HAS_CPP = False

# Adversarial contraction graph:
# 1 -> 2 -> 3 (weight 1.5 + 1.5 = 3.0)
# 1 -> 0 -> 4 -> 3 (weight 1.0 + 1.0 + 1.0 = 3.0)
# Node 4 has high degree, so it is contracted after 1 and 3.
# Node 0 and 1 also have higher degrees so they are contracted after 2.
# When 2 is contracted, 0, 1, 4 are all uncontracted.
# - High settled_limit finds witness path 1 -> 0 -> 4 -> 3 and skips shortcut (1, 3).
# - Low settled_limit aborts and adds shortcut (1, 3) via 2.
_ADVERSARIAL_GRAPH = [
    {4: 1.0, 12: 1.0, 13: 1.0},  # 0
    {2: 1.5, 0: 1.0, 11: 1.0},  # 1
    {3: 1.5},  # 2
    {},  # 3
    {3: 1.0, 5: 1.0, 6: 1.0, 7: 1.0, 8: 1.0, 9: 1.0, 10: 1.0},  # 4
    {},  # 5
    {},  # 6
    {},  # 7
    {},  # 8
    {},  # 9
    {},  # 10
    {},  # 11
    {},  # 12
    {},  # 13
]


def _run_settled_limit_comparison(graph_class):
    # 1. High settled limit: should find the witness path and skip adding the shortcut
    g_high = graph_class(_ADVERSARIAL_GRAPH)
    ch_high = g_high.create_contraction_hierarchy(settled_limit=10)
    shortcuts_high = ch_high.shortcuts

    # 2. Low settled limit: should abort and add the shortcut
    g_low = graph_class(_ADVERSARIAL_GRAPH)
    ch_low = g_low.create_contraction_hierarchy(settled_limit=2)
    shortcuts_low = ch_low.shortcuts

    # Verify that shortcuts_low has more shortcuts than shortcuts_high
    assert len(shortcuts_low) > len(shortcuts_high), (
        f"Low settled limit should add more shortcuts ({len(shortcuts_low)}) "
        f"than high settled limit ({len(shortcuts_high)})"
    )

    # Verify that query correctness is preserved in both cases
    res_high = g_high.contraction_hierarchy(1, 3)
    res_low = g_low.contraction_hierarchy(1, 3)
    res_dijkstra = g_high.dijkstra(1, 3)

    assert abs(res_high["length"] - 3.0) < 1e-9
    assert abs(res_low["length"] - 3.0) < 1e-9
    assert abs(res_dijkstra["length"] - 3.0) < 1e-9


def test_python_settled_limit():
    _run_settled_limit_comparison(PyGraph)


@pytest.mark.skipif(not HAS_CPP, reason="C++ extension not available")
def test_cpp_settled_limit():
    _run_settled_limit_comparison(CppGraph)
