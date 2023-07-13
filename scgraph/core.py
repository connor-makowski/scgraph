import copy
from .utils import Distance


class Graph:
    def __init__(self, data: dict):
        """
        Function:

        - Initialize a Graph object
        - Returns `None`

        Required Arguments:

        - None

        Optional Arguments:

        - `data`:
            - Type: dict
            - What: A dictionary of dictionaries
            - Structure:
                - `graph`
                    - Type: dict of dicts of ints or floats
                    - What: A dictionary of dictionaries of integers or floats
                        - The first level of keys are the origin nodes
                        - The second level of keys are the destination nodes
                        - The values are the distances between the origin and destination nodes
                        - Note: The graph is assumed to be directed
                - `nodes`
                    - Type: dict of dicts of ints or floats
                    - What: A dictionary of dictionaries of integers or floats
                        - The first level of keys are the node ids
                        - The second level of keys are the attributes:
                            - `latitude`
                                - Type: float
                                - What: The latitude of the node
                            - `longitude`
                                - Type: float
                                - What: The longitude of the node
                        - The values are the attributes for the nodes
            - EG: {
                "graph": {
                        "0": {"1": 5, "2": 1},
                        "1": {"0": 5, "2": 2, "3": 1},
                        "2": {"0": 1, "1": 2, "3": 4, "4": 8},
                        "3": {"1": 1, "2": 4, "4": 3, "5": 6},
                        "4": {"2": 8, "3": 3},
                        "5": {"3": 6}
                    }
                "nodes": {
                        "0": {"latitude": 0, "longitude": 0},
                        "1": {"latitude": 0, "longitude": 1},
                        "2": {"latitude": 1, "longitude": 0},
                        "3": {"latitude": 1, "longitude": 1},
                        "4": {"latitude": 2, "longitude": 0},
                        "5": {"latitude": 2, "longitude": 1}
                    }
                }
            - Note: In the example:
                - The distance to travel from node "0" to node "1" is 5
                - The distance to travel from node "0" to node "2" is 1
                - Node "0" is at latitude 0 and longitude 0
        """
        self.graph = copy.deepcopy(data.get("graph", {}))
        self.nodes = copy.deepcopy(data.get("nodes", {}))

    def validate_nodes(self):
        """
        Function:

        - Validate that the nodes are a dictionary of dictionaries of floats or integers
        - Returns `None`

        Required Arguments:

        - None

        Optional Arguments:

        - None
        """
        assert isinstance(self.nodes, dict), "Your nodes must be a dictionary"
        # Check that the nodes are a dictionary of dictionaries of floats
        for node, node_dict in self.nodes.items():
            assert isinstance(
                node_dict, dict
            ), f"Your nodes must be a dictionary of dictionaries but the value for node {node} is not a dictionary"
            for key, value in node_dict.items():
                assert isinstance(
                    value,
                    (
                        float,
                        int,
                    ),
                ), f"Your nodes must be a dictionary of dictionaries where the values are floats or ints but the value for node ({node}) and key ({key}) is not a float"

    def validate_graph(self, check_symmetry: bool = True):
        """
        Function:

        - Validate that the graph is a dictionary of dictionaries of integers or floats
        - If `check_symmetry` is True, also validate that the graph is symmetric
        - Returns `None`

        Required Arguments:

        - None

        Optional Arguments:

        - `check_symmetry`
            - Type: bool
            - What: Whether to validate that the graph is symmetric
            - Default: True
        """
        assert isinstance(self.graph, dict), "Your graph must be a dictionary"
        # Check that the graph is a dictionary of dictionaries of integers or floats
        for origin, destination_dict in self.graph.items():
            assert isinstance(
                destination_dict, dict
            ), f"Your graph must be a dictionary of dictionaries but the value for origin ({origin}) is not a dictionary"
            for destination, distance in destination_dict.items():
                assert isinstance(
                    distance,
                    (
                        int,
                        float,
                    ),
                ), f"Your graph must be a dictionary of dictionaries where the keys are integers or floats but the key for origin ({origin}) and destination ({destination}) is not an integer or a float"
        # Check that the graph is symmetric
        if check_symmetry:
            for origin, destination_dict in self.graph.items():
                for destination, distance in destination_dict.items():
                    if distance != self.graph.get(destination, {}).get(
                        origin, None
                    ):
                        raise ValueError(
                            f"Graph is not symmetric for origin ({origin}) and destination ({destination})"
                        )

    def dijkstra(self, origin: str, destination: str):
        """
        Function:

        - Identify the minimum length route between two nodes in a sparse network graph
        - Return that route as a list of node keys in the order they are visited as well as the total distance traveled

        Algorithm Notes:

        - Runs in O(n^2) time

        Required Arguments:

        - `origin`
            - Type: str
            - What: The origin node key
        - `destination`
            - Type: str
            - What: The destination node key

        Optional Arguments:

        - None
        """
        ids = list(
            set(
                [key for key in self.graph.keys()]
                + [
                    key
                    for subdict in self.graph.values()
                    for key in subdict.keys()
                ]
            )
        )
        id_map = {key: idx for idx, key in enumerate(ids)}
        id_map_inv = {v: k for k, v in id_map.items()}

        origin_id = id_map[origin]
        destination_id = id_map[destination]

        id_graph = {
            id_map[origin]: {
                id_map[destination]: distance
                for destination, distance in self.graph[origin].items()
            }
            for origin in self.graph.keys()
        }

        distance_matrix = [float("inf") for i in id_map]
        branch_tip_distances = [float("inf") for i in id_map]
        predecessor = [None for i in id_map]

        distance_matrix[origin_id] = 0
        branch_tip_distances[origin_id] = 0

        while True:
            current_distance = min(branch_tip_distances)
            if current_distance == float("inf"):
                return None
            current = branch_tip_distances.index(current_distance)
            if current == destination_id:
                break
            for destination, distance in id_graph[current].items():
                new_distance = current_distance + distance
                if new_distance < distance_matrix[destination]:
                    distance_matrix[destination] = new_distance
                    predecessor[destination] = current
                    branch_tip_distances[destination] = new_distance
            branch_tip_distances[current] = float("inf")

        id_path = [current]
        while predecessor[current] is not None:
            current = predecessor[current]
            id_path.append(current)

        return {
            "path_ids": [id_map_inv[id] for id in id_path[::-1]],
            "length": distance_matrix[destination_id],
        }

    def dijkstra_v2(self, origin: str, destination: str):
        """
        Function:

        - Identify the minimum length route between two nodes in a sparse network graph
        - Return that route as a list of node keys in the order they are visited

        Algorithm Notes:

        - Runs between O(n) time and O(n^2) time depending on the sparsity of the graph
        - This algorithm is faster than `dijkstra` for graphs that terminate branches in dead ends
        - In general, this applies to graphs that are more sparse
        - For dense graphs, this algorithm will be slower than `dijkstra` because of the overhead of maintaining the open leaves as a dictionary

        Required Arguments:

        - `origin`
            - Type: str
            - What: The origin node key
        - `destination`
            - Type: str
            - What: The destination node key

        Optional Arguments:

        - None
        """
        ids = list(
            set(
                [key for key in self.graph.keys()]
                + [
                    key
                    for subdict in self.graph.values()
                    for key in subdict.keys()
                ]
            )
        )
        id_map = {key: idx for idx, key in enumerate(ids)}
        id_map_inv = {v: k for k, v in id_map.items()}

        origin_id = id_map[origin]
        destination_id = id_map[destination]

        id_graph = {
            id_map[origin]: {
                id_map[destination]: distance
                for destination, distance in self.graph[origin].items()
            }
            for origin in self.graph.keys()
        }

        distance_matrix = [float("inf") for i in id_map]
        open_leaves = {}
        predecessor = [None for i in id_map]

        distance_matrix[origin_id] = 0
        open_leaves[origin_id] = 0

        while True:
            if len(open_leaves) == 0:
                return None
            current = min(open_leaves, key=open_leaves.get)
            open_leaves.pop(current)
            if current == destination_id:
                break
            current_distance = distance_matrix[current]
            for destination, distance in id_graph[current].items():
                if current_distance + distance < distance_matrix[destination]:
                    distance_matrix[destination] = current_distance + distance
                    predecessor[destination] = current
                    open_leaves[destination] = current_distance + distance

        id_path = [current]
        while predecessor[current] is not None:
            current = predecessor[current]
            id_path.append(current)

        return {
            "path_ids": [id_map_inv[id] for id in id_path[::-1]],
            "length": distance_matrix[destination_id],
        }

    def get_shortest_path(
        self,
        origin,
        destination,
        algorithm: str = "dijkstra_v2",
        node_addition_type: str = "quadrant",
    ):
        """
        Function:

        - Identify the shortest path between two nodes in a sparse network graph

        - Return a dictionary of various path information including:
            - `id_path`: A list of node ids in the order they are visited
            - `path`: A list of node dictionaries (lat + long) in the order they are visited
            - `length`: The length of the path

         Required Arguments:

        - `origin`
            - Type: dict
            - What: A dictionary with the keys 'latitude' and 'longitude'
        - `destination`
            - Type: dict
            - What: A dictionary with the keys 'latitude' and 'longitude'

        Optional Arguments:

        - `algorithm`
            - Type: str
            - What: The algorithm to use to identify the shortest path
            - Default: 'dijkstra'
            - Options:
                - 'dijkstra': A modified dijkstra algorithm that uses a sparse distance matrix to identify the shortest path
                - 'dijkstra_v2': A modified dijkstra algorithm that uses a sparse distance matrix to identify the shortest path
        - `node_addition_type`
            - Type: str
            - What: The type of node addition to use when adding your origin and destination nodes to the distance matrix
            - Default: 'quadrant'
            - Options:
                - 'quadrant': Add the closest node in each quadrant (ne, nw, se, sw) to the distance matrix for this node
                - 'closest': Add only the closest node to the distance matrix for this node
                - 'all': Add all nodes to the distance matrix for this node
            - Notes:
                - `dijkstra_v2` will operate substantially faster if the `node_addition_type` is set to 'quadrant' or 'closest'
                - `dijkstra` will operate at the similar speeds regardless of the `node_addition_type`
                - When using `all`, you should consider using `dijkstra` instead of `dijkstra_v2` as it will be faster
        """
        # Assert that the algorithm is valid
        assert algorithm in [
            "dijkstra",
            "dijkstra_v2",
        ], f"Invalid algorithm provided ({algorithm}), valid options are: dijkstra or dijkstra_v2"

        # Add the origin and destination nodes to the graph
        self.add_node(
            node=origin, name="origin", node_addition_type=node_addition_type
        )
        self.add_node(
            node=destination,
            name="destination",
            node_addition_type=node_addition_type,
        )

        # Identify the shortest path
        if algorithm == "dijkstra":
            output = self.dijkstra("origin", "destination")
            if output is not None:
                output["path"] = [
                    self.nodes[node_id] for node_id in output["path_ids"]
                ]
            return output
        elif algorithm == "dijkstra_v2":
            output = self.dijkstra_v2("origin", "destination")
            if output is not None:
                output["path"] = [
                    self.nodes[node_id] for node_id in output["path_ids"]
                ]
            return output
        else:
            raise ValueError(f"Invalid algorithm: {algorithm}")

    def add_node(
        self,
        node: dict,
        name: str,
        circuity: [float, int] = 4,
        distance_calculation: str = "haversine",
        node_addition_type: str = "quadrant",
    ):
        """
        Function:

        - Add a node to the network
        - Return None

        Required Arguments:

        - `node`
            - Type: dict
            - What: A dictionary with the keys 'latitude' and 'longitude'
        - `name`
            - Type: str
            - What: The name of the node

        Optional Arguments:

        - `circuity`
            - Type: float | int
            - What: The circuity of the network
            - Default: 2
        - `distance_calculation`
            - Type: str
            - What: The distance calculation to use
            - Default: 'haversine'
            - Options: 'haversine'
        - `node_addition_type`
            - Type: str
            - What: The type of node addition to use
            - Default: 'quadrant'
            - Options:
                - 'quadrant': Add the closest node in each quadrant (ne, nw, se, sw) to the distance matrix for this node
                - 'closest': Add only the closest node to the distance matrix for this node
                - 'all': Add all nodes to the distance matrix for this node
            - Notes:
                - `dijkstra_v2` will operate substantially faster if the `node_addition_type` is set to 'quadrant' or 'closest'
                - `dijkstra` will operate at the similar speeds regardless of the `node_addition_type`
                - When using `all`, you should consider using `dijkstra` instead of `dijkstra_v2` as it will be faster

        """
        # Validate the node
        assert isinstance(name, str), f"Your node name ({name}) is not a string"
        assert isinstance(
            node, dict
        ), f"Your node ({name}) must be a dictionary"
        assert (
            "latitude" in node.keys()
        ), f'Your node must ({name}) have a key called "latitude"'
        assert (
            "longitude" in node.keys()
        ), 'Your node ({name}) must have a key called "longitude"'
        assert isinstance(
            node["latitude"], (int, float)
        ), f"Your node ({name}) latitude must be an integer or a float"
        assert isinstance(
            node["longitude"], (int, float)
        ), f"Your node ({name}) longitude must be an integer or a float"
        # Validate the circuity
        assert isinstance(
            circuity, (int, float)
        ), f"Your circuity for node ({name}) must be an integer or a float"
        assert (
            circuity >= 1
        ), f"Your circuity for node  ({name}) must be greater than or equal to 1"
        # Validate the distance calculation
        assert distance_calculation in [
            "haversine"
        ], f"Invalid distance calculation provided for node ({name}) with option ({distance_calculation}), valid options are: haversine"
        assert node_addition_type in [
            "quadrant",
            "all",
            "closest",
        ], f"Invalid node addition type provided for node ({name}) with option ({node_addition_type}), valid options are: quadrant, all, closest"
        if node_addition_type == "quadrant":
            # Calculate the distance from the new node to all other nodes and add
            # only the closest node in each directional quadrant (ne, nw, se, sw) to the graph
            quadrant_distances = {}
            for node_i_id, node_i in self.nodes.items():
                direction = (
                    "n" if node["latitude"] > node_i["latitude"] else "s"
                )
                direction += (
                    "e" if node["longitude"] > node_i["longitude"] else "w"
                )
                lowest_distance = quadrant_distances.get(direction, {}).get(
                    "distance", float("inf")
                )
                node_i_distance = Distance.haversine(
                    node, node_i, circuity=circuity
                )
                if node_i_distance < lowest_distance:
                    quadrant_distances[direction] = {
                        "distance": node_i_distance,
                        "node": node_i_id,
                    }
            self.graph[name] = {}
            for quadrant in quadrant_distances.values():
                self.graph[quadrant["node"]][name] = quadrant["distance"]
                self.graph[name][quadrant["node"]] = quadrant["distance"]
            # Add the node to the nodes dictionary
            self.nodes[name] = node
        elif node_addition_type == "all":
            # Calculate the distance from the new node to all other nodes
            self.graph[name] = {}
            for node_i_id, node_i in self.nodes.items():
                distance = Distance.haversine(node, node_i, circuity=circuity)
                self.graph[node_i_id][name] = distance
                self.graph[name][node_i_id] = distance
            # Add the node to the nodes dictionary
            self.nodes[name] = node
        elif node_addition_type == "closest":
            # Calculate the distance from the new node to all other nodes and add
            # only the closest node to the graph
            closest_node = None
            closest_distance = float("inf")
            for node_i_id, node_i in self.nodes.items():
                distance = Distance.haversine(node, node_i, circuity=circuity)
                if distance < closest_distance:
                    closest_node = node_i_id
                    closest_distance = distance
            self.graph[name] = {closest_node: closest_distance}
            self.graph[closest_node][name] = closest_distance
            # Add the node to the nodes dictionary
            self.nodes[name] = node
        else:
            raise ValueError(
                f"Invalid node addition type: {node_addition_type}"
            )
