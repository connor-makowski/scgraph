from heapq import heappush, heappop


class SpanningTree:
    @staticmethod
    def makowskis_spanning_tree(graph: list[dict], node_id: int) -> dict:
        """
        Function:

        - Calculate the spanning tree of a graph using Makowski's modified Dijkstra algorithm
            - Modifications allow for a sparse distance matrix to be used instead of a dense distance matrix
            - Improvements include only computing future potential nodes based on the open leaves for each branch
                - Open leaves are nodes that have not been visited yet but are adjacent to other visited nodes
            - This can dramatically reduce the memory and compute requirements of the algorithm
            - For particularly sparse graphs, this algorithm runs close to O(n log n) time
                - Where n is the number of nodes in the graph
            - For dense graphs, this algorithm runs closer to O(n^2) time (similar to the standard Dijkstra algorithm)
                - Where n is the number of nodes in the graph

        Required Arguments:

        - `graph`:
            - Type: list of dictionaries
            - See: https://connor-makowski.github.io/scgraph/scgraph/graph.html#Graph.validate_graph
        - `node_id`
            - Type: int
            - What: The id of the node from which to calculate the spanning tree

        Returns:

        - A dictionary with the following keys:
            - `node_id`: The id of the node from which the spanning tree was calculated
            - `predecessors`: A list of node ids referring to the predecessor of each node given the spanning tree
                - Note: For disconnected graphs, nodes that are not connected to the origin node will have a predecessor of None
            - `distance_matrix`: A list of distances from the origin node to each node in the graph
                - Note: For disconnected graphs, nodes that are not connected to the origin node will have a distance of float("inf")

        """
        # Input Validation
        assert isinstance(node_id, int), "node_id must be an integer"
        assert 0 <= node_id < len(graph), "node_id must be a valid node id"
        # Variable Initialization
        distance_matrix = [float("inf")] * len(graph)
        distance_matrix[node_id] = 0
        open_leaves = []
        heappush(open_leaves, (0, node_id))
        predecessor = [-1] * len(graph)

        while open_leaves:
            current_distance, current_id = heappop(open_leaves)
            for connected_id, connected_distance in graph[current_id].items():
                possible_distance = current_distance + connected_distance
                if possible_distance < distance_matrix[connected_id]:
                    distance_matrix[connected_id] = possible_distance
                    predecessor[connected_id] = current_id
                    heappush(open_leaves, (possible_distance, connected_id))

        return {
            "node_id": node_id,
            "predecessors": predecessor,
            "distance_matrix": distance_matrix,
        }

    @staticmethod
    def get_path(
        origin_id: int,
        destination_id: int,
        spanning_tree: dict,
        length_only: bool = False,
    ) -> dict:
        """
        Function:

        - Get the path from the origin node to the destination node using the provided spanning tree
        - Return a list of node ids in the order they are visited as well as the length of the path
        - If the destination node is not reachable from the origin node, return None

        Required Arguments:

        - `origin_id`
            - Type: int
            - What: The id of the origin node from the graph dictionary to start the shortest path from
        - `destination_id`
            - Type: int
            - What: The id of the destination node from the graph dictionary to end the shortest path at
        - `spanning_tree`
            - Type: dict
            - What: The output from the makowskis_spanning_tree function

        Optional Arguments:

        - `length_only`
            - Type: bool
            - What: If True, only returns the length of the path
            - Default: False

        Returns:

        - A dictionary with the following keys:
            - `path`: A list of node ids in the order they are visited from the origin node to the destination node
            - `length`: The length of the path from the origin node to the destination node
        """
        if spanning_tree["node_id"] != origin_id:
            raise Exception(
                "The origin node must be the same as the spanning node for this function to work."
            )
        destination_distance = spanning_tree["distance_matrix"][destination_id]
        if destination_distance == float("inf"):
            raise Exception(
                "Something went wrong, the origin and destination nodes are not connected."
            )
        if length_only:
            return {"length": destination_distance}
        current_id = destination_id
        current_path = [destination_id]
        while current_id != origin_id:
            current_id = spanning_tree["predecessors"][current_id]
            current_path.append(current_id)
        current_path.reverse()
        return {
            "path": current_path,
            "length": destination_distance,
        }
