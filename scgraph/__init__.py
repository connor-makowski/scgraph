"""
# scgraph
[![PyPI version](https://badge.fury.io/py/scgraph.svg)](https://badge.fury.io/py/scgraph)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![PyPI Downloads](https://pepy.tech/badge/scgraph)](https://pypi.org/project/scgraph/)
<!-- [![PyPI Downloads](https://img.shields.io/pypi/dm/scgraph.svg?label=PyPI%20downloads)](https://pypi.org/project/scgraph/) -->


Supply chain graph package for Python


![scgraph](https://raw.githubusercontent.com/connor-makowski/scgraph/main/static/scgraph.png)

## Documentation

Getting Started: https://github.com/connor-makowski/scgraph

Low Level: https://connor-makowski.github.io/scgraph/scgraph.html


## Key Features

- `GeoGraph`s:
    - A geographic graph data structure that allows for the calculation of shortest paths between two points on earth
    - Uses latitude / longitude pairs to represent points on earth
    - Supports maritime, rail, road and other geographic networks
    - Uses a sparse network data structure to represent the graph
    - How to use it - Calculate the shortest path between two points on earth
        - Inputs:
            - A latitude / longitude pair for the origin
            - A latitude / longitude pair for the destination
        - Calculation:
            - Algorithms:
                - Dijkstra's algorithm
                    - Modified to support sparse network data structures
                - Modified Dijkstra algorithm
                    - Modified for O((n+m)log(n)) performance where n is the number of nodes and m is the number of edges
                    - Uses a priority queue and other improvements to run fast on large graphs
                - A* algorithm (Extension of the Modified Dijkstra)
                    - Uses a heuristic function to improve performance on large graphs
                - Possible future support for other algorithms
        - Returns:
            - `path`:
                - A list of lists `[latitude, longitude]` that make up the shortest path
            - `length`:
                - The distance (in the units requested) between the two points
    - Precompiled Geographs offer Antimeridian support
    - Arbitrary start and end points are supported
        - Start and end points do not need to be in the graph
    - Cached shortest path calculations can be used for very fast repetative calculations from the same origin node in a GeoGraph.
        - This is done by caching the origin node's spanning tree
        - The first call will be slower, but future calls using this origin node will be substantially faster.
- `GridGraph`s:
    - A grid based graph data structure that allows for the calculation of shortest paths between two points on a grid
    - Supports arbitrary grid sizes and blockages
    - Uses a sparse network data structure to represent the graph
    - How to use it - Calculate the shortest path between two points on a grid
        - Inputs:
            - A (x,y) coordinate on the grid for the origin
            - A (x,y) coordinate on the grid for the destination
        - Calculation:
            - Algorithms:
                - Dijkstra's algorithm
                - Modified Dijkstra algorithm
                - A* algorithm (Extension of the Modified Dijkstra)
        - Returns:
            - `length`:
                - The distance between the two points on the grid
            - `coordinate_path`:
                - A list of dicts `{"x": x, "y": y}` representing the path taken through the grid
    - Arbitrary start and end points are supported
        - Start and end points do not need to be in the graph
    - Arbitrary connection matricies are supported
        - Cardinal connections (up, down, left, right) and diagonal connections (up-left, up-right, down-left, down-right) are used by default
        - Custom connection matricies can be used to change the connections between grid items
    - Cached shortest path calculations can be used for very fast repetative calculations to or from the same point in a GridGraph.
- Other Useful Features:
    - Graph
        - A low level graph object that has methods for validating graphs, calculating shortest paths, and more
    - CacheGraphs
        - A graph extension that caches spanning trees for fast shortest path calculations on repeat calls from the same origin node


## Setup

Make sure you have Python 3.10.x (or higher) installed on your system. You can download it [here](https://www.python.org/downloads/).

Note: Support for python3.6-python3.9 is available up to version 2.2.0.

## Installation

```
pip install scgraph
```

## Use with Google Colab

- [Getting Started](https://colab.research.google.com/github/connor-makowski/scgraph/blob/main/examples/getting_started.ipynb)
- [Creating A Multi Path Geojson](https://colab.research.google.com/github/connor-makowski/scgraph/blob/main/examples/multi_path_geojson.ipynb)
- [Modifying A Geograph](https://colab.research.google.com/github/connor-makowski/scgraph/blob/main/examples/geograph_modifications.ipynb)


# Getting Started

## Basic Geograph Usage

Get the shortest path between two points on earth using a latitude / longitude pair.

In this case, calculate the shortest maritime path between Shanghai, China and Savannah, Georgia, USA.

```py
# Use a maritime network geograph
from scgraph.geographs.marnet import marnet_geograph

# Get the shortest maritime path between Shanghai, China and Savannah, Georgia, USA
# Note: The origin and destination nodes can be any latitude / longitude pair
output = marnet_geograph.get_shortest_path(
    origin_node={"latitude": 31.23,"longitude": 121.47},
    destination_node={"latitude": 32.08,"longitude": -81.09},
    output_units='km',
    # Optional: Cache the origin node's spanning tree for faster calculations on future calls from the same origin node when cache=True
    # Note: This will make the first call slower, but future calls using this origin node will be substantially faster.
    cache=True,
)
print('Length: ',output['length']) #=> Length:  19596.4653
```

Adding in a few additional parameters to the `get_shortest_path` function can change the output format as well as performance of the calculation.
```py
# Use a maritime network geograph
from scgraph.geographs.marnet import marnet_geograph

# Get the shortest maritime path between Shanghai, China and Savannah, Georgia, USA
output = marnet_geograph.get_shortest_path(
    origin_node={"latitude": 31.23,"longitude": 121.47},
    destination_node={"latitude": 32.08,"longitude": -81.09},
    output_units='km',
    node_addition_lat_lon_bound=180, # Optional: The maximum distance in degrees to consider nodes when attempting to add the origin and destination nodes to the graph
    node_addition_type='quadrant', # Optional: Instead of connecting the origin node to the graph by the closest node, connect it to the closest node in each direction (NE, NW, SE, SW) if found within the node_addition_lat_lon_bound
    destination_node_addition_type='all', # Optional: Instead of connecting the destination node to the graph by the closest node, connect it to all nodes found within the node_addition_lat_lon_bound
    # When destination_node_addition_type='all' is set with a node_addition_lat_lon_bound=180, this will guarantee a solution can be found since the destination node will also connect to the origin node
)
print('Length: ',output['length']) #=> Length:  19596.4653
```

In the above example, the `output` variable is a dictionary with two keys: `length` and `coordinate_path`.

- `length`: The distance between the passed origin and destination when traversing the graph along the shortest path
    - Notes:
        - This will be in the units specified by the `output_units` parameter.
        - `output_units` options:
            - `km` (kilometers - default)
            - `m` (meters)
            - `mi` (miles)
            - `ft` (feet)
- `coordinate_path`: A list of lists [`latitude`,`longitude`] that make up the shortest path


You can also use the efficient distance matrix function to quickly get the distances between multiple points on the graph.
```py
from scgraph.geographs.us_freeway import us_freeway_geograph

cities = [
    {"latitude": 34.0522, "longitude": -118.2437},  # Los Angeles
    {"latitude": 40.7128, "longitude": -74.0060},   # New York City
    {"latitude": 41.8781, "longitude": -87.6298},   # Chicago
    {"latitude": 29.7604, "longitude": -95.3698},   # Houston
]

distance_matrix = us_freeway_geograph.distance_matrix(cities, output_units='km')
# [
#  [0.0, 4510.965665644833, 3270.3864033755776, 2502.886438995942],
#  [4510.9656656448415, 0.0, 1288.473118634311, 2637.5821542546687],
#  [3270.3864033755744, 1288.4731186343113, 0.0, 1913.1928919854067],
#  [2502.886438995935, 2637.5821542546687, 1913.1928919854076, 0.0],
# ]
```

For more examples including viewing the output on a map, see the [example notebook](https://colab.research.google.com/github/connor-makowski/scgraph/blob/main/examples/getting_started.ipynb).

## Included GeoGraphs

- marnet_geograph:
    - What: A maritime network data set from searoute
    - Use: `from scgraph.geographs.marnet import marnet_geograph`
    - Attribution: [searoute](https://github.com/genthalili/searoute-py)
    - Length Measurement: Kilometers
    - [Marnet Picture](https://raw.githubusercontent.com/connor-makowski/scgraph/main/static/marnet.png)
- oak_ridge_maritime_geograph:
    - What: A maritime data set from the Oak Ridge National Laboratory campus
    - Use: `from scgraph.geographs.oak_ridge_maritime import oak_ridge_maritime_geograph`
    - Attribution: [Oak Ridge National Laboratory](https://www.ornl.gov/) with data from [Geocommons](http://geocommons.com/datasets?id=25)
    - Length Measurement: Kilometers
    - [Oak Ridge Maritime Picture](https://raw.githubusercontent.com/connor-makowski/scgraph/main/static/oak_ridge_maritime.png)
- north_america_rail_geograph:
    - What: Class 1 Rail network for North America
    - Use: `from scgraph.geographs.north_america_rail import north_america_rail_geograph`
    - Attribution: [U.S. Department of Transportation: ArcGIS Online](https://geodata.bts.gov/datasets/usdot::north-american-rail-network-lines-class-i-freight-railroads-view/about)
    - Length Measurement: Kilometers
    - [North America Rail Picture](https://raw.githubusercontent.com/connor-makowski/scgraph/main/static/north_america_rail.png)
- us_freeway_geograph:
    - What: Freeway network for the United States
    - Use: `from scgraph.geographs.us_freeway import us_freeway_geograph`
    - Attribution: [U.S. Department of Transportation: ArcGIS Online](https://hub.arcgis.com/datasets/esri::usa-freeway-system-over-1500k/about)
    - Length Measurement: Kilometers
    - [US Freeway Picture](https://raw.githubusercontent.com/connor-makowski/scgraph/main/static/us_freeway.png)
- `scgraph_data` geographs:
    - What: Additional geographs are available in the `scgraph_data` package
        - Note: These include larger geographs like the world highways geograph and world railways geograph.
    - Installation: `pip install scgraph_data`
    - Use: `from scgraph_data.world_highways import world_highways_geograph`
    - See: [scgraph_data](https://github.com/connor-makowski/scgraph_data) for more information and all available geographs.

## GridGraph usage

Example:
- Create a grid of 20x20 cells.
    - This creates a grid based graph with connections to all 8 neighbors for each grid item.
    - Each grid item has 4 cardinal connections at length 1 and 4 diagonal connections at length sqrt(2)
- Create a wall from (10,5) to (10,19).
    - This would foce any path to go to the bottom of the graph to get around the wall.
- Get the shortest path between (2,10) and (18,10)
    - Note: The length of this path should be 16 without the wall and 20.9704 with the wall.

```py
from scgraph import GridGraph

x_size = 20
y_size = 20
blocks = [(10, i) for i in range(5, y_size)]

# Create the GridGraph object
gridGraph = GridGraph(
    x_size=x_size,
    y_size=y_size,
    blocks=blocks,
    add_exterior_walls=True,
)

# Solve the shortest path between two points
output = gridGraph.get_shortest_path(
    origin_node={"x": 2, "y": 10},
    destination_node={"x": 18, "y": 10},
    # Optional: Specify the output coodinate format (default is 'list_of_dicts)
    output_coordinate_path="list_of_lists",
    # Optional: Cache the origin point spanning_tree for faster calculations on future calls
    cache=True,
)

print(output)
#=> {'length': 20.9704, 'coordinate_path': [[2, 10], [3, 9], [4, 8], [5, 8], [6, 7], [7, 6], [8, 5], [9, 4], [10, 4], [11, 4], [12, 5], [13, 6], [14, 7], [15, 7], [16, 8], [17, 9], [18, 10]]}
```

## Advanced Usage

### Using scgraph_data geographs

Using `scgraph_data` geographs:
- Note: Make sure to install the `scgraph_data` package before using these geographs
```py
from scgraph_data.world_railways import world_railways_geograph
from scgraph import Graph

# Get the shortest path between Kalamazoo Michigan and Detroit Michigan by Train
output = world_railways_geograph.get_shortest_path(
    origin_node={"latitude": 42.29,"longitude": -85.58},
    destination_node={"latitude": 42.33,"longitude": -83.05},
    # Optional: Use the A* algorithm
    algorithm_fn=Graph.a_star,
    # Optional: Pass the haversine function as the heuristic function to the A* algorithm
    algorithm_kwargs={"heuristic_fn": world_railways_geograph.haversine},
)
```

### Using Geographs for Visualization
Get a geojson line path of an output for easy visualization:
- Note: `mapshaper.org` and `geojson.io` are good tools for visualizing geojson files
```py
from scgraph.geographs.marnet import marnet_geograph
from scgraph.utils import get_line_path

 # Get the shortest sea path between Sri Lanka and Somalia
output = marnet_geograph.get_shortest_path(
    origin_node={"latitude": 7.87,"longitude": 80.77},
    destination_node={"latitude": 5.15,"longitude": 46.20}
)
# Write the output to a geojson file
get_line_path(output, filename='output.geojson')
```

### Building your own Geographs from Open Source Data
You can build your own geographs using various tools and data sources. For example, you can use OpenStreetMap data to create a high fidelity geograph for a specific area.

Expand the secion below for a step by step guide on how to create a geograph from OpenStreetMap data.
<details>
<summary>Click to see an example for Michigan, USA</summary>

For this example, we will use some various tools to create a geograph for highways (including seconday highways) in Michigan, USA.

Download an OSM PBF file using the AWS CLI:
- Geofabrik is a good source for smaller OSM PBF files. See: https://download.geofabrik.de/
- To keep things generalizable, you can also download the entire planet OSM PBF file using AWS. But you should consider downloading a smaller region if you are only interested in a specific area.
    - Note: For this, you will need to install the AWS CLI.
    - Note: The planet OSM PBF file is very large (About 100GB)
        ```
        aws s3 cp s3://osm-pds/planet-latest.osm.pbf .
        ```
- Use Osmium to filter and extract the highways from the OSM PBF file.
    - Install osmium on macOS:
        ```
        brew install osmium-tool
        ```
    - Install osmium on Ubuntu:
        ```
        sudo apt-get install osmium-tool
        ```
- Download a Poly file for the area you are interested in. This is a polygon file that defines the area you want to extract from the OSM PBF file.
    - For Michigan, you can download the poly file from Geofabrik:
        ```
        curl https://download.geofabrik.de/north-america/us/michigan.poly > michigan.poly
        ```
    - Google around to find an appropriate poly file for your area of interest.
- Filter and extract as GeoJSON (EG: Michigan) substituting the poly and pbf file names as needed:
    ```
    osmium extract -p michigan.poly --overwrite -o michigan.osm.pbf planet-latest.osm.pbf
    ```
- Filter the OSM PBF file to only areas of interest and export to GeoJSON:
    - See: https://wiki.openstreetmap.org/wiki/
    - EG For Highways, see: https://wiki.openstreetmap.org/wiki/Key:highway
    ```
    osmium tags-filter michigan.osm.pbf w/highway=motorway,trunk,primary,motorway_link,trunk_link,primary_link,secondary,secondary_link,tertiary,tertiary_link -t --overwrite -o michigan_roads.osm.pbf
    osmium export michigan_roads.osm.pbf -f geojson --overwrite -o michigan_roads.geojson
    ```

- Simplify the geojson
    - This uses some tools in the SCGraph library as well as Mapshaper to simplify the geojson files.
    - Mapshaper is a CLI and web tool for simplifying and editing geojson files.
    - To install Mapshaper for CLI use, use NPM:
        ```
        npm install -g mapshaper
        ```
    - Mapshaper is particularly helpful since it repairs intersections in the lines which is crutial for geographs to work properly.
    - Mapshaper, however, does not handle larger files very well, so it is recommended to simplify the geojson file first using the `scgraph.helpers.geojson.simplify_geojson` function first to reduce the size of the file.
    - Make sure to tailor the parameters to your needs.
    ```
    python -c "from scgraph.helpers.geojson import simplify_geojson; simplify_geojson('michigan_roads.geojson', 'michigan_roads_simple.geojson', precision=4, pct_to_keep=100, min_points=3, silent=False)"
    mapshaper michigan_roads_simple.geojson -simplify 10% -filter-fields -o force michigan_roads_simple.geojson
    mapshaper michigan_roads_simple.geojson -snap -clean -o force michigan_roads_simple.geojson
    ```
- Load the newly created geojson file as a geograph:
    - Note: The `GeoGraph.load_from_geojson` function is used to load the geojson file as a geograph.
    - This will create a geograph that can be used to calculate shortest paths between points on the graph.
    ```
    from scgraph import GeoGraph
    michigan_roads_geograph = GeoGraph.load_from_geojson('michigan_roads_simple.geojson')
    ```
</details>

### Custom Graphs and Geographs
Modify an existing geograph: See the notebook [here](https://colab.research.google.com/github/connor-makowski/scgraph/blob/main/examples/geograph_modifications.ipynb)


You can specify your own custom graphs for direct access to the solving algorithms. This requires the use of the low level `Graph` class

```py
from scgraph import Graph

# Define an arbitrary graph
# See the graph definitions here:
# https://connor-makowski.github.io/scgraph/scgraph/graph.html#Graph.validate_graph
graph = [
    {1: 5, 2: 1},
    {0: 5, 2: 2, 3: 1},
    {0: 1, 1: 2, 3: 4, 4: 8},
    {1: 1, 2: 4, 4: 3, 5: 6},
    {2: 8, 3: 3},
    {3: 6}
]

# Optional: Validate your graph
Graph.validate_graph(graph=graph)

# Get the shortest path between idx 0 and idx 5
output = Graph.dijkstra_makowski(graph=graph, origin_id=0, destination_id=5)
#=> {'path': [0, 2, 1, 3, 5], 'length': 10}
```

You can also use a slightly higher level `GeoGraph` class to work with latitude / longitude pairs

```py
from scgraph import GeoGraph

# Define nodes
# See the nodes definitions here:
# https://connor-makowski.github.io/scgraph/scgraph/geograph.html#GeoGraph.__init__
nodes = [
    # London
    [51.5074, -0.1278],
    # Paris
    [48.8566, 2.3522],
    # Berlin
    [52.5200, 13.4050],
    # Rome
    [41.9028, 12.4964],
    # Madrid
    [40.4168, -3.7038],
    # Lisbon
    [38.7223, -9.1393]
]
# Define a graph
# See the graph definitions here:
# https://connor-makowski.github.io/scgraph/scgraph/graph.html#Graph.validate_graph
graph = [
    # From London
    {
        # To Paris
        1: 311,
    },
    # From Paris
    {
        # To London
        0: 311,
        # To Berlin
        2: 878,
        # To Rome
        3: 1439,
        # To Madrid
        4: 1053
    },
    # From Berlin
    {
        # To Paris
        1: 878,
        # To Rome
        3: 1181,
    },
    # From Rome
    {
        # To Paris
        1: 1439,
        # To Berlin
        2: 1181,
    },
    # From Madrid
    {
        # To Paris
        1: 1053,
        # To Lisbon
        5: 623
    },
    # From Lisbon
    {
        # To Madrid
        4: 623
    }
]

# Create a GeoGraph object
my_geograph = GeoGraph(nodes=nodes, graph=graph)

# Optional: Validate your graph
my_geograph.validate_graph()

# Optional: Validate your nodes
my_geograph.validate_nodes()

# Get the shortest path between two points
# In this case, Birmingham England and Zaragoza Spain
# Since Birmingham and Zaragoza are not in the graph,
# the algorithm will add them into the graph.
# See: https://connor-makowski.github.io/scgraph/scgraph/geograph.html#GeoGraph.get_shortest_path
# Expected output would be to go from
# Birmingham -> London -> Paris -> Madrid -> Zaragoza

output = my_geograph.get_shortest_path(
    # Birmingham England
    origin_node = {'latitude': 52.4862, 'longitude': -1.8904},
    # Zaragoza Spain
    destination_node = {'latitude': 41.6488, 'longitude': -0.8891}
)
print(output)
# {
#     'length': 1799.4323,
#     'coordinate_path': [
#         [52.4862, -1.8904],
#         [51.5074, -0.1278],
#         [48.8566, 2.3522],
#         [40.4168, -3.7038],
#         [41.6488, -0.8891]
#     ]
# }

```

# Development
## Running Tests, Prettifying Code, and Updating Docs

Make sure Docker is installed and running on a Unix system (Linux, MacOS, WSL2).

- Create a docker container and drop into a shell
    - `./run.sh`
- Run all tests (see ./utils/test.sh)
    - `./run.sh test`
- Prettify the code (see ./utils/prettify.sh)
    - `./run.sh prettify`
- Update the docs (see ./utils/docs.sh)
    - `./run.sh docs`

- Note: You can and should modify the `Dockerfile` to test different python versions.


## Attributions and Thanks
Originally inspired by [searoute](https://github.com/genthalili/searoute-py) including the use of one of their [datasets](https://github.com/genthalili/searoute-py/blob/main/searoute/data/marnet_densified_v2_old.geojson) that has been modified to work properly with this package.
"""

from .graph import Graph
from .geograph import GeoGraph
from .grid import GridGraph
