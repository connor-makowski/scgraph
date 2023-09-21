import time
from pamda import pamda
from scgraph import Graph
from scgraph.geographs.oak_ridge_maritime import oak_ridge_maritime_geograph

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

print('\n===============\nOak Ridge GeoGraph Tests:\n===============')

expected = {
    'path': [10661, 1357, 8597, 8599, 2374, 1714, 8823, 8007, 8644, 10662], 
    'length': 3894.053, 
    'coordinate_path': [{'latitude': 30, 'longitude': 160}, {'longitude': 160.0, 'latitude': 30.0}, {'longitude': 165.0005, 'latitude': 30.0935}, {'longitude': 170.0, 'latitude': 30.0}, {'longitude': -178.5, 'latitude': 28.5}, {'longitude': -174.2807, 'latitude': 29.3168}, {'longitude': -170.0, 'latitude': 30.0}, {'longitude': -164.9995, 'latitude': 30.0935}, {'longitude': -160.0, 'latitude': 30.0}, {'latitude': 30, 'longitude': -160}]
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
    realized = oak_ridge_maritime_geograph.validate_graph(check_symmetry=True, check_connected=False),
    expected = None
)
validate(
    name='Node Validation',
    realized = oak_ridge_maritime_geograph.validate_nodes(),
    expected = None
)

validate(
    name='Dijkstra',
    realized = oak_ridge_maritime_geograph.get_shortest_path(
        origin_node=origin_node, 
        destination_node=destination_node,
        algorithm_fn=Graph.dijkstra
    ), 
    expected = expected
)

validate(
    name='Dijkstra-Makowski',
    realized = oak_ridge_maritime_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn=Graph.dijkstra_makowski
    ), 
    expected = expected
)

print('\n===============\nOak Ridge GeoGraph Time Tests:\n===============')

time_test('Graph Validation', pamda.thunkify(oak_ridge_maritime_geograph.validate_graph)(check_symmetry=True, check_connected=False))
time_test('Node Validation', pamda.thunkify(oak_ridge_maritime_geograph.validate_nodes))

origin_node={
    "latitude": 31.23,
    "longitude": 121.47
}
destination_node={
    "latitude": 32.08,
    "longitude": -81.09
} 

def dijkstra():
    oak_ridge_maritime_geograph.get_shortest_path(
        origin_node=origin_node, 
        destination_node=destination_node,
        algorithm_fn=Graph.dijkstra
    )

def dijkstra_makowski():
    oak_ridge_maritime_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn=Graph.dijkstra_makowski
    )

time_test('Dijkstra', dijkstra)
time_test('Dijkstra-Makowski', dijkstra_makowski)
# oak_ridge_maritime_geograph.save_as_geojson('oak_ridge_maritime.geojson')