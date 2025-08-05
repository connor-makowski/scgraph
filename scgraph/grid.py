from scgraph.graph import Graph
from scgraph.helpers.shape_mover_utils import ShapeMoverUtils
from scgraph.cache import CacheGraph
from typing import Literal


class GridGraph:
    def __init__(
        self,
        x_size: int,
        y_size: int,
        blocks: list[tuple[int, int]],
        shape: list[tuple[int | float, int | float]] | None = None,
        add_exterior_walls: bool = True,
        conn_data: list[tuple[int, int, float]] | None = None,
    ) -> None:
        """
        Initializes a GridGraph object.

        Required Arguments:

        - `x_size`
            - Type: int
            - What: The size of the grid in the x direction
        - `y_size`
            - Type: int
            - What: The size of the grid in the y direction
        - `blocks`
            - Type: list of tuples
            - What: A list of tuples representing the coordinates of the blocked cells

        Optional Arguments:

        - `shape`
            - Type: list of tuples
            - What: A list of tuples representing the shape of the moving object relative to the object location in the grid
            - Default: [(0, 0), (0, 1), (1, 0), (1, 1)]
            - Example: [(0, 0), (0, 1), (1, 0), (1, 1)]
                - Note: This would form a square of size 1x1
                - Assuming the grid location is at (0,0) the square takes up the grid space between (0, 0) and (1, 1)
                - Assumint the grid location is at (1,1) the square takes up the grid space between (1, 1) and (2, 2) with the same shape
            - Note: This shape is used to determine which connections are allowed when passing through the grid.
                - For example
                    - The shape is a square of size 1x1
                    - The location of the square is (0, 0)
                    - There is a blocked cell at (0, 1)
                    - There is a potential connection to (1, 1), (0, 1), and (1, 0)
                    - The square can not move to (1, 1) as it would collide with the blocked cell at (0, 1)
                      - This is because the square would pass partly through the blocked cell on its way to (1, 1)
                      - To achieve the same result, it can move to (1, 0) and then up to (1, 1) taking extra time / distance
        - `add_exterior_walls`
            - Type: bool
            - What: Whether to add exterior walls to the grid
            - Default: True
        - `conn_data`
            - Type: list of tuples
            - What: A list of tuples representing movements allowed in the grid
                - Each tuple should contain three values: (x_offset, y_offset, distance)
                - x_offset: The x offset from the current cell
                - y_offset: The y offset from the current cell
                - distance: The distance to the connected cell
            - Default: [(0, 1, 1), (1, 0, 1), (0, -1, 1), (-1, 0, 1), (1, 1, sqrt(2)), (-1, -1, sqrt(2)), (1, -1, sqrt(2)), (-1, 1, sqrt(2))]
                - Note: If None, the default connection data will be used
                - Note: This includes 8 directions, 4 cardinal and 4 diagonal
                - Cardinal directions are 1 unit away, diagonal directions are sqrt(2) units away
        """
        # Validate the inputs
        assert x_size > 0, "x_size must be greater than 0"
        assert y_size > 0, "y_size must be greater than 0"

        self.x_size = x_size
        self.y_size = y_size
        self.blocks = blocks
        self.add_exterior_walls = add_exterior_walls

        # Update the blocks if add_exterior_walls is True
        # This is done by adding all the cells in the first and last row and column
        if add_exterior_walls:
            self.blocks += [
                (x, y) for x in range(x_size) for y in [0, y_size - 1]
            ] + [(x, y) for x in [0, x_size - 1] for y in range(y_size)]

        # If shape is None, set the default shape
        if shape is None:
            self.shape = [(0, 0), (0, 1), (1, 0), (1, 1)]
        else:
            self.shape = shape

        # If conn_data is None, set the default connection data
        if conn_data is None:
            sqrt_2 = 1.4142
            self.conn_data = [
                (-1, -1, sqrt_2),
                (-1, 0, 1),
                (-1, 1, sqrt_2),
                (0, -1, 1),
                (0, 1, 1),
                (1, -1, sqrt_2),
                (1, 0, 1),
                (1, 1, sqrt_2),
            ]
        else:
            self.conn_data = conn_data

        self.graph = self.__create_graph__()
        self.nodes = [self.__get_x_y__(idx) for idx in range(len(self.graph))]
        self.cacheGraph = CacheGraph(self.graph)

    def __get_idx__(self, x: int, y: int):
        """
        Function:
        - Get the index of a cell in a 2D grid given its x and y coordinates
        - This does not have any error checking, so be careful with the inputs

        Required Arguments:
        - `x`
            - Type: int
            - What: The x coordinate of the cell
        - `y`
            - Type: int
            - What: The y coordinate of the cell

        Returns:

        - `idx`
            - Type: int
            - What: The index of the cell in the grid
        """
        return x + y * self.x_size

    def __get_x_y__(self, idx: int):
        """
        Function:
        - Get the x and y coordinates of a cell in a 2D grid given its index
        - This does not have any error checking so be careful with the inputs

        Required Arguments:

        - `idx`
            - Type: int
            - What: The index of the cell

        Returns:
        - `x`
            - Type: int
            - What: The x coordinate of the cell
        - `y`
            - Type: int
            - What: The y coordinate of the cell
        """
        return idx % self.x_size, idx // self.x_size

    def get_idx(self, x: int, y: int):
        """
        Function:
        - Get the index of a cell in a 2D grid given its x and y coordinates

        Required Arguments:
        - `x`
            - Type: int
            - What: The x coordinate of the cell
        - `y`
            - Type: int
            - What: The y coordinate of the cell

        Returns:

        - `idx`
            - Type: int
            - What: The index of the cell in the grid
        """
        assert x >= 0 and x < self.x_size, "x coordinate is out of bounds"
        assert y >= 0 and y < self.y_size, "y coordinate is out of bounds"
        return x + y * self.x_size

    def get_x_y(self, idx: int):
        """
        Function:
        - Get the x and y coordinates of a cell in a 2D grid given its index

        Required Arguments:

        - `idx`
            - Type: int
            - What: The index of the cell

        Returns:
        - `x`
            - Type: int
            - What: The x coordinate of the cell
        - `y`
            - Type: int
            - What: The y coordinate of the cell
        """
        assert idx >= 0 and idx < len(self.graph), "idx is out of bounds"
        return idx % self.x_size, idx // self.x_size

    def __get_relative_shape_offsets__(
        self,
        shape: list[tuple[int | float, int | float]],
        x_off: int,
        y_off: int,
    ):
        return list(
            ShapeMoverUtils.moving_shape_overlap_intervals(
                x_coord=0,
                y_coord=0,
                x_shift=x_off,
                y_shift=y_off,
                t_start=0,
                t_end=1,
                shape=shape,
            ).keys()
        )

    def __create_graph__(
        self,
    ):
        """
        Function:

        - Create a graph from the grid specifications

        Returns:

        - `graph`
            - Type: list
            - What: The adjacency list representation of the graph
        """
        ####################
        # Create a list of lists to hold all the possible connections in an easy to access/understand format
        ####################

        # Each cell in the list will be a dictionary of connections
        # The keys will be the coordinates of the cell that can be moved to
        # The values will be the distance to that cell
        # This essentially creates a sparse matrix
        graph_matrix = [
            [{} for _ in range(self.x_size)] for _ in range(self.y_size)
        ]
        for y in range(self.y_size):
            for x in range(self.x_size):
                for x_off, y_off, dist in self.conn_data:
                    if (
                        0 <= x + x_off < self.x_size
                        and 0 <= y + y_off < self.y_size
                    ):
                        graph_matrix[y][x][(x + x_off, y + y_off)] = dist

        ####################
        # Remove all connections that would not be possible based on the blocks and the shape
        ####################

        # Create a set of offsets that will be used to help remove connections relative to each blocked cell
        delta_offsets = {
            (x_delta, y_delta): self.__get_relative_shape_offsets__(
                self.shape, x_delta, y_delta
            )
            for x_delta, y_delta, _ in self.conn_data
        }

        # Loop over all the blocks and remove all connections that would be not possible based on the blocks
        for block in self.blocks:
            # Clear out all connections leaving from the blocked cell
            graph_matrix[block[1]][block[0]] = {}
            # Clear out all connections that would be blocked by each movement given the blocked cell and the delta offsets
            # Our delta offsets dictionary essentially tells us which relative cells would be blocked by the moving shape
            for delta, offsets in delta_offsets.items():
                for offset in offsets:
                    x_cell = block[0] - offset[0]
                    y_cell = block[1] - offset[1]
                    if 0 <= x_cell < self.x_size and 0 <= y_cell < self.y_size:
                        x_move_to = x_cell + delta[0]
                        y_move_to = y_cell + delta[1]
                        graph_matrix[y_cell][x_cell].pop(
                            (x_move_to, y_move_to), None
                        )

        ####################
        # Convert the graph matrix into the very efficient graph format as specified by the scgraph library
        ####################
        graph = []
        for x_data in graph_matrix:
            for connection_dict in x_data:
                graph.append(
                    {
                        self.__get_idx__(x, y): dist
                        for (x, y), dist in connection_dict.items()
                    }
                )

        return graph

    def euclidean_heuristic(self, origin_id: int, destination_id: int) -> float:
        """
        Function:

        - Calculate the Euclidean distance between two nodes in the grid graph

        Required Arguments:

        - `origin_id`
            - Type: int
            - What: The id of the origin node
        - `destination_id`
            - Type: int
            - What: The id of the destination node

        Returns:

        - `distance`
            - Type: float
            - What: The Euclidean distance between the two nodes
        """
        origin_location = self.nodes[origin_id]
        destination_location = self.nodes[destination_id]
        return (
            (origin_location[0] - destination_location[0]) ** 2
            + (origin_location[1] - destination_location[1]) ** 2
        ) ** 0.5

    def __get_closest_node_with_connections__(
        self,
        x: int | float,
        y: int | float,
    ):
        """
        Function:

        - Get the closest node in the graph that has connections

        Required Arguments:

        - `x`
            - Type: int | float
            - What: The x coordinate of the node
        - `y`
            - Type: int | float
            - What: The y coordinate of the node

        Returns:

        - `closest_node_id`
            - Type: int
            - What: The id of the closest node with connections
        - `closest_distance`
            - Type: float
            - What: The distance to the closest node with connections
        """
        x = int(x) if int(x) == x else x
        y = int(y) if int(y) == y else y
        if isinstance(x, int) and isinstance(y, int):
            return self.get_idx(x, y), 0.0
        closest_node_id = None
        closest_distance = float("inf")
        for x_off, y_off in [(0, 0), (1, 0), (0, 1), (1, 1)]:
            node_x = int(x) + x_off
            node_y = int(y) + y_off
            try:
                node_id = self.get_idx(node_x, node_y)
            except AssertionError:
                continue
            if self.graph[node_id] == {}:
                continue
            distance = ((node_x - x) ** 2 + (node_y - y) ** 2) ** 0.5
            if distance < closest_distance:
                closest_distance = distance
                closest_node_id = node_id
        if closest_node_id is None:
            raise ValueError(
                "No valid adjacent node with connections found for the given coordinates"
            )
        return closest_node_id, closest_distance

    def format_coordinate(self, cooinate_dict, output_coorinate_path):
        if output_coorinate_path == "list_of_tuples":
            return (cooinate_dict["x"], cooinate_dict["y"])
        elif output_coorinate_path == "list_of_lists":
            return [cooinate_dict["x"], cooinate_dict["y"]]
        elif output_coordinate_path == "list_of_dicts":
            return {"x": cooinate_dict["x"], "y": cooinate_dict["y"]}
        else:
            raise ValueError("Invalid output_coordinate_path format")

    def get_shortest_path(
        self,
        origin_node: (
            dict[Literal["x", "y"], int | float]
            | tuple[int | float, int | float]
            | list[int | float]
        ),
        destination_node: (
            dict[Literal["x", "y"], int | float]
            | tuple[int | float, int | float]
            | list[int | float]
        ),
        output_coordinate_path: str = "list_of_dicts",
        cache: bool = False,
        cache_for: str = "origin",
        output_path: bool = False,
        heuristic_fn: callable | Literal["euclidean"] | None = "euclidean",
        **kwargs,
    ) -> dict:
        """
        Function:

        - Identify the shortest path between two nodes in a sparse network graph
        - If an off graph origin and/or destination node is provided, it will find the closest adjacent node with connections
          as the origin and/or destination node
            - This is done to increase the likelihood that the pathfinding algorithm can find a valid path
            - If no valid adjacent node is found, an error will be raised

        - Return a dictionary of various path information including:
            - `path`: A list of graph ids in the order they are visited
            - `coordinate_path`: A list of dicts (x, y) in the order they are visited
            - `length`: The length of the path

         Required Arguments:

        - `origin_node`
            - Type: dict of int | float
            - What: A dictionary with the keys 'x' and 'y'
            - Alternatively, a tuple or list of two values (x, y) can be used
        - `destination_node`
            - Type: dict of int | float
            - What: A dictionary with the keys 'x' and 'y'
            - Alternatively, a tuple or list of two values (x, y) can be used

        Optional Arguments:

        - `output_coordinate_path`
            - Type: str
            - What: The format of the output coordinate path
            - Default: 'list_of_lists'
            - Options:
                - `list_of_tuples`: A list of tuples with the first value being x and the second being y
                - 'list_of_dicts': A list of dictionaries with keys 'x' and 'y'
                - 'list_of_lists': A list of lists with the first value being x and the second being y
        - `cache`
            - Type: bool
            - What: Whether to use the cache (save and reuse the spanning tree)
            - Default: False
        - `cache_for`
            - Type: str
            - What: Whether to cache the spanning tree for the origin or destination node if `cache` is True
            - Default: 'origin'
            - Options: 'origin', 'destination'
        - `output_path`
            - Type: bool
            - What: Whether to output the path as a list of graph idxs (mostly for debugging purposes)
            - Default: False
        - `heuristic_fn`
            - Type: callable | Literal['euclidean'] | None
            - What: A heuristic function to use for the A* algorithm if caching is False
            - Default: 'euclidean' (A predefined heuristic function that calculates the Euclidean distance for this grid graph)
            - If None, the A* algorithm will not be used and the Dijkstra's algorithm will be used instead
            - If a callable is provided, it should take two arguments: origin_id and destination_id and return a float representing the heuristic distance between the two nodes
                - Note: This distance should never be greater than the actual distance between the two nodes or you may get suboptimal paths
        - `**kwargs`
            - Additional keyword arguments. These are included for forwards and backwards compatibility reasons, but are not currently used.
        """
        if isinstance(origin_node, (tuple, list)):
            origin_node = {"x": origin_node[0], "y": origin_node[1]}
        if isinstance(destination_node, (tuple, list)):
            destination_node = {
                "x": destination_node[0],
                "y": destination_node[1],
            }

        origin_id, origin_distance = self.__get_closest_node_with_connections__(
            **origin_node
        )
        destination_id, destination_distance = (
            self.__get_closest_node_with_connections__(**destination_node)
        )

        if self.graph[origin_id] == {}:
            raise ValueError(
                "Origin node is not connected to any other nodes. This is likely caused by the origin node not being possible given a blocked cell or nearby blocked cell"
            )
        if self.graph[destination_id] == {}:
            raise ValueError(
                "Destination node is not connected to any other nodes. This is likely caused by the destination node not being possible given a blocked cell or nearby blocked cell"
            )
        if cache:
            if cache_for not in ["origin", "destination"]:
                raise ValueError(
                    "cache_for must be 'origin' or 'destination' when cache is True"
                )
            # Reverse for cache graphing if cache_for is destination since the graph is undirected
            if cache_for == "destination":
                origin_id, destination_id = destination_id, origin_id
            output = self.cacheGraph.get_shortest_path(
                origin_id=origin_id,
                destination_id=destination_id,
            )
            # Undo the reverse if cache_for is destination
            if cache_for == "destination":
                output["path"].reverse()
                origin_id, destination_id = destination_id, origin_id
        else:
            output = Graph.a_star(
                graph=self.graph,
                origin_id=origin_id,
                destination_id=destination_id,
                heuristic_fn=(
                    self.euclidean_heuristic
                    if heuristic_fn == "euclidean"
                    else heuristic_fn
                ),
            )
        output["coordinate_path"] = self.get_coordinate_path(
            output["path"], output_coordinate_path
        )
        if origin_distance > 0:
            output["coordinate_path"] = [
                self.format_coordinate(origin_node, output_coordinate_path)
            ] + output["coordinate_path"]
            output["path"] = [-1] + output["path"]
            output["length"] += origin_distance
        if destination_distance > 0:
            output["coordinate_path"].append(
                self.format_coordinate(destination_node, output_coordinate_path)
            )
            output["path"].append(-1)
            output["length"] += destination_distance
        if not output_path:
            del output["path"]
        return output

    def get_coordinate_path(
        self, path: list[int], output_coordinate_path: str = "list_of_dicts"
    ) -> list[dict[str, int]]:
        """
        Function:

        - Return a list of node dictionaries (lat + long) in the order they are visited

        Required Arguments:

        - `path`
            - Type: list
            - What: A list of node ids in the order they are visited

        Optional Arguments:

        - `output_coordinate_path`
            - Type: str
            - What: The format of the output coordinate path
            - Default: 'list_of_dicts'
            - Options:
                - 'list_of_dicts': A list of dictionaries with keys 'x' and 'y'
                - 'list_of_lists': A list of lists with the first value being x and the second being y
                - `list_of_tuples`: A list of tuples with the first value being x and the second being y

        Returns:

        - `coordinate_path`
            - Type: list
            - What: A list of dictionaries with keys 'x' and 'y' in the order they are visited
        """
        output = [self.__get_x_y__(idx) for idx in path]
        if output_coordinate_path == "list_of_tuples":
            return output
        elif output_coordinate_path == "list_of_lists":
            return [[x, y] for x, y in output]
        elif output_coordinate_path == "list_of_dicts":
            return [{"x": x, "y": y} for x, y in output]
        else:
            raise ValueError(
                "output_coordinate_path must be 'list_of_dicts' or 'list_of_lists' or 'list_of_tuples'"
            )

    def export_object(
        self, filename: str = "", include_blocks: bool = False
    ) -> dict:
        """
        Function:

        - Export the graph as a list of dictionaries

        Arguments:

        - `filename`
            - Type: str
            - What: The name of the file to export the graph to.
            - An extension of .gridgraph will be added to the file name if not already present

        Optional Arguments:

        - `include_blocks`
            - Type: bool
            - What: Whether to include the blocks in the export
            - Default: False
            - Note: This is not needed as the graph is already created
            - Note: You can include blocks in the export if you need them for some reason
                - This will be set as the blocks attribute in the imported object
                - This will increase the size of the export file
        """
        if filename == "":
            raise ValueError("filename must be specified to export the graph")
        filename = (
            filename
            if filename.endswith(".gridgraph")
            else filename + ".gridgraph"
        )
        try:
            import pickle, zlib, os
        except ImportError:
            raise ImportError(
                "os, pickle and zlib are required to export the graph"
            )
        export_data = {
            "graph_attributes": {
                "graph": self.graph,
                "nodes": self.nodes,
                "x_size": self.x_size,
                "y_size": self.y_size,
                "shape": self.shape,
                "add_exterior_walls": self.add_exterior_walls,
                "conn_data": self.conn_data,
            },
            "graph_cache": self.cacheGraph.cache,
            "export_version": 1,
        }
        if include_blocks:
            export_data["graph_attributes"]["blocks"] = self.blocks

        if not os.path.exists(os.path.dirname(filename)):
            os.makedirs(os.path.dirname(filename))
        with open(filename, "wb") as f:
            f.write(zlib.compress(pickle.dumps(export_data)))

    @staticmethod
    def import_object(filename: str = "") -> None:
        """
        Function:

        - A staticmethod to import the graph from a file

        Arguments:

        - `filename`
            - Type: str
            - What: The name of the file to import the graph from.
            - An extension of .gridgraph will be added to the file name if not already present

        Returns:

        - `GridGraph`
            - Type: GridGraph
            - What: The imported graph object
        """
        if filename == "":
            raise ValueError("filename must be specified to import the graph")
        filename = (
            filename
            if filename.endswith(".gridgraph")
            else filename + ".gridgraph"
        )
        try:
            import pickle, zlib
        except ImportError:
            raise ImportError(
                "pickle and zlib are required to import the graph"
            )
        with open(filename, "rb") as f:
            import_data = pickle.loads(zlib.decompress(f.read()))

        # Check the version of the export
        if import_data["export_version"] != 1:
            raise ValueError(
                f"Incompatible export version {import_data['export_version']}. The current version is 1"
            )
        # Create a new basic GridGraph object and overwrite the attributes with the imported data
        # This is done as the init method calls the __create_graph__ method which is not needed here
        GridGraph_object = GridGraph(
            x_size=1, y_size=1, blocks=[], add_exterior_walls=False
        )
        for key, value in import_data["graph_attributes"].items():
            GridGraph_object.__setattr__(key, value)

        GridGraph_object.cacheGraph = CacheGraph(GridGraph_object.graph)
        GridGraph_object.cacheGraph.cache = import_data["graph_cache"]
        return GridGraph_object
