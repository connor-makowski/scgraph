# Routes by Time, Cost and CO2

This guide is for a user who routes by time, by cost or by CO2. After it, you can weigh each edge your own way, find the best route by these weights, read its parts, and close a canal.

A network gives each edge a length. A **metric** gives each edge another weight, under a name: its hours, its cost, its kg of CO2. You create a metric on a geograph, then you name it in a query. The **total** of a metric along a route is the sum of the weights of its edges. A query by a metric returns the route with the smallest total.

```py
from scgraph import GeoGraph

europe = GeoGraph.load_geograph("europe")

# Hours: a speed by road, by rail, by sea and by air, and a wait at each port, airport and rail terminal
europe.create_metric(
    "hours",
    per_km={"road": 1 / 70, "rail": 1 / 50, "sea": 1 / 30, "air": 1 / 750, "off_graph": 1 / 30},
    at_hub={"port": {"sea": 12}, "airport": {"air": 3}, "rail_terminal": {"rail": 4}},
    unit="h",
)

paris = {"latitude": 48.8566, "longitude": 2.3522}
berlin = {"latitude": 52.52, "longitude": 13.405}
route = europe.get_shortest_path(origin_node=paris, destination_node=berlin, metric="hours")
route["length"]   # the km of the fastest route
route["metrics"]  # {'hours': ...}: its hours
```

- **Rate.** A **rate** is the weight of 1 km of an edge. Here a rate is in hours per km: `1 / 70` means 70 km/h. These rates are examples. The library ships no speed, no cost and no emission factor: you give your own.
- **Modes.** A **node mode** says where a node is: `road`, `rail`, `sea`, `port`, `airport` or `rail_terminal`. An **edge mode** says how an edge is travelled: `road`, `rail`, `sea` or `air`. `per_km` gives a rate to each edge mode.
- **Class.** Each edge of `europe` has a **class**: its category in the source, such as `motorway`, `rail_main`, `suez` or `flight`. So does each edge of the other networks that scgraph publishes. Each class has one edge mode. A class can have its own rate, which wins over the rate of its edge mode: `"motorway": 1 / 90`.
- **Off the graph.** A **query point** is the origin or the destination of a query. An **access leg** is the straight line from a query point to its node. `"off_graph"` is the rate of the access legs. The total of a route counts its two access legs. The routing guide says [where a query point snaps](https://github.com/connor-makowski/scgraph/blob/main/guides/routing.md#where-a-query-point-snaps).
- **Hub.** A **hub** is a port, an airport or a rail terminal. `at_hub` adds a weight at a hub. Its first key is the node mode of the hub. Its second key is an edge mode or a class. Only these edges pay: here a truck pays nothing at a port. An edge into the hub pays, and so does an edge out of the hub. Here a flight pays 3 hours at the airport that it leaves and 3 hours at the airport that it reaches.
- **The result.** `length` is always the length of the route. `metrics` holds the total of each metric other than `length` along the route.

## The Legs of a Route

A **leg** is a part of a route on one edge mode. `output_legs=True` returns the legs, and the hubs between them:

```py
route = europe.get_shortest_path(origin_node=paris, destination_node=berlin, metric="hours", output_legs=True)
for leg in route["legs"]:
    print(leg["mode"], round(leg["length"]), "km", round(leg["metrics"]["hours"], 1), "h")
# One line for each leg: its edge mode, its km and its hours
route["hubs"]  # [{'node_id': ..., 'mode': 'airport'}, ...]: the hubs between two legs
```

The first leg and the last leg are the two access legs: their `mode` is `off_graph`. A leg by air holds the hours of its two airports. A leg also holds `class_lengths` and `coordinate_path`. `class_lengths` gives the km of the leg on each class.

## Three Ways to Compute the Weights

`create_metric` computes the weights in one of three ways:

| Way | Argument | Use it when |
|---|---|---|
| Rates | `per_km`, with `at_hub` | Each edge mode or each class has a rate per km, as in `hours` above |
| A weighted sum | `weighted_sum_of` | A metric combines other metrics, for example a cost of the hours and of the km |
| A function of an edge | `edge_weight_fn` | The weight of an edge is not a rate times its km |

With each of the three ways, `edge_weights` gives the weights of chosen edges. Use it when a few edges differ from the others. These weights replace the computed ones.

```py
# A weighted sum: 30 euros for each hour and 0.5 euro for each km
europe.create_metric("euros", weighted_sum_of={"hours": 30, "length": 0.5}, unit="EUR")

# A function of an edge: a short flight emits more CO2 for each km than a long flight
def get_co2(edge):
    if edge["mode"] == "air":
        return edge["length"] * (0.8 if edge["length"] < 1000 else 0.6)
    # None is the mode of an edge without a class, such as an edge that you add
    rates = {"road": 0.1, "rail": 0.02, "sea": 0.01, "off_graph": 0.1, None: 0.1}
    return edge["length"] * rates[edge["mode"]]

europe.create_metric("co2", edge_weight_fn=get_co2, unit="kg")

# The weights of chosen edges: each vehicle ferry takes twice its hours.
# A sum of one metric with the coefficient 1 copies it
ferries = europe.get_edges(edge_class="ferry")
europe.create_metric(
    "hours_with_slow_ferries",
    weighted_sum_of={"hours": 1},
    edge_weights={
        (edge["origin_id"], edge["destination_id"]): 2 * edge["metrics"]["hours"]
        for edge in ferries
    },
)
```

**A weighted sum.** A weighted sum is computed once, at its creation. When you create `hours` again, create `euros` again too. A weighted sum can also trade one metric against another: `weighted_sum_of={"co2": 1, "hours": 10}` counts one hour as 10 kg of CO2. An edge that is closed in one metric of the sum is closed in the sum. The notebook [Trade-offs between time, cost and CO2](https://colab.research.google.com/github/connor-makowski/scgraph/blob/main/examples/time_cost_co2_trade_offs.ipynb) tries several coefficients, and draws the routes on charts and on a map.

**The function.** The function gets one edge as a dict, with the keys `origin_id`, `destination_id`, `length`, `class`, `mode` and `metrics`. `metrics` holds the weight of the edge in each metric that exists at the call. The function is called once for each edge, so a function is slower than rates. It is called once more for the rate of the access legs, with a length of 1 km and `off_graph` as the `mode`.

**The rules of a call.** A call gives exactly one of `per_km`, `weighted_sum_of` and `edge_weight_fn`. A dict of `per_km` gives a rate for `"off_graph"`. It also gives a rate for each class that has an edge, by its name or by its edge mode. A geograph without classes, such as one made from your own graph, takes one number as `per_km`. A weight is a number of zero or more. A wrong argument raises a `ValueError` that names it. A metric that has the same name is replaced, and `remove_metric(name)` removes a metric. The docstring of [`create_metric`](https://connor-makowski.github.io/scgraph/scgraph.html#GeoGraph.create_metric) gives every argument.

## Closing a Class or an Edge

A rate of `None` closes a class: no route by this metric takes an edge of this class. The Suez Canal is the class `suez` of the sea lanes:

```py
world_sea = GeoGraph.load_geograph("world_sea")
world_sea.create_metric("km_without_suez", per_km={"sea": 1, "suez": None, "off_graph": 1})

rotterdam = {"latitude": 51.95, "longitude": 4.14}
singapore = {"latitude": 1.26, "longitude": 103.82}
by_the_canal = world_sea.get_shortest_path(origin_node=rotterdam, destination_node=singapore)
around_africa = world_sea.get_shortest_path(
    origin_node=rotterdam, destination_node=singapore, metric="km_without_suez"
)
around_africa["length"] > by_the_canal["length"]  # True
```

The network is not edited. A query by `length`, or by another metric, still takes the canal. When every route between two query points needs a closed edge, the query raises `PathNotFoundError`.

To close one edge, name it in `edge_weights`: `edge_weights={(origin_id, destination_id): None}`. An edge has one direction. Name `(destination_id, origin_id)` too to close both.

## Reading the Network

A geograph gives its node modes, its classes, its metrics, its nodes and its edges:

```py
europe.modes    # [{'name': 'road', ...}, ...]: the node modes
europe.classes  # [{'name': 'motorway', 'mode': 'road'}, ...]: each class with its edge mode
europe.metrics  # [{'name': 'length', 'unit': 'km'}, {'name': 'hours', 'unit': 'h', ...}, ...]

# The airports around Paris: mode is a node mode, bbox is (south, west, north, east) in degrees
europe.get_nodes(mode="airport", bbox=(48, 1, 50, 4))
# [{'node_id': ..., 'latitude': ..., 'longitude': ..., 'mode': 'airport'}, ...]

# The edges of one class, or the edges that leave one node: get_edges(origin_id=...)
europe.get_edges(edge_class="ferry")
# [{'origin_id': ..., 'destination_id': ..., 'length': ..., 'class': 'ferry', 'mode': 'road', 'metrics': {...}}, ...]

# The edges of a route, in its order: get_path_edges takes the node ids of the route
route = europe.get_shortest_path(origin_node=paris, destination_node=berlin, metric="hours", output_path=True)
europe.get_path_edges(route["path"])
```

**Files and edits.** `save_as_scgraph` writes the weights of each metric to the network file, and `load_from_scgraph` reads them. An edit of the network removes its metrics: create them again after it. The guide of your own graphs says more in [Modifying a GeoGraph](https://github.com/connor-makowski/scgraph/blob/main/guides/custom_graphs.md#modifying-a-geograph).

## Metrics and Algorithms

Each metric has its own graph: the edges of the network, with the weights of the metric. A query by a metric searches this graph, so every `algorithm_fn` works with every metric. `get_graph_object(metric)` returns this graph, for example to build a hierarchy of the metric. The routing guide gives the call in [Hierarchies: CH and TNR](https://github.com/connor-makowski/scgraph/blob/main/guides/routing.md#hierarchies-ch-and-tnr). [ARCHITECTURE.md](https://github.com/connor-makowski/scgraph/blob/main/ARCHITECTURE.md#classes-and-metrics) explains the graph of a metric.
