from scgraph.spanning import SpanningTree
from scgraph.graph import Graph


class CacheGraph:
    """
    A class allowing a graph to cache spanning trees to quickly compute shortest paths between nodes.
    This is useful for speeding up the computation of shortest when origins or destinations are often the same.
    """

    def __init__(self, graph: list[dict], validate_graph: bool = False):
        """
        Initialize the CacheGraph with a graph.

        Requires:

        - graph:
            - Type: list of dictionaries
            - See: https://connor-makowski.github.io/scgraph/scgraph/graph.html#Graph.validate_graph
            - Note: The graph must be symmetric for the CacheGraph to work based on how it takes advantage of spanning trees.

        Optional:

        - validate_graph:
            - Type: bool
            - What: If True, validates the graph before caching
            - Default: False
            - Note: This is useful to ensure the graph is valid before caching, but can be skipped for performance reasons if you are sure the graph is valid.

        - Note: Take care when caching spanning trees to avoid memory issues. It is recommend to only cache for nodes that will be used often.
        """
        if validate_graph:
            Graph.validate_graph(
                graph, check_connected=False, check_symmetry=True
            )
        self.graph = graph
        self.cache = [0] * len(graph)

    def get_shortest_path(
        self,
        origin_id: int,
        destination_id: int,
        length_only: bool = False,
    ):
        """
        Function:

        - Get the shortest path between two nodes in the graph attempting to use a cached spanning tree if available
        - If a cached spanning tree is not available, it will compute the spanning tree and cache it for future use if specified by `cache`

        Requires:

        - origin_id: The id of the origin node
        - destination_id: The id of the destination node

        Optional:

        - length_only: If True, only returns the length of the path
        """
        spanning_tree = self.cache[origin_id]
        if spanning_tree == 0:
            spanning_tree = SpanningTree.makowskis_spanning_tree(
                graph=self.graph, node_id=origin_id
            )
            self.cache[origin_id] = spanning_tree
        return SpanningTree.get_path(
            origin_id=origin_id,
            destination_id=destination_id,
            spanning_tree=spanning_tree,
            length_only=length_only,
        )
