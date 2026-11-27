"""Loading and saving of a `GeoGraph`.

This module is internal. `GeoGraphIO` is the mixin of `GeoGraph` that reads and writes
GeoJSON, graphjson, `.scgraph` files, OpenStreetMap files and OSMnx graphs.
`scgraph.geograph` imports it and re-exports it.
"""

from scgraph.utils import get_line_path, resolve_cache_dir
from scgraph.deprecations import warn_deprecated_parameter
from scgraph.step_logs import log_step
from scgraph.helpers.geojson import parse_geojson, simplify_geojson
from scgraph.helpers.polylines import build_graph_from_polylines
from scgraph.helpers.hilbert import get_hilbert_order
from scgraph.helpers.osm import MAX_KM_BETWEEN_NODES
from scgraph.edge_classes import CLASSES
from scgraph.metrics import Metric, check_weights
from scgraph.coordinates import encode_coordinates
from scgraph.turn_restrictions import has_turn_restrictions
from scgraph import array_views, network_file
import json
import os
import warnings
from array import array
from collections import Counter
from math import inf, isfinite
from operator import eq
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from collections.abc import Callable
from scgraph import Graph
import logging

if TYPE_CHECKING:  # Only for annotations.
    import networkx
    from scgraph.geograph import GeoGraph

# The records keep the logger name that they had in `scgraph.geograph`: the documents
# show this name, and a user filters on it.
logger = logging.getLogger("scgraph.geograph")

# A method that builds a geograph names `GeoGraph` or `LazyGeoGraph`, which
# `scgraph.geograph` defines. That module imports this one at its top, so each such
# method imports these names when it runs.


class GeoGraphIO:
    def _get_edge_coordinates(
        self,
        origin_idx: int,
        destination_idx: int,
        sequence: str,
        save_intermediate_nodes: bool,
    ) -> list[list[float]]:
        """Build the coordinates for one exported edge."""
        origin = self.nodes[origin_idx]
        destination = self.nodes[destination_idx]
        if sequence == "lon_lat":
            coordinates = [[origin[1], origin[0]]]
            final_pair = [destination[1], destination[0]]
        else:
            coordinates = [origin]
            final_pair = destination

        if self.intermediate_nodes is not None and save_intermediate_nodes:
            coordinates.extend(
                self._get_intermediate_nodes(
                    origin_idx=origin_idx,
                    destination_idx=destination_idx,
                    sequence=sequence,
                )
            )
        coordinates.append(final_pair)
        return coordinates

    # Save Methods

    def save_as_geojson(
        self,
        filename: str | os.PathLike,
        compact: bool = False,
        save_intermediate_nodes: bool = True,
    ) -> None:
        """
        Function:

        - Save the current geograph object as a geojson file specifed by `filename`
        - This is useful for understanding the underlying geograph and for debugging purposes
        - The file holds the lines of the edges only: a geograph loaded from it follows no turn restriction
        - Returns None

        Required Arguments:

        - `filename`
            - Type: str
            - What: The filename to save the geojson file as

        Optional Arguments:

        - `compact`
            - Type: bool
            - What:
                - If True, saves the geojson as a compact multiline string without distances or other properties
                - If False, saves the geojson as a feature collection with each line as a separate feature
                    - Note: If False, the resulting file can be loaded with the legacy load_geojson_as_geograph function
            - Default: False

        """
        graph = self.graph_object.unreduced_graph
        if compact:
            multiline = []
            for origin_idx, destinations in enumerate(graph):
                for destination_idx in destinations:
                    multiline.append(
                        self._get_edge_coordinates(
                            origin_idx,
                            destination_idx,
                            "lon_lat",
                            save_intermediate_nodes,
                        )
                    )
            out_dict = {
                "type": "GeometryCollection",
                "geometries": [
                    {
                        "type": "MultiLineString",
                        "coordinates": multiline,
                    }
                ],
            }

        else:
            features = []
            for origin_idx, destinations in enumerate(graph):
                for destination_idx, distance in destinations.items():
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
                                "coordinates": self._get_edge_coordinates(
                                    origin_idx,
                                    destination_idx,
                                    "lon_lat",
                                    save_intermediate_nodes,
                                ),
                            },
                        }
                    )
            out_dict = {"type": "FeatureCollection", "features": features}
        with open(filename, "w") as f:
            json.dump(out_dict, f)

    def save_as_graphjson(
        self,
        filename: str | os.PathLike,
        save_intermediate_nodes: bool = True,
    ) -> None:
        """
        Function:

        - Save the current geograph as a JSON file that can be used to recreate the geograph later
        - This is particularly useful for larger geographs that you want to save and load later without having to recreate them from scratch
        - Only the graph and nodes are saved, not the methods or any other attributes of the GeoGraph class
        - A geograph that follows turn restrictions is also saved with its `external_node_ids`, `node_mode_ids` and `node_modes`. A geograph loaded from the file then follows the turn restrictions too
        - Another geograph loses its node modes. A geograph loaded from the file snaps to every node by default, so its routes can change

        Required Arguments:

        - `filename`
            - Type: str
            - What: The filename to save the JSON file as
            - EG: 'custom.graphjson'
                - Stored as: 'custom.graphjson'
                    - In your current directory
            - Note: The filename must end with .graphjson
            - Note: A file inside the `networks/` folder of the cache directory (`build_geograph`'s) raises a ValueError: save it elsewhere

        Optional Arguments:

        - `save_intermediate_nodes`
            - Type: bool
            - What: Whether to include the intermediate nodes in the saved JSON file (if they exist)
            - Default: True
        """
        filename = os.fspath(filename)
        if not filename.endswith(".graphjson"):
            raise ValueError("Filename must end with .graphjson")
        # A cached network must stay the one its cache.json names
        built = resolve_cache_dir().joinpath("networks").resolve()
        if Path(filename).resolve().is_relative_to(built):
            raise ValueError(
                f"{filename} is in scgraph's cache ({built}); save it elsewhere"
            )
        extra_kwargs = {}
        if self.intermediate_nodes is not None and save_intermediate_nodes:
            extra_kwargs["intermediate_nodes"] = [
                dict(row) for row in self.intermediate_nodes
            ]
        if has_turn_restrictions(self):
            # A load finds the nodes of a junction with these three values
            # (`scgraph/turn_restrictions.py`). Another geograph is written
            # without them, as release 3.6.0 writes it.
            extra_kwargs["external_node_ids"] = list(self.external_node_ids)
            extra_kwargs["node_mode_ids"] = list(self._read_node_mode_ids())
            extra_kwargs["node_modes"] = self.node_modes
        with open(filename, "w") as f:
            json.dump(
                {
                    "type": "GeoGraph",
                    "graph": self.graph_object.unreduced_graph,
                    "nodes": list(self.nodes),
                    "default_off_graph_circuity": self.default_off_graph_circuity,
                    "default_node_addition_circuity": self.default_node_addition_circuity,
                    "geograph_units": self.geograph_units,
                    **extra_kwargs,
                },
                f,
            )

    def save_as_scgraph(
        self,
        filename: str | os.PathLike,
        save_intermediate_nodes: bool = True,
        metadata: dict | Literal["auto"] | None = "auto",
        coordinate_dtype: Literal["auto", "float64", "int32"] = "auto",
    ) -> str:
        """
        Function:

        - Save the current geograph as a binary network file, much faster to load than graphjson
        - The format is described in ARCHITECTURE.md, section "Network File Format", and in the header of each file
        - Only the graph, the nodes, their ids and node modes, their intermediate nodes, the classes of the edges, the metrics with their weights and the GeoGraph defaults are saved; `default_metric` is not saved
        - The nodes are written node mode by node mode, in the order of `node_modes`, and in Hilbert order within each node mode (nodes close on the globe get close ids); the geograph itself is not renumbered, and each node keeps its id in `external_node_ids`
        - Coordinates that are not finite numbers raise a ValueError

        Required Arguments:

        - `filename`
            - Type: str
            - What: The filename to save the network file as
            - Note: The filename must end with .scgraph
            - Note: The file does not hold `default_node_addition_circuity` and `default_off_graph_circuity`: a geograph loaded from it has the defaults (4 and 1); a `.graphjson` file keeps them
            - Note: A file inside the `networks/` folder of the cache directory (`build_geograph`'s) raises a ValueError: save it elsewhere
            - Note: On Windows (C++ build), a file that a live GeoGraph (or its `snap_index`) was loaded from raises a PermissionError: save to another name

        Optional Arguments:

        - `save_intermediate_nodes`
            - Type: bool
            - What: Whether to include the intermediate nodes in the saved file (if they exist)
            - Default: True
        - `metadata`
            - Type: dict | 'auto' | None
            - What: What the file header says about how the network was built, so that it travels with the file: the build metadata, whose fields `scgraph.pipelines` and ARCHITECTURE.md (section "Network File Format") describe, for example its `sources`, each with a `name`; 'auto' writes the geograph's own `metadata` (read from the file it was loaded from), None writes none
            - Default: 'auto'
            - Note: Changes made to a geograph after loading are not recorded in it (its `content_sha256` changes); a merge adds the other geograph's `sources`
            - Note: A key scgraph writes itself (`crs`, `metrics`, `node_modes`, `node_order`, ...), or a node mode whose `source` names no entry of `sources` (also with None), raises a ValueError
            - Note: A string other than 'auto' raises a ValueError, and a value that is not a dict, a string or None raises a TypeError
        - `coordinate_dtype`
            - Type: str
            - What: How coordinates are stored: 'float64' exactly, 'int32' rounded to 1e-7 degree (OSM's encoding, about 1 cm; 8 bytes less per node), 'auto' as the geograph's `coordinate_dtype`
            - Default: 'auto'

        Returns:

        - The `content_sha256` of the file: the SHA-256 of every byte after its first 40, also stored in its bytes 8 to 39
        """
        filename = os.fspath(filename)
        if not filename.endswith(".scgraph"):
            raise ValueError(
                f"Filename must end with .scgraph, not {filename!r}"
            )
        if isinstance(metadata, str) and metadata != "auto":
            raise ValueError(
                f"metadata must be a dict, 'auto' or None, not {metadata!r}"
            )
        if not (metadata is None or isinstance(metadata, (str, dict))):
            raise TypeError(
                f"metadata must be a dict, 'auto' or None, not {metadata!r}"
            )
        if coordinate_dtype not in ("auto", "float64", "int32"):
            raise ValueError(
                "coordinate_dtype must be 'auto', 'float64' or 'int32'"
            )
        if self.default_metric != "length":
            warnings.warn(
                "The file does not keep the default metric "
                f"{self.default_metric!r}. After the load, pass "
                f"metric={self.default_metric!r} to each query, or set "
                "geograph.default_metric.",
                stacklevel=2,
            )
        # The class id and the weights of each edge, in arrays "by edge id": one
        # value for each edge, at the id of the edge. A geograph without classes
        # and without metrics does not read the arrays of its edges here.
        classes, edge_value_arrays = None, {}
        if self.classes or self._read_metrics():
            geograph_node_first_edge_ids = self._read_edge_arrays(
                check_edge_count=True
            )[0]
            edge_class_ids = self._read_edge_class_ids()
            if edge_class_ids is not None:
                classes = self.classes
                edge_value_arrays["edge_class_ids"] = edge_class_ids
            for name, metric_record in self._read_metrics().items():
                edge_value_arrays[f"metric_{name}"] = metric_record.weights
        # A cached network must stay the one its cache.json names
        built = resolve_cache_dir().joinpath("networks").resolve()
        if Path(filename).resolve().is_relative_to(built):
            raise ValueError(
                f"{filename} is in scgraph's cache ({built}); save it elsewhere"
            )
        # Written in Hilbert order within each node mode (nodes close on the globe get
        # close ids, and the nodes of a node mode stay together); the geograph is not
        # renumbered
        nodes, node_mode_ids = self.nodes, self._read_node_mode_ids()
        # (by node mode only if there are several: the key is cheaper without)
        multimodal = len(self.node_modes) > 1
        try:
            order = get_hilbert_order(
                nodes, node_mode_ids if multimodal else None
            )
        except (OverflowError, ValueError):
            node = next(
                (
                    i
                    for i, point in enumerate(nodes)
                    if not all(map(isfinite, point))
                ),
                None,
            )
            if node is None:
                raise
            raise ValueError(
                f"Node {node} has coordinates that are not finite numbers"
            ) from None
        if all(map(eq, order, range(len(order)))):
            order = None  # already in that order: written as it is
        old = range(len(nodes)) if order is None else order
        # In the order searches visit the edges, so that the file gives the same paths
        node_first_edge_ids, edge_destination_node_ids, weights = (
            self.graph_object._get_edge_arrays(order)
        )
        if order is not None and edge_value_arrays:
            edge_value_arrays = {
                name: _reorder_edge_values(
                    edge_values, geograph_node_first_edge_ids, order
                )
                for name, edge_values in edge_value_arrays.items()
            }
        arrays = {
            "node_first_edge_ids": node_first_edge_ids,
            "edge_destination_node_ids": edge_destination_node_ids,
            "metric_length": weights,
            **edge_value_arrays,
        }
        node_points = array("d", (value for i in old for value in nodes[i][:2]))
        # None: each node's id is its position
        external_node_ids = self.external_node_ids.array(order)
        if external_node_ids is not None:
            arrays["external_node_ids"] = external_node_ids
        if multimodal:
            node_mode_ids = array("B", (node_mode_ids[i] for i in old))
        metadata = network_file.build_header_metadata(
            self.metadata if metadata == "auto" else metadata or {},
            node_modes=self.node_modes,
            node_mode_ids=node_mode_ids,
            metrics=self.metrics,
            classes=classes,
        )
        shapes = self.intermediate_nodes if save_intermediate_nodes else None
        if shapes is not None:
            starts, points = array("i", [0]), array("d")
            for new, origin in enumerate(old):
                # Nodes added after loading (add_coord_node, merges) have no shapes
                row = shapes[origin] if origin < len(shapes) else {}
                for edge in range(
                    node_first_edge_ids[new], node_first_edge_ids[new + 1]
                ):
                    destination_id = old[edge_destination_node_ids[edge]]
                    for latitude, longitude in row.get(destination_id, ()):
                        if not (isfinite(latitude) and isfinite(longitude)):
                            raise ValueError(
                                f"The shape of edge {origin} -> {destination_id} has a point "
                                "that is not a finite number"
                            )
                        points.append(latitude)
                        points.append(longitude)
                    starts.append(len(points) // 2)
            arrays["edge_first_shape_point_ids"] = starts
        point_arrays = [node_points] + ([points] if shapes is not None else [])
        if coordinate_dtype == "auto":
            coordinate_dtype = self.coordinate_dtype
        arrays.update(
            zip(
                network_file.POINT_ARRAYS,
                encode_coordinates(point_arrays, coordinate_dtype),
            )
        )
        return network_file.write(filename, arrays, metadata=metadata)

    # Load Methods
    @staticmethod
    def load_from_geojson(
        filename: str | os.PathLike,
        precision: int = 5,
        pct_to_keep: float = 100,
        min_points: int = 3,
        load_intermediate_nodes: bool = True,
        silent: bool | None = None,
        reduce_iterations: int = 0,
        lazy: bool = False,
        max_km_between_nodes: float | None = None,
    ) -> "GeoGraph":
        """
        Function:

        - Load a GeoGraph from an arbitrary geojson file (GeometryCollection or FeatureCollection)
        - This function
            - Merges all LineStrings and MultiLineStrings into a single MultiLineString
            - Simplifies the MultiLineString to reduce the number of points using a percentage based Visvalengam simplification algorithm
            - Rounds the coordinates to the specified precision
            - Merges lines that start and end at the same location after rounding
            - Converts the MultiLineString into a GeoGraph object
            - Numbers the nodes along a Hilbert curve (nodes close on the globe get close ids); without `max_km_between_nodes`, `external_node_ids[i]` is node i's id before this ordering (the numbering of earlier versions)
        - Note:
            - All edges read in will be undirected


        Required Arguments:

        - `filename`
            - Type: str
            - What: The filename of the geojson file to load
            - EG: 'custom.geojson'
                - Stored as: 'custom.geojson'
                    - In your current directory

        Optional Arguments:

        - `precision`
            - Type: int
            - What: Decimal places to round coordinates when loading and simplifying the lines
            - Default: 5
        - `pct_to_keep`
            - Type: int|float
            - What: Percentage of the interior line points to keep (note the ends are always kept)
            - Default: 100
        - `min_points`
            - Type: int
            - What: Minimum number of points to keep in the simplified line (The ends are always kept but should be included in this count)
            - Default: 3
        - `load_intermediate_nodes`
            - Type: bool
            - What: Whether to keep the shape of each edge (its intermediate points) in the GeoGraph object
            - Default: True
            - Note: Only used with `max_km_between_nodes`; otherwise every point is a node and edges have no intermediate points.
        - `silent`
            - Deprecated and without effect. scgraph reports its messages through `logging`.
        - `reduce_iterations`
            - Type: int
            - What: Number of reduction iterations to perform upon loading. If 0, no reduction is done. If -1, reduces iteratively until convergence.
            - Default: 0
        - `lazy`
            - Type: bool
            - What: Whether to delay loading the geograph until its first use
            - Default: False
        - `max_km_between_nodes`
            - Type: float | int | None
            - What: If set, nodes are only the points where polylines meet or end, and a polyline is also cut at the first point where the edge since the previous node reaches `max_km_between_nodes`; the other points become the shape of the edges, whose length is the length of their full polyline
            - Default: None (every point is a node)
            - Note: Useful for sources with many points per line, such as rail or road networks, to keep the graph small
        """
        from scgraph.geograph import GeoGraph, LazyGeoGraph

        warn_deprecated_parameter("silent", silent)
        if lazy:
            return LazyGeoGraph(
                lambda: GeoGraph.load_from_geojson(
                    filename=filename,
                    precision=precision,
                    pct_to_keep=pct_to_keep,
                    min_points=min_points,
                    load_intermediate_nodes=load_intermediate_nodes,
                    reduce_iterations=reduce_iterations,
                    lazy=False,
                    max_km_between_nodes=max_km_between_nodes,
                )
            )
        if max_km_between_nodes is not None:
            # A vertex is (id, point). Its id is its (longitude, latitude) tuple in the
            # file, so that the vertices at one place are one vertex.
            lines = [
                [(tuple(lon_lat), [lon_lat[1], lon_lat[0]]) for lon_lat in line]
                for line in simplify_geojson(
                    filename_in=filename,
                    precision=precision,
                    pct_to_keep=pct_to_keep,
                    min_points=min_points,
                )
            ]
            uses = Counter(vertex_id for line in lines for vertex_id, _ in line)
            junctions = {
                vertex_id for vertex_id, count in uses.items() if count > 1
            }
            # A GeoGraph numbers its nodes by index, so the node ids are dropped
            graph, nodes, shapes, _, _ = build_graph_from_polylines(
                ((0, line) for line in lines), junctions, max_km_between_nodes
            )
            geograph = GeoGraph(
                graph=graph,
                nodes=nodes,
                intermediate_nodes=shapes if load_intermediate_nodes else None,
                coordinate_dtype="int32" if precision <= 7 else "float64",
            )
            geograph.reduce(reduce_iterations)
            return geograph
        data = parse_geojson(
            filename_in=filename,
            precision=precision,
            pct_to_keep=pct_to_keep,
            min_points=min_points,
            # load_intermediate_nodes=load_intermediate_nodes,
        )
        # In Hilbert order: nodes close on the globe get close ids
        geograph = renumber_in_hilbert_order(
            GeoGraph(
                graph=data["graph"],
                nodes=data["nodes"],
                coordinate_dtype="int32" if precision <= 7 else "float64",
            )
        )
        geograph.reduce(reduce_iterations)
        return geograph

    @staticmethod
    def load_from_osm(
        filename: str | os.PathLike,
        select: Callable | None = None,
        tag_keys: tuple[str, ...] = ("highway",),
        max_km_between_nodes: float | None = MAX_KM_BETWEEN_NODES,
        largest_component: bool = True,
        load_intermediate_nodes: bool = True,
        reduce_iterations: int = 0,
        lazy: bool = False,
        load_turn_restrictions: bool = True,
    ) -> "GeoGraph":
        """
        Function:

        - Load a GeoGraph from an OpenStreetMap file (`.osm.pbf`, `.osm` or `.osm.bz2`)
        - Needs the optional dependency `osmium`: `pip install scgraph[osm]`
        - Ways meet only where they share an OSM node: roads that cross on a bridge or in a tunnel are not connected
        - Each edge has the length of its piece of way, in kilometers, so it is never shorter than the straight line between its ends
        - One edge at most goes from a node to another. Of two ways of one class between the same two nodes, the shortest is kept. A longer way of another class is kept too, with one more node at its middle: this node has an id below zero in `external_node_ids`
        - Nodes are the OSM nodes where kept ways meet or end; a way is also cut at the first point where the edge since the previous node reaches `max_km_between_nodes`
        - Nodes are numbered along a Hilbert curve (nodes close on the globe get close ids), and `external_node_ids[i]` is node i's OSM id
        - With the default `select`, ways tagged `oneway=yes` or `-1`, motorways and roundabouts are one way
        - A route makes no turn that a turn restriction of the file forbids, for cars (`load_turn_restrictions`)
        - Some junctions then have more than one node, with the same point and the same external id. `scgraph/turn_restrictions.py` explains these nodes
        - Conditional turn restrictions, and the turn restrictions of other vehicles, are not read
        - Each edge has the class that `select` gives to its way: `classes` holds the classes of `scgraph.pipelines.CLASSES`, and `get_edges` gives the class of each edge. With the default `select`, the class of a way is its `highway` value
        - The load builds its graph with `scgraph.helpers.osm` and `scgraph.network_assembly`, as the OpenStreetMap pipelines do, on one node mode: it reads and cuts the ways, builds the graph, keeps the largest component and orders the nodes. It neither attaches ferries, nor contracts chains, nor simplifies shapes
        - Memory: osmium's node and way filters take about 1.7 GB, whatever the size of the file

        Required Arguments:

        - `filename`
            - Type: str | os.PathLike | source object
            - What: The path of the OpenStreetMap file, for example an extract downloaded from https://download.geofabrik.de, or a source object as `scgraph.helpers.osm.locate_ways` takes

        Optional Arguments:

        - `select`
            - Type: Callable (tags -> int | tuple[int, str] | None), the tags of a way read as `tags.get(key)` or `key in tags`
            - What: Gives, from the tags of a way, its direction: 1 (one way, along its drawing), -1 (one way, against it), 0 (both ways), or None to leave the way out. In place of the direction, it may give a pair: the direction and the class of the way, a name of `scgraph.pipelines.CLASSES`
            - Default: None: `scgraph.helpers.osm.select_main_roads_with_class` (motorway to primary and their links, each with its `highway` value as its class, one way where `scgraph.helpers.osm.get_way_direction(tags)` returns 1 or -1)
            - Note: When `select` gives a direction alone for every way, the geograph has no classes. `select` gives a class to every way that it keeps, or to none
            - Example: `lambda tags: 0 if tags.get("railway") == "rail" and tags.get("service") in (None, "crossover") else None` for railway lines without yards, sidings and spurs, both ways (a crossover joins the two tracks of a double line)
            - Note: Called for each way in two passes over the file: it must give the same answer each time
        - `tag_keys`
            - Type: tuple[str, ...]
            - What: Tag keys of which a way must have at least one to reach `select`; osmium leaves out the other ways before Python sees them, which is faster. Empty: every way reaches `select`
            - Default: ("highway",)
            - Note: Give the tag keys that `select` keeps ways by, for example `("railway",)` for railway lines
        - `max_km_between_nodes`
            - Type: float | int | None
            - What: Length in kilometers at which a way is cut into a new edge (at the next point of the way), so that origins and destinations can attach close to where they are. None cuts a way only where it meets another kept way or ends
            - Default: 2 (`scgraph.helpers.osm.MAX_KM_BETWEEN_NODES`)
        - `largest_component`
            - Type: bool
            - What: Whether to keep only the largest part of the network where every node can reach every other, so that origins and destinations are never placed on a one-way dead end or on a fragment cut by the border of the extract
            - Default: True
            - Note: Parts not connected to the largest one, such as islands without a road link, are dropped
        - `load_intermediate_nodes`
            - Type: bool
            - What: Whether to keep the shape of each edge, to draw routes
            - Default: True
        - `reduce_iterations`
            - Type: int
            - What: Number of reduction iterations to perform upon loading. If 0, no reduction is done. If -1, reduces iteratively until convergence.
            - Default: 0
        - `lazy`
            - Type: bool
            - What: Whether to delay loading the geograph until its first use
            - Default: False
        - `load_turn_restrictions`
            - Type: bool
            - What: Whether to read the turn restrictions of the file (the relations with `type=restriction`): a route then makes no turn that one of them forbids, for cars; if False, a route may make any turn
            - Default: True
            - Note: Some junctions then have more than one node, with the same point and the same external id (`scgraph/turn_restrictions.py`)
            - Note: The turn restrictions are read in one more pass over the file

        Raises:

        - `ImportError` if the optional dependency `osmium` is not installed
        - `ValueError` if no way of the file has one of `tag_keys` and is kept by `select`, or if `select` returns anything else than 1, -1, 0, a pair of one of them and a name of `scgraph.pipelines.CLASSES`, or None (`True` and `False` included), or if `select` gives a class to some of the kept ways only
        """
        from scgraph.geograph import GeoGraph, LazyGeoGraph

        if lazy:
            return LazyGeoGraph(
                lambda: GeoGraph.load_from_osm(
                    filename=filename,
                    select=select,
                    tag_keys=tag_keys,
                    max_km_between_nodes=max_km_between_nodes,
                    largest_component=largest_component,
                    load_intermediate_nodes=load_intermediate_nodes,
                    reduce_iterations=reduce_iterations,
                    lazy=False,
                    load_turn_restrictions=load_turn_restrictions,
                )
            )
        from scgraph import network_assembly
        from scgraph.helpers.osm import (
            build_way_pieces,
            select_main_roads_with_class,
        )
        from scgraph.helpers.osm import read_turn_restrictions
        from scgraph.turn_restrictions import list_forbidden_turns

        # The functions that the OpenStreetMap pipelines build their graph with,
        # without the hubs and without the contraction of the chains. The shapes
        # are kept as they are.
        pieces = build_way_pieces(
            filename,
            {"ways": {"ways": select or select_main_roads_with_class}},
            tag_keys,
            inf if max_km_between_nodes is None else max_km_between_nodes,
            optional_modes=("ways",),
            shape_tolerance_meters=None,
        )["ways"]
        if not len(pieces.km):
            raise ValueError(
                f"No way of {filename} has one of the tag keys {tag_keys} and is kept by select"
            )
        arrays = network_assembly.build_graph_from_pieces(pieces)
        forbidden_turns = (
            list_forbidden_turns(arrays, read_turn_restrictions(filename))
            if load_turn_restrictions
            else []
        )
        # Only `list_forbidden_turns` reads the way of an edge
        arrays.pop("edge_way_ids", None)
        arrays = network_assembly.forbid_turns(arrays, forbidden_turns)
        if largest_component:
            arrays = network_assembly.keep_components(arrays, None)
        arrays = network_assembly.order_nodes(arrays)
        edge_arrays = (
            arrays["node_first_edge_ids"],
            arrays["edge_destination_node_ids"],
            arrays["metric_length"],
        )
        # The arrays are the edges of the new graph, in the same order
        geograph = GeoGraph._build_from_edge_arrays(
            edge_arrays,
            arrays.get("edge_class_ids"),
            graph=Graph.from_edge_arrays(*edge_arrays, copy=False),
            nodes=array_views.NodePoints(arrays["node_points"]),
            intermediate_nodes=(
                array_views.EdgeShapes(arrays)
                if load_intermediate_nodes
                else None
            ),
            external_node_ids=arrays["external_node_ids"],
            coordinate_dtype="int32",  # OSM's own: 1e-7 degree
            # The geograph gets every class of `CLASSES`, as a file of a pipeline.
            classes=(
                [
                    {"name": name, "edge_mode": edge_mode}
                    for name, edge_mode in CLASSES.items()
                ]
                if "edge_class_ids" in arrays
                else None
            ),
            node_modes=(
                [{"name": None, "has_turn_restrictions": True}]
                if load_turn_restrictions
                else None
            ),
        )
        geograph.reduce(reduce_iterations)
        return geograph

    @staticmethod
    def load_from_graphjson(
        filename: str | os.PathLike,
        reduce_iterations: int = 0,
        lazy: bool = False,
    ) -> "GeoGraph":
        """
        Function:

        - Load a GeoGraph from a JSON file that was saved using the `save_as_graphjson` method
        - Edge shapes are read as the points between their edge's two nodes, from origin to destination: nodes they repeat (files saved by released versions) are dropped, a shape running from destination to origin is reversed, and an edge left without points has no shape

        Required Arguments:

        - `filename`
            - Type: str
            - What: The filename of the JSON file to load
            - EG: 'custom.json'
                - Stored as: 'custom.json'
                    - In your current directory

        Optional Arguments:

        - `reduce_iterations`
            - Type: int
            - What: Number of reduction iterations to perform upon loading. If 0, no reduction is done. If -1, reduces iteratively until convergence.
            - Default: 0
        - `lazy`
            - Type: bool
            - What: Whether to delay loading the geograph until its first use
            - Default: False

        Returns:

        - A GeoGraph object with the graph and nodes loaded from the JSON file
        """
        from scgraph.geograph import GeoGraph, LazyGeoGraph

        if lazy:
            return LazyGeoGraph(
                lambda: GeoGraph.load_from_graphjson(
                    filename=filename,
                    reduce_iterations=reduce_iterations,
                    lazy=False,
                )
            )
        filename = os.fspath(filename)
        if not filename.endswith(".graphjson"):
            raise ValueError("Filename must end with .graphjson")
        with open(filename, "r") as f:
            data = json.load(f)
        if data.get("type", None) != "GeoGraph":
            raise ValueError(
                "JSON file is not a valid GeoGraph. Ensure it was saved using the save_as_graphjson method."
            )
        data.pop("type")
        # Clean the graph data such that all keys are ints (JSON only allows string keys, but we want int keys for the graph)
        data["graph"] = [
            {int(k): v for k, v in item.items()} for item in data["graph"]
        ]
        if data.get("intermediate_nodes") is not None:
            data["intermediate_nodes"] = [
                {int(k): v for k, v in item.items()}
                for item in data["intermediate_nodes"]
            ]
            # Files saved by scgraph 3.0 to 3.6 repeat each edge's two nodes in its shape
            _keep_interior_points(data["intermediate_nodes"], data["nodes"])
        geograph = GeoGraph(**data)
        geograph.reduce(reduce_iterations)
        return geograph

    @staticmethod
    def get_scgraph_info(filename: str | os.PathLike) -> dict:
        """
        Function:

        - What a binary network file holds, read from its header without loading the network
        - A damaged or foreign file raises a ValueError

        Required Arguments:

        - `filename`
            - Type: str
            - What: The network file (.scgraph) to read

        Returns:

        - The dict of `scgraph.network_file.get_scgraph_info`: its docstring gives the keys, such as `attribution`, the credit line to cite with results
        """
        return network_file.get_scgraph_info(filename)

    @staticmethod
    def load_from_scgraph(
        filename: str | os.PathLike,
        reduce_iterations: int = 0,
        lazy: bool = False,
        node_modes: list[str] | str | None = None,
    ) -> "GeoGraph":
        """
        Function:

        - Load a GeoGraph from a binary network file saved with `save_as_scgraph`
        - The file is checked before use: a damaged or foreign file raises a ValueError (in the C++ build, damaged edge shapes raise it when they are read)
        - In the C++ build, the file is mapped and read in place while the geograph or its `snap_index` is alive; on Windows it can't be replaced or deleted meanwhile
        - `nodes` reads the file's coordinates: `nodes[i]` is a new list each time, so replace a node with `nodes[i] = [latitude, longitude]`
        - `intermediate_nodes` reads the file's edge shapes when asked for, read-only: `intermediate_nodes[i]` is a new mapping {destination: shape} each time, so editing a shape changes nothing and assigning raises a TypeError
        - `external_node_ids` reads the file's node ids, if it has them (otherwise each node's id is its position); `node_mode_ids` and `node_modes` give the node mode of each node
        - `classes` holds the classes of the file, if it has them, and `get_edges` gives the class of each edge
        - `metrics` holds the metrics of the file, with their weights. An edit of the network removes them, as every metric other than `length` (see `add_edge`). `default_metric` is 'length'
        - `metadata` holds what the file says about how the network was built (`sources`, `pipeline`, ...), which `save_as_scgraph` writes back by default
        - `scgraph_file` is the path of the file that was read: `GeoGraph.get_scgraph_info(geograph.scgraph_file)` gives its `content_sha256` and the credit line to cite (`attribution`). A later change of the geograph, such as a merge, does not change `scgraph_file`.
        - The snapping index (`snap_index`) is built while loading, so that the first query is as fast as the next ones. On a file with road nodes and other nodes, the first query also builds the index of the road nodes

        Required Arguments:

        - `filename`
            - Type: str
            - What: The filename of the network file to load
            - Note: The filename must end with .scgraph

        Optional Arguments:

        - `reduce_iterations`
            - Type: int
            - What: Number of reduction iterations to perform upon loading. If 0, no reduction is done. If -1, reduces iteratively until convergence.
            - Default: 0
        - `lazy`
            - Type: bool
            - What: Whether to delay loading the geograph until its first use
            - Default: False
        - `node_modes`
            - Type: list[str] | str | None
            - What: The names of the node modes to load (see `node_modes`): only their nodes and the edges between them, in the order of the file; `node_modes` is the file's list, which `node_mode_ids` indexes, and the file's metadata (sources, attribution, as `scgraph_info` gives it) stays the whole file's
            - Default: None (every node mode)
        """
        from scgraph.geograph import GeoGraph, LazyGeoGraph

        if lazy:
            return LazyGeoGraph(
                lambda: GeoGraph.load_from_scgraph(
                    filename=filename,
                    reduce_iterations=reduce_iterations,
                    lazy=False,
                    node_modes=node_modes,
                )
            )
        filename = os.fspath(filename)
        if not filename.endswith(".scgraph"):
            raise ValueError("Filename must end with .scgraph")
        # The C++ graph reads the edges in place and checks them. The edges are in the
        # mapped file, or in the new arrays of a selection of node modes.
        # Not a choice of kernel: the test chooses a layout of the data.
        mapped = Graph.__module__ == "scgraph.cpp"
        with log_step(
            logger,
            "read the network file",
            {"file": filename, "mapped": mapped},
        ) as values:
            arrays, metadata = network_file.read(filename, mapped, node_modes)
            values["nodes"] = len(arrays["node_points"]) // 2
            values["edges"] = len(arrays["edge_destination_node_ids"])
        edge_arrays = (
            arrays["node_first_edge_ids"],
            arrays["edge_destination_node_ids"],
            arrays["metric_length"],
        )
        try:
            graph = Graph.from_edge_arrays(*edge_arrays, copy=False)
            for row in metadata["metrics"][1:]:
                check_weights(
                    row["name"],
                    arrays[f"metric_{row['name']}"],
                    *edge_arrays[:2],
                )
        except ValueError as error:
            raise ValueError(f"{filename}: {error}") from error
        # The arrays of the file are the edges of the new graph, in the same order
        geograph = GeoGraph._build_from_edge_arrays(
            edge_arrays,
            arrays.get("edge_class_ids"),
            {
                row["name"]: Metric(
                    row["name"],
                    row.get("unit"),
                    row.get("description"),
                    arrays[f"metric_{row['name']}"],
                    row["off_graph_weight_per_km"],
                )
                for row in metadata["metrics"][1:]
            },
            graph=graph,
            nodes=array_views.NodePoints(arrays["node_points"]),
            intermediate_nodes=(
                array_views.EdgeShapes(arrays)
                if "edge_first_shape_point_ids" in arrays
                else None
            ),
            geograph_units=metadata["metrics"][0]["unit"],
            external_node_ids=arrays.get("external_node_ids"),
            node_mode_ids=(
                network_file.build_node_mode_ids(
                    metadata["node_modes"], node_modes
                )
                if "node_modes" in metadata
                else None
            ),
            # A count of nodes would be wrong after an edit: the save counts them
            node_modes=[
                {
                    key: value
                    for key, value in row.items()
                    if key != "node_count"
                }
                for row in metadata.get("node_modes", [{"name": None}])
            ],
            coordinate_dtype=network_file.get_coordinate_dtype(arrays),
            classes=metadata["classes"] if "edge_class_ids" in arrays else None,
        )
        geograph.metadata = {
            key: value
            for key, value in metadata.items()
            if key not in network_file.RESERVED_METADATA_KEYS
        }
        geograph.scgraph_file = filename
        geograph.reduce(reduce_iterations)
        # Every route snaps its points (node ids depend on how the file was sorted): the
        # index is built now, not at the first query (an empty network has none)
        if len(geograph.nodes):
            try:
                geograph.snap_index  # noqa: B018 (reading it builds the index)
            except ValueError as error:  # e.g. coordinates that are not finite
                raise ValueError(f"{filename}: {error}") from error
        return geograph

    @staticmethod
    def load_from_osmnx_graph(
        osmnx_graph: "networkx.MultiDiGraph",
        coord_precision: int = 5,
        weight_precision: int = 3,
        weight_key: Literal["length", "travel_time"] = "length",
        off_graph_travel_speed: float | None = None,
        load_intermediate_nodes: bool = True,
        silent: bool | None = None,
        reduce_iterations: int = 0,
        lazy: bool = False,
    ) -> "GeoGraph":
        """
        Function:

        - Load a GeoGraph from an OSMnx graph object
        - This function:
            - Will convert the OSMnx graph into a GeoGraph object
            - Rounds the coordinates to the specified precision
            - Rounds the lengths (in kilometers) and the travel times (in seconds) to the specified precision
            - This preserves directionality of edges from the OSMnx graph
            - Numbers the nodes along a Hilbert curve (nodes close on the globe get close ids); `external_node_ids[i]` is node i's OSMnx id (its OSM id), when the ids are integers
            - Keeps the `highway` value of each edge as its class, of the edge mode `road` (see `classes` and `get_edges`): the first value when `highway` is a list, and no class for an edge without `highway`
            - The lengths of the geograph are always the `length` of the edges, in kilometers
            - Keeps the `travel_time` of each edge as the metric `travel_time`, in seconds, when every edge has one: `get_shortest_path(metric="travel_time")` then finds the fastest path. Its result has the kilometers of this path in `length` and its seconds in `metric_totals["travel_time"]`
            - The weight of an off-graph leg, the straight line between a query point and its node, is its kilometers times 3600 / `off_graph_travel_speed` seconds in the metric `travel_time`, or times 240 seconds without a speed
            - Of several edges from one node to another, keeps the one with the smallest value of `weight_key`, with its length, its class and its travel time. So with the weight key 'length', `travel_time` holds the time of the shortest edge, which may not be the fastest

        Required Arguments:

        - `osmnx_graph`
            - Type: osmnx.graph
            - What: The OSMnx graph object to load
            - EG: G

        Optional Arguments:

        - `coord_precision`
            - Type: int
            - What: Decimal places to round coordinates when loading the graph
            - Default: 5
        - `weight_precision`
            - Type: int
            - What: Decimal places to round weights when loading the graph
            - Default: 3
            - Note: By default, OSMNX returns meters, but they are adjusted to kilometers in this function before rounding
        - `weight_key`
            - Type: str
            - What: The edge attribute that the queries minimise. It sets the `default_metric` of the geograph: the metric of a query that names no `metric`
            - Options:
                - 'length': Use the length attribute (in kilometers)
                - 'travel_time': Use the travel_time attribute (in seconds). Every edge must have one
            - Default: 'length'
            - Note: With 'travel_time', a query without `metric` finds the fastest path: `length` is its kilometers and `metric_totals["travel_time"]` its seconds. `metric="length"` finds the shortest path on the same geograph
        - `off_graph_travel_speed`
            - Type: int | float | None
            - What: The travel speed (km/h) to assume for off-graph travel in the metric `travel_time`
            - Default: None
            - Options:
                - If a number, the weight of 1 km off the graph is 3600 / speed seconds in the metric `travel_time` (`off_graph_weight_per_km`)
                - If None, the weight of 1 km off the graph is 240 seconds: 15 km/h
            - Note: The speed does not change the lengths: an off-graph leg counts its kilometers in `length`
        - `load_intermediate_nodes`
            - Type: bool
            - What: Whether to load the intermediate nodes for each edge (if they exist)
            - Default: True
            - Note: The shape kept for an edge is the points of its geometry between its two nodes, from origin to destination (a geometry listed from destination to origin is reversed, repeated end nodes are dropped); an edge without such points has no shape
        - `silent`
            - Deprecated and without effect. scgraph reports its messages through `logging`.
        - `reduce_iterations`
            - Type: int
            - What: Number of reduction iterations to perform upon loading. If 0, no reduction is done. If -1, reduces iteratively until convergence.
            - Default: 0
        - `lazy`
            - Type: bool
            - What: Whether to delay loading the geograph until its first use
            - Default: False

        """
        from scgraph.geograph import GeoGraph, LazyGeoGraph

        warn_deprecated_parameter("silent", silent)
        if weight_key not in ("length", "travel_time"):
            raise ValueError(
                f"weight_key must be 'length' or 'travel_time': got {weight_key!r}"
            )
        if lazy:
            return LazyGeoGraph(
                lambda: GeoGraph.load_from_osmnx_graph(
                    osmnx_graph=osmnx_graph,
                    coord_precision=coord_precision,
                    weight_precision=weight_precision,
                    weight_key=weight_key,
                    off_graph_travel_speed=off_graph_travel_speed,
                    load_intermediate_nodes=load_intermediate_nodes,
                    reduce_iterations=reduce_iterations,
                    lazy=False,
                )
            )
        located = {
            node: [
                round(data["y"], coord_precision),
                round(data["x"], coord_precision),
            ]
            for node, data in osmnx_graph.nodes(data=True)
        }
        # In Hilbert order: nodes close on the globe get close ids
        node_list = list(osmnx_graph.nodes)
        node_list = [
            node_list[i]
            for i in get_hilbert_order([located[node] for node in node_list])
        ]
        node_to_idx = {node: i for i, node in enumerate(node_list)}

        graph = [dict() for _ in range(len(node_list))]
        if load_intermediate_nodes:
            intermediate_nodes = [dict() for _ in range(len(node_list))]
        # OSMnx gives a length in meters and a travel time in seconds
        weight_divisor = 1000 if weight_key == "length" else 1
        # The weight of the kept edge from a node to another, and its attributes
        kept_weights = [dict() for _ in range(len(node_list))]
        kept_attributes = [dict() for _ in range(len(node_list))]
        for u, v, data in osmnx_graph.edges(data=True):
            i = node_to_idx[u]
            j = node_to_idx[v]
            weight = round(
                float(data.get(weight_key)) / weight_divisor, weight_precision
            )
            # Keep only the parallel edge with the smallest weight, with its own
            # length and its own geometry
            if weight >= kept_weights[i].get(j, float("inf")):
                continue
            kept_weights[i][j] = weight
            graph[i][j] = round(
                float(data.get("length")) / 1000, weight_precision
            )
            kept_attributes[i][j] = data
            if load_intermediate_nodes and "geometry" in data:
                intermediate_nodes[i][j] = [
                    [
                        round(lon_lat[1], coord_precision),
                        round(lon_lat[0], coord_precision),
                    ]
                    for lon_lat in data["geometry"].coords
                ]
            elif load_intermediate_nodes:
                intermediate_nodes[i].pop(j, None)

        nodes = [located[node] for node in node_list]
        # OSMnx identifies its nodes by their OSM ids (integers, numpy's included)
        try:
            kwargs = {"external_node_ids": array("q", node_list)}
        except (TypeError, OverflowError):
            kwargs = {}
        if load_intermediate_nodes:
            # An edge's geometry should run from its first node to its second
            _keep_interior_points(intermediate_nodes, nodes)
            kwargs["intermediate_nodes"] = intermediate_nodes
        # The name of the class of each edge that has a `highway` value, by its
        # two nodes. OSMnx gives a list to an edge that it made from ways of
        # several values.
        edge_class_names = [
            {
                destination_id: (
                    highway[0] if isinstance(highway, list) else highway
                )
                for destination_id, data in attributes_of_origin.items()
                if (highway := data.get("highway")) is not None
            }
            for attributes_of_origin in kept_attributes
        ]
        class_names = sorted(
            set().union(*(names.values() for names in edge_class_names))
        )
        if class_names:
            kwargs["classes"] = [
                {"name": name, "edge_mode": "road"} for name in class_names
            ]
            kwargs["edge_classes"] = edge_class_names
        # The graph is built first: the ids of its edges give the order of the
        # weights of a metric. The attributes of each edge, by edge id:
        graph_object = Graph(graph)
        edge_arrays = graph_object._get_edge_arrays()
        node_first_edge_ids, edge_destination_node_ids, _ = edge_arrays
        edge_attributes = [
            attributes_of_origin[edge_destination_node_ids[edge_id]]
            for origin_id, attributes_of_origin in enumerate(kept_attributes)
            for edge_id in range(
                node_first_edge_ids[origin_id],
                node_first_edge_ids[origin_id + 1],
            )
        ]
        if all("travel_time" in data for data in edge_attributes):
            travel_time = Metric(
                "travel_time",
                "s",
                "Attribute travel_time of the OSMnx graph.",
                array(
                    "d",
                    (
                        round(float(data["travel_time"]), weight_precision)
                        for data in edge_attributes
                    ),
                ),
                (
                    240.0
                    if off_graph_travel_speed is None
                    else 3600 / off_graph_travel_speed
                ),
            )
            check_weights(
                "travel_time",
                travel_time.weights,
                node_first_edge_ids,
                edge_destination_node_ids,
            )
            kwargs["metrics"] = {"travel_time": travel_time}
        geograph = GeoGraph._build_from_edge_arrays(
            edge_arrays,
            graph=graph_object,
            nodes=nodes,
            coordinate_dtype="int32" if coord_precision <= 7 else "float64",
            **kwargs,
        )
        # The list of dicts itself, as for a geograph built from a list
        geograph.graph = graph
        geograph.default_metric = weight_key
        geograph.reduce(reduce_iterations)
        return geograph

    # Misc IO Methods
    @staticmethod
    def get_multi_path_geojson(
        routes: list[dict],
        filename: str | os.PathLike | None = None,
        show_progress: bool | None = None,
        get_intermediate_nodes: bool = True,
    ) -> dict:
        """
        Creates a GeoJSON file with the shortest path between the origin and destination of each route.

        Required Parameters:

        - `routes`: list[dict]
            - List of dictionaries with the following keys:
                - geograph: GeoGraph
                    - Geograph object to use for the shortest path calculation.
                - origin: dict[float|float]
                    - Origin coordinates
                    - EG: {"latitude":39.2904, "longitude":-76.6122}
                - destination: dict[float|int]
                    - Destination coordinates
                    - EG: {"latitude":39.2904, "longitude":-76.6122}
                - properties: dict
                    - Dictionary with the properties of the route
                    - Everything in this dictionary will be included in the output GeoJSON file as properties of the route.
                    - EG: {"id":"route_1", "name":"Route 1", "color":"#ff0000"}

        Optional Parameters:

        - `filename`: str | None
            - Name of the output GeoJSON file.
            - If None, the function will not save the file
            - Default: None
        - `show_progress`
            - Deprecated and without effect. The progress is logged at INFO, once for each tenth of the routes.
        - `get_intermediate_nodes`: bool
            - Whether to include intermediate nodes in the shortest path calculation
            - Default: True

        Returns

        - `output`: dict
            - Dictionary with the GeoJSON file content.
        """
        from scgraph.geograph import GeoGraph

        warn_deprecated_parameter("show_progress", show_progress)
        if not (isinstance(routes, list)):
            raise ValueError("Routes must be a list")
        if not (all([isinstance(i, dict) for i in routes])):
            raise ValueError("Routes must be a list of dictionaries")
        if not (all([isinstance(i.get("geograph"), GeoGraph) for i in routes])):
            raise ValueError(
                "All routes must have a 'geograph' key with a GeoGraph object"
            )
        if not (all([isinstance(i.get("origin"), dict) for i in routes])):
            raise ValueError(
                "All routes must have an 'origin' key with a dictionary"
            )
        if not (all([isinstance(i.get("destination"), dict) for i in routes])):
            raise ValueError(
                "All routes must have a 'destination' key with a dictionary"
            )
        if not (all([isinstance(i.get("properties"), dict) for i in routes])):
            raise ValueError(
                "All routes must have a 'properties' key with a dictionary"
            )
        if not (
            all(
                [
                    isinstance(i["origin"].get("latitude"), (int, float))
                    for i in routes
                ]
            )
        ):
            raise ValueError(
                "All origins must have a 'latitude' key with a number"
            )
        if not (
            all(
                [
                    isinstance(i["origin"].get("longitude"), (int, float))
                    for i in routes
                ]
            )
        ):
            raise ValueError(
                "All origins must have a 'longitude' key with a number"
            )
        if not (
            all(
                [
                    isinstance(i["destination"].get("latitude"), (int, float))
                    for i in routes
                ]
            )
        ):
            raise ValueError(
                "All destinations must have a 'latitude' key with a number"
            )
        if not (
            all(
                [
                    isinstance(i["destination"].get("longitude"), (int, float))
                    for i in routes
                ]
            )
        ):
            raise ValueError(
                "All destinations must have a 'longitude' key with a number"
            )
        if not (
            all(
                [
                    (
                        i["origin"].get("latitude") >= -90
                        and i["origin"].get("latitude") <= 90
                    )
                    for i in routes
                ]
            )
        ):
            raise ValueError("All origin latitudes must be between -90 and 90")
        if not (
            all(
                [
                    (
                        i["origin"].get("longitude") >= -180
                        and i["origin"].get("longitude") <= 180
                    )
                    for i in routes
                ]
            )
        ):
            raise ValueError(
                "All origin longitudes must be between -180 and 180"
            )
        if not (
            all(
                [
                    (
                        i["destination"].get("latitude") >= -90
                        and i["destination"].get("latitude") <= 90
                    )
                    for i in routes
                ]
            )
        ):
            raise ValueError(
                "All destination latitudes must be between -90 and 90"
            )
        if not (
            all(
                [
                    (
                        i["destination"].get("longitude") >= -180
                        and i["destination"].get("longitude") <= 180
                    )
                    for i in routes
                ]
            )
        ):
            raise ValueError(
                "All destination longitudes must be between -180 and 180"
            )

        output = {"type": "FeatureCollection", "features": []}
        len_routes = len(routes)
        for idx, route in enumerate(routes):
            shortest_path = route["geograph"].get_shortest_path(
                origin_node=route["origin"],
                destination_node=route["destination"],
                get_intermediate_nodes=True,
            )
            shortest_line_path = get_line_path(shortest_path)
            output["features"].append(
                {
                    "type": "Feature",
                    "properties": route["properties"],
                    "geometry": shortest_line_path,
                }
            )
            # One message each time another tenth of the routes is done
            if (idx + 1) * 10 // len_routes > idx * 10 // len_routes:
                logger.info("Routed %d of %d routes", idx + 1, len_routes)
        if filename is not None:
            json.dump(output, open(filename, "w"))
        return output


def _reorder_edge_values(
    edge_values: array | memoryview,
    node_first_edge_ids: array | memoryview,
    order: list[int],
) -> array:
    """Return the values of the edges in the order of a graph with reordered nodes.

    Args:
        edge_values: An array by edge id: one value for each edge, at its id.
        node_first_edge_ids: The id of the first edge of each node, before the new order.
        order: The nodes in their new order: `order[new id] = id`. A node keeps the
            order of its edges, as `Graph._get_edge_arrays(order)` does.
    """
    edge_values = memoryview(edge_values)
    reordered_edge_values = array(edge_values.format)
    for origin_id in order:
        first, last = (
            node_first_edge_ids[origin_id],
            node_first_edge_ids[origin_id + 1],
        )
        reordered_edge_values.frombytes(edge_values[first:last].cast("B"))
    return reordered_edge_values


def _keep_interior_points(shapes, nodes):
    # Edge shapes hold the points between the edge's two nodes, from origin to destination:
    # reverse a shape that runs from the destination to the origin, remove the points
    # equal to the origin at its start and to the destination at its end, and the edges
    # left without points, as a network file has none (edits the shapes in place)
    for origin, row in enumerate(shapes):
        start = nodes[origin]
        for destination, shape in list(row.items()):
            end = nodes[destination]
            if shape and shape[0] == end and shape[-1] == start != end:
                shape.reverse()
            while shape and shape[-1] == end:
                del shape[-1]
            first = 0
            while first < len(shape) and shape[first] == start:
                first += 1
            del shape[:first]
            if not shape:
                del row[destination]


def renumber_in_hilbert_order(geograph):
    """Copy a geograph with its nodes in Hilbert order within each node mode."""
    # The ids change, the lengths do not (where two routes tie, another may be
    # returned). Each caller orders a geograph that it just read from a list of
    # edges, and drops it. So the copy takes no class and no metric, and it shares the `metadata` dict.
    from scgraph.geograph import GeoGraph

    if (
        geograph.classes
        or geograph._metrics
        or geograph.default_metric != "length"
    ):
        raise ValueError(
            "The Hilbert order of the nodes drops the classes and the "
            "metrics: it takes a geograph without them"
        )
    multimodal = len(geograph.node_modes) > 1
    order = get_hilbert_order(
        geograph.nodes, geograph.node_mode_ids if multimodal else None
    )
    # Each node keeps its id (its position before ordering, if it had none)
    external_node_ids = geograph.external_node_ids.take(order)
    new_id = [0] * len(order)
    for new, old in enumerate(order):
        new_id[old] = new
    # Not a choice of kernel: the test chooses a layout of the data.
    if Graph.__module__ == "scgraph.cpp":
        # Renumbered as arrays (read as dicts, the C++ graph would be copied whole), which
        # the new graph keeps instead of copying them again
        graph = Graph.from_edge_arrays(
            *geograph.graph_object._get_edge_arrays(order), copy=False
        )
    else:
        # Renumbered dicts, sharing the graph's weight objects (from_edge_arrays would not)
        rows = geograph.graph_object.unreduced_graph
        graph = [
            {
                new_id[destination_id]: weight
                for destination_id, weight in rows[old].items()
            }
            for old in order
        ]
    shapes = geograph.intermediate_nodes
    renumbered = GeoGraph(
        graph=graph,
        nodes=[geograph.nodes[old] for old in order],
        intermediate_nodes=(
            None
            if shapes is None
            else [
                (
                    {
                        new_id[destination_id]: shape
                        for destination_id, shape in shapes[old].items()
                    }
                    if old < len(shapes)
                    else {}
                )
                for old in order
            ]
        ),
        default_off_graph_circuity=geograph.default_off_graph_circuity,
        default_node_addition_circuity=geograph.default_node_addition_circuity,
        geograph_units=geograph.geograph_units,
        external_node_ids=(
            None
            if external_node_ids == array("q", range(len(order)))
            else external_node_ids
        ),
        node_mode_ids=[geograph.node_mode_ids[old] for old in order],
        node_modes=geograph.node_modes,
        coordinate_dtype=geograph.coordinate_dtype,
    )
    renumbered.metadata = geograph.metadata
    return renumbered
