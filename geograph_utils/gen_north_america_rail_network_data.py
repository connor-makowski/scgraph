import json
from pamda import pamda
from scgraph.utils import hard_round, distance_converter
from collections import Counter

# This `geojson_file` is not comitted in the git repo for size reasons
# It can be downloaded from: 
# https://geodata.bts.gov/datasets/usdot::north-american-rail-network-lines-class-i-freight-railroads-view/about
geojson_file = "utils/north_america_rail_network.geojson"
out_filename = "scgraph/geographs/north_america_rail.py"
initialized_class_name = "north_america_rail_geograph"

data_geojson = json.load(open(geojson_file, "r"))

def lessThanAbs(threshold, a):
    abs_a = abs(a)
    while abs_a > threshold:
        abs_a -= 360
    return abs_a * (1 if a > 0 else -1)

def format_coord_pair(coord_pair):
    try:
        return [lessThanAbs(180,hard_round(3, coord_pair[0])), lessThanAbs(90,hard_round(3, coord_pair[1]))]
    except:
        print(coord_pair)
        raise Exception()
    
def get_agg_arc(origin, destination, arcs_dict):
    distance = 0
    current_node = origin
    next_node = destination
    arc_dict = arcs_dict.get(current_node)
    while True:
        distance += arc_dict.get(next_node, 0)
        arc_dict = arcs_dict.get(next_node)
        if len(arc_dict)!=2:
            break
        new_next_node = [k for k in arc_dict.keys() if k != current_node][0]
        current_node = next_node
        next_node = new_next_node
    return {
        'origin':origin,
        'destination':next_node,
        'distance':round(distance,3),
    }

def invert_arc(arc):
    return {
        'origin':arc['destination'],
        'destination':arc['origin'],
        'distance':arc['distance'],
    }

def agg_arcs(arcs, remove_tips:bool=False, tip_threshold:int=5):
    arcs_dict = {}
    for arc in arcs:
        arcs_dict = pamda.assocPath([str(arc['origin']),str(arc['destination'])], arc['distance'], arcs_dict)
        arcs_dict = pamda.assocPath([str(arc['destination']),str(arc['origin'])], arc['distance'], arcs_dict)

    intersections = [k for k, v in arcs_dict.items() if len(v) > 2]
    tips = set([k for k, v in arcs_dict.items() if len(v) == 1])

    agg_arcs = []
    for intersection in intersections:
        for outbound in arcs_dict.get(intersection):
            agg_arc = get_agg_arc(intersection, outbound, arcs_dict)
            if remove_tips:
                # Remove all small arcs that are connected to tips (short offshoots - eg to local factories)
                if agg_arc['origin'] in tips or agg_arc['destination'] in tips:
                    if agg_arc['distance']<tip_threshold:
                        continue
            agg_arcs.append(agg_arc)
            agg_arcs.append(invert_arc(agg_arc))
    return agg_arcs

def get_arcs(geojson):
    arcs = [{
        'origin':format_coord_pair(arc['geometry']['coordinates'][0][0]),
        'destination':format_coord_pair(arc['geometry']['coordinates'][0][-1]),
        'distance':round(distance_converter(distance=pamda.path(["properties","MILES"], arc), input_units='mi', output_units='km'),2),
    } for arc in geojson["features"]]
    # Aggregate up arcs then remove arcs with tips that are too short
    arcs_no_tips = agg_arcs(arcs, remove_tips=True, tip_threshold=5)
    # After removing tips, aggregate up arcs again to merge arcs on intersections that were previously broken by a tip
    return agg_arcs(arcs_no_tips, remove_tips=False)

arcs = get_arcs(data_geojson)

raw_nodes = {}
for i in arcs:
    origin = json.loads(i['origin'])
    raw_nodes[str(origin)] = {"longitude": origin[0], "latitude": origin[1]}


key_mapping = {node_id:idx for idx, node_id in enumerate(raw_nodes.keys())}
nodes = {key_mapping[node_id]: node for node_id, node in raw_nodes.items()}
graph = {}
for arc in arcs:
    origin_id = key_mapping[arc['origin']]
    destination_id = key_mapping[arc['destination']]
    pamda.assocPath([origin_id, destination_id], arc['distance'], graph)
    pamda.assocPath([destination_id, origin_id], arc['distance'], graph)

out_string = f"""
from scgraph.core import GeoGraph
graph={str(graph)}
nodes={str(nodes)}
{initialized_class_name} = GeoGraph(graph=graph, nodes=nodes)
"""

with open(out_filename, "w") as f:
    f.write(out_string)



