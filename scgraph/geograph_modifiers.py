"""Changes to the network of a `GeoGraph`.

This module is internal. `GeoGraphModifiers` is the mixin of `GeoGraph` that adds and removes
nodes and edges, by id or by coordinates, and that merges another geograph.
"""

from scgraph.utils import haversine
from scgraph.deprecations import warn_deprecated_parameter
from scgraph.node_snapping import LazyEveryNodeSnapIndex
from scgraph import array_views
from copy import deepcopy
from typing import TYPE_CHECKING
from scgraph import Graph

if TYPE_CHECKING:  # Only for annotations.
    from scgraph.geograph import GeoGraph


class GeoGraphModifiers:
    def add_edge(
        self,
        origin_id: int,
        destination_id: int,
        distance: float,
        symmetric: bool = False,
        *,
        edge_class: str | None = None,
    ) -> None:
        """
        Function:

        - Add an edge to the geograph. It replaces an edge that the geograph already has between the two nodes
        - This method is an edit of the network, as each method that adds or removes a node or an edge. An edit removes the metrics other than `length`, and the geograph warns with their names (a `UserWarning`). Create them again with `create_metric` after the edits
        - Example: `geograph.add_edge(0, 7, 85.0, symmetric=True, edge_class="primary")`

        Required Arguments:

        - `origin_id`, `destination_id`: The ids of the two nodes of the edge
        - `distance`: The length of the edge, in `geograph_units`

        Optional Arguments:

        - `symmetric`: Whether to add the edge in both directions
        - `edge_class`: The name of the class of the new edge, a name of `classes`; an unknown name raises a ValueError. With None, the edge has no class: a metric made from weights per km gives it the weight of an off-graph leg (see `create_metric`)
        """
        self._edge_classes.check_class(edge_class)
        self.graph_object.add_edge(
            origin_id=origin_id,
            destination_id=destination_id,
            distance=distance,
            symmetric=symmetric,
        )
        new_edges = [(origin_id, destination_id)]
        if symmetric:
            new_edges.append((destination_id, origin_id))
        self._edge_classes.set_class(new_edges, edge_class)
        self._remove_metrics()
        # `graph` may be a copy of the graph object. It is read again after a change.
        self.graph = None

    def remove_node(
        self, symmetric_node: bool = False
    ) -> dict[int, int | float]:
        """
        Function:

        - Remove the last node of the geograph: its edges, its point and its node mode
        - As each edit of the network, it removes the metrics other than `length` (see `add_edge`)

        Optional Arguments:

        - `symmetric_node`
            - Type: bool
            - What: Whether each edge to this node has an edge back from this node; if True, the removal reads the edges of this node only
            - Default: False

        Returns:

        - The edges of the removed node, as a dictionary {destination id: distance}

        Raises:

        - `RuntimeError`: The geograph has no node
        """
        removed_edges = self.graph_object.remove_node(
            symmetric_node=symmetric_node
        )
        self.nodes.pop()
        self._edge_classes.forget_node(len(self.nodes))
        self._remove_metrics()
        del self.node_mode_ids[len(self.nodes) :]
        self.snap_index = None
        self.graph = None
        return removed_edges

    def remove_edge(
        self, origin_id: int, destination_id: int, symmetric: bool = False
    ) -> int | float | None:
        removed_weight = self.graph_object.remove_edge(
            origin_id=origin_id,
            destination_id=destination_id,
            symmetric=symmetric,
        )
        removed_edges = [(origin_id, destination_id)]
        if symmetric:
            removed_edges.append((destination_id, origin_id))
        self._edge_classes.forget_added_edges(removed_edges)
        self._remove_metrics()
        self.graph = None
        return removed_weight

    def add_coord_edge(
        self,
        origin_coord_dict: dict[str, float],
        destination_coord_dict: dict[str, float],
        symmetric: bool = True,
        distance: float | None = None,
        circuity: float = 1,
        *,
        edge_class: str | None = None,
    ) -> None:
        """
        Function:

        - Add an edge to the graph between two nodes specified by their coordinates
        - Finds the closest nodes in the graph to the provided coordinates and adds an edge between them
        - As each edit of the network, it removes the metrics other than `length` (see `add_edge`)

        Required Arguments:

        - `origin_coord_dict`
            - Type: dict
            - What: A dictionary with the keys 'latitude' and 'longitude' for the origin node
            - Note: The function will find the closest node in the graph to these coordinates and use that as the origin node for the edge
        - `destination_coord_dict`
            - Type: dict
            - What: A dictionary with the keys 'latitude' and 'longitude' for the destination node
            - Note: The function will find the closest node in the graph to these coordinates and use that as the destination node for the edge

        Optional Arguments:

        - `symmetric`
            - Type: bool
            - What: Whether to add the edge in both directions
            - Default: True
        - `distance`
            - Type: int | float | None
            - What: The distance to use for the edge. If None, the haversine distance between the origin and destination nodes (the closest nodes to the provided ones) will be used (with circuity applied)
            - Default: None
        - `circuity`
            - Type: int | float
            - What: The circuity to apply to the distance calculation if distance is None
            - Default: 1
        - `edge_class`
            - Type: str | None
            - What: The name of the class of the new edge (see `add_edge`)
            - Default: None (no class: a metric made from weights per km gives the new edge the weight of an off-graph leg)
        """
        if not (isinstance(origin_coord_dict, dict)):
            raise ValueError("Origin node must be a dictionary")
        if not (isinstance(destination_coord_dict, dict)):
            raise ValueError("Destination node must be a dictionary")
        if "latitude" not in origin_coord_dict.keys():
            raise ValueError("Origin node must have a latitude")
        if "longitude" not in origin_coord_dict.keys():
            raise ValueError("Origin node must have a longitude")
        if "latitude" not in destination_coord_dict.keys():
            raise ValueError("Destination node must have a latitude")
        if "longitude" not in destination_coord_dict.keys():
            raise ValueError("Destination node must have a longitude")
        if not (
            origin_coord_dict["latitude"] >= -90
            and origin_coord_dict["latitude"] <= 90
        ):
            raise ValueError("Origin latitude must be between -90 and 90")
        if not (
            origin_coord_dict["longitude"] >= -180
            and origin_coord_dict["longitude"] <= 180
        ):
            raise ValueError("Origin longitude must be between -180 and 180")
        if not (
            destination_coord_dict["latitude"] >= -90
            and destination_coord_dict["latitude"] <= 90
        ):
            raise ValueError("Destination latitude must be between -90 and 90")
        if not (
            destination_coord_dict["longitude"] >= -180
            and destination_coord_dict["longitude"] <= 180
        ):
            raise ValueError(
                "Destination longitude must be between -180 and 180"
            )
        origin_node = [
            origin_coord_dict["latitude"],
            origin_coord_dict["longitude"],
        ]
        destination_node = [
            destination_coord_dict["latitude"],
            destination_coord_dict["longitude"],
        ]
        closest_origin_idx = self.snap_index.closest_idx(point=origin_node)
        closest_destination_idx = self.snap_index.closest_idx(
            point=destination_node
        )
        if distance is None:
            distance = (
                haversine(
                    self.nodes[closest_origin_idx],
                    self.nodes[closest_destination_idx],
                )
                * circuity
            )
        self.add_edge(
            origin_id=closest_origin_idx,
            destination_id=closest_destination_idx,
            distance=distance,
            symmetric=symmetric,
            edge_class=edge_class,
        )

    def add_coord_node(
        self,
        coord_dict: dict[str, float],
        auto_edge: bool = True,
        circuity: float = 1,
        node_addition_type: str = "quadrant",
        node_addition_math: str = "euclidean",
        lat_lon_bound: float = 5,
        silent: bool | None = None,
        temp_node: bool = False,
        node_mode: str | None = None,
        *,
        edge_class: str | None = None,
    ) -> int:
        """
        Function:

        - Add a node to the network
        - Returns the id of the new node
        - Automatically updates the distance matrix to include distances to/from the new node (symmetric)
        - As each edit of the network, it removes the metrics other than `length` (see `add_edge`)

        Required Arguments:

        - `coord_dict`
            - Type: dict
            - What: A dictionary with the keys 'latitude' and 'longitude'

        Optional Arguments:

        - `auto_edge`
            - Type: bool
            - What: Whether to automatically create edges between the new node and existing nodes in the graph
            - Default: True
        - `circuity`
            - Type: int | float
            - What: The circuity to apply to any auto edge distance calculations
            - Default: 1
        - `node_addition_type`
            - Type: str
            - What: The type of edge creation to use
            - Default: 'quadrant'
            - Options:
                - 'quadrant' / 'kdquadrant': Add the closest node in each quadrant with the snapping index (`snap_index`)
                - 'closest' / 'kdclosest': Add only the closest node with the snapping index (`snap_index`)
                - 'all': Add all nodes to the distance matrix for this node
        - `node_addition_math`
            - Type: str
            - What: Retained for compatibility; ignored by the snapping index
            - Default: 'euclidean'
        - `lat_lon_bound`
            - Type: int | float
            - What: Forms a bounding box around the node that is to be added to graph. Only selects graph nodes to consider joining that are within this bounding box.
            - Default: 5
        - `silent`
            - Deprecated and without effect. scgraph reports its messages through `logging`.
        - `temp_node`
            - Type: bool
            - What: If True, the node is considered temporary and will not be used to increase the __original_graph_length__ value
            - Default: False
        - `node_mode`
            - Type: str | None
            - What: The name of the node mode of the node: the first node mode of that name in `node_modes`, added if there is none
            - Default: None (the node mode without a name)
        - `edge_class`
            - Type: str | None
            - What: The name of the class of the new edges (see `add_edge`)
            - Default: None (no class: a metric made from weights per km gives each new edge the weight of an off-graph leg)

        Returns:

        - The id of the new node

        """
        warn_deprecated_parameter("silent", silent)
        # Validate the inputs
        if not (isinstance(coord_dict, dict)):
            raise ValueError("Node must be a dictionary")
        if "latitude" not in coord_dict.keys():
            raise ValueError("Node must have a latitude")
        if "longitude" not in coord_dict.keys():
            raise ValueError("Node must have a longitude")
        if not (coord_dict["latitude"] >= -90 and coord_dict["latitude"] <= 90):
            raise ValueError("Latitude must be between -90 and 90")
        if not (
            coord_dict["longitude"] >= -180 and coord_dict["longitude"] <= 180
        ):
            raise ValueError("Longitude must be between -180 and 180")
        self._edge_classes.check_class(edge_class)
        node = [coord_dict["latitude"], coord_dict["longitude"]]
        if auto_edge:
            if not (circuity >= 1):
                raise ValueError("Circuity must be greater than or equal to 1")
            if node_addition_type not in [
                "quadrant",
                "all",
                "closest",
                "kdclosest",
                "kdquadrant",
            ]:
                raise ValueError(
                    f"Invalid node addition type provided ({node_addition_type}), valid options are: ['kdclosest', 'closest', 'kdquadrant', 'quadrant', 'all']"
                )
            node_addition_type = self.__get_node_addition_type__(
                node_addition_type
            )
            if not (isinstance(lat_lon_bound, (int, float))):
                raise ValueError("Lat_lon_bound must be a number")
            if not (lat_lon_bound > 0):
                raise ValueError("Lat_lon_bound must be greater than 0")
            # Get the distances to all relevant nodes
            node_dict = self.__get_node_distances__(
                node=node,
                circuity=circuity,
                node_addition_type=node_addition_type,
                lat_lon_bound=lat_lon_bound,
                snap_index=LazyEveryNodeSnapIndex(self),
            )
        else:
            node_dict = {}

        if not temp_node:
            self.__original_graph_length__ += 1

        node_mode_id = self._get_node_mode_id(
            node_mode
        )  # It runs before any change, because it may raise.
        # Create the node
        new_node_id = self.graph_object.add_node(
            node_dict=node_dict, symmetric=True
        )
        self._edge_classes.set_class(
            (
                edge
                for destination_id in node_dict
                for edge in (
                    (new_node_id, destination_id),
                    (destination_id, new_node_id),
                )
            ),
            edge_class,
        )
        self._remove_metrics()
        self.nodes.append(node)
        self.node_mode_ids.append(node_mode_id)
        self.snap_index = None
        self.graph = None
        return new_node_id

    def _get_node_mode_id(self, name: str | None) -> int:
        # The id of the first node mode named `name`, added if there is none
        for node_mode_id, node_mode in enumerate(self.node_modes):
            if node_mode.get("name") == name:
                return node_mode_id
        if len(self.node_modes) == 256:
            raise ValueError("A geograph has at most 256 node modes")
        self.node_modes.append({"name": name})
        return len(self.node_modes) - 1

    def remove_coord_node(self) -> None:
        """
        Function:

        - Remove the last coord node that was appended to the graph
        - Assumes that this node has symmetric flows
            - EG: If node A has a distance of 10 to node B, then node B has a distance of 10 to node A
        - As each edit of the network, it removes the metrics other than `length` (see `add_edge`)
        """
        self.remove_node(symmetric_node=True)

    def add_haversine_edge(
        self,
        origin_idx: int,
        destination_idx: int,
        symmetric: bool = True,
        *,
        edge_class: str | None = None,
    ) -> None:
        """
        Function:

        - Add an edge to the graph
        - As each edit of the network, it removes the metrics other than `length` (see `add_edge`)

        Required Arguments:

        - `origin_idx`
            - Type: int
            - What: The index of the origin node
        - `destination_idx`
            - Type: int
            - What: The index of the destination node

        Optional Arguments:

        - `symmetric`
            - Type: bool
            - What: Whether to add the edge in both directions
            - Default: True
        - `edge_class`
            - Type: str | None
            - What: The name of the class of the new edge (see `add_edge`)
            - Default: None (no class: a metric made from weights per km gives the new edge the weight of an off-graph leg)
        """
        if not (origin_idx < len(self.graph_object.graph)):
            raise ValueError("Origin node does not exist")
        if not (destination_idx < len(self.graph_object.graph)):
            raise ValueError("Destination node does not exist")
        self.add_edge(
            origin_id=origin_idx,
            destination_id=destination_idx,
            distance=haversine(
                self.nodes[origin_idx], self.nodes[destination_idx]
            ),
            symmetric=symmetric,
            edge_class=edge_class,
        )

    def merge_with_other_geograph(
        self,
        other_geograph: "GeoGraph",
        connection_nodes: list[list[int | float]],
        circuity_to_current_geograph: float = 1.2,
        circuity_to_other_geograph: float = 1.2,
        node_addition_type_current_geograph: str = "closest",
        node_addition_type_other_geograph: str = "closest",
        node_addition_math: str = "euclidean",
        node_mode: str | None = None,
    ) -> None:
        """
        Function:

        - Merge the current geograph with another geograph
        - This is useful for combining multiple geographs into one
        - This modifies the current geograph in place
        - The edges of both geographs keep their classes; a class of the other geograph is added to `classes`, unless a class has its name
        - As each edit of the network, the merge removes the metrics other than `length` (see `add_edge`). It removes them from both geographs, because it adds the connection nodes to the other geograph and then removes them

        Required Arguments:

        - `other_geograph`
            - Type: GeoGraph
            - What: The other geograph to merge with
        - `connection_nodes`
            - Type: list of tuples
            - What: A list of [latitude, longitude] pairs that represent the nodes to connect between the two geographs
            - The only connections between the two graphs will be those specified in this list

        Optional Arguments:

        - `circuity_to_current_geograph`
            - Type: int | float
            - What: The circuity factor to apply to the distance calculations between the connection nodes and the current geograph
            - Default: 1.2
        - `circuity_to_other_geograph`
            - Type: int | float
            - What: The circuity factor to apply to the distance calculations between the connection nodes and the other geograph
            - Default: 1.2
        - `node_addition_type_current_geograph`
            - Type: str
            - What: The type of node addition to use when adding the connection nodes to the current geograph
            - Default: 'closest'
            - Options:
                - 'closest': Add the closest node to the connection node in the current geograph
                - 'quadrant': Add the closest node in each quadrant (ne, nw, se, sw) to the connection node in the current geograph
        - `node_addition_type_other_geograph`
            - Type: str
            - What: The type of node addition to use when adding the connection nodes to the other geograph
            - Default: 'closest'
            - Options:
                - 'closest': Add the closest node to the connection node in the other geograph
                - 'quadrant': Add the closest node in each quadrant (ne, nw, se, sw) to the connection node in the other geograph
        - `node_addition_math`
            - Type: str
            - What: The math to use when calculating the distance between nodes in determining which nodes to connect into when applying node addition
            - Note: Haversine distance is used to calculate the distance between the added connection nodes and the existing nodes in the geographs once they are chosen
            - Default: 'euclidean'
            - Options:
                - 'euclidean': Use the euclidean distance between nodes. This is much faster but is not accurate (especially near the poles)
                - 'haversine': Use the haversine distance between nodes. This is slower but is an accurate representation of the surface distance between two points
        - `node_mode`
            - Type: str | None
            - What: The name of the node mode of the connection nodes (see `add_coord_node`); the node modes of the other geograph are added after those of this geograph, so that its nodes keep theirs
            - Default: None (the node mode without a name)
        """
        node_connection_mapper = {}
        original_other_graph_length = len(other_geograph.nodes)
        original_other_modes = len(other_geograph.node_modes)
        if len(self.node_modes) + original_other_modes + 1 > 256:
            raise ValueError("A geograph has at most 256 node modes")
        # The classes of the edges of the other geograph, taken before the two
        # geographs get the connection nodes. A node of the other geograph follows
        # the nodes of this geograph and the connection nodes.
        self._edge_classes.merge(
            other_geograph._edge_classes,
            first_node_id=len(self.nodes) + len(connection_nodes),
        )
        # Connection nodes connect to the two networks as they were before
        # the merge, not to each other
        current_snap_index = self.snap_index
        other_snap_index = other_geograph.snap_index
        for node in connection_nodes:
            node_dict = {
                "latitude": node[0],
                "longitude": node[1],
            }
            self.snap_index = current_snap_index
            other_geograph.snap_index = other_snap_index
            # Add the connection node to the current geograph
            new_node_id = self.add_coord_node(
                coord_dict=node_dict,
                circuity=circuity_to_current_geograph,
                node_addition_type=node_addition_type_current_geograph,
                node_addition_math=node_addition_math,
                node_mode=node_mode,
            )
            # Add the connection node to the other geograph
            other_node_id = other_geograph.add_coord_node(
                coord_dict=node_dict,
                circuity=circuity_to_other_geograph,
                node_addition_type=node_addition_type_other_geograph,
                node_addition_math=node_addition_math,
            )
            node_connection_mapper[other_node_id] = new_node_id

        # Store the modified other geograph graph that include the connection nodes
        other_graph = deepcopy(other_geograph.graph_object.unreduced_graph)
        # Rows of the current graph before the other graph is appended: counted on the nodes
        # (a C++ graph would be copied to Python to count its rows), before they are extended
        graph_length = len(self.nodes)
        # The other graph's nodes keep their ids, its negative ids moved below this
        # graph's (connection nodes have negative ids of this graph)
        external_node_ids = self.external_node_ids.take(range(graph_length))
        floor = min(0, min(external_node_ids, default=0))
        external_node_ids.extend(
            i if i >= 0 else i + floor
            for i in other_geograph.external_node_ids.take(
                range(original_other_graph_length)
            )
        )
        # Add the other graph nodes to the current geograph (removing the connection nodes since they are already added to the current geograph)
        self.nodes += deepcopy(other_geograph.nodes)[
            :original_other_graph_length
        ]
        self.external_node_ids = array_views.ExternalNodeIds(
            external_node_ids, self.nodes
        )
        # Its node modes follow this graph's, renumbered
        offset = len(self.node_modes)
        # The finer precision of the two is kept
        if other_geograph.coordinate_dtype == "float64":
            self.coordinate_dtype = "float64"
        self.node_modes += [
            dict(row)
            for row in other_geograph.node_modes[:original_other_modes]
        ]
        # Its sources follow this graph's, so that its node modes still cite them
        sources = self.metadata.get("sources", [])
        named = {source.get("name") for source in sources}
        added = [
            source
            for source in other_geograph.metadata.get("sources", [])
            if source.get("name") not in named
        ]
        if added:
            self.metadata["sources"] = sources + added
        self.node_mode_ids.extend(
            offset + node_mode_id
            for node_mode_id in other_geograph.node_mode_ids[
                :original_other_graph_length
            ]
        )
        self.snap_index = None

        # Clean up the other geograph to remove any appended nodes
        while len(other_geograph.nodes) > original_other_graph_length:
            other_geograph.remove_coord_node()
        del other_geograph.node_modes[original_other_modes:]

        # Create a list based connection map to map the merging nodes into the current graph
        node_connection_map = [
            i + graph_length for i in range(len(other_graph))
        ]
        # Adjust the added nodes to match the nodes added to the current graph
        for idx, node in node_connection_mapper.items():
            node_connection_map[idx] = node
        # Re establish the graph object (To support C++ Graph Objects)
        graph = self.graph_object.unreduced_graph
        # Fill the current graph with empty dictionaries to match the length of the other graph
        graph.extend(
            [{} for _ in range(len(other_graph) - len(connection_nodes))]
        )
        # Populate the new connections
        for origin_idx, destinations in enumerate(other_graph):
            for destination_idx, distance in destinations.items():
                graph[node_connection_map[origin_idx]][
                    node_connection_map[destination_idx]
                ] = distance
        self.graph_object = Graph(graph=graph)
