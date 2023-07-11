import copy
from .utils import Distance, hardRound


class Graph:
    def __init__(self, data: dict):
        """
        Function:

            Initialize a Graph object

            Returns `None`

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

            Validate that the nodes are a dictionary of dictionaries of floats or integers

            Returns `None`

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

            Validate that the graph is a dictionary of dictionaries of integers or floats

            If `check_symmetry` is True, also validate that the graph is symmetric

            Returns `None`

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

            Identify the minimum length route between two nodes in a sparse network graph

            Return that route as a list of node keys in the order they are visited

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
        # Create a dictionary to store the distance from the origin to each node
        # Initialize the distance to infinity for all nodes except the origin
        distance = {node: float("inf") for node in self.graph.keys()}
        distance[origin] = 0

        # Create a dictionary to store the predecessor of each node
        predecessor = {node: None for node in self.graph.keys()}

        # Create a list of unvisited nodes
        unvisited = set([node for node in self.graph.keys()])

        # While there are still unvisited nodes
        while unvisited:
            # Identify the unvisited node with the smallest distance
            current = min(unvisited, key=lambda node: distance[node])

            # Remove the current node from the unvisited list
            unvisited.remove(current)

            # If the current node is the destination, return the route
            if current == destination:
                route = []
                while current != origin:
                    route.append(current)
                    current = predecessor[current]
                route.append(origin)
                route.reverse()
                return route

            # For each neighbor of the current node
            for neighbor in self.graph[current].keys():
                # If the neighbor is still unvisited
                if neighbor in unvisited:
                    # Identify the distance from the origin to the neighbor
                    # through the current node
                    new_distance = (
                        distance[current] + self.graph[current][neighbor]
                    )
                    # If the new_distance is shorter than the current distance
                    if new_distance < distance[neighbor]:
                        # Update the distance
                        distance[neighbor] = new_distance
                        # Update the predecessor
                        predecessor[neighbor] = current

        # If there is no route between the origin and destination, return None
        return None

    def get_path_length(self, id_path):
        """
        Function:
            Calculate the length of a path

            Return the length of the path

        Required Arguments:

            - `id_path`
                - Type: list of strs
                - What: A list of node ids in the order they are visited

        Optional Arguments:

            - None
        """
        # Initialize the length to zero
        length = 0
        # For each pair of nodes in the path
        for origin, destination in zip(id_path[:-1], id_path[1:]):
            # Add the distance between the nodes to the length
            length += self.graph[origin][destination]
        return length

    def get_shortest_path(
        self, origin, destination, algorithm: str = "dijkstra"
    ):
        """
        Function:
            Identify the shortest path between two nodes in a sparse network graph

            Return a dictionary of various path information including:
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
                - Options: 'dijkstra'
        """
        # Assert that the algorithm is valid
        assert algorithm in [
            "dijkstra"
        ], f"Invalid algorithm provided ({algorithm}), valid options are: dijkstra"

        # Add the origin and destination nodes to the graph
        self.add_node(node=origin, name="origin")
        self.add_node(node=destination, name="destination")

        # Identify the shortest path
        if algorithm == "dijkstra":
            id_path = self.dijkstra("origin", "destination")
        else:
            raise ValueError(f"Invalid algorithm: {algorithm}")
        return {
            # 'id_path': id_path,
            "path": [self.nodes[node_id] for node_id in id_path],
            "length": hardRound(3, self.get_path_length(id_path)),
        }

    def add_node(
        self,
        node: dict,
        name: str,
        circuity: [float, int] = 4,
        distance_calculation: str = "haversine",
    ):
        """
        Function:

            Add a node to the network

            Return None

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
        # Calculate the distance from the new node to all other nodes
        self.graph[name] = {}
        for node_i_id, node_i in self.nodes.items():
            distance = Distance.haversine(node, node_i, circuity=circuity)
            self.graph[node_i_id][name] = distance
            self.graph[name][node_i_id] = distance
        # Add the node to the nodes dictionary
        self.nodes[name] = node
