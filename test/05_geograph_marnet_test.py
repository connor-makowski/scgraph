import time
from pamda import pamda
from scgraph import Graph
from scgraph.marnet import marnet_geograph

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

print('\n===============\nMarnet GeoGraph Tests:\n===============')

expected = {
    'path': [
        11065, 
        4380, 
        7029, 
        6101, 
        9841, 
        7067,
        3664,
        2823,
        5795,
        1363,
        2394,
        388,
        953,
        4193,
        11066
    ], 
    'length': 4477.148, 
    'coordinate_path': [
        {'latitude': 30, 'longitude': 160}, 
        {'longitude': 160.0, 'latitude': 30.0}, 
        {'longitude': 164.6948, 'latitude': 35.1041}, 
        {'longitude': 165.0, 'latitude': 35.3857}, 
        {'longitude': 166.316, 'latitude': 36.6002}, 
        {'longitude': 169.999, 'latitude': 37.695}, 
        {'longitude': 171.814, 'latitude': 38.2345}, 
        {'longitude': 180.0, 'latitude': 40.0}, 
        {'longitude': -180.0, 'latitude': 40.0}, 
        {'longitude': -174.9996, 'latitude': 40.1067}, 
        {'longitude': -170.0, 'latitude': 40.0}, 
        {'longitude': -165.0, 'latitude': 35.3857}, 
        {'longitude': -164.6929, 'latitude': 35.1023}, 
        {'longitude': -160.0, 'latitude': 30.0}, 
        {'latitude': 30, 'longitude': -160}
    ]
}

origin_node = {
    "latitude": 30,
    "longitude": 160
}
destination_node = {
    "latitude": 30,
    "longitude": -160
}

validate(
    name='Graph Validation',
    realized = marnet_geograph.validate_graph(),
    expected = None
)
validate(
    name='Node Validation',
    realized = marnet_geograph.validate_nodes(),
    expected = None
)

validate(
    name='Dijkstra',
    realized = marnet_geograph.get_shortest_path(
        origin_node=origin_node, 
        destination_node=destination_node,
        algorithm_fn=Graph.dijkstra
    ), 
    expected = expected
)

validate(
    name='Dijkstra-Makowski',
    realized = marnet_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn=Graph.dijkstra_makowski
    ), 
    expected = expected
)

print('\n===============\nMarnet GeoGraph Time Tests:\n===============')

time_test('Graph Validation', pamda.thunkify(marnet_geograph.validate_graph))
time_test('Node Validation', pamda.thunkify(marnet_geograph.validate_nodes))

origin_node={
    "latitude": 31.23,
    "longitude": 121.47
}
destination_node={
    "latitude": 32.08,
    "longitude": -81.09
} 

def dijkstra():
    marnet_geograph.get_shortest_path(
        origin_node=origin_node, 
        destination_node=destination_node,
        algorithm_fn=Graph.dijkstra
    )

def dijkstra_makowski():
    marnet_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn=Graph.dijkstra_makowski
    )

time_test('Dijkstra', dijkstra)
time_test('Dijkstra-Makowski', dijkstra_makowski)