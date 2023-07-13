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
            - Dijkstra's algorithm
                - Modified to support sparse network data structures
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

# Getting Started

## Basic Usage

Get the shortest path between two points on earth using a latitude / longitude pair
In this case, calculate the shortest maritime path between Shanghai, China and Savannah, Georgia, USA.

```py
from scgraph import Graph
from scgraph.data import marnet_data

my_graph = Graph(data=marnet_data)
# Get the shortest path between 
output = my_graph.get_shortest_path(
    origin={"latitude": 31.23,"longitude": 121.47}, 
    destination={"latitude": 32.08,"longitude": -81.09}
)
print('Length: ',output['length']) #=> Length:  19596.735
```

In the above example, the `output` variable is a dictionary with two keys: `length` and `path`. The `length` key contains the distance in kilometers between the two points. The `path` key contains a list of dictionaries (containing `latitude` and `longitude`) that make up the shortest path between the two points.

To get the latitude / longitude pairs that make up the shortest path, as a list of lists, you could do something like the following:

```py
from scgraph import Graph
from scgraph.data import marnet_data

my_graph = Graph(data=marnet_data)
# Get the shortest path between 
output = my_graph.get_shortest_path(
    origin={"latitude": 31.23,"longitude": 121.47}, 
    destination={"latitude": 32.08,"longitude": -81.09}
)
print(str([[i['latitude'],i['longitude']] for i in output['path']]))
```

## Included Data Sets

- marnet_data:
    - What: A maritime network data set
    - Use: `from scgraph.data import marnet_data`

## Attributions and Thanks
Inspired by [searoute](https://github.com/genthalili/searoute-py) including the use of one of their [datasets](https://github.com/genthalili/searoute-py/blob/main/searoute/data/marnet_densified_v2_old.geojson) that has been modified to work properly with this package.