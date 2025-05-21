from scgraph.helpers.shape_mover_utils import ShapeMoverUtils
from scgraph.cache import CacheGraph


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

    def get_shortest_path(
        self,
        origin_node: dict[str, int] | tuple[int, int] | list[int],
        destination_node: dict[str, int] | tuple[int, int] | list[int],
        output_coordinate_path: str = "list_of_dicts",
        cache: bool = False,
        cache_for: str = "origin",
        output_path: bool = False,
        **kwargs,
    ) -> dict:
        """
        Function:

        - Identify the shortest path between two nodes in a sparse network graph

        - Return a dictionary of various path information including:
            - `id_path`: A list of graph ids in the order they are visited
            - `path`: A list of dicts (x, y) in the order they are visited
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
            - What: Whether to cache the spanning tree for future use
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

        origin_id = self.get_idx(
            x=origin_node["x"],
            y=origin_node["y"],
        )
        destination_id = self.get_idx(
            x=destination_node["x"],
            y=destination_node["y"],
        )

        if self.graph[origin_id] == {}:
            raise ValueError(
                "Origin node is not connected to any other nodes. This is likely caused by the origin node not being possible given a blocked cell or nearby blocked cell"
            )
        if self.graph[destination_id] == {}:
            raise ValueError(
                "Destination node is not connected to any other nodes. This is likely caused by the destination node not being possible given a blocked cell or nearby blocked cell"
            )
        output = self.cacheGraph.get_shortest_path(
            origin_id=origin_id,
            destination_id=destination_id,
            cache=cache,
            cache_for=cache_for,
        )
        output["coordinate_path"] = self.get_coordinate_path(
            output["path"], output_coordinate_path
        )
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
