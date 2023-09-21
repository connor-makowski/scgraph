import time
from pamda import pamda
from scgraph import Graph
from scgraph.geographs.north_america_rail import north_america_rail_geograph

def validate(name, realized, expected):
    if realized == expected:
        print(f'{name}: PASS')
    else:
        print(f'{name}: FAIL')
        print('Expected:', expected)
        print('Realized:', realized)

def time_test(name, thunk):
    start = time.time()
    thunk()
    print(f"{name}: {round(time.time()-start, 4)}s")

print('\n===============\nNorth America Rail GeoGraph Tests:\n===============')

expected = {
    'path': [9929, 260, 259, 334, 9930], 
    'length': 39.9236, 
    'coordinate_path': [
        {'longitude': -102.352, 'latitude': 48.325}, 
        {'longitude': -102.352, 'latitude': 48.325}, 
        {'longitude': -102.354, 'latitude': 48.328}, 
        {'longitude': -102.652, 'latitude': 48.561}, 
        {'longitude': -102.651, 'latitude': 48.561}
    ]
}

# Stanley ND
origin_node = {'longitude': -102.352, 'latitude': 48.325}
# Powers Lake ND
destination_node = {"longitude": -102.651, "latitude": 48.561}

validate(
    name='Graph Validation',
    realized = north_america_rail_geograph.validate_graph(check_symmetry=True, check_connected=False),
    expected = None
)
validate(
    name='Node Validation',
    realized = north_america_rail_geograph.validate_nodes(),
    expected = None
)

validate(
    name='Dijkstra',
    realized = north_america_rail_geograph.get_shortest_path(
        origin_node=origin_node, 
        destination_node=destination_node,
        algorithm_fn=Graph.dijkstra
    ), 
    expected = expected
)

validate(
    name='Dijkstra-Makowski',
    realized = north_america_rail_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn=Graph.dijkstra_makowski
    ), 
    expected = expected
)

print('\n===============\nNorth America Rail GeoGraph Time Tests:\n===============')

time_test('Graph Validation', pamda.thunkify(north_america_rail_geograph.validate_graph)(check_symmetry=True, check_connected=False))
time_test('Node Validation', pamda.thunkify(north_america_rail_geograph.validate_nodes))

# Seattle
origin_node={
    "latitude": 47.6,
    "longitude": -122.33
}
# Miami
destination_node={
    "latitude": 25.78,
    "longitude": -80.21
} 

def dijkstra():
    north_america_rail_geograph.get_shortest_path(
        origin_node=origin_node, 
        destination_node=destination_node,
        algorithm_fn=Graph.dijkstra
    )

def dijkstra_makowski():
    north_america_rail_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn=Graph.dijkstra_makowski
    )

time_test('Dijkstra', dijkstra)
time_test('Dijkstra-Makowski', dijkstra_makowski)

# north_america_rail_geograph.save_as_geojson('north_america_rail.geojson')