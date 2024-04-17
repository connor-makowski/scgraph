from scgraph.geographs.us_freeway_old import graph, nodes

graph = [v for v in graph.values()]
nodes = [[v.get("latitude"), v.get("longitude")] for v in nodes.values()]

out_string = f"""
from scgraph.core import GeoGraph
graph={str(graph)}
nodes={str(nodes)}
us_freeway_geograph = GeoGraph(graph=graph, nodes=nodes)
"""

with open("geographs/us_freeway.py", "w") as f:
    f.write(out_string)
