from .utils import haversine, hard_round, distance_converter
import json


class Graph:
    @staticmethod
    def validate_graph(graph: dict):
        """
        Function:

        - Validate that a graph is properly formatted

        Required Arguments:

        - `graph`
            - Type: dict
            - What: A dictionary of dictionaries where the keys are origin node ids and the values are dictionaries of destination node ids and distances
            - Note: Ids must be integers starting at 0 and increasing sequentially to the number of nodes in the graph
            - Note: All nodes must be included as origins in the graph regardless of if they have any connected destinations

        Optional Arguments:

        - None
        """
        ids = []
        assert isinstance(graph, dict), "Your graph must be a dictionary"
        for origin_id, origin_dict in graph.items():
            assert isinstance(
                origin_id, int
            ), f"Origin and destination ids must be integers but {origin_id} is not an integer"
            assert isinstance(
                origin_dict, dict
            ), f"Your graph must be a dictionary of dictionaries but the value for origin {origin_id} is not a dictionary"
            ids.append(origin_id)
            for destination_id, distance in origin_dict.items():
                assert isinstance(
                    destination_id, int
                ), f"Origin and destination ids must be integers but {destination_id} is not an integer"
                assert isinstance(
                    distance, (int, float)
                ), f"Distances must be integers or floats but {distance} is not an integer or float"
                ids.append(destination_id)
        ids = set(ids)
        assert (
            min(ids) == 0
        ), f"Your graph must have ids starting at 0 but the minimum id is {min(ids)}"
        assert (
            max(ids) == len(ids) - 1
        ), f"Your graph must have ids that are sequential starting at 0 but the maximum id is {max(ids)}"
        assert len(graph) == len(
            ids
        ), f"Your graph must have origin ids for all nodes regardless of if they have any connected destinations"

    @staticmethod
    def dijkstra(graph: dict, origin_id: int, destination_id: int):
        """
        Function:

        - Identify the shortest path between two nodes in a sparse network graph using a modified dijkstra algorithm
            - Modifications allow for a sparse distance matrix to be used instead of a dense distance matrix
            - This can dramatically reduce the memory and compute requirements of the algorithm
            - This algorithm runs in O(n^2) time where n is the number of nodes in the graph
        - Return a dictionary of various path information including:
            - `id_path`: A list of node ids in the order they are visited
            - `path`: A list of node dictionaries (lat + long) in the order they are visited

        Required Arguments:

        - `graph`
            - Type: dict
            - What: A dictionary of dictionaries where the keys are origin node ids and the values are dictionaries of destination node ids and distances
        - `origin_id`
            - Type: int
            - What: The id of the origin node from the graph dictionary to start the shortest path from
        - `destination_id`
            - Type: int
            - What: The id of the destination node from the graph dictionary to end the shortest path at

        Optional Arguments:

        - None
        """
        distance_matrix = [float("inf") for i in graph]
        branch_tip_distances = [float("inf") for i in graph]
        predecessor = [None for i in graph]

        distance_matrix[origin_id] = 0
        branch_tip_distances[origin_id] = 0

        while True:
            current_distance = min(branch_tip_distances)
            if current_distance == float("inf"):
                return None
            current_id = branch_tip_distances.index(current_distance)
            branch_tip_distances[current_id] = float("inf")
            if current_id == destination_id:
                break
            for connected_id, connected_distance in graph[current_id].items():
                possible_distance = current_distance + connected_distance
                if possible_distance < distance_matrix[connected_id]:
                    distance_matrix[connected_id] = possible_distance
                    predecessor[connected_id] = current_id
                    branch_tip_distances[connected_id] = possible_distance

        output_path = [current_id]
        while predecessor[current_id] is not None:
            current_id = predecessor[current_id]
            output_path.append(current_id)

        output_path.reverse()

        return {
            "path": output_path,
            "length": hard_round(4, distance_matrix[destination_id]),
        }

    @staticmethod
    def dijkstra_makowski(graph: dict, origin_id: int, destination_id: int):
        """
        Function:

        - Identify the shortest path between two nodes in a sparse network graph using Makowski's modified Dijkstra algorithm
            - Modifications allow for a sparse distance matrix to be used instead of a dense distance matrix
            - Improvements include only computing future potential nodes based on the open leaves for each branch
                - Open leaves are nodes that have not been visited yet but are adjacent to other visited nodes
            - This can dramatically reduce the memory and compute requirements of the algorithm
            - For particularly sparse graphs, this algorithm runs close to O(n) time
                - Where n is the number of nodes in the graph
            - For dense graphs, this algorithm runs in O(n^2) time
                - Where n is the number of nodes in the graph
        - Return a dictionary of various path information including:
            - `id_path`: A list of node ids in the order they are visited
            - `path`: A list of node dictionaries (lat + long) in the order they are visited

        Required Arguments:

        - `graph`
            - Type: dict
            - What: A dictionary of dictionaries where the keys are origin node ids and the values are dictionaries of destination node ids and distances
        - `origin_id`
            - Type: int
            - What: The id of the origin node from the graph dictionary to start the shortest path from
        - `destination_id`
            - Type: int
            - What: The id of the destination node from the graph dictionary to end the shortest path at

        Optional Arguments:

        - None
        """
        distance_matrix = [float("inf") for i in graph]
        open_leaves = {}
        predecessor = [None for i in graph]

        distance_matrix[origin_id] = 0
        open_leaves[origin_id] = 0

        while True:
            if len(open_leaves) == 0:
                return None
            current_id = min(open_leaves, key=open_leaves.get)
            open_leaves.pop(current_id)
            if current_id == destination_id:
                break
            current_distance = distance_matrix[current_id]
            for connected_id, connected_distance in graph[current_id].items():
                possible_distance = current_distance + connected_distance
                if possible_distance < distance_matrix[connected_id]:
                    distance_matrix[connected_id] = possible_distance
                    predecessor[connected_id] = current_id
                    open_leaves[connected_id] = possible_distance

        output_path = [current_id]
        while predecessor[current_id] is not None:
            current_id = predecessor[current_id]
            output_path.append(current_id)

        output_path.reverse()

        return {
            "path": output_path,
            "length": hard_round(4, distance_matrix[destination_id]),
        }


class GeoGraph:
    def __init__(self, graph: dict, nodes: dict):
        """
        Function:

        - Create a GeoGraph object

        Required Arguments:

        - `graph`
            - Type: dict
            - What: A dictionary of dictionaries where the keys are origin node ids and the values are dictionaries of destination node ids and distances
            - Note: Ids must be integers starting at 0 and increasing sequentially to the number of nodes in the graph
            - Note: All nodes must be included as origins in the graph regardless of if they have any connected destinations
        - `nodes`
            - Type: dict
            - What: A dictionary of dictionaries where the keys are node ids and the values are dictionaries of node coordinates (latitude and longitude)
            - Note: Ids must be integers starting at 0 and increasing sequentially to the number of nodes in the graph
            - Note: All nodes must be included in the nodes dictionary

        Optional Arguments:

        """
        self.graph = graph
        self.nodes = nodes

    def validate_graph(self):
        """
        Function:

        - Validate that self.graph is properly formatted (see Graph.validate_graph)

        Required Arguments:

        - None

        Optional Arguments:

        - None
        """
        Graph.validate_graph(self.graph)

    def validate_nodes(self):
        """

        Function:

        - Validate that self.nodes is properly formatted (see GeoGraph.__init__ docs for more details)

        Required Arguments:

        - None

        Optional Arguments:

        - None
        """
        assert isinstance(self.nodes, dict), "Your nodes must be a dictionary"
        for node, node_dict in self.nodes.items():
            assert isinstance(
                node_dict, dict
            ), f"Your nodes must be a dictionary of dictionaries but the value for node {node} is not a dictionary"
            for key, value in node_dict.items():
                assert key in [
                    "latitude",
                    "longitude",
                ], f"Your nodes must be a dictionary of dictionaries where the keys are 'latitude' and 'longitude' but the key ({key}) for node ({node}) is not 'latitude' or 'longitude'"
                assert isinstance(
                    value,
                    (
                        float,
                        int,
                    ),
                ), f"Your nodes must be a dictionary of dictionaries where the values are floats or ints but the value for node ({node}) and key ({key}) is not a float"
            assert (
                node_dict.get("latitude") >= -90
                and node_dict.get("latitude") <= 90
            ), f"Your latitude values must be between -90 and 90 but the latitude value for node {node} is {node_dict.get('latitude')}"
            assert (
                node_dict.get("longitude") >= -180
                and node_dict.get("longitude") <= 180
            ), f"Your longitude values must be between -180 and 180 but the longitude value for node {node} is {node_dict.get('longitude')}"

    def get_shortest_path(
        self,
        origin_node,
        destination_node,
        output_units: str = "km",
        algorithm_fn=Graph.dijkstra_makowski,
        off_graph_circuity: [float, int] = 1,
        node_addition_type: str = "quadrant",
        node_addition_circuity: [float, int] = 4,
        geograph_units: str = "km",
        **kwargs,
    ):
        """
        Function:

        - Identify the shortest path between two nodes in a sparse network graph

        - Return a dictionary of various path information including:
            - `id_path`: A list of node ids in the order they are visited
            - `path`: A list of node dictionaries (lat + long) in the order they are visited
            - `length`: The length of the path

         Required Arguments:

        - `origin_node`
            - Type: dict
            - What: A dictionary with the keys 'latitude' and 'longitude'
        - `destination_node`
            - Type: dict
            - What: A dictionary with the keys 'latitude' and 'longitude'

        Optional Arguments:

        - `output_units`
            - Type: str
            - What: The units in which to return the length of the path
            - Default: 'km'
            - Options:
                - 'km': Kilometers
                - 'm': Meters
                - 'mi': Miles
                - 'ft': Feet
        - `algorithm_fn`
            - Type: function | method
            - What: The algorithm function to identify the shortest path
            - Default: 'Graph.dijkstra_makowski'
            - Options:
                - 'Graph.dijkstra': A modified dijkstra algorithm that uses a sparse distance matrix to identify the shortest path
                - 'Graph.dijkstra_makowski': A modified dijkstra algorithm that uses a sparse distance matrix to identify the shortest path
                - Any user defined algorithm that takes the arguments:
                    - `graph`: A dictionary of dictionaries where the keys are origin node ids and the values are dictionaries of destination node ids and distances
                    - `origin`: The id of the origin node from the graph dictionary to start the shortest path from
                    - `destination`: The id of the destination node from the graph dictionary to end the shortest path at
        - `off_graph_circuity`
            - Type: float | int
            - What: The circuity factor to apply to any distance calculations between your origin and destination nodes and their connecting nodes in the graph
            - Default: 1
            - Notes:
                - For alogrithmic solving purposes, the node_addition_circuity is applied to the origin and destination nodes when they are added to the graph
                - This is only applied after an `optimal solution` using the `node_addition_circuity` has been found when it is then adjusted to equal the `off_graph_circuity`
        - `node_addition_type`
            - Type: str
            - What: The type of node addition to use when adding your origin and destination nodes to the distance matrix
            - Default: 'quadrant'
            - Options:
                - 'quadrant': Add the closest node in each quadrant (ne, nw, se, sw) to the distance matrix for this node
                - 'closest': Add only the closest node to the distance matrix for this node
                - 'all': Add all nodes to the distance matrix for this node
            - Notes:
                - `dijkstra_makowski` will operate substantially faster if the `node_addition_type` is set to 'quadrant' or 'closest'
                - `dijkstra` will operate at the similar speeds regardless of the `node_addition_type`
                - When using `all`, you should consider using `dijkstra` instead of `dijkstra_makowski` as it will be faster
        - `node_addition_circuity`
            - Type: float | int
            - What: The circuity factor to apply when adding your origin and destination nodes to the distance matrix
            - Default: 4
            - Note:
                - This defaults to 4 to prevent the algorithm from taking a direct route in direction of the destination over some impassible terrain (EG: a maritime network that goes through land)
                - A higher value will push the algorithm to join the network at a closer node to avoid the extra distance from the circuity factor
                - This is only relevant if `node_addition_type` is set to 'quadrant' or 'all' as it affects the choice on where to enter the graph network
                - This factor is used to calculate the node sequence for the `optimal route`, however the reported `length` of the path will be calculated using the `off_graph_circuity` factor
        - `geograph_units`
            - Type: str
            - What: The units of measurement in the geograph data
            - Default: 'km'
            - Options:
                - 'km': Kilometers
                - 'm': Meters
                - 'mi': Miles
                - 'ft': Feet
            - Note: In general, all scgraph provided geographs be in kilometers
        - `**kwargs`
            - Additional keyword arguments. These are included for forwards and backwards compatibility reasons, but are not currently used.
        """
        # Add the origin and destination nodes to the graph
        origin_id = self.add_node(
            node=origin_node,
            node_addition_type=node_addition_type,
            circuity=node_addition_circuity,
        )
        destination_id = self.add_node(
            node=destination_node,
            node_addition_type=node_addition_type,
            circuity=node_addition_circuity,
        )

        try:
            output = algorithm_fn(
                graph=self.graph,
                origin_id=origin_id,
                destination_id=destination_id,
            )
            output["coordinate_path"] = self.get_coordinate_path(output["path"])
            output["length"] = self.adujust_circuity_length(
                output=output,
                node_addition_circuity=node_addition_circuity,
                off_graph_circuity=off_graph_circuity,
            )
            output["length"] = distance_converter(
                output["length"],
                input_units=geograph_units,
                output_units=output_units,
            )
            self.remove_added_node(node_id=origin_id)
            self.remove_added_node(node_id=destination_id)
            return output
        except Exception as e:
            self.remove_added_node(node_id=origin_id)
            self.remove_added_node(node_id=destination_id)
            raise e

    def adujust_circuity_length(
        self,
        output: dict,
        node_addition_circuity: [float, int],
        off_graph_circuity: [float, int],
    ):
        """
        Function:

        - Adjust the length of the path to account for the circuity factors applied to the origin and destination nodes

        Required Arguments:

        - `output`
            - Type: dict
            - What: The output from the algorithm function
        - `node_addition_circuity`
            - Type: float | int
            - What: The circuity factor that was applied when adding your origin and destination nodes to the distance matrix
        - `off_graph_circuity`
            - Type: float | int
            - What: The circuity factor to apply to any distance calculations between your origin and destination nodes and their connecting nodes in the graph
        """
        coordinate_path = output["coordinate_path"]
        # If the path does not enter the graph, undo the node_addition_circuity and apply the off_graph_circuity
        if len(output["coordinate_path"]) == 2:
            return (
                output["length"] / node_addition_circuity
            ) * off_graph_circuity
        else:
            direct_off_graph_length = haversine(
                coordinate_path[0], coordinate_path[1], circuity=1
            ) + haversine(coordinate_path[-2], coordinate_path[-1], circuity=1)
            return round(
                output["length"]
                + direct_off_graph_length
                * (off_graph_circuity - node_addition_circuity),
                4,
            )

    def get_coordinate_path(self, path):
        """
        Function:

        - Return a list of node dictionaries (lat + long) in the order they are visited

        Required Arguments:

        - `path`
            - Type: list
            - What: A list of node ids in the order they are visited

        Optional Arguments:

        - None
        """
        return [self.nodes[node_id] for node_id in path]

    def remove_added_node(self, node_id: int):
        """
        Function:

        - Remove a node that has been added to the network from the network
        - Assumes that this node has symmetric flows
            - EG: If node A has a distance of 10 to node B, then node B has a distance of 10 to node A
        - Return None

        Required Arguments:

        - `node_id`
            - Type: str
            - What: The name of the node to remove

        Optional Arguments:

        - None
        """
        # Assert that the node exists
        assert (
            node_id in self.nodes
        ), f"Node {node_id} does not exist in the network"
        reverse_connections = [i for i in self.graph[node_id].keys()]
        for reverse_connection in [i for i in self.graph[node_id].keys()]:
            del self.graph[reverse_connection][node_id]
        del self.graph[node_id]
        del self.nodes[node_id]

    def add_node(
        self,
        node: dict,
        circuity: [float, int],
        node_addition_type: str = "quadrant",
    ):
        """
        Function:

        - Add a node to the network
        - Returns the id of the new node

        Required Arguments:

        - `node`
            - Type: dict
            - What: A dictionary with the keys 'latitude' and 'longitude'

        Optional Arguments:

        - `circuity`
            - Type: float | int
            - What: The circuity to apply to any distance calculations
            - Default: 4
            - Note: This defaults to 4 to prevent the algorithm from taking a direct route in direction of the destination over some impassible terrain (EG: a maritime network that goes through land)
        - `node_addition_type`
            - Type: str
            - What: The type of node addition to use
            - Default: 'quadrant'
            - Options:
                - 'quadrant': Add the closest node in each quadrant (ne, nw, se, sw) to the distance matrix for this node
                - 'closest': Add only the closest node to the distance matrix for this node
                - 'all': Add all nodes to the distance matrix for this node
            - Notes:
                - `dijkstra_makowski` will operate substantially faster if the `node_addition_type` is set to 'quadrant' or 'closest'
                - `dijkstra` will operate at the similar speeds regardless of the `node_addition_type`
                - When using `all`, you should consider using `dijkstra` instead of `dijkstra_makowski` as it will be faster

        """
        # Validate the inputs
        assert isinstance(node, dict), "Node must be a dictionary"
        assert "latitude" in node.keys(), "Node must have a latitude"
        assert "longitude" in node.keys(), "Node must have a longitude"
        assert (
            node["latitude"] >= -90 and node["latitude"] <= 90
        ), "Latitude must be between -90 and 90"
        assert (
            node["longitude"] >= -180 and node["longitude"] <= 180
        ), "Longitude must be between -180 and 180"
        assert circuity > 0, "Circuity must be greater than 0"
        assert node_addition_type in [
            "quadrant",
            "all",
            "closest",
        ], f"Invalid node addition type provided ({node_addition_type}), valid options are: ['quadrant', 'all', 'closest']"

        # Create the node
        new_node_id = max(self.graph) + 1
        self.nodes[new_node_id] = node
        self.graph[new_node_id] = {}

        distances = {
            node_i_id: {
                "distance": round(
                    haversine(node, node_i, circuity=circuity), 4
                ),
                "quadrant": (
                    "n" if node["latitude"] > node_i["latitude"] else "s"
                )
                + ("e" if node["longitude"] > node_i["longitude"] else "w"),
            }
            for node_i_id, node_i in self.nodes.items()
        }

        if node_addition_type == "all":
            for node_i_id, node_i in self.nodes.items():
                self.graph[new_node_id][node_i_id] = distances[node_i_id][
                    "distance"
                ]
                self.graph[node_i_id][new_node_id] = distances[node_i_id][
                    "distance"
                ]
        elif node_addition_type == "closest":
            min_node_id = min(distances, key=lambda x: distances[x]["distance"])
            self.graph[new_node_id][min_node_id] = distances[min_node_id][
                "distance"
            ]
            self.graph[min_node_id][new_node_id] = distances[min_node_id][
                "distance"
            ]
        elif node_addition_type == "quadrant":
            for quadrant in ["ne", "nw", "se", "sw"]:
                min_node_id = min(
                    distances,
                    key=lambda x: distances[x]["distance"]
                    if distances[x]["quadrant"] == quadrant
                    else float("inf"),
                )
                self.graph[new_node_id][min_node_id] = distances[min_node_id][
                    "distance"
                ]
                self.graph[min_node_id][new_node_id] = distances[min_node_id][
                    "distance"
                ]
        return new_node_id

    def save_as_geojson(self, filename):
        """
        Function:

        - Save the current geograph object as a geojson file
        - This is useful for understanding the underlying geograph and for debugging purposes

        Required Arguments:

        - `filename`
            - Type: str
            - What: The filename to save the geojson file as

        """
        features = []
        for origin_idx, destinations in self.graph.items():
            for destination_idx, distance in destinations.items():
                # Create an undirected graph for geojson purposes
                if origin_idx > destination_idx:
                    continue
                origin = self.nodes.get(origin_idx)
                destination = self.nodes.get(destination_idx)
                features.append(
                    {
                        "type": "Feature",
                        "properties": {
                            "origin_idx": origin_idx,
                            "destination_idx": destination_idx,
                            "distance": distance,
                        },
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [
                                [origin["longitude"], origin["latitude"]],
                                [
                                    destination["longitude"],
                                    destination["latitude"],
                                ],
                            ],
                        },
                    }
                )

        out_dict = {"type": "FeatureCollection", "features": features}
        with open(filename, "w") as f:
            json.dump(out_dict, f)
