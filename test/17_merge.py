from scgraph.geographs.marnet import marnet_geograph
from scgraph.geographs.us_freeway import us_freeway_geograph

print("\n===============\nGeoGraph Merge Tests:\n===============")

ports = [
    # Boston
    [42.3601, -71.0589],
    # New York
    [40.7128, -74.0060],
    # Philadelphia
    [39.9526, -75.1652],
    # Baltimore
    [39.2904, -76.6122],
    # Washington D.C.
    [38.9072, -77.0369],
    # Savannah
    [32.0835, -81.0998],
    # Charleston
    [32.7765, -79.9311],
    # Jacksonville
    [30.3322, -81.6557],
    # Miami
    [25.7617, -80.1918],
    # Tampa
    [27.9506, -82.4572],
    # New Orleans
    [29.9511, -90.0715],
    # Houston
    [29.7604, -95.3698],
    # Los Angeles
    [34.0522, -118.2437],
    # San Francisco
    [37.7749, -122.4194],
    # Seattle
    [47.6062, -122.3321],
    # Portland
    [45.5152, -122.6784],
]

us_freeway_geograph.merge_with_other_geograph(
    other_geograph=marnet_geograph,
    connection_nodes=ports,
    circuity_to_current_geograph=1.1,
    circuity_to_other_geograph=1.3,
    node_addition_type_current_geograph="closest",
    node_addition_type_other_geograph="closest",
    node_addition_math="euclidean",
)

# Test from Atlanta to London
atlanta_node = {"latitude": 33.7490, "longitude": -84.3880}
london_node = {"latitude": 51.5074, "longitude": -0.1278}

freeway = us_freeway_geograph.get_shortest_path(
    origin_node=atlanta_node,
    destination_node=london_node,
)

marnet = marnet_geograph.get_shortest_path(
    origin_node=atlanta_node,
    destination_node=london_node,
)

expected_freeway_length=7094.0603
expected_marnet_length=8820.8927

success = True

if abs(freeway["length"] - expected_freeway_length) > 0.1:
    success = False

if abs(marnet["length"] - expected_marnet_length) > 0.1:
    success = False

if not success:
    print("Merge Test: FAIL")
else:
    print("Merge Test: PASS")


# To visually test the merge, you can save the GeoJSON output to make sure that the merged route traverse both geographs

# from scgraph.geograph import get_multi_path_geojson
# get_multi_path_geojson(
#     routes=[
#         {
#             'geograph': us_freeway_geograph,
#             'origin': atlanta_node,
#             'destination': london_node,
#             'properties':{"id":"route_1", "name":"Freeway Modified", "color":"#ff0000"}
#         },
#         {
#             'geograph': marnet_geograph,
#             'origin': atlanta_node,
#             'destination': london_node,
#             'properties':{"id":"route_2", "name":"MARNET Unmodified", "color":"#0000ff"}
#         }
#     ],
#     filename = "atlanta_to_london.geojson",
# )