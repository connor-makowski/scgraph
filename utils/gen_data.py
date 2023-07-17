import json
from pamda import pamda
from scgraph.utils import Distance, hardRound

geojson_file = "utils/marnet.geojson"
out_filename = "scgraph/data/marnet.py"
data_name = "marnet_data"

data_geojson = json.load(open(geojson_file, "r"))
coords = pamda.pluck(["geometry","coordinates"], data_geojson["features"])

def lessThanAbs(threshold, a):
    abs_a = abs(a)
    while abs_a > threshold:
        abs_a -= threshold
    return abs_a * (1 if a > 0 else -1)

def format_coord_pair(coord_pair):
    return [lessThanAbs(180,hardRound(4, coord_pair[0])), lessThanAbs(90,hardRound(4, coord_pair[1]))]

def get_distance(origin_id, destination_id, nodes):
    origin = nodes.get(origin_id)
    destination = nodes.get(destination_id)
    if origin is None or destination is None:
        return None
    return hardRound(3,Distance.haversine(origin, destination))

def gen_data(coord_list):
    clean_nodes = [format_coord_pair(coord_pair) for coord_pair in coord_list]
    nodes = {f"{i[0]}__{i[1]}": {"longitude": i[0], "latitude": i[1]} for i in clean_nodes}
    graph = {}
    for i,j in zip(list(nodes.keys())[:-1], list(nodes.keys())[1:]):
        distance = get_distance(i,j,nodes)
        if distance is None:
            continue
        graph = pamda.assocPath([i,j], distance, graph)
        graph = pamda.assocPath([j,i], distance, graph)
    return {"nodes": nodes, "graph": graph}
    
data = {}
for coord_list in coords:
    data = pamda.mergeDeep(data, gen_data(coord_list))

key_mapping = {node_id:idx for idx, node_id in enumerate(data["nodes"].keys())}
output = {
    "graph":{key_mapping[origin_id]: {key_mapping[destination_id]: distance for destination_id, distance in origin.items()} for origin_id, origin in data["graph"].items()},
    "nodes": {key_mapping[node_id]: node for node_id, node in data["nodes"].items()}
}

# add data_name = to the beginning of the .py file's first line
with open(out_filename, "w") as f:
    f.writelines(data_name + "=" + str(output) + "\n")