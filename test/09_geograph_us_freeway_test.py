import time
from pamda import pamda
from scgraph import Graph
from scgraph.geographs.us_freeway import us_freeway_geograph

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

print('\n===============\nUS Freeway GeoGraph Tests:\n===============')

expected = {
    'path': [14591, 6276, 6149, 6145, 6148, 6258, 6257, 6256, 6255, 6251, 6250, 6252, 6272, 6271, 6270, 6269, 6268, 6267, 6266, 1737, 1031, 1735, 14592], 
    'length': 138.6748, 
    'coordinate_path': [
        {'longitude': -85.158, 'latitude': 41.129},
        {'longitude': -85.163, 'latitude': 41.129},
        {'longitude': -85.114, 'latitude': 41.151},
        {'longitude': -85.104, 'latitude': 41.171},
        {'longitude': -85.103, 'latitude': 41.179},
        {'longitude': -85.091, 'latitude': 41.25},
        {'longitude': -85.055, 'latitude': 41.501},
        {'longitude': -85.011, 'latitude': 41.671},
        {'longitude': -85.005, 'latitude': 41.71},
        {'longitude': -85.001, 'latitude': 41.72},
        {'longitude': -85.0, 'latitude': 41.736},
        {'longitude': -84.998, 'latitude': 41.847},
        {'longitude': -84.973, 'latitude': 41.971},
        {'longitude': -84.972, 'latitude': 42.0},
        {'longitude': -84.995, 'latitude': 42.082},
        {'longitude': -84.991, 'latitude': 42.155},
        {'longitude': -84.986, 'latitude': 42.235},
        {'longitude': -84.989, 'latitude': 42.266},
        {'longitude': -84.991, 'latitude': 42.271},
        {'longitude': -84.997, 'latitude': 42.286},
        {'longitude': -84.997, 'latitude': 42.297},
        {'longitude': -84.996, 'latitude': 42.297},
        {'longitude': -84.996, 'latitude': 42.297}
    ]
}


# Fort Wayne IN
origin_node = {'longitude': -85.158, 'latitude': 41.129}
# Marshall MI
destination_node = {"longitude": -84.996, "latitude": 42.297}

validate(
    name='Graph Validation',
    realized = us_freeway_geograph.validate_graph(),
    expected = None
)
validate(
    name='Node Validation',
    realized = us_freeway_geograph.validate_nodes(),
    expected = None
)

validate(
    name='Dijkstra',
    realized = us_freeway_geograph.get_shortest_path(
        origin_node=origin_node, 
        destination_node=destination_node,
        algorithm_fn=Graph.dijkstra
    ), 
    expected = expected
)

validate(
    name='Dijkstra-Makowski',
    realized = us_freeway_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn=Graph.dijkstra_makowski
    ), 
    expected = expected
)

print('\n===============\nUS Freeway GeoGraph Time Tests:\n===============')

time_test('Graph Validation', pamda.thunkify(us_freeway_geograph.validate_graph))
time_test('Node Validation', pamda.thunkify(us_freeway_geograph.validate_nodes))

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
    us_freeway_geograph.get_shortest_path(
        origin_node=origin_node, 
        destination_node=destination_node,
        algorithm_fn=Graph.dijkstra
    )

def dijkstra_makowski():
    us_freeway_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn=Graph.dijkstra_makowski
    )

time_test('Dijkstra', dijkstra)
time_test('Dijkstra-Makowski', dijkstra_makowski)

# us_freeway_geograph.save_as_geojson('us_freeway_geograph.geojson')