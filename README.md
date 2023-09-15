# scgraph
[![PyPI version](https://badge.fury.io/py/scgraph.svg)](https://badge.fury.io/py/scgraph)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Supply chain graph package for Python


![scgraph](https://raw.githubusercontent.com/connor-makowski/scgraph/main/static/scgraph.png)

## Documentation

Getting Started: https://github.com/connor-makowski/scgraph

Low Level: https://connor-makowski.github.io/scgraph/core.html


## Key Features

- Calculate the shortest path between two points on earth using a latitude / longitude pair
    - Inputs:
        - A latitude / longitude pair for the origin
        - A latitude / longitude pair for the destination
    - Calculation:
        - Algorithms:
            - Dijkstra's algorithm (Modified for sparse networks)
                - Modified to support sparse network data structures
            - Makowski's Modified Sparse Dijkstra algorithm
                - Modified for O(n) performance on particularly sparse networks
            - Possible future support for other algorithms
        - Distances:
            - Uses the [haversine formula](https://en.wikipedia.org/wiki/Haversine_formula) to calculate the distance between two points on earth
    - Returns:
        - `path`:
            - A list of dictionaries (`latitude` and `longitude`) that make up the shortest path
        - `length`:
            - The distance in kilometers between the two points
- Antimeridian support
- Arbitrary start and end points
- Arbitrary network data sets
    


## Setup

Make sure you have Python 3.6.x (or higher) installed on your system. You can download it [here](https://www.python.org/downloads/).

## Installation

```
pip install scgraph
```

## Use with Google Colab

See the example [here](https://colab.research.google.com/github/connor-makowski/scgraph/blob/main/example.ipynb) 

# Getting Started

## Basic Usage

Get the shortest path between two points on earth using a latitude / longitude pair
In this case, calculate the shortest maritime path between Shanghai, China and Savannah, Georgia, USA.

```py
# Use a maritime network geograph
from scgraph.geographs.marnet import marnet_geograph

# Get the shortest path between 
output = marnet_geograph.get_shortest_path(
    origin_node={"latitude": 31.23,"longitude": 121.47}, 
    destination_node={"latitude": 32.08,"longitude": -81.09},
    output_units='km'
)
print('Length: ',output['length']) #=> Length:  19596.4653
```

In the above example, the `output` variable is a dictionary with three keys: `length`, `coordinate_path` and `path`.

- `length`: The distance between the passed origin and destination when traversing the graph along the shortest path
    - Notes: 
        - This will be in the units specified by the `output_units` parameter. 
        - `output_units` options:
            - `km` (kilometers - default)
            - `m` (meters)
            - `mi` (miles)
            - `ft` (feet)
- `coordinate_path`: A list of dictionaries (`latitude` and `longitude`) that make up the shortest path
- `path`: A list of node ids (from the network data set) that make up the shortest path
    - In general, these are only relevant if you are providing your own custom network data set

To get the latitude / longitude pairs that make up the shortest path, as a list of lists, you could do something like the following:

```py
# Use a maritime network geograph
from scgraph.geographs.marnet import marnet_geograph

# Get the shortest path between 
output = marnet_geograph.get_shortest_path(
    origin_node={"latitude": 31.23,"longitude": 121.47}, 
    destination_node={"latitude": 32.08,"longitude": -81.09}
)
print(str([[i['latitude'],i['longitude']] for i in output['coordinate_path']]))
```

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

## Advanced Usage

You can specify your own custom graphs for direct access to the solving algorithms. This requires the use of the low level `Graph` class

```py
from scgraph import Graph

# Define a graph
# See the graph definitions here: 
# https://connor-makowski.github.io/scgraph/core.html
graph = {
    0:{1: 5, 2: 1},
    1:{0: 5, 2: 2, 3: 1},
    2:{0: 1, 1: 2, 3: 4, 4: 8},
    3:{1: 1, 2: 4, 4: 3, 5: 6},
    4:{2: 8, 3: 3},
    5:{3: 6}
}

# Optional: Validate your graph
Graph.validate_graph(graph=graph)

# Get the shortest path between 0 and 5
output = Graph.dijkstra_makowski(graph=graph, origin_id=0, destination_id=5)
#=> {'path': [0, 2, 1, 3, 5], 'length': 10}
```

You can also use a slightly higher level `GeoGraph` class to work with latitude / longitude pairs

```py
from scgraph import GeoGraph

# Define nodes
# See the nodes definitions here: 
# https://connor-makowski.github.io/scgraph/core.html
nodes = {
    0: {"latitude": 0, "longitude": 0},
    1: {"latitude": 0, "longitude": 1},
    2: {"latitude": 1, "longitude": 0},
    3: {"latitude": 1, "longitude": 1},
    4: {"latitude": 1, "longitude": 2},
    5: {"latitude": 2, "longitude": 1}
}
# Define a graph
# See the graph definitions here: 
# https://connor-makowski.github.io/scgraph/core.html
graph = {
    0:{1: 5, 2: 1},
    1:{0: 5, 2: 2, 3: 1},
    2:{0: 1, 1: 2, 3: 4, 4: 8},
    3:{1: 1, 2: 4, 4: 3, 5: 6},
    4:{2: 8, 3: 3},
    5:{3: 6}
}

# Create a GeoGraph object
my_geograph = GeoGraph(nodes=nodes, graph=graph)

# Optional: Validate your graph
my_geograph.validate_graph()

# Optional: Validate your nodes
my_geograph.validate_nodes()

# Get the shortest path between two points
output = my_geograph.get_shortest_path(
    origin_node = {'latitude': 0, 'longitude': 0},
    destination_node = {'latitude': 2, 'longitude': 1}
)
#=>
# {
#     "path": [6, 0, 2, 1, 3, 5, 7],
#     "coordinate_path": [
#         {'latitude': 0, 'longitude': 0},
#         {'latitude': 0, 'longitude': 0},
#         {'latitude': 1, 'longitude': 0},
#         {'latitude': 0, 'longitude': 1},
#         {'latitude': 1, 'longitude': 1},
#         {'latitude': 2, 'longitude': 1},
#         {'latitude': 2, 'longitude': 1}
#     ],
#     "length": 10
# }
```

## Attributions and Thanks
Originally inspired by [searoute](https://github.com/genthalili/searoute-py) including the use of one of their [datasets](https://github.com/genthalili/searoute-py/blob/main/searoute/data/marnet_densified_v2_old.geojson) that has been modified to work properly with this package.