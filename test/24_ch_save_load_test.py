from scgraph import CHGraph
from scgraph.utils import validate
import os
import json

print("\n===============\nCH Save/Load Tests:\n===============")

graph_data = [
    {1: 5, 2: 1},
    {0: 5, 2: 2, 3: 1},
    {0: 1, 1: 2, 3: 4, 4: 8},
    {1: 1, 2: 4, 4: 3, 5: 6},
    {2: 8, 3: 3},
    {3: 6},
]

ch_graph = CHGraph(graph_data)
filename = "test_graph.chjson"
ch_graph.save_as_chjson(filename)
loaded_ch = CHGraph.load_from_chjson(filename)

validate(
    name="CH Save/Load - Ranks Match",
    realized=loaded_ch.ranks,
    expected=ch_graph.ranks,
)

output_orig = ch_graph.search(0, 5)

validate(
    name="CH Save/Load - Search Result Match",
    realized=loaded_ch.search(0, 5),
    expected=output_orig,
)

with open(filename, "r") as f:
    data = json.load(f)
data["original_graph"] = None
with open("test_no_orig.chjson", "w") as f:
    json.dump(data, f)

validate(
    name="CH Save/Load - No Original Graph Search",
    realized=CHGraph.load_from_chjson("test_no_orig.chjson").search(0, 5),
    expected=output_orig,
)

if os.path.exists(filename):
    os.remove(filename)
if os.path.exists("test_no_orig.chjson"):
    os.remove("test_no_orig.chjson")
