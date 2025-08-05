from heapq import heappop, heappush


class Graph:
    @staticmethod
    def validate_graph(
        graph: list[dict[int, int | float]],
        check_symmetry: bool = True,
        check_connected: bool = True,
    ) -> None:
        """
        Function:

        - Validate that a graph is properly formatted

        Required Arguments:

        - `graph`:
            - Type: list of dictionaries with integer keys and integer or float values
            - What: A list of dictionaries where the indicies are origin node ids and the values are dictionaries of destination node indices and graph weights
            - Note: All nodes must be included as origins in the graph regardless of if they have any connected destinations
            - EG:
            ```
                [
                    # From London (index 0)
                    {
                        # To Paris (index 1)
                        1: 311,
                    },
                    # From Paris (index 1)
                    {
                        # To London (index 0)
                        0: 311,
                        # To Berlin (index 2)
                        2: 878,
                        # To Rome (index 3)
                        3: 1439,
                        # To Madrid (index 4)
                        4: 1053
                    },
                    # From Berlin (index 2)
                    {
                        # To Paris (index 1)
                        1: 878,
                        # To Rome (index 3)
                        3: 1181,
                    },
                    # From Rome (index 3)
                    {
                        # To Paris (index 1)
                        1: 1439,
                        # To Berlin (index 2)
                        2: 1181,
                    },
                    # From Madrid (index 4)
                    {
                        # To Paris (index 1)
                        1: 1053,
                        # To Lisbon (index 5)
                        5: 623
                    },
                    # From Lisbon (index 5)
                    {
                        # To Madrid (index 4)
                        4: 623
                    }
                ]
            ```

        Optional Arguments:

        - `check_symmetry`
            - Type: bool
            - What: Whether to check that the graph is symmetric
            - Default: True
            - Note: This is forced to True if `check_connected` is True
        - `check_connected`
            - Type: bool
            - What: Whether to check that the graph is fully connected
            - Default: True
            - Note: For computational efficiency, only symmetric graphs are checked for connectivity
            - Note: If this is True, `check_symmetry` is forced to True and the graph will be checked for symmetry prior to checking for connectivity
        """
        check_symmetry = check_symmetry or check_connected
        assert isinstance(graph, list), "Your graph must be a list"
        len_graph = len(graph)
        for origin_id, origin_dict in enumerate(graph):
            assert isinstance(
                origin_dict, dict
            ), f"Your graph must be a list of dictionaries but the value for origin {origin_id} is not a dictionary"
            destinations = list(origin_dict.keys())
            lengths = list(origin_dict.values())
            assert all(
                [
                    (isinstance(i, int) and i >= 0 and i < len_graph)
                    for i in destinations
                ]
            ), f"Destination ids must be non-negative integers and equivalent to an existing index, but graph[{origin_id}] has an error in the destination ids"
            assert all(
                [(isinstance(i, (int, float)) and i >= 0) for i in lengths]
            ), f"Distances must be integers or floats, but graph[{origin_id}] contains a non-integer or non-float distance"
            if check_symmetry:
                for destination_id, distance in origin_dict.items():
                    assert (
                        graph[destination_id].get(origin_id) == distance
                    ), f"Your graph is not symmetric, the distance from node {origin_id} to node {destination_id} is {distance} but the distance from node {destination_id} to node {origin_id} is {graph.get(destination_id, {}).get(origin_id)}"
        if check_connected:
            assert Graph.validate_connected(
                graph
            ), "Your graph is not fully connected"

    @staticmethod
    def validate_connected(
        graph: list[dict[int, int | float]], origin_id: int = 0
    ) -> bool:
        """
        Function:

        - Validate that a graph is fully connected
            - This means that every node in the graph has a path to every other node in the graph
            - Note: This assumes that the graph is symmetric
        - Return True if the graph is fully connected and False if it is not

        Required Arguments:

        - `graph`:
            - Type: list of dictionaries
            - See: https://connor-makowski.github.io/scgraph/scgraph/graph.html#Graph.validate_graph

        Optional Arguments:

        - `origin_id`
            - Type: int
            - What: The id of the origin node from which to start the connectivity check
            - Default: 0
        """
        visited = [0] * len(graph)
        open_leaves = [origin_id]

        while open_leaves:
            current_id = open_leaves.pop()
            visited[current_id] = 1
            for connected_id, connected_distance in graph[current_id].items():
                if visited[connected_id] == 0:
                    open_leaves.append(connected_id)
        return min(visited) == 1

    @staticmethod
    def input_check(
        graph: list[dict[int, int | float]], origin_id: int, destination_id: int
    ) -> None:
        """
        Function:

        - Check that the inputs passed to the shortest path algorithm are valid
        - Raises an exception if the inputs passed are not valid

        Required Arguments:

        - `graph`:
            - Type: list of dictionaries
            - See: https://connor-makowski.github.io/scgraph/scgraph/graph.html#Graph.validate_graph
        - `origin_id`
            - Type: int
            - What: The id of the origin node from the graph dictionary to start the shortest path from
        - `destination_id`
            - Type: int
            - What: The id of the destination node from the graph dictionary to end the shortest path at

        Optional Arguments:

        - None
        """
        if (
            not isinstance(origin_id, int)
            and origin_id < len(graph)
            and origin_id >= 0
        ):
            raise Exception(f"Origin node ({origin_id}) is not in the graph")
        if (
            not isinstance(destination_id, int)
            and origin_id < len(graph)
            and origin_id >= 0
        ):
            raise Exception(
                f"Destination node ({destination_id}) is not in the graph"
            )

    @staticmethod
    def dijkstra(
        graph: list[dict[int, int | float]], origin_id: int, destination_id: int
    ) -> dict:
        """
        Function:

        - Identify the shortest path between two nodes in a sparse network graph using a modified dijkstra algorithm
            - Modifications allow for a sparse distance matrix to be used instead of a dense distance matrix
            - This can dramatically reduce the memory and compute requirements of the algorithm
            - This algorithm should run in O(n^2) time where n is the number of nodes in the graph
        - Return a dictionary of various path information including:
            - `id_path`: A list of node ids in the order they are visited
            - `path`: A list of node dictionaries (lat + long) in the order they are visited

        Required Arguments:

        - `graph`:
            - Type: list of dictionaries
            - See: https://connor-makowski.github.io/scgraph/scgraph/graph.html#Graph.validate_graph
        - `origin_id`
            - Type: int
            - What: The id of the origin node from the graph dictionary to start the shortest path from
        - `destination_id`
            - Type: int
            - What: The id of the destination node from the graph dictionary to end the shortest path at

        Optional Arguments:

        - None
        """
        Graph.input_check(
            graph=graph, origin_id=origin_id, destination_id=destination_id
        )
        distance_matrix = [float("inf")] * len(graph)
        branch_tip_distances = [float("inf")] * len(graph)
        predecessor = [-1] * len(graph)

        distance_matrix[origin_id] = 0
        branch_tip_distances[origin_id] = 0

        while True:
            current_distance = min(branch_tip_distances)
            if current_distance == float("inf"):
                raise Exception(
                    "Something went wrong, the origin and destination nodes are not connected."
                )
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
        while predecessor[current_id] != -1:
            current_id = predecessor[current_id]
            output_path.append(current_id)

        output_path.reverse()

        return {
            "path": output_path,
            "length": distance_matrix[destination_id],
        }

    @staticmethod
    def dijkstra_makowski(
        graph: list[dict[int, int | float]], origin_id: int, destination_id: int
    ) -> dict:
        """
        Function:

        - Identify the shortest path between two nodes in a sparse network graph using a modified Dijkstra algorithm
            - Modifications allow for a sparse distance matrix to be used instead of a dense distance matrix
            - Improvements include only computing future potential nodes based on the open leaves for each branch
                - Open leaves are nodes that have not been visited yet but are adjacent to other visited nodes
            - This can dramatically reduce the memory and compute requirements of the algorithm
            - This algorithm should run close to O((n+m) log n) time
                - Where n is the number of nodes in the graph and m is the number of edges in the graph
        - Return a dictionary of various path information including:
            - `id_path`: A list of node ids in the order they are visited
            - `path`: A list of node dictionaries (lat + long) in the order they are visited

        Required Arguments:

        - `graph`:
            - Type: list of dictionaries
            - See: https://connor-makowski.github.io/scgraph/scgraph/graph.html#Graph.validate_graph
        - `origin_id`
            - Type: int
            - What: The id of the origin node from the graph dictionary to start the shortest path from
        - `destination_id`
            - Type: int
            - What: The id of the destination node from the graph dictionary to end the shortest path at

        Optional Arguments:

        - None
        """
        # Input Validation
        Graph.input_check(
            graph=graph, origin_id=origin_id, destination_id=destination_id
        )
        # Variable Initialization
        distance_matrix = [float("inf")] * len(graph)
        distance_matrix[origin_id] = 0
        open_leaves = []
        heappush(open_leaves, (0, origin_id))
        predecessor = [-1] * len(graph)

        while open_leaves:
            current_distance, current_id = heappop(open_leaves)
            if current_id == destination_id:
                break
            # Technically, the next line is not necessary but can help with performance
            if current_distance == distance_matrix[current_id]:
                for connected_id, connected_distance in graph[
                    current_id
                ].items():
                    possible_distance = current_distance + connected_distance
                    if possible_distance < distance_matrix[connected_id]:
                        distance_matrix[connected_id] = possible_distance
                        predecessor[connected_id] = current_id
                        heappush(open_leaves, (possible_distance, connected_id))
        if current_id != destination_id:
            raise Exception(
                "Something went wrong, the origin and destination nodes are not connected."
            )

        output_path = [current_id]
        while predecessor[current_id] != -1:
            current_id = predecessor[current_id]
            output_path.append(current_id)

        output_path.reverse()

        return {
            "path": output_path,
            "length": distance_matrix[destination_id],
        }

    @staticmethod
    def cycle_check(predecessor_matrix, node_id):
        """
        Function:

        - Check if a cycle exists in the predecessor matrix starting from the given node_id
        - Returns None if no cycle is detected
        - Raises an Exception if a cycle is detected

        Required Arguments:

        - `predecessor_matrix`:
            - Type: list[int]
            - What: A list where the index represents the node id and the value at that index is the predecessor node id
        - `node_id`:
            - Type: int
            - What: The node id to start checking for cycles from

        Optional Arguments:

        - None
        """
        cycle_id = node_id
        while True:
            cycle_id = predecessor_matrix[cycle_id]
            if cycle_id == -1:
                return
            if cycle_id == node_id:
                raise Exception(
                    f"Cycle detected in the graph at node {node_id}"
                )

    @staticmethod
    def dijkstra_negative(
        graph: list[dict[int, int | float]],
        origin_id: int,
        destination_id: int,
        cycle_check_iterations: int | None = None,
    ) -> dict:
        """
        Function:

        - Identify the shortest path between two nodes in a sparse network graph using a modified Dijkstra algorithm that catches negative cycles
            - Negative cycles raise an exception if they are detected
        - Note: This algorithm is guaranteed to find the shortest path or raise an exception if a negative cycle is detected
        - Note: This algorithm requires computing the entire spanning tree of the graph and is therefore not able to be terminated early
            - For non negative weighted graphs, it is recommended to use the `dijkstra_makowski` algorithm instead
        - Note: For certain graphs with weights that are negative, this algorithm may run far slower than O((n+m) log n)

        - Return a dictionary of various path information including:
            - `id_path`: A list of node ids in the order they are visited
            - `path`: A list of node dictionaries (lat + long) in the order they are visited

        Required Arguments:

        - `graph`:
            - Type: list of dictionaries
            - See: https://connor-makowski.github.io/scgraph/scgraph/graph.html#Graph.validate_graph
        - `origin_id`
            - Type: int
            - What: The id of the origin node from the graph dictionary to start the shortest path from
        - `destination_id`
            - Type: int
            - What: The id of the destination node from the graph dictionary to end the shortest path at

        Optional Arguments:

        - `cycle_check_iterations`
            - Type: int | None
            - Default: None -> The length of the graph is used as the default number of iterations to loop over before checking for negative cycles
            - What: The number of iterations to loop over before checking for negative cycles
        """
        # Input Validation
        Graph.input_check(
            graph=graph, origin_id=origin_id, destination_id=destination_id
        )
        # Variable Initialization
        distance_matrix = [float("inf")] * len(graph)
        distance_matrix[origin_id] = 0
        open_leaves = []
        heappush(open_leaves, (0, origin_id))
        predecessor = [-1] * len(graph)

        # Cycle iteration Variables
        cycle_iteration = 0
        if cycle_check_iterations is None:
            cycle_check_iterations = len(graph)

        while open_leaves:
            current_distance, current_id = heappop(open_leaves)
            if current_distance == distance_matrix[current_id]:
                # Increment the cycle iteration counter and check for negative cycles if the iteration limit is reached
                cycle_iteration += 1
                if cycle_iteration >= cycle_check_iterations:
                    cycle_iteration = 0  # Reset the cycle iteration counter
                    Graph.cycle_check(
                        predecessor_matrix=predecessor, node_id=current_id
                    )
                for connected_id, connected_distance in graph[
                    current_id
                ].items():
                    possible_distance = current_distance + connected_distance
                    if possible_distance < distance_matrix[connected_id]:
                        distance_matrix[connected_id] = possible_distance
                        predecessor[connected_id] = current_id
                        heappush(open_leaves, (possible_distance, connected_id))

        if distance_matrix[destination_id] == float("inf"):
            raise Exception(
                "Something went wrong, the origin and destination nodes are not connected."
            )

        output_path = [current_id]
        while predecessor[current_id] != -1:
            current_id = predecessor[current_id]
            output_path.append(current_id)

        output_path.reverse()

        return {
            "path": output_path,
            "length": distance_matrix[destination_id],
        }

    @staticmethod
    def a_star(
        graph: list[dict[int, int | float]],
        origin_id: int,
        destination_id: int,
        heuristic_fn=None,
    ) -> dict:
        """
        Function:

        - Identify the shortest path between two nodes in a sparse network graph using an A* extension of Makowski's modified Dijkstra algorithm
        - Return a dictionary of various path information including:
            - `id_path`: A list of node ids in the order they are visited
            - `path`: A list of node dictionaries (lat + long) in the order they are visited

        Required Arguments:

        - `graph`:
            - Type: list of dictionaries
            - See: https://connor-makowski.github.io/scgraph/scgraph/graph.html#Graph.validate_graph
        - `origin_id`
            - Type: int
            - What: The id of the origin node from the graph dictionary to start the shortest path from
        - `destination_id`
            - Type: int
            - What: The id of the destination node from the graph dictionary to end the shortest path at
        - `heuristic_fn`
            - Type: function
            - What: A heuristic function that takes two node ids and returns an estimated distance between them
            - Note: If None, returns the shortest path using Makowski's modified Dijkstra algorithm
            - Default: None

        Optional Arguments:

        - None
        """
        if heuristic_fn is None:
            return Graph.dijkstra_makowski(
                graph=graph,
                origin_id=origin_id,
                destination_id=destination_id,
            )
        # Input Validation
        Graph.input_check(
            graph=graph, origin_id=origin_id, destination_id=destination_id
        )
        # Variable Initialization
        distance_matrix = [float("inf")] * len(graph)
        distance_matrix[origin_id] = 0
        # Using a visited matrix does add a tad bit of overhead but avoids revisiting nodes
        # and does not require anything extra to be stored in the heap
        visited = [0] * len(graph)
        open_leaves = []
        heappush(open_leaves, (0, origin_id))
        predecessor = [-1] * len(graph)

        while open_leaves:
            current_id = heappop(open_leaves)[1]
            if current_id == destination_id:
                break
            if visited[current_id] == 1:
                continue
            visited[current_id] = 1
            current_distance = distance_matrix[current_id]
            for connected_id, connected_distance in graph[current_id].items():
                possible_distance = current_distance + connected_distance
                if possible_distance < distance_matrix[connected_id]:
                    distance_matrix[connected_id] = possible_distance
                    predecessor[connected_id] = current_id
                    heappush(
                        open_leaves,
                        (
                            possible_distance
                            + heuristic_fn(connected_id, destination_id),
                            connected_id,
                        ),
                    )
        if current_id != destination_id:
            raise Exception(
                "Something went wrong, the origin and destination nodes are not connected."
            )

        output_path = [current_id]
        while predecessor[current_id] != -1:
            current_id = predecessor[current_id]
            output_path.append(current_id)

        output_path.reverse()

        return {
            "path": output_path,
            "length": distance_matrix[destination_id],
        }
