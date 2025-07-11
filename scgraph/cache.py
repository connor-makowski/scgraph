from .spanning import SpanningTree
from .core import Graph


class CacheGraph:
    """
    A class allowing a graph to cache spanning trees to quickly compute shortest paths between nodes.
    This is useful for speeding up the computation of shortest when origins or destinations are often the same.
    """

    def __init__(self, graph: list[dict]):
        """
        Initialize the CacheGraph with a graph.

        Requires:

        - graph:
            - Type: list of dictionaries
            - See: https://connor-makowski.github.io/scgraph/scgraph/core.html#GeoGraph
            - Note: The graph must be symmetric for the CacheGraph to work based on how it takes advantage of spanning trees.

        - Note: Take care when caching spanning trees to avoid memory issues. It is recommend to only cache for nodes that will be used often.
        """
        Graph.validate_graph(graph, check_connected=False, check_symmetry=True)
        self.graph = graph
        self.cache = {}

    def get_shortest_path(
        self,
        origin_id: int,
        destination_id: int,
        cache: bool = True,
        cache_for: str = "origin",
        heuristic_fn=None,
    ):
        """
        Function:

        - Get the shortest path between two nodes in the graph attempting to use a cached spanning tree if available
        - If a cached spanning tree is not available, it will compute the spanning tree and cache it for future use if specified by `cache`

        Requires:

        - origin_id: The id of the origin node
        - destination_id: The id of the destination node

        Optional:

        - cache: Whether to cache the spanning tree for future use
            - Default: True
        - cache_for: Whether to cache the spanning tree for the origin or destination node
            - Default: 'origin'
            - Options: 'origin', 'destination'
        - heuristic_fn: A heuristic function to use for the A* algorithm if cache is False and the origin or destination node is not in the cache
            - Type: callable | None
            - If None, the A* function will compute with Dijkstra's algorithm instead
            - If a callable is provided, it should take two arguments: origin_id and destination_id
              and return a float representing the heuristic distance between the two nodes
              - Note: This distance should never be greater than the actual distance between the two nodes or you may get suboptimal paths


        """
        spanning_tree = self.cache.get(
            origin_id, self.cache.get(destination_id, None)
        )
        # Only calculate the full spanning tree if the cached tree is not available
        # and cache is True, otherwise using dijkstra_makowski is faster since it
        # terminates the spanning tree calculation when the destination is reached
        if spanning_tree is None and cache:
            spanning_id = origin_id if cache_for == "origin" else destination_id
            spanning_tree = SpanningTree.makowskis_spanning_tree(
                graph=self.graph, node_id=spanning_id
            )
            self.cache[spanning_id] = spanning_tree
        # If the spanning_tree is not None, use it to get the path
        if spanning_tree is not None:
            return SpanningTree.get_path(
                origin_id=origin_id,
                destination_id=destination_id,
                spanning_tree=spanning_tree,
            )
        return Graph.a_star(
            graph=self.graph,
            origin_id=origin_id,
            destination_id=destination_id,
            heuristic_fn=heuristic_fn,
        )
