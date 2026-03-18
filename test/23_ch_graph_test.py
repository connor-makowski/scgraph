try:
    from scgraph.cpp import Graph as CPPGraph
except ImportError:
    CPPGraph = None

from scgraph.graph import Graph 
from scgraph.utils import validate

print(
    "\n===============\nCH Graph Tests:\n==============="
)

graph_data = [
    {1: 5, 2: 1},
    {0: 5, 2: 2, 3: 1},
    {0: 1, 1: 2, 3: 4, 4: 8},
    {1: 1, 2: 4, 4: 3, 5: 6},
    {2: 8, 3: 3},
    {3: 6},
]


def test_ch_graph(graph_class, name):
    graph_obj = graph_class(graph_data)
    graph_obj.create_contraction_hierarchy(
        # heuristic_fn=...
    )

    validate(
        name=f"{name} - Search 0 to 5",
        realized=graph_obj.contraction_hierarchy(origin_id=0, destination_id=5),
        expected={"path": [0, 2, 1, 3, 5], "length": 10},
    )

    validate(
        name=f"{name} - Search 5 to 0",
        realized=graph_obj.contraction_hierarchy(origin_id=5, destination_id=0),
        expected={"path": [5, 3, 1, 2, 0], "length": 10},
    )

    validate(
        name=f"{name} - Search 4 to 0",
        realized=graph_obj.contraction_hierarchy(origin_id=4, destination_id=0),
        expected={"path": [4, 3, 1, 2, 0], "length": 7},
    )

    validate(
        name=f"{name} - Search Same Node",
        realized=graph_obj.contraction_hierarchy(origin_id=2, destination_id=2),
        expected={"path": [2], "length": 0},
    )


test_ch_graph(Graph, "Python CH based Graph")
if CPPGraph:
    test_ch_graph(CPPGraph, "C++ CH based Graph")
else:
    print("C++ not available, skipping C++ CH Graph tests.")
