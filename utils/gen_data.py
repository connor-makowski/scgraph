import json
from pamda import pamda
from SCgraph import Distance

geojson_file = "utils/marnet.geojson"
out_filename = "SCgraph/data/marnet.py"
data_name = "marnet_data"

data_geojson = json.load(open(geojson_file, "r"))
coords = pamda.pluck(["geometry","coordinates"], data_geojson["features"])

def hardRound(decimal_places, a):
    return int(a * (10**decimal_places) + (0.5 if a > 0 else -0.5)) / (10**decimal_places)

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
    return hardRound(5,Distance.haversine(origin, destination))

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

pamda.write_json(out_filename, output)

# add data_name = to the beginning of the .py file's first line
with open(out_filename, "r") as f:
    lines = f.readlines()
    lines[0] = data_name + "=" + lines[0]
with open(out_filename, "w") as f:
    f.writelines(lines)