"""Geographic graphs: a `Graph` whose nodes have a latitude and a longitude.

- `GeoGraphIO` loads and saves networks (GeoJSON, graphjson, `.scgraph` files,
  OpenStreetMap, OSMnx), and loads or builds the networks of scgraph.
- `GeoGraphModifiers` adds and removes nodes and edges, by id or by coordinates.
- `GeoGraphUtils` connects a point to nearby nodes and builds the coordinates of a path.
- `GeoGraphDistanceCalculations` gives the haversine and cheap-ruler distances.
- `GeoGraph` joins these classes and answers `get_shortest_path` between two points.
- `LazyGeoGraph` stands for a `GeoGraph` and loads it at its first use.

Users reach this module through `scgraph.GeoGraph`. `scgraph/network_cache.py` downloads
the released networks, and `scgraph/built_in_geographs.py` holds the seven networks
of scgraph 3.6.0.
"""

from scgraph.utils import (
    haversine,
    distance_converter,
    get_line_path,
    cheap_ruler,
    get_lat_lon_bound_between_pts,
    get_units_per_km,
    resolve_cache_dir,
    earth_radius,
    radians_per_degree,
)
from scgraph._internal import warn_deprecated_parameter, log_step
from scgraph.helpers.geojson import parse_geojson, simplify_geojson
from scgraph.helpers.polylines import build_graph_from_polylines
from scgraph.helpers.hilbert import hilbert_order
from scgraph.edge_classes import EdgeClasses, find_edge_id
from scgraph.metrics import (
    Metric,
    parse_off_graph_weight_per_km,
    compute_weights_from_sum,
    compute_weights_from_function,
    build_default_description,
    resolve_weights_per_km,
    copy_with_edge_weights,
)
from scgraph import built_in_geographs, network_cache, network_file
from scgraph import network_release as pinned_network_release
import hashlib
import json
import logging
import warnings
import os
import re
import types
from array import array
from collections import Counter
from itertools import chain, zip_longest
from math import inf, isfinite
from operator import eq
from copy import deepcopy
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from collections.abc import Callable, Iterable, Iterator, Sequence
from scgraph import Graph, PathNotFoundError

try:
    from scgraph.cpp import (
        NodeOrderError,
        SnapIndex,
        compute_weights_from_km,
    )
except ImportError:
    from scgraph.helpers.metric_weights import compute_weights_from_km
    from scgraph.helpers.snap_index import NodeOrderError, SnapIndex

if (
    TYPE_CHECKING
):  # Only for annotations. A function that needs one of these modules imports it.
    import networkx
    from geokdtree import GeoKDTree

logger = logging.getLogger(__name__)


class GeoGraphIO:
    def __get_edge_coordinates__(
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
                self.__get_intermediate_nodes__(
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
                        self.__get_edge_coordinates__(
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
                                "coordinates": self.__get_edge_coordinates__(
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
        - Only the graph, the nodes, their ids and node modes, their intermediate nodes, the classes of the edges, the metrics with their weights, `default_metric`, `default_node_addition_modes` and the GeoGraph defaults are saved
        - The nodes are written in Hilbert order within each node mode (nodes close on the globe get close ids); the geograph itself is not renumbered, and each node keeps its id in `source_node_ids`
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
        - `coordinate_dtype`
            - Type: str
            - What: How coordinates are stored: 'float64' exactly, 'int32' rounded to 1e-7 degree (OSM's encoding, about 1 cm; 8 bytes less per node), 'auto' as the geograph's `coordinate_dtype`
            - Default: 'auto'

        Returns:

        - The `content_sha256` of the file: the SHA-256 of every byte after its first 40, also stored in its bytes 8 to 39
        """
        filename = os.fspath(filename)
        if not filename.endswith(".scgraph"):
            raise ValueError("Filename must end with .scgraph")
        if coordinate_dtype not in ("auto", "float64", "int32"):
            raise ValueError(
                "coordinate_dtype must be 'auto', 'float64' or 'int32'"
            )
        # The class id and the weights of each edge, in arrays "by edge id": one
        # value for each edge, at the id of the edge. A geograph without classes
        # and without metrics does not read the arrays of its edges here.
        classes, edge_value_arrays = None, {}
        if self.classes or self._metrics:
            geograph_offsets = self._read_edge_arrays()[0]
            edge_class_ids = self._read_edge_class_ids()
            if edge_class_ids is not None:
                classes = self.classes
                edge_value_arrays["edge_class_ids"] = edge_class_ids
            for name, metric_record in self._metrics.items():
                edge_value_arrays[f"weights_{name}"] = metric_record.weights
        metadata = network_file.build_header_metadata(
            self.metadata if metadata == "auto" else metadata or {},
            node_modes=self.node_modes,
            metrics=self.metrics,
            classes=classes,
            node_addition_modes=self.default_node_addition_modes,
            default_metric=self.default_metric,
        )
        # A cached network must stay the one its cache.json names
        built = resolve_cache_dir().joinpath("networks").resolve()
        if Path(filename).resolve().is_relative_to(built):
            raise ValueError(
                f"{filename} is in scgraph's cache ({built}); save it elsewhere"
            )
        # Written in Hilbert order within each node mode (nodes close on the globe get
        # close ids, and the nodes of a node mode stay together); the geograph is not
        # renumbered
        nodes, node_mode_ids = self.nodes, self.node_mode_ids
        # Nodes appended to `nodes` directly are in the first node mode
        node_mode_ids.extend(bytes(len(nodes) - len(node_mode_ids)))
        # (by node mode only if there are several: the key is cheaper without)
        multimodal = len(self.node_modes) > 1
        try:
            order = hilbert_order(nodes, node_mode_ids if multimodal else None)
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
        offsets, heads, weights = self.graph_object._csr(order)
        if order is not None and edge_value_arrays:
            edge_value_arrays = {
                name: _reorder_edge_values(edge_values, geograph_offsets, order)
                for name, edge_values in edge_value_arrays.items()
            }
        arrays = {
            "offsets": offsets,
            "heads": heads,
            "weights_length": weights,
            **edge_value_arrays,
        }
        node_points = array("d", (value for i in old for value in nodes[i][:2]))
        # None: each node's id is its position
        source_node_ids = self.source_node_ids.array(order)
        if source_node_ids is not None:
            arrays["source_node_ids"] = source_node_ids
        if multimodal:
            arrays["node_mode_ids"] = array(
                "B", (node_mode_ids[i] for i in old)
            )
        shapes = self.intermediate_nodes if save_intermediate_nodes else None
        if shapes is not None:
            starts, points = array("i", [0]), array("d")
            for new, origin in enumerate(old):
                # Nodes added after loading (add_coord_node, merges) have no shapes
                row = shapes[origin] if origin < len(shapes) else {}
                for edge in range(offsets[new], offsets[new + 1]):
                    head = old[heads[edge]]
                    for latitude, longitude in row.get(head, ()):
                        if not (isfinite(latitude) and isfinite(longitude)):
                            raise ValueError(
                                f"The shape of edge {origin} -> {head} has a point "
                                "that is not a finite number"
                            )
                        points.append(latitude)
                        points.append(longitude)
                    starts.append(len(points) // 2)
            arrays["shape_offsets"] = starts
        point_arrays = [node_points] + ([points] if shapes is not None else [])
        if coordinate_dtype == "auto":
            coordinate_dtype = self.coordinate_dtype
        arrays.update(
            zip(
                network_file.POINT_ARRAYS,
                network_file.encode_coordinates(point_arrays, coordinate_dtype),
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
            - Numbers the nodes along a Hilbert curve (nodes close on the globe get close ids); without `max_km_between_nodes`, `source_node_ids[i]` is node i's id before this ordering (the numbering of earlier versions)
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
            - Default: 4
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
        geograph = _order_by_hilbert(
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
        max_km_between_nodes: float | None = None,
        largest_component: bool = True,
        load_intermediate_nodes: bool = True,
        reduce_iterations: int = 0,
        lazy: bool = False,
    ) -> "GeoGraph":
        """
        Function:

        - Load a GeoGraph from an OpenStreetMap file (`.osm.pbf`, `.osm` or `.osm.bz2`)
        - Needs the optional dependency `osmium`: `pip install scgraph[osm]`
        - Ways meet only where they share an OSM node: roads that cross on a bridge or in a tunnel are not connected
        - Each edge has the length of its piece of way, in kilometers, so it is never shorter than the straight line between its ends
        - Nodes are the OSM nodes where kept ways meet or end; a way is also cut at the first point where the edge since the previous node reaches `max_km_between_nodes`
        - Nodes are numbered along a Hilbert curve (nodes close on the globe get close ids), and `source_node_ids[i]` is node i's OSM id
        - With the default `select`, ways tagged `oneway=yes` or `-1`, motorways and roundabouts are one way
        - Each edge has the class that `select` gives to its way: `classes` holds the classes of `scgraph.pipelines.CLASSES`, and `get_edges` gives the class of each edge. With the default `select`, the class of a way is its `highway` value
        - Not the graph of the `geofabrik_multimodal` pipeline from the same file: this loader reads one mode, and neither attaches ferries, nor contracts chains, nor simplifies shapes
        - Memory: osmium's node and way filters take about 1.7 GB, whatever the size of the file

        Required Arguments:

        - `filename`
            - Type: str | os.PathLike | source object
            - What: The path of the OpenStreetMap file, for example an extract downloaded from https://download.geofabrik.de, or a source object as `scgraph.pipelines.steps.step1_osm_ways.locate_ways` takes

        Optional Arguments:

        - `select`
            - Type: Callable (tags -> int | tuple[int, str] | None), the tags of a way read as `tags.get(key)` or `key in tags`
            - What: Gives, from the tags of a way, its direction: 1 (one way, along its drawing), -1 (one way, against it), 0 (both ways), or None to leave the way out. In place of the direction, it may give a pair: the direction and the class of the way, a name of `scgraph.pipelines.CLASSES`
            - Default: None: `scgraph.helpers.osm.select_main_roads_with_class` (motorway to primary and their links, each with its `highway` value as its class, one way where `scgraph.helpers.osm.get_way_direction(tags)` returns 1 or -1)
            - Note: When `select` gives a direction alone for every way, the geograph has no classes. An edge of a way without a class has no class
            - Example: `lambda tags: 0 if tags.get("railway") == "rail" and tags.get("service") in (None, "crossover") else None` for railway lines without yards, sidings and spurs, both ways (a crossover joins the two tracks of a double line)
            - Note: Called for each way in two passes over the file: it must give the same answer each time
        - `tag_keys`
            - Type: tuple[str, ...]
            - What: Tag keys of which a way must have at least one to reach `select`; osmium leaves out the other ways before Python sees them, which is faster. Empty: every way reaches `select`
            - Default: ("highway",)
            - Note: Give the tag keys that `select` keeps ways by, for example `("railway",)` for railway lines
        - `max_km_between_nodes`
            - Type: float | int | None
            - What: Length in kilometers at which a way is cut into a new edge (at the next point of the way), so that origins and destinations can attach close to where they are
            - Default: None: `scgraph.helpers.osm.MAX_KM_BETWEEN_NODES` (2)
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

        Raises:

        - `ImportError` if the optional dependency `osmium` is not installed
        - `ValueError` if no way of the file has one of `tag_keys` and is kept by `select`, or if `select` returns anything else than 1, -1, 0, a pair of one of them and a name of `scgraph.pipelines.CLASSES`, or None (`True` and `False` included)
        """
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
                )
            )
        from scgraph.helpers.components import (
            keep_largest_strongly_connected_component,
        )
        from scgraph.helpers.osm import (
            MAX_KM_BETWEEN_NODES,
            read_osm,
            select_main_roads_with_class,
        )
        from scgraph.pipelines import CLASSES

        graph, nodes, shapes, ids, edge_class_names = read_osm(
            filename,
            select or select_main_roads_with_class,
            tag_keys,
            (
                MAX_KM_BETWEEN_NODES
                if max_km_between_nodes is None
                else max_km_between_nodes
            ),
            CLASSES,
        )
        if not nodes:
            raise ValueError(
                f"No way of {filename} has one of the tag keys {tag_keys} and is kept by select"
            )
        if largest_component:
            graph, nodes, shapes, ids, edge_class_names = (
                keep_largest_strongly_connected_component(
                    graph, nodes, shapes, ids, edge_class_names
                )
            )
        class_arguments = {}
        if any(edge_class_names):
            # The geograph gets every class of `CLASSES`, as a file of a pipeline.
            class_arguments = {
                "classes": [
                    {"name": name, "edge_mode": edge_mode}
                    for name, edge_mode in CLASSES.items()
                ],
                "edge_classes": edge_class_names,
            }
        geograph = GeoGraph(
            graph=graph,
            nodes=nodes,
            intermediate_nodes=shapes if load_intermediate_nodes else None,
            source_node_ids=ids,
            coordinate_dtype="int32",  # OSM's own: 1e-7 degree
            **class_arguments,
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

        - A dict: the metadata of the file (`metrics`, `sources`, `node_modes`, `classes`, `node_addition_modes`, `pipeline`, ...), `content_sha256`, `format_version`, the number of `nodes` and `edges`, `coordinate_dtype`, and whether the file has `shapes` and `source_node_ids`
        - With `sources`, also `attribution`, the credit line to cite with results ("credit (license); ..."), and `data_up_to`, the newest `version` of a source that is a date (None if no source has one)
        """
        info = network_file.get_scgraph_info(filename)
        if "sources" in info:
            sources = info["sources"]
            credits = dict.fromkeys(
                f"{s['credit']} ({s.get('license', 'NOASSERTION')})"
                for s in sources
                if "credit" in s
            )
            if credits:
                info["attribution"] = "; ".join(credits)
            # ISO 8601 times in UTC (as Geofabrik gives them) sort as text
            dates = [
                s["version"] for s in sources if _is_date(s.get("version"))
            ]
            info["data_up_to"] = max(dates, default=None)
        return info

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
        - `source_node_ids` reads the file's node ids, if it has them (otherwise each node's id is its position); `node_mode_ids` and `node_modes` give the node mode of each node
        - `classes` holds the classes of the file, if it has them, and `get_edges` gives the class of each edge; `default_node_addition_modes` holds the `node_addition_modes` of the file: the node modes that the points of a query snap to by default (see `get_shortest_path`)
        - `metrics` holds the metrics of the file, with their weights. An edit of the network removes them, as every metric other than `length` (see `add_edge`). `default_metric` holds the `default_metric` of the file: the metric that a call without `metric` uses
        - `metadata` holds what the file says about how the network was built (`sources`, `pipeline`, ...), which `save_as_scgraph` writes back by default
        - `scgraph_file` is the path of the file that was read: `GeoGraph.get_scgraph_info(geograph.scgraph_file)` gives its `content_sha256` and the credit line to cite (`attribution`). A later change of the geograph, such as a merge, does not change `scgraph_file`.
        - The snapping index (`snap_index`) is built while loading, so that the first query is as fast as the next ones. On a file with `node_addition_modes`, the first query also builds the index of the nodes of these node modes

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
        mapped = Graph.__module__ == "scgraph.cpp"
        with log_step(
            logger,
            "read the network file",
            {"file": filename, "mapped": mapped},
        ) as indicators:
            arrays, metadata = network_file.read(filename, mapped, node_modes)
            indicators["nodes"] = len(arrays["node_points"]) // 2
            indicators["edges"] = len(arrays["heads"])
        edge_arrays = (
            arrays["offsets"],
            arrays["heads"],
            arrays["weights_length"],
        )
        try:
            graph = Graph.from_csr(*edge_arrays, copy=False)
        except ValueError as error:
            raise ValueError(f"{filename}: {error}") from error
        geograph = GeoGraph(
            graph=graph,
            nodes=network_file.NodePoints(arrays["node_points"]),
            intermediate_nodes=(
                network_file.EdgeShapes(arrays)
                if "shape_offsets" in arrays
                else None
            ),
            geograph_units=metadata["metrics"][0]["unit"],
            source_node_ids=arrays.get("source_node_ids"),
            node_mode_ids=arrays.get("node_mode_ids"),
            node_modes=metadata.get("node_modes"),
            coordinate_dtype=network_file.get_coordinate_dtype(arrays),
        )
        geograph.metadata = {
            key: value
            for key, value in metadata.items()
            if key not in network_file.RESERVED_METADATA_KEYS
        }
        geograph.scgraph_file = filename
        # The arrays of the file are the edges of the new graph, in the same order
        geograph._set_edge_arrays(edge_arrays, arrays.get("edge_class_ids"))
        if "edge_class_ids" in arrays:
            geograph._edge_classes = EdgeClasses(
                metadata["classes"],
                arrays["offsets"],
                arrays["heads"],
                arrays["edge_class_ids"],
            )
        for row in metadata["metrics"][1:]:
            geograph._metrics[row["name"]] = Metric(
                row["name"],
                row.get("unit"),
                row.get("description"),
                arrays[f"weights_{row['name']}"],
                row["off_graph_weight_per_km"],
            )
        geograph.default_node_addition_modes = metadata.get(
            "node_addition_modes"
        )
        geograph.default_metric = metadata.get("default_metric", "length")
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
    def __fetch_geograph_to_cache__(
        name: str, cached_file: Path, geograph_url: str
    ) -> None:
        """
        Function:

        - Download a built-in GeoGraph file from GitHub into the cache directory.

        Required Arguments:

        - `name`
            - Type: str
            - What: The name of the built-in geograph to fetch
        - `cached_file`
            - Type: Path
            - What: The destination path in the cache to write the file to
        """
        built_in_geographs.fetch_built_in_geograph(
            name, cached_file, geograph_url
        )

    @staticmethod
    def load_geograph(
        name: str,
        cache_dir: str | os.PathLike | None = None,
        geograph_url: str = built_in_geographs.GEOGRAPH_URL,
        reduce_iterations: int = 0,
        lazy: bool = False,
        *,
        local_files_only: bool | None = None,
        network_release: str | None = None,
        content_sha256: str | None = None,
        node_modes: list[str] | str | None = None,
        load_intermediate_nodes: bool = True,
    ) -> "GeoGraph":
        """
        Function:

        - Load a built-in GeoGraph by name, using a local cache.
        - A network release is a set of networks that the maintainers of scgraph build from open sources and publish together under one tag. A network of a network release is a released network. The name of a released network, such as `europe`, `world_sea` or `world_multimodal`, loads that network. `list_geographs` gives every name, and `guides/networks.md` describes each network (section *Released Networks*).
        - For such a name, the first call downloads the network file, decompresses it, checks its content, then keeps it in the cache. Later calls read the cache without any network request. The arguments `network_release`, `content_sha256`, `node_modes` and `load_intermediate_nodes` apply to these networks only.
        - The points below apply to the seven networks of scgraph 3.6.0 (`marnet`, `us_freeway`, ...), which are published as `.graphjson` files.
        - On first call for a given name, downloads the .graphjson file from GitHub into the cache directory.
        - On subsequent calls, loads directly from cache without any network requests.
        - The first load converts the .graphjson into a network file beside it (`<name>.scgraph`, much faster to load), which later loads read; the .graphjson is kept, and a damaged conversion is made again from it.
        - The conversion orders the nodes along a Hilbert curve, so that nodes close on the globe get close ids: node ids differ from those of the .graphjson (lengths do not; of two routes of exactly equal length, another may be returned), and `source_node_ids[i]` is node i's id in the .graphjson (its id in scgraph 3.6.0). `load_from_graphjson` on the cached .graphjson keeps its numbering.
        - With `local_files_only=True` (or the environment variable `SCGRAPH_OFFLINE=1`), never downloads: a geograph that is not in the cache raises a FileNotFoundError.

        Required Arguments:

        - `name`
            - Type: str
            - What: The name of the built-in geograph to load
            - Examples: 'marnet', 'north_america_rail', 'oak_ridge_maritime', 'us_freeway'

        Optional Arguments:

        - `cache_dir`
            - Type: str | None
            - What: Path to the local cache directory where geograph files are stored
            - Default: None: the `SCGRAPH_CACHE_DIR` environment variable if set, else the platform's cache directory
                - Linux:   ~/.cache/scgraph/
                - macOS:   ~/Library/Caches/scgraph/
                - Windows: %LOCALAPPDATA%\\scgraph\\
        - `geograph_url`
            - Type: str
            - What: The base URL where the built-in geograph .graphjson files are hosted
            - Note: With another URL than the default, every name loads `<name>.graphjson` from that URL, also the name of a released network
            - Note: Deprecated. A call that passes another URL than the default gets a `DeprecationWarning`, and scgraph 5.0 removes the parameter. To load your own network, use `load_from_graphjson` or `load_from_scgraph`
        - `reduce_iterations`
            - Type: int
            - What: Number of reduction iterations to perform upon loading. If 0, no reduction is done. If -1, reduces iteratively until convergence.
            - Default: 0
        - `lazy`
            - Type: bool
            - What: Whether to delay loading/fetching the geograph until its first use
            - Default: False
        - `local_files_only`
            - Type: bool | None
            - What: Whether to use only the cache, without any network request
            - Default: None: True if the environment variable `SCGRAPH_OFFLINE` is `1`, else False
        - `network_release`
            - Type: str | None
            - What: The tag of the network release to load, for example 'networks-2026.11.20'
            - Default: None: the network release that this version of scgraph loads (`scgraph.network_release.TAG`)
        - `content_sha256`
            - Type: str | None
            - What: The `content_sha256` that the network file must have. It is the SHA-256 digest of the content of the file, and `get_scgraph_info` gives it. A file with another digest raises a ValueError. Pass it with `network_release` to load exactly the network of an earlier computation.
            - Default: None
        - `node_modes`
            - Type: list[str] | str | None
            - What: The names of the node modes to load, as in `load_from_scgraph`, for example `["road"]`
            - Default: None (every node mode)
        - `load_intermediate_nodes`
            - Type: bool
            - What: Whether to load the shapes of the edges. The shape of an edge is the list of points that draw it on a map between its two nodes. False downloads a file of about half the size. The route lengths are the same, and a `coordinate_path` then goes in a straight line from node to node.
            - Default: True

        Raises:

        - `ValueError` if the downloaded file is damaged, or if it is not the file that scgraph records for the network release that it loads by default. The file does not enter the cache.
        - `ValueError` if the file does not have the digest of `content_sha256`, or if `network_release` is not a tag
        - `ValueError` if `network_release`, `content_sha256`, `node_modes` or `load_intermediate_nodes` is passed for a network that is not loaded from a network release
        - `FileNotFoundError` if the network release does not have the file, or with `local_files_only` if the file is not in the cache
        - `ConnectionError` if the server refuses the download
        """
        # The warnings come from this call, also for a lazy load that reads the network
        # later.
        built_in_geographs.warn_deprecated_load(name, geograph_url)
        options = {
            "name": name,
            "cache_dir": cache_dir,
            "geograph_url": geograph_url,
            "reduce_iterations": reduce_iterations,
            "local_files_only": local_files_only,
            "network_release": network_release,
            "content_sha256": content_sha256,
            "node_modes": node_modes,
            "load_intermediate_nodes": load_intermediate_nodes,
        }
        if lazy:
            return LazyGeoGraph(lambda: GeoGraph._load_geograph(**options))
        return GeoGraph._load_geograph(**options)

    @staticmethod
    def _load_geograph(
        name: str,
        cache_dir: str | os.PathLike | None,
        geograph_url: str,
        reduce_iterations: int,
        local_files_only: bool | None,
        network_release: str | None,
        content_sha256: str | None,
        node_modes: list[str] | str | None,
        load_intermediate_nodes: bool,
    ) -> "GeoGraph":
        """Load the network of `load_geograph` now. The arguments are those of
        `load_geograph`, which gives the deprecation warnings."""
        if local_files_only is None:
            local_files_only = os.environ.get("SCGRAPH_OFFLINE") == "1"
        cache_path = resolve_cache_dir(cache_dir)
        # A caller that passes its own `geograph_url` hosts `.graphjson` files, and
        # one of them may have the name of a released network. That name then loads
        # the file of the caller.
        if (
            name in network_cache.RELEASED_GEOGRAPHS
            and geograph_url == built_in_geographs.GEOGRAPH_URL
        ):
            released_file = network_cache.fetch_released_file(
                name=name,
                tag=network_release,
                shapes=load_intermediate_nodes,
                content_sha256=content_sha256,
                cache_path=cache_path,
                local_files_only=local_files_only,
            )
            return GeoGraph.load_from_scgraph(
                str(released_file),
                reduce_iterations=reduce_iterations,
                node_modes=node_modes,
            )
        if (
            network_release,
            content_sha256,
            node_modes,
            load_intermediate_nodes,
        ) != (
            None,
            None,
            None,
            True,
        ):
            raise ValueError(
                f"'{name}' is not loaded from a network release: its name is not in "
                "the network release that this scgraph loads "
                f"({pinned_network_release.TAG}), or `geograph_url` is given. "
                "`network_release`, `content_sha256`, `node_modes` and "
                "`load_intermediate_nodes` do not apply to it"
            )
        cache_path.mkdir(parents=True, exist_ok=True)
        cached_file = cache_path.joinpath(f"{name}.graphjson")
        # Converted once into a network file beside it, which every later load reads
        converted = cache_path.joinpath(f"{name}.scgraph")
        if converted.exists():
            try:
                return GeoGraph.load_from_scgraph(
                    str(converted),
                    reduce_iterations=reduce_iterations,
                    lazy=False,
                )
            except ValueError:  # damaged, or another format: converted again
                pass
        if not cached_file.exists():
            if local_files_only:
                raise FileNotFoundError(
                    f"Geograph '{name}' is not in the cache ({cache_path}) and "
                    "local_files_only=True (or SCGRAPH_OFFLINE=1) forbids downloading it"
                )
            GeoGraph.__fetch_geograph_to_cache__(
                name, cached_file, geograph_url
            )
        # Written in Hilbert order (nodes close on the globe get close ids): node ids
        # differ from the .graphjson's, which the nodes keep as their source_node_ids
        geograph = GeoGraph.load_from_graphjson(str(cached_file))
        geograph.node_modes = [{"name": None, "source": cached_file.name}]
        # To 1e-7 degree, as OSM: the file's compact encoding (a few published ports
        # have 9 decimals, from arcseconds)
        geograph.coordinate_dtype = "int32"
        for node in geograph.nodes:
            node[:] = round(node[0], 7), round(node[1], 7)
        with open(cached_file, "rb") as file:
            sha256 = hashlib.file_digest(file, "sha256").hexdigest()
        source = {
            "name": cached_file.name,
            "url": f"{geograph_url}/{cached_file.name}",
            "sha256": sha256,
        }
        try:
            geograph.metadata = {"sources": [source]}
            with log_step(
                logger, "convert the published network", {"name": name}
            ):
                geograph.save_as_scgraph(str(converted))
        except OSError:
            # A cache that can't be written: the .graphjson is read at every load, its
            # nodes ordered as the file would have them
            geograph = _order_by_hilbert(geograph)
            geograph.reduce(reduce_iterations)
            if len(geograph.nodes):  # as load_from_scgraph
                geograph.snap_index  # noqa: B018 (reading it builds the index)
            return geograph
        del geograph  # one copy of the network in memory at a time
        return GeoGraph.load_from_scgraph(
            str(converted), reduce_iterations=reduce_iterations, lazy=False
        )

    @staticmethod
    def list_geographs(
        cache_dir: str | os.PathLike | None = None,
        geograph_url: str = built_in_geographs.GEOGRAPH_URL,
    ) -> list[dict]:
        """
        Function:

        - List the networks that `load_geograph` takes, indicating which are already cached locally.
        - The published geographs are a fixed list, listed without any network request; for another `geograph_url`, the names are read from the `contents.txt` file at that URL.
        - The list holds the seven networks of scgraph 3.6.0 and the networks of the network release that this version of scgraph loads (`scgraph.network_release.TAG`).

        Optional Arguments:

        - `cache_dir`
            - Type: str | None
            - What: Path to the local cache directory to check for cached files
            - Default: None: the `SCGRAPH_CACHE_DIR` environment variable if set, else the platform's cache directory
                - Linux:   ~/.cache/scgraph/
                - macOS:   ~/Library/Caches/scgraph/
                - Windows: %LOCALAPPDATA%\\scgraph\\
        - `geograph_url`
            - Type: str
            - What: The base URL where the geograph files and contents.txt are hosted
            - Default: https://raw.githubusercontent.com/connor-makowski/scgraph/main/geographs

        Returns:

        - A list of dicts, one per available geograph, sorted by name:
            - `name`: str — the geograph name (without extension)
            - `cached`: bool — whether the file is already in the local cache (for a released network: its file of that release, with or without shapes)
            - With the default `geograph_url`, also:
                - `kind`: str — `"released"` for a network of the network release, `"built-in"` for a network of scgraph 3.6.0
                - `description`: str — what the network holds
                - for `"released"`: `nodes`, `edges`, `download_mb` and `download_mb_without_shapes` (the size of the two downloads), and `data_up_to` (the time of the newest source data, or None when no source gives a time)
                - for `"built-in"`: `superseded_by`, the name of the released network that covers the same need with newer data; that network may hold more node modes (load it with `node_modes`), and its results differ
        """
        built_in_geographs.warn_deprecated_url(geograph_url)
        return network_cache.list_networks(
            cache_dir=cache_dir, geograph_url=geograph_url
        )

    @staticmethod
    def clear_geograph_cache(
        cache_dir: str | os.PathLike | None = None,
        *,
        name: str | None = None,
        region: str | None = None,
    ) -> None:
        """
        Function:

        - Remove what scgraph keeps in the local cache directory: the built-in geographs `load_geograph` downloaded (and their `.scgraph` conversions), the network files it downloaded from network releases (under `releases/`) and the networks `build_geograph` built (under `networks/`)
        - With `name` (and `region`), remove only that network: its built-in geograph, its files of every network release, and its built networks (of every region, or of `region` only)
        - Other files in the directory are kept; the directory itself is removed if nothing else is left in it
        - On Windows, the files of a network still loaded in this process can't be removed: they are left in place, with a logging warning that names them, until a later clear

        Optional Arguments:

        - `cache_dir`
            - Type: str | None
            - What: Path to the local cache directory to clear
            - Default: None: the `SCGRAPH_CACHE_DIR` environment variable if set, else the platform's cache directory
                - Linux:   ~/.cache/scgraph/
                - macOS:   ~/Library/Caches/scgraph/
                - Windows: %LOCALAPPDATA%\\scgraph\\
        - `name`
            - Type: str | None
            - What: The network to remove, by the name `load_geograph` or `build_geograph` take (not a pipeline module of one's own)
            - Default: None: every network
        - `region`
            - Type: str | None
            - What: With `name`, the region of the built network to remove (its sub-regions are kept)
            - Default: None: every region
        """
        return network_cache.clear_cache(
            cache_dir=cache_dir, name=name, region=region
        )

    @staticmethod
    def get_cache_info(
        cache_dir: str | os.PathLike | None = None,
    ) -> list[dict]:
        """
        Function:

        - List what scgraph keeps in the local cache directory, read from disk only, without any network request
        - Unlike `list_geographs` and `list_buildable_geographs`, which list what can be loaded or built

        Optional Arguments:

        - `cache_dir`
            - Type: str | None
            - What: Path to the local cache directory
            - Default: None: the `SCGRAPH_CACHE_DIR` environment variable if set, else the platform's cache directory (as in `load_geograph`)

        Returns:

        - A list of dicts, one per file or folder:
            - `kind`: str — `"published"` (a built-in geograph `load_geograph` downloaded, `.graphjson`, or its conversion, `.scgraph`), `"released"` (a network file `load_geograph` downloaded from a network release), `"built"` (a network `build_geograph` built) or `"building"` (the work folder of a build that is running, has failed or was interrupted; `clear_geograph_cache()` removes it)
            - `name`: str | None — the network name
            - `region`: str | None — the region of a built network, if it has one
            - `file`: str — the path of the file or folder
            - `bytes`: int — its size
            - for `"released"` only: `network_release`, the tag of the network release
            - for `"built"` only: `pipeline_version` and `scgraph`, the versions of the network's pipeline and of scgraph that built it, read from the file (None if it can't be read)
        """
        return network_cache.get_cache_info(cache_dir=cache_dir)

    @staticmethod
    def build_geograph(
        name: (
            Literal[
                "eurostat_sea_lanes",
                "geofabrik_multimodal",
                "osm_world_multimodal",
            ]
            | types.ModuleType
        ),
        region: str | None = None,
        cache_dir: str | os.PathLike | None = None,
        reduce_iterations: int = 0,
        lazy: bool = False,
        *,
        refresh: bool = False,
        local_files_only: bool | None = None,
        node_modes: list[str] | str | None = None,
        validate: bool = False,
    ) -> "GeoGraph":
        """
        Function:

        - Download the online sources of a reference network once, build the network on this machine and keep it in the local cache; later calls load it from the cache, without any network request, until an upgrade of scgraph changes how that network is built
        - With `local_files_only=True` (or the environment variable `SCGRAPH_OFFLINE=1`), nothing is downloaded: a network built with another version of its pipeline is loaded with a warning (one of another file format is refused), and one that is not in the cache raises a FileNotFoundError
        - Sources can take several GB (an OpenStreetMap extract of a country): a download above 100 MB is announced with a logging warning before it starts; `logging.basicConfig(level=logging.INFO)` shows each download and the credit to cite, and the DEBUG level shows each step of the build with its counts
        - These networks are not the files that `load_geograph` returns: their node numbers differ, and the road and rail networks have more nodes, which `reduce_iterations=-1` removes for routing
        - `GeoGraph.list_buildable_geographs()` lists the networks, who to credit and what is already in the cache
        - The network file's header says what built it (pipeline, sources and the time their data is up to, software): `GeoGraph.get_scgraph_info(file)` reads it

        Required Arguments:

        - `name`
            - Type: str | module
            - What: The name of the network (see `GeoGraph.list_buildable_geographs()`), or a pipeline module with the contract of `scgraph.pipelines` (for example a copy of one, adapted)
            - Note: A module is cached under its last name (`my.cycleways` in `networks/cycleways/`), which must not be the name of a built-in pipeline; two modules with the same last name share that cache entry; `list_buildable_geographs` does not list it

        - The runner behind this function, `scgraph.pipelines.network_builder.build_network_file`, has one more option: keeping the work folder of a long build to resume it.

        Optional Arguments:

        - `region`
            - Type: str | None
            - What: For `geofabrik_multimodal`, the path of a Geofabrik extract, as in its download URL
            - Default: None
            - Examples: 'europe/luxembourg', 'europe/france/bretagne', 'north-america/us/texas'
            - See: https://download.geofabrik.de for the extracts and their paths (all of them, machine-readable: https://download.geofabrik.de/index-v1-nogeom.json)
        - `cache_dir`
            - Type: str | None
            - What: Path to the local cache directory
            - Default: None: the `SCGRAPH_CACHE_DIR` environment variable if set, else the platform's cache directory (as in `load_geograph`)
        - `reduce_iterations`
            - Type: int
            - What: Number of reduction iterations to perform upon loading. If 0, no reduction is done. If -1, reduces iteratively until convergence.
            - Default: 0
        - `lazy`
            - Type: bool
            - What: Whether to delay downloading or loading the geograph until its first use
            - Default: False
        - `refresh`
            - Type: bool
            - What: Whether to download the sources and build the network again even if the cache holds a current build
            - Default: False
        - `local_files_only`
            - Type: bool | None
            - What: Whether to use only the cache, without any network request
            - Default: None: True if the environment variable `SCGRAPH_OFFLINE` is `1`, else False
        - `node_modes`
            - Type: list[str] | str | None
            - What: The names of the node modes to load from the built network, as in `load_from_scgraph`, for example `["road"]`
            - Default: None: every node mode
        - `validate`
            - Type: bool
            - What: Whether to check the built network against the validation cases of its pipeline; a network that fails is not kept in the cache, and a RuntimeError names the failed cases; a network that the cache already holds is checked as it is, and stays
            - Default: False

        Returns:

        - The GeoGraph of the network (a LazyGeoGraph if `lazy`); `scgraph_file` gives the path of its network file

        Raises:

        - `RuntimeError` with `validate` if the network fails a validation case
        - `ValueError` if `node_modes` names a node mode that the network does not have
        - `ValueError` for an unknown name or a pipeline module named like a built-in one, a missing or invalid region, or a region Geofabrik does not have, before any large download; with `local_files_only`, for `refresh=True` or a cached network of another file format
        - `FileNotFoundError` with `local_files_only` if the network is not in the cache
        - `ImportError` for the OpenStreetMap networks if `osmium` is not installed (`pip install scgraph[osm]`), before downloading the extract
        - `requests.HTTPError` or `ConnectionError` if a source can't be downloaded; a network already cached stays there. A build that fails keeps its downloaded sources in the work folder (`.work/` of the cache directory). The next call resumes from it. `clear_geograph_cache()` removes it
        """
        if lazy:
            return LazyGeoGraph(
                lambda: GeoGraph.build_geograph(
                    name=name,
                    region=region,
                    cache_dir=cache_dir,
                    reduce_iterations=reduce_iterations,
                    lazy=False,
                    refresh=refresh,
                    local_files_only=local_files_only,
                    node_modes=node_modes,
                    validate=validate,
                )
            )
        from scgraph.pipelines.network_builder import build_network_file

        return GeoGraph.load_from_scgraph(
            build_network_file(
                name,
                region,
                cache_dir,
                refresh=refresh,
                local_files_only=local_files_only,
                validate=validate,
            ),
            reduce_iterations=reduce_iterations,
            node_modes=node_modes,
        )

    @staticmethod
    def list_buildable_geographs(
        cache_dir: str | os.PathLike | None = None,
    ) -> list[dict]:
        """
        Function:

        - List the networks that `build_geograph` builds from their online sources, without any network request
        - Unlike `list_geographs`, which lists the published files that `load_geograph` returns

        Optional Arguments:

        - `cache_dir`
            - Type: str | None
            - What: Path to the local cache directory to check for built networks
            - Default: None: the `SCGRAPH_CACHE_DIR` environment variable if set, else the platform's cache directory (as in `load_geograph`)

        Returns:

        - A list of dicts, one per network, sorted by name:
            - `name`: str — the value to pass as `name`
            - `description`: str — what the network is and where it comes from
            - `credit`: str — who to credit with results
            - `license`: str — the licences of the sources (SPDX identifiers; `NOASSERTION` when not established)
            - `needs_region`: bool — whether `build_geograph` needs a `region` (see https://download.geofabrik.de)
            - `cached`: bool — whether a build is already in the cache (for a network with regions: of any region)
            - `cached_regions`: list[str] — the regions already built (empty for a network without regions)
        """
        return network_cache.list_buildable_networks(cache_dir=cache_dir)

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
            - Numbers the nodes along a Hilbert curve (nodes close on the globe get close ids); `source_node_ids[i]` is node i's OSMnx id (its OSM id), when the ids are integers
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
            for i in hilbert_order([located[node] for node in node_list])
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
            kwargs = {"source_node_ids": array("q", node_list)}
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
        geograph = GeoGraph(
            graph=graph,
            nodes=nodes,
            coordinate_dtype="int32" if coord_precision <= 7 else "float64",
            **kwargs,
        )
        # The attributes of each edge, by edge id
        offsets, heads, _ = geograph._read_edge_arrays()
        edge_attributes = [
            attributes_of_origin[heads[edge_id]]
            for origin_id, attributes_of_origin in enumerate(kept_attributes)
            for edge_id in range(offsets[origin_id], offsets[origin_id + 1])
        ]
        if all("travel_time" in data for data in edge_attributes):
            geograph._metrics["travel_time"] = Metric(
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
            - Default: False

        Returns

        - `output`: dict
            - Dictionary with the GeoJSON file content.
        """
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
        removed_node_id = len(self.nodes)
        self._edge_classes.forget_added_edges(
            edge
            for destination_id in removed_edges
            for edge in (
                (removed_node_id, destination_id),
                (destination_id, removed_node_id),
            )
        )
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
        source_node_ids = self.source_node_ids.take(range(graph_length))
        floor = min(0, min(source_node_ids, default=0))
        source_node_ids.extend(
            i if i >= 0 else i + floor
            for i in other_geograph.source_node_ids.take(
                range(original_other_graph_length)
            )
        )
        # Add the other graph nodes to the current geograph (removing the connection nodes since they are already added to the current geograph)
        self.nodes += deepcopy(other_geograph.nodes)[
            :original_other_graph_length
        ]
        self.source_node_ids = network_file.SourceNodeIds(
            source_node_ids, self.nodes
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


def _reorder_edge_values(
    edge_values: array | memoryview,
    offsets: array | memoryview,
    order: list[int],
) -> array:
    """Return the values of the edges in the order of a graph with reordered nodes.

    Args:
        edge_values: An array by edge id: one value for each edge, at its id.
        offsets: The id of the first edge of each node, before the new order.
        order: The nodes in their new order: `order[new id] = id`. A node keeps the
            order of its edges, as `Graph._csr(order)` does.
    """
    edge_values = memoryview(edge_values)
    reordered_edge_values = array(edge_values.format)
    for origin_id in order:
        first, last = offsets[origin_id], offsets[origin_id + 1]
        reordered_edge_values.frombytes(edge_values[first:last].cast("B"))
    return reordered_edge_values


def _cut_legs(edges: list[dict]) -> list[dict]:
    """Cut the edges of a path into legs, and total each leg. A "leg" is a part of
    a route on one edge mode: consecutive edges whose classes have the same edge
    mode.

    Example, a path of four edges: a road of 2 km, two railways of 1 km and 90 km,
    and a road of 2 km. Its legs are a road leg of 2 km, a rail leg of 91 km and a
    road leg of 2 km: the two road legs stay two legs.

    Args:
        edges: The dict of each edge, in the order of the path (see
            `GeoGraph.get_path_edges`).

    Returns:
        One dict for each leg: its `mode`, its total `length`, its totals
        `metric_totals` by name, its lengths by class `class_lengths` and its node
        ids `path`. A leg starts at the node where the leg before it ends.
    """
    legs = []
    for edge in edges:
        if not legs or legs[-1]["mode"] != edge["edge_mode"]:
            legs.append(
                {
                    "mode": edge["edge_mode"],
                    "length": 0.0,
                    "metric_totals": dict.fromkeys(edge["metric_weights"], 0.0),
                    "class_lengths": {},
                    "path": [edge["origin_id"]],
                }
            )
        leg = legs[-1]
        leg["length"] += edge["length"]
        for name, weight in edge["metric_weights"].items():
            leg["metric_totals"][name] += weight
        class_lengths = leg["class_lengths"]
        class_lengths[edge["edge_class"]] = (
            class_lengths.get(edge["edge_class"], 0.0) + edge["length"]
        )
        leg["path"].append(edge["destination_id"])
    return legs


class _SortedSnapIndex:
    """
    A snapping index over nodes in an order that is not the order of their ids. It
    answers with the ids of the nodes. The nodes are every node in Hilbert order (an
    exact tie between two places goes to the node earlier on the curve, not to the
    lower id), or the nodes of one node mode (`GeoGraph._get_snap_index_of_node_mode`).
    """

    def __init__(self, order: array | range, index: SnapIndex):
        # order[position in the index] = node id. An array or a range, not a list: the
        # garbage collector never walks it (a list of 572,009 ids cost a 16 ms pause)
        self.order, self.index = order, index

    def closest_idx(self, point) -> int:
        return self.order[self.index.closest_idx(point)]

    def closest_idx_per_quadrant(self, point) -> dict[str, int | None]:
        # Changes the index's dict in place and creates no object the garbage collector
        # tracks, so that queries don't make it run more often
        found = self.index.closest_idx_per_quadrant(point)
        for quadrant in ("ne", "nw", "se", "sw"):
            p = found[quadrant]
            if p is not None:
                found[quadrant] = self.order[p]
        return found


class _NodeModeSnapIndexes:
    """
    The snapping indexes of several node modes, used as one index. Each index gives
    its closest node, and the answer is the closest of these nodes.

    Example: a point is 3 km from its closest road node and 1 km from its closest rail
    node. The index of the road nodes gives the road node, the index of the rail nodes
    gives the rail node, and `closest_idx` returns the rail node.

    Of two nodes at the same distance, the answer is the lowest id, as in one index.
    """

    def __init__(self, indexes: list[_SortedSnapIndex], nodes: Sequence):
        # `nodes` are the nodes of the geograph: an answer of an index is a node id
        self.indexes, self.nodes = indexes, nodes

    @property
    def order(self) -> Iterator[int]:
        # The ids of the nodes of every index, as `_SortedSnapIndex.order`
        return chain.from_iterable(index.order for index in self.indexes)

    def _find_closest(self, point, node_ids: list[int | None]) -> int | None:
        # The node closest to `point` among the answers of the indexes. An index
        # answers None for a quadrant without a node.
        return min(
            (node_id for node_id in node_ids if node_id is not None),
            key=lambda node_id: (
                haversine(point, self.nodes[node_id]),
                node_id,
            ),
            default=None,
        )

    def closest_idx(self, point) -> int:
        return self._find_closest(
            point, [index.closest_idx(point) for index in self.indexes]
        )

    def closest_idx_per_quadrant(self, point) -> dict[str, int | None]:
        answers = [
            index.closest_idx_per_quadrant(point) for index in self.indexes
        ]
        return {
            quadrant: self._find_closest(
                point, [answer[quadrant] for answer in answers]
            )
            for quadrant in ("ne", "nw", "se", "sw")
        }


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


def _order_by_hilbert(geograph):
    # A copy of the geograph with its nodes in Hilbert order within each node mode: ids
    # change, lengths do not (where two routes tie, another may be returned)
    multimodal = len(geograph.node_modes) > 1
    order = hilbert_order(
        geograph.nodes, geograph.node_mode_ids if multimodal else None
    )
    # Each node keeps its id (its position before ordering, if it had none)
    source_node_ids = geograph.source_node_ids.take(order)
    new_id = [0] * len(order)
    for new, old in enumerate(order):
        new_id[old] = new
    if Graph.__module__ == "scgraph.cpp":
        # Renumbered as arrays (read as dicts, the C++ graph would be copied whole), which
        # the new graph keeps instead of copying them again
        graph = Graph.from_csr(*geograph.graph_object._csr(order), copy=False)
    else:
        # Renumbered dicts, sharing the graph's weight objects (from_csr would not)
        rows = geograph.graph_object.unreduced_graph
        graph = [
            {new_id[head]: weight for head, weight in rows[old].items()}
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
                    {new_id[head]: shape for head, shape in shapes[old].items()}
                    if old < len(shapes)
                    else {}
                )
                for old in order
            ]
        ),
        default_off_graph_circuity=geograph.default_off_graph_circuity,
        default_node_addition_circuity=geograph.default_node_addition_circuity,
        geograph_units=geograph.geograph_units,
        source_node_ids=(
            None
            if source_node_ids == array("q", range(len(order)))
            else source_node_ids
        ),
        node_mode_ids=[geograph.node_mode_ids[old] for old in order],
        node_modes=geograph.node_modes,
        coordinate_dtype=geograph.coordinate_dtype,
    )
    renumbered.metadata = geograph.metadata
    return renumbered


def _is_date(text):
    try:
        datetime.fromisoformat(text)
        return True
    except (TypeError, ValueError):
        return False


class GeoGraphUtils:
    def __get_quadrant_node_indices__(
        self,
        node: list,
        node_mode_snap_index: "_SortedSnapIndex | _NodeModeSnapIndexes | None" = None,
    ) -> set[int]:
        snap_index = node_mode_snap_index or self.snap_index
        indices = snap_index.closest_idx_per_quadrant(point=node)
        node_indices = {idx for idx in indices.values() if idx is not None}
        if not node_indices:
            node_indices.add(snap_index.closest_idx(point=node))
        return node_indices

    def __get_node_distances__(
        self,
        node: list,
        circuity: float,
        node_addition_type: str,
        lat_lon_bound: float,
        node_mode_snap_index: "_SortedSnapIndex | _NodeModeSnapIndexes | None" = None,
    ) -> dict[int, float]:
        """
        Function:

        - Get distances from a new node to graph nodes selected for connection

        Required Arguments:

        - `node`
            - Type: list
            - What: A list of the latitude and longitude of the node
            - EG: [latitude, longitude] -> [31.23, 121.47]
        - `circuity`
            - Type: int | float
            - What: The circuity to apply to any distance calculations
            - Note: This defaults to 4 to prevent the algorithm from taking a direct route in direction of the destination over some impassible terrain (EG: a maritime network that goes through land)
        - `node_addition_type`
            - Type: str
            - What: The type of node addition to use
            - Options:
                - 'closest' / 'kdclosest': Connect to the closest node with the snapping index (`snap_index`)
                - 'quadrant' / 'kdquadrant': Connect to closest nodes in each quadrant with the snapping index (`snap_index`)
                - 'all': Connect to every node inside the latitude/longitude bound
            - Notes:
                - The snapping index searches the full graph; the bound applies only to 'all'
        - `lat_lon_bound`
            - Type: int | float
            - What: Forms a bounding box around the node that is to be added to graph. Only selects graph nodes to consider joining that are within this bounding box.

        Optional Arguments:

        - `node_mode_snap_index`
            - Type: _SortedSnapIndex | _NodeModeSnapIndexes | None
            - What: The snapping index of the nodes of some node modes (see `_get_node_mode_snap_index`): only these nodes are selected
            - Default: None (every node may be selected)

        """
        if node_addition_type in ["kdclosest", "closest"]:
            closest_idx = (node_mode_snap_index or self.snap_index).closest_idx(
                point=node
            )
            closest_point = self.nodes[closest_idx]
            return {
                closest_idx: haversine(
                    node,
                    closest_point,
                    circuity=circuity,
                    units=self.geograph_units,
                ),
            }
        if node_addition_type in ["kdquadrant", "quadrant"]:
            return {
                idx: haversine(
                    node,
                    self.nodes[idx],
                    circuity=circuity,
                    units=self.geograph_units,
                )
                for idx in self.__get_quadrant_node_indices__(
                    node, node_mode_snap_index
                )
            }
        if not (node_addition_type == "all"):
            raise ValueError(
                f"Invalid node addition type provided ({node_addition_type})"
            )
        # Get only bounded nodes
        # Find the only keep nodes that are within the bounding latitude
        top_lat = node[0] + lat_lon_bound
        bottom_lat = node[0] - lat_lon_bound
        top_lon = node[1] + lat_lon_bound
        bottom_lon = node[1] - lat_lon_bound
        nodes = {
            node_idx: node_i
            for node_idx, node_i in (
                enumerate(self.nodes)
                if node_mode_snap_index is None
                else (
                    (node_id, self.nodes[node_id])
                    for node_id in node_mode_snap_index.order
                )
            )
            if node_i[0] >= bottom_lat
            and node_i[0] <= top_lat
            and node_i[1] >= bottom_lon
            and node_i[1] <= top_lon
        }
        if len(nodes) == 0:
            logger.debug(
                "No node within %s degrees of %s; the closest node is used",
                lat_lon_bound,
                node,
            )
            closest_idx = (node_mode_snap_index or self.snap_index).closest_idx(
                point=node
            )
            closest_point = self.nodes[closest_idx]
            return {
                closest_idx: haversine(
                    node,
                    closest_point,
                    circuity=circuity,
                    units=self.geograph_units,
                )
            }
        return {
            node_idx: haversine(
                node,
                node_i,
                circuity=circuity,
                units=self.geograph_units,
            )
            for node_idx, node_i in nodes.items()
        }

    def __get_intermediate_nodes__(
        self, origin_idx: int, destination_idx: int, sequence: str = "lat_lon"
    ) -> list[list[float]]:
        """
        Function:

        - Get the intermediate nodes between two nodes if they exist in the graph object
        - Note: Not as performant so not used in __get_coordinate_path__, but can be used in post processing of the path if desired

        Required Arguments:

        - `origin_idx`
            - Type: int
            - What: The index of the origin node
        - `destination_idx`
            - Type: int
            - What: The index of the destination node
        - `sequence`
            - Type: str
            - What: The sequence of coordinates to return, either "lat_lon" or "lon_lat"
            - Default: "lat_lon"
        """
        if self.intermediate_nodes is not None:
            if sequence not in [
                "lat_lon",
                "lon_lat",
            ]:
                raise ValueError(
                    f"Invalid sequence provided ({sequence}), valid options are: ['lat_lon', 'lon_lat']"
                )
            out = self.intermediate_nodes[origin_idx].get(destination_idx, [])
            if sequence == "lon_lat":
                out = [[point[1], point[0]] for point in out]
            return out
        else:
            return []

    def __format_coordinates__(
        self,
        coordinate_path: list[list[int | float]],
        output_format: str = "list_of_lists",
    ) -> list:
        """
        Function:

        Arguments:

        - `coordinate_path`
            - Type: list of lists
            - What: A list of lists where each sublist is a point [latitude, longitude]
        - `output_format`
            - Type: str
            - What: The format to return the coordinates in
            - Options:
                - 'list_of_lists': A list of lists with the first value being latitude and the second being longitude
                - 'list_of_lists_long_first': A list of lists with the first value being longitude and the second being latitude
                - 'list_of_dicts': A list of dictionaries with keys 'latitude' and 'longitude'
            - Default: 'list_of_lists'

        """
        if output_format == "list_of_lists":
            return coordinate_path
        elif output_format == "list_of_lists_long_first":
            return [[i[1], i[0]] for i in coordinate_path]
        elif output_format == "list_of_dicts":
            return [
                {"latitude": i[0], "longitude": i[1]} for i in coordinate_path
            ]
        else:
            raise ValueError(
                "Invalid output_format. Must be one of 'list_of_lists', 'list_of_lists_long_first', or 'list_of_dicts'"
            )

    def __get_coordinate_path__(
        self, path: list[int], get_intermediate_nodes: bool = False
    ) -> list[list[float]]:
        """
        Function:

        - Return a list of node dictionaries (lat + long) in the order they are visited

        Required Arguments:

        - `path`
            - Type: list
            - What: A list of node ids in the order they are visited

        Optional Arguments:

        - `get_intermediate_nodes`
            - Type: bool
            - What: If True, returns the intermediate nodes in the path (if they exist for each segment)
            - Default: False
        """
        nodes = self.nodes
        coordinates = (
            nodes.take(path)
            if isinstance(nodes, network_file.NodePoints)
            else [nodes[node_id] for node_id in path]
        )
        if (
            get_intermediate_nodes
            and self.intermediate_nodes is not None
            and path
        ):
            if isinstance(self.intermediate_nodes, network_file.EdgeShapes):
                return self.intermediate_nodes.coordinate_path(
                    path, coordinates
                )
            # Start with the origin node
            coordinate_path = [coordinates[0]]
            for i in range(len(path) - 1):
                origin_id = path[i]
                destination_id = path[i + 1]
                # Nodes added after loading (add_coord_node) have no shapes
                shapes = (
                    self.intermediate_nodes[origin_id]
                    if origin_id < len(self.intermediate_nodes)
                    else {}
                )
                intermediate_nodes = shapes.get(destination_id, [])
                coordinate_path.extend(intermediate_nodes)
                # Add the destination node
                coordinate_path.append(coordinates[i + 1])
            return coordinate_path
        return coordinates

    def get_path_weight(
        self,
        path_result: dict,
        off_graph_circuity: float | None = None,
        output_units: str = "km",
        *,
        metric: str | None = None,
    ) -> float:
        """
        Function:

        - Compute the total weight of a pre-computed path in this geograph's units
        - With `metric`, compute the total of this metric along the path: `geograph.get_path_weight(result, metric="hours")`

        - This allows computing the weight of a path optimized for one metric
          (e.g., time) using a different geograph's weights (e.g., distance),
          including the off-graph entry and exit segments using this geograph's
          circuity.

        Required Arguments:

        - `path_result`
            - Type: dict
            - What: The output from `get_shortest_path` called with `output_path=True`
            - Must contain both a `path` key (list of on-graph node ids) and a
              `coordinate_path` key (list of [lat, lon] pairs)

        Optional Arguments:

        - `off_graph_circuity`
            - Type: float | int | None
            - What: Circuity to apply to the off-graph entry and exit haversine
              distances. Defaults to `self.default_off_graph_circuity`.
            - Default: None

        - `output_units`
            - Type: str
            - What: Units for the returned weight value
            - Default: 'km'

        - `metric`
            - Type: str
            - What: The name of a metric of `metrics`. The total is the weight in
              this metric of the edges of the path, plus the weight of the two
              off-graph legs: their km times `off_graph_circuity` times the
              weight of 1 km of an off-graph leg in the metric
            - Note: The total of a metric other than 'length' is not converted to
              `output_units`. An unknown name raises a ValueError
            - Default: None (the `default_metric` of the geograph, which is
              'length' unless a loader or the caller set it)

        Returns:

        - The total weight of the path in this geograph's edge units, converted
          to `output_units`
        """
        if off_graph_circuity is None:
            off_graph_circuity = self.default_off_graph_circuity
        if metric is None:
            metric = self.default_metric
        path = path_result.get("path")
        coordinate_path = path_result.get("coordinate_path")
        if not (path is not None):
            raise ValueError(
                "path_result must contain a 'path' key; call get_shortest_path with output_path=True"
            )
        if not (coordinate_path is not None):
            raise ValueError("path_result must contain a 'coordinate_path' key")

        origin = coordinate_path[0]
        destination = coordinate_path[-1]

        if metric != "length":
            off_graph_km = off_graph_circuity * self._get_off_graph_km(
                path, origin, destination
            )
            return (
                self._get_path_total(path, metric)
                + off_graph_km
                * self._read_metric(metric).off_graph_weight_per_km
            )
        if len(path) == 0:
            # Edge case: origin and destination map to the same graph node
            total = haversine(
                origin,
                destination,
                circuity=off_graph_circuity,
                units=self.geograph_units,
            )
        else:
            on_graph_weight = self.graph_object.get_path_weight(path)
            origin_off = haversine(
                origin,
                self.nodes[path[0]],
                circuity=off_graph_circuity,
                units=self.geograph_units,
            )
            destination_off = haversine(
                self.nodes[path[-1]],
                destination,
                circuity=off_graph_circuity,
                units=self.geograph_units,
            )
            total = on_graph_weight + origin_off + destination_off

        return distance_converter(
            total,
            input_units=self.geograph_units,
            output_units=output_units,
        )

    def validate(
        self,
        check_symmetry: bool = True,
        check_connected: bool = True,
    ) -> None:
        return self.graph_object.validate(
            check_symmetry=check_symmetry,
            check_connected=check_connected,
        )


class GeoGraphDistanceCalculations:
    def haversine(
        self,
        origin_id: int,
        destination_id: int,
    ) -> float:
        """
        Function:

        - Calculate the haversine distance between two points on the Earth, in the units of the GeoGraph (`geograph_units`).
        - Passed as `heuristic_fn` to `get_shortest_path` with `algorithm_fn='a_star'`, the same bound is computed natively (C++ build) from a cache of the node coordinates, rebuilt when nodes are added or removed; edit nodes through the GeoGraph methods rather than in place.

        Required Arguments:

        - `origin_id`
            - Type: int
            - What: The id of the origin node in the graph
        - `destination_id`
            - Type: int
            - What: The id of the destination node in the graph

        Optional Arguments:

        - None
        """
        return haversine(
            origin=self.nodes[origin_id],
            destination=self.nodes[destination_id],
            units=self.geograph_units,
            circuity=1,
        )

    def cheap_ruler(
        self,
        origin_id: int,
        destination_id: int,
    ) -> float:
        """
        Function:

        - Calculate the distance between two points on the Earth using the cheap ruler algorithm.
        - This is based off of Mapbox's cheap ruler algorithm which is a fast approximation of the haversine distance
        - It has modifications to support distances across the antimeridian
        - The distance is in the units of the GeoGraph (`geograph_units`).

        Required Arguments:

        - `origin_id`
            - Type: int
            - What: The id of the origin node in the graph
        - `destination_id`
            - Type: int
            - What: The id of the destination node in the graph

        Optional Arguments:

        - None
        """
        return cheap_ruler(
            origin=self.nodes[origin_id],
            destination=self.nodes[destination_id],
            units=self.geograph_units,
            # Use a circuity factor of 0.95 to account for the fact that cheap_ruler can overestimate distances
            circuity=0.9,
        )


class GeoGraph(
    GeoGraphIO, GeoGraphModifiers, GeoGraphUtils, GeoGraphDistanceCalculations
):
    def __init__(
        self,
        graph: list[dict[int, int | float]],
        nodes: list[list[float]],
        validate: bool = False,
        intermediate_nodes: list[dict[int, list[list[float]]]] | None = None,
        default_off_graph_circuity: float = 1,
        default_node_addition_circuity: float = 4,
        geograph_units: Literal["km", "m", "mi", "ft"] = "km",
        source_node_ids: list[int] | None = None,
        node_mode_ids: list[int] | None = None,
        node_modes: list[dict] | None = None,
        coordinate_dtype: Literal["float64", "int32"] = "float64",
        classes: list[dict] | None = None,
        edge_classes: list[dict[int, str]] | None = None,
    ) -> None:
        """
        Function:

        - Create a GeoGraph object
        - The attribute `default_metric` is the name of the metric that a call without `metric` uses (`get_shortest_path`, `distance_matrix`, `get_path_weight`, `get_graph_object`). It is 'length', until a loader or the caller sets it to another name of `metrics`
        - A call fails with a ValueError while `default_metric` names a metric that the geograph does not have, for example after an edit of the network, which removes the metrics other than 'length'

        Required Arguments:

        - `graph`
            - Type: list of dictionaries
            - See: https://connor-makowski.github.io/scgraph/scgraph/graph.html#Graph
            - Note: May be kept and modified instead of copied (pure-Python backend; the C++ backend copies it); do not modify it afterwards
        - `nodes`
            - Type: list of lists of ints or floats
            - What: A list of lists where the values are coordinates (latitude then longitude)
            - Note: The length of the nodes list must be the same as that of the graph list
            - Note: Kept without copying and may be modified by the GeoGraph; do not modify it afterwards
            - Example:
            ```
                [
                    # London (index 0)
                    [51.5074, 0.1278],
                    # Paris (index 1)
                    [48.8566, 2.3522],
                    # Berlin (index 2)
                    [52.5200, 13.4050],
                    # Rome (index 3)
                    [41.9028, 12.4964],
                    # Madrid (index 4)
                    [40.4168, 3.7038],
                    # Lisbon (index 5)
                    [38.7223, 9.1393]
                ]
            ```

        Optional Arguments:

        - `validate`
            - Type: bool
            - What: Whether to validate the graph upon initialization
            - Default: False
        - `intermediate_nodes`
            - Type: list of dicts of lists of [float, float]
            - What: One dict per node, {destination: [[latitude, longitude], ...]}: the coordinates of each edge's shape, between its two nodes (not repeated), from origin to destination
            - Note: Allows for more detailed path plotting along edges without needing to increase the number of nodes in the graph
            - Default: None
        - `source_node_ids`
            - Type: list of ints | None
            - What: The stable id of each node, for example its id in the source the network was built from; read back as `source_node_ids`
            - Note: Node ids in paths and graph methods stay positions; `[geograph.source_node_ids[p] for p in path]` translates a path
            - Note: Nodes added later (`add_coord_node`, merges) get negative ids, below all the others; extend `nodes` in place (replacing it leaves `source_node_ids` counting the former list)
            - Default: None (each node's id is its position)
        - `node_mode_ids`
            - Type: list of ints | None
            - What: The node mode of each node (road, sea, port, ...), as its position in `node_modes`; read back as `node_mode_ids`
            - Note: `(node mode, node id)` identifies a node: node ids of different node modes may come from different sources
            - Default: None (every node in the first node mode)
        - `node_modes`
            - Type: list of dicts | None
            - What: The node modes, each a dict with its `name` (str or None) and, optionally, the `source` of its node ids (the name of an entry of the network's sources); read back as `node_modes`
            - Note: At most 256 node modes; two node modes may have the same name (two sea networks merged)
            - Default: None (one node mode, without a name: `[{"name": None}]`)
        - `coordinate_dtype`
            - Type: str
            - What: The coordinate dtype `save_as_scgraph` uses by default, 'float64' or 'int32' (see there); loaders that round to 7 decimals or fewer, and int32 network files, give 'int32'
            - Default: 'float64'
        - `classes`
            - Type: list of dicts | None
            - What: The classes of the edges, each a dict with its `name` (str) and the `edge_mode` of its edges; read back as `classes`
            - Note: At most 255 classes; more raise a ValueError
            - Example: `[{"name": "motorway", "edge_mode": "road"}, {"name": "ferry", "edge_mode": "sea"}]`
            - Default: None (a geograph without classes)
        - `edge_classes`
            - Type: list of dicts | None
            - What: One dict per node, {destination: name of a class}: the class of each edge, as a name of `classes`; `get_edges` reads it back as `edge_class`
            - Note: An edge that is not in its dict has no class
            - Note: A name that is not in `classes`, a destination that is no edge of `graph`, a list that has not one dict per node, or `edge_classes` without `classes` raises a ValueError
            - Example: `[{1: "motorway"}, {0: "motorway", 2: "ferry"}, {1: "ferry"}]`
            - Default: None (no edge has a class)
        - `default_off_graph_circuity`
            - Type: float | int
            - What: The physical distance multiplier applied to final off-graph access legs (origin -> entrance node and exit node -> destination) after the route is solved
            - Purpose: Accounts for the real-world winding of local roads or converts spatial distances to different graph units (e.g. time)
                - EG: For distance routing, 1.0 represents straight-line (great-circle) access distance, while 1.2 models average local street circuity
                - EG: For travel time in seconds with an assumed off-graph speed of 30 km/h, set circuity to 3600 / 30 = 120
                - EG: Set to 0 if off-graph travel should not contribute to the reported route length/time
            - Default: 1
        - `default_node_addition_circuity`
            - Type: float | int
            - What: The algorithmic search penalty applied to candidate off-graph connection legs *during* shortest path finding
            - Purpose: Prevents the pathfinding algorithm from "flying" off-network across impassable geographic barriers (e.g. crossing land in a maritime graph or crossing water without bridges)
                - When connecting origins/destinations with multiple candidate entry points (`node_addition_type="quadrant"` or `"all"`), this factor artificially inflates the cost of traveling off-graph during the search
                - A higher penalty (default: 4) forces the search to enter the graph at a nearby node rather than shortcutting off-graph towards the destination
                - Once the optimal route sequence is determined, the actual reported path length uses `default_off_graph_circuity` instead of this penalty factor
            - Default: 4
        - `geograph_units`
            - Type: str
            - What: The units in which the geograph is represented
            - Default: 'km'
            - Options:
                - 'km': Kilometers
                - 'm': Meters
                - 'mi': Miles
                - 'ft': Feet
        """
        if isinstance(graph, Graph) or (
            hasattr(graph, "get_shortest_path") and not isinstance(graph, list)
        ):
            self.graph_object = graph
            self.graph = None  # built from the graph object on first use
        else:
            self.graph_object = Graph(graph=graph, validate=validate)
            self.graph = graph
        self.nodes = nodes
        if source_node_ids is not None and len(source_node_ids) != len(nodes):
            raise ValueError("source_node_ids must give one id per node")
        self.source_node_ids = network_file.SourceNodeIds(
            range(len(nodes)) if source_node_ids is None else source_node_ids,
            nodes,
        )
        if coordinate_dtype not in ("float64", "int32"):
            raise ValueError("coordinate_dtype must be 'float64' or 'int32'")
        self.coordinate_dtype = coordinate_dtype
        # How the network was built, as read from a network file (see save_as_scgraph)
        self.metadata = {}
        # The network file that the geograph was read from, if any (load_from_scgraph)
        self.scgraph_file = None
        # The class of each edge (`scgraph/edge_classes.py`)
        self._edge_classes = EdgeClasses()
        # The metrics other than `length`, by name (`scgraph/metrics.py`). A
        # method reads them with `_read_metrics`: an edit of `graph_object`
        # removes them.
        self._metrics = {}
        # The offsets, the heads and the lengths of the edges of `graph_object`
        # (`Graph._csr`), as `_read_edge_arrays` last read them. The id of an edge
        # is its position in the heads. The graph and its count of edits at that
        # time show whether the graph was edited since.
        self._edge_arrays = None
        self._edge_arrays_graph = None
        self._edge_arrays_edit_count = None
        # The class id of each of these edges, by edge id, as
        # `_read_edge_class_ids` computed it. None before the first call and
        # after an edit.
        self._edge_class_ids = None
        if classes is not None or edge_classes is not None:
            offsets, heads, _ = self._read_edge_arrays()
            self._edge_classes = EdgeClasses.build_from_class_names(
                classes, edge_classes, offsets, heads
            )
        # The argument of the last `reduce`, for the graph of each metric
        self._reduce_iterations = None
        # The node modes that a query point snaps to by default, as a network file names
        # them. None for every node mode.
        self.default_node_addition_modes = None
        self.node_modes = (
            [dict(mode) for mode in node_modes]
            if node_modes
            else [{"name": None}]
        )
        self.node_mode_ids = array(
            "B", bytes(len(nodes) if node_mode_ids is None else node_mode_ids)
        )
        if node_mode_ids is not None and (
            len(self.node_mode_ids) != len(nodes)
            or max(self.node_mode_ids, default=0) >= len(self.node_modes)
        ):
            raise ValueError(
                "node_mode_ids must give each node the position of a row of "
                "node_modes"
            )
        self.intermediate_nodes = intermediate_nodes
        self.default_off_graph_circuity = default_off_graph_circuity
        self.default_node_addition_circuity = default_node_addition_circuity
        self.default_get_intermediate_nodes = (
            True if intermediate_nodes is not None else False
        )
        self.geograph_units = geograph_units
        # The name of the metric that a call without `metric` uses
        self.default_metric = "length"
        # Built at the first snap, not here: a GeoGraph that never snaps never pays for it
        self.snap_index = None
        # len(nodes), not len(graph): a C++ graph would be copied to Python to count it
        self.__original_graph_length__ = len(self.nodes)

    @property
    def classes(self) -> list[dict]:
        """
        The classes of the edges, as rows `{"name": ..., "edge_mode": ...}`. A class
        is the category of an edge, such as `motorway`. Its edge mode is the kind of
        transport of its edges, such as `road`. A loader, the arguments `classes` and
        `edge_classes` of the constructor, or a merge gives classes to a geograph.
        Without them, the list is empty. `get_edges` gives the class of each edge.
        """
        return self._edge_classes.classes

    def _read_edge_arrays(self) -> tuple[array | memoryview, ...]:
        # Return the offsets, the heads and the lengths of the edges of
        # `graph_object`. The method reads them again when the graph or its count
        # of edits has changed: the caller may have edited `graph_object` itself.
        # It then removes the metrics: a metric has the weight of each edge at the
        # id that the edge had before the edit.
        graph = self.graph_object
        if (
            graph is not self._edge_arrays_graph
            or graph._edit_count != self._edge_arrays_edit_count
        ):
            self._remove_metrics()
            self._set_edge_arrays(graph._csr())
        return self._edge_arrays

    def _set_edge_arrays(
        self,
        edge_arrays: tuple[array | memoryview, ...],
        edge_class_ids: array | memoryview | None = None,
    ) -> None:
        # Keep the offsets, the heads and the lengths of the edges of
        # `graph_object`, for `_read_edge_arrays`. `edge_class_ids` gives the
        # class id of each of these edges when a network file holds it. With
        # None, `_read_edge_class_ids` computes it.
        self._edge_arrays = edge_arrays
        self._edge_arrays_graph = self.graph_object
        self._edge_arrays_edit_count = self.graph_object._edit_count
        self._edge_class_ids = edge_class_ids

    def _read_edge_class_ids(self) -> array | memoryview | None:
        # Return the class id of each edge of `graph_object`, by edge id: 255 for
        # an edge without a class. Return None for a geograph without classes.
        # The array is computed at the first call, and again after an edit.
        offsets, heads, _ = self._read_edge_arrays()
        if self._edge_class_ids is None:
            self._edge_class_ids = self._edge_classes.list_edge_class_ids(
                offsets, heads
            )
        return self._edge_class_ids

    def _remove_metrics(self) -> None:
        # Remove every metric other than `length`, at an edit of the network, and
        # warn with their names.
        if self._metrics:
            warnings.warn(
                "An edit of the network removed its metrics "
                f"{list(self._metrics)}. Create them again with `create_metric`.",
                stacklevel=3,
            )
            self._metrics = {}

    def _read_metrics(self) -> dict[str, Metric]:
        # Return the metrics other than `length`, by name. A geograph with
        # metrics first reads its edges: an edit made on `graph_object` removes
        # the metrics here.
        if self._metrics:
            self._read_edge_arrays()
        return self._metrics

    def _read_metric(self, metric: str) -> Metric:
        # Return the record of a metric other than `length`, as `_read_metrics`
        # reads it.
        metrics = self._read_metrics()
        if metric not in metrics:
            raise ValueError(
                f"Unknown metric {metric!r}: the metrics of this geograph are "
                f"{['length', *metrics]}. An edit of the network removes the "
                "metrics other than 'length'"
                + (
                    f". {metric!r} is the `default_metric` of this geograph: "
                    "create this metric again, or set `default_metric`"
                    if metric == self.default_metric
                    else ""
                )
            )
        return metrics[metric]

    @property
    def graph(self) -> list[dict[int, int | float]]:
        if self._graph is None:
            # The original graph, whether or not it has been reduced
            self._graph = self.graph_object.unreduced_graph
        return self._graph

    @graph.setter
    def graph(self, graph: list[dict[int, int | float]] | None) -> None:
        self._graph = graph

    @property
    def snap_index(self) -> "SnapIndex | _SortedSnapIndex | GeoKDTree":
        """
        The index that snaps coordinates to their closest nodes (`closest_idx(point)`,
        `closest_idx_per_quadrant(point)`), built when a network file is loaded or else at
        the first snap, and again after nodes were added or removed.

        - Nodes too scattered for the index (a graph built from a list, or many nodes added
          to a network file) are indexed in Hilbert order, sorted in Python at each build:
          an exact tie between two places then goes to the node earlier on the curve
        """
        # Dropped by add_coord_node, remove_coord_node and merge_with_other_geograph (merge
        # keeps the index of the networks before the merge while it connects them); direct
        # edits of nodes are not detected
        if self.__snap_index__ is None:
            with log_step(
                logger, "build the snapping index", {"nodes": len(self.nodes)}
            ) as indicators:
                self.__snap_index__ = self._build_snap_index()
                indicators["sorted_for_the_index"] = isinstance(
                    self.__snap_index__, _SortedSnapIndex
                )
        return self.__snap_index__

    @snap_index.setter
    def snap_index(
        self, snap_index: "SnapIndex | _SortedSnapIndex | GeoKDTree | None"
    ) -> None:
        self.__snap_index__ = snap_index
        # Node coordinates in radians for the native A* heuristic, rebuilt with the index
        self.__node_radians__ = None
        # The snapping index of the nodes of each node mode that a query used, by the
        # name of the node mode (see `_get_snap_index_of_node_mode`). They are rebuilt
        # with the index.
        self._node_mode_snap_indexes = {}
        if snap_index is None:
            self.__geokdtree__ = None

    def _build_snap_index(
        self, node_ids: range | array | None = None
    ) -> "SnapIndex | _SortedSnapIndex":
        """
        Builds the snapping index of the nodes, or of the nodes `node_ids` alone: a
        range, or an array of ids in rising order (see `_find_node_ids`). Nodes too
        scattered for the index are indexed in Hilbert order, and keep their ids.
        """
        nodes = self.nodes
        try:
            if node_ids is None:
                return (
                    SnapIndex.from_array(nodes.points())
                    if isinstance(nodes, network_file.NodePoints)
                    else SnapIndex(nodes)
                )
            if isinstance(node_ids, range) and isinstance(
                nodes, network_file.NodePoints
            ):
                # The index reads the points of the range in place, as the index of
                # every node does
                points = memoryview(nodes.points())
                return _SortedSnapIndex(
                    node_ids,
                    SnapIndex.from_array(
                        points[2 * node_ids.start : 2 * node_ids.stop]
                    ),
                )
            return _SortedSnapIndex(
                node_ids, SnapIndex([nodes[i] for i in node_ids])
            )
        except NodeOrderError:
            # A graph built from a list, or one with many added nodes, does not keep
            # nearby nodes together
            points = (
                list(nodes)
                if node_ids is None
                else [nodes[i] for i in node_ids]
            )
            order = array("q", hilbert_order(points))
            index = SnapIndex([points[i] for i in order])
            if node_ids is not None:
                # A position in `points` becomes the id of its node
                order = array("q", [node_ids[i] for i in order])
            return _SortedSnapIndex(order, index)

    def _get_node_mode_snap_index(
        self, node_addition_modes: list[str] | None
    ) -> "_SortedSnapIndex | _NodeModeSnapIndexes | None":
        """
        Returns the snapping index of the nodes that a point of a query may snap to.
        Returns None when the point may snap to every node: `snap_index` is then the
        index.

        The geograph has one snapping index for each node mode, built at the first query
        that needs it (`_get_snap_index_of_node_mode`). A query point snaps to the
        closest node among the indexes of its node modes.

        - `node_addition_modes` is the argument of the query: names of `node_modes`,
          or None for the node modes of `default_node_addition_modes`
        - With None, a point also snaps to a node without a named node mode: a node that
          the user added. A list of names keeps only the nodes of these node modes
        - A default node mode that no node has does not count. A geograph that read
          only the sea lanes of a file has no node of the default node mode `road` of
          this file: a point then snaps to every node
        - Raises a ValueError for a list with a name that is not in `node_modes`, and
          for a list whose node modes have no node. An empty list is such a list
        """
        if node_addition_modes is None:
            snap_indexes = self._list_snap_indexes(
                self.default_node_addition_modes or []
            )
            if not snap_indexes:
                return None
            # The nodes without a named node mode
            snap_indexes += self._list_snap_indexes([None])
        else:
            node_mode_names = [mode.get("name") for mode in self.node_modes]
            if not set(node_addition_modes) <= set(node_mode_names) - {None}:
                raise ValueError(
                    "node_addition_modes must be a list of node modes of this geograph, "
                    f"which are {node_mode_names}: got {node_addition_modes!r}"
                )
            snap_indexes = self._list_snap_indexes(node_addition_modes)
            if not snap_indexes:
                raise ValueError(
                    "node_addition_modes names no node mode that a node of this geograph "
                    f"has: got {node_addition_modes!r}"
                )
        if len(snap_indexes) == 1:
            return snap_indexes[0]
        return _NodeModeSnapIndexes(snap_indexes, self.nodes)

    def _list_snap_indexes(
        self, node_modes: Iterable[str | None]
    ) -> "list[_SortedSnapIndex]":
        # The snapping index of each of these node modes that has a node. A name
        # given twice counts once.
        snap_indexes = [
            self._get_snap_index_of_node_mode(node_mode)
            for node_mode in dict.fromkeys(node_modes)
        ]
        return [
            snap_index for snap_index in snap_indexes if snap_index is not None
        ]

    def _get_snap_index_of_node_mode(
        self, node_mode: str | None
    ) -> "_SortedSnapIndex | None":
        """
        Returns the snapping index of the nodes of one node mode, built at the first
        call. Returns None for a node mode without a node.

        - `node_mode` is a name of `node_modes`, or None for the nodes without a named
          node mode
        - The geograph keeps the index. The setter of `snap_index` removes it when
          the nodes change
        """
        if node_mode not in self._node_mode_snap_indexes:
            node_ids = self._find_node_ids(node_mode)
            snap_index = None
            if node_ids:
                with log_step(
                    logger,
                    "build the snapping index",
                    {"nodes": len(node_ids), "node_mode": node_mode},
                ) as indicators:
                    snap_index = self._build_snap_index(node_ids)
                    indicators["sorted_for_the_index"] = (
                        snap_index.order is not node_ids
                    )
            self._node_mode_snap_indexes[node_mode] = snap_index
        return self._node_mode_snap_indexes[node_mode]

    def _find_node_ids(self, node_mode: str | None) -> range | array:
        """
        Returns the ids of the nodes of one node mode, in rising order. `node_mode` is
        a name of `node_modes`, or None for the nodes without a named node mode.

        - The nodes of a network file are sorted by node mode. So the nodes of one node
          mode are a range of node ids, and their index reads their points in the file
        - A merge or an added node changes this order: the ids are then an array. A
          merge can also give the same name to two rows of `node_modes`, and a geograph
          may have no row for a name
        - `add_coord_node` without `node_mode` gives the node mode without a name to
          its node. A node appended to `nodes` directly is not in `node_mode_ids`: it
          has no named node mode either
        """
        wanted_node_mode_ids = [
            node_mode_id
            for node_mode_id, row in enumerate(self.node_modes)
            if row.get("name") == node_mode
        ]
        appended_node_ids = (
            range(len(self.node_mode_ids), len(self.nodes))
            if node_mode is None
            else range(0)
        )
        if not wanted_node_mode_ids:
            return appended_node_ids
        if len(wanted_node_mode_ids) == 1 and not appended_node_ids:
            # `bytes` searches a value in C: a search in the array costs as much as
            # the build of the index
            node_mode_ids = bytes(self.node_mode_ids)
            node_mode_id = wanted_node_mode_ids[0]
            first = node_mode_ids.find(node_mode_id)
            last = node_mode_ids.rfind(node_mode_id)
            if node_mode_ids.count(node_mode_id) == last - first + 1:
                return range(first, last + 1)
        return array(
            "q",
            [
                node_id
                for node_id, node_mode_id in enumerate(self.node_mode_ids)
                if node_mode_id in wanted_node_mode_ids
            ]
            + list(appended_node_ids),
        )

    @property
    def geokdtree(self) -> "GeoKDTree":
        """
        A `geokdtree.GeoKDTree` of the nodes.
        Interchangeable with `snap_index`, sharing the same `closest_idx` and
        `closest_idx_per_quadrant` methods.
        """
        if self.__geokdtree__ is None:
            from geokdtree import GeoKDTree

            self.__geokdtree__ = GeoKDTree(points=self.nodes)
        return self.__geokdtree__

    @geokdtree.setter
    def geokdtree(self, geokdtree: "GeoKDTree | None") -> None:
        self.__geokdtree__ = geokdtree
        self.snap_index = geokdtree

    def _get_node_radians(self) -> tuple[array, array]:
        # Also rebuilt when nodes were appended or removed directly; in-place edits of
        # existing nodes are not detected (as for the snapping index)
        if self.__node_radians__ is None or len(
            self.__node_radians__[0]
        ) != len(self.nodes):
            self.__node_radians__ = (
                array(
                    "d", (radians_per_degree * node[0] for node in self.nodes)
                ),
                array(
                    "d", (radians_per_degree * node[1] for node in self.nodes)
                ),
            )
        return self.__node_radians__

    def reduce(self, iterations: int = -1) -> None:
        """
        Function:

        - Reduce the graph by bypassing pass-through nodes and summing intermediate weights.
        - Precomputes and sets reduced graph structures on self.graph_object for faster queries.
        - The graph of each metric is reduced the same way (see `get_graph_object`).

        Optional Arguments:

        - `iterations`:
            - Type: int
            - What: Number of reduction iterations to perform. If -1, reduces iteratively until convergence. If 0, no reduction is done.
            - Default: -1

        Returns:

        - None
        """
        if iterations == 0:
            return
        with log_step(
            logger, "reduce the graph", {"iterations": iterations}
        ) as indicators:
            self.graph_object.reduce(iterations)
            is_reduced = self.graph_object.is_reduced or []
            indicators["nodes"] = len(is_reduced)
            indicators["kept_nodes"] = len(is_reduced) - sum(is_reduced)
        self._reduce_iterations = iterations
        for metric_record in self._metrics.values():
            if metric_record.graph_object is not None:
                metric_record.graph_object.reduce(iterations)

    @property
    def metrics(self) -> list[dict]:
        """
        The info of each metric (see `create_metric`): what describes the metric,
        without the weights of its edges. The first one is `length`, with its unit:
        `geograph_units`. The info of another metric has its `name`, its `unit` and
        `description` if it has them, and `off_graph_weight_per_km`: the weight of
        1 km of an off-graph leg.
        """
        return [{"name": "length", "unit": self.geograph_units}] + [
            metric_record.get_info()
            for metric_record in self._read_metrics().values()
        ]

    def create_metric(
        self,
        name: str,
        *,
        weight_per_km: float | dict | None = None,
        class_weight_per_km: dict | None = None,
        weight_at_hub: dict | None = None,
        weighted_sum_of: dict[str, float] | None = None,
        edge_weight_fn: Callable | None = None,
        off_graph_weight_per_km: float | None = None,
        edge_weights: dict | None = None,
        unit: str | None = None,
        description: str | None = None,
    ) -> None:
        """
        Function:

        - Create a metric: one weight for each edge, under a name. `get_shortest_path(metric=name)` then finds the route with the smallest total of these weights
        - Every optional argument is None by default. A call gives exactly one of `weight_per_km`, `weighted_sum_of` and `edge_weight_fn`. A weight is a number of zero or more. None in place of a weight closes its edges: no route by this metric takes them
        - The weights are computed at the call. A metric of the same name is replaced, and no other metric changes. An edit of the network removes the metric (see `add_edge`)
        - Example: `geograph.create_metric("hours", weight_per_km={"road": 1 / 60, "rail": 1 / 40, "off_graph": 1 / 30}, class_weight_per_km={"motorway": 1 / 90}, weight_at_hub={"rail_terminal": {"rail": 4}}, unit="h")`

        Required Arguments:

        - `name`: The name of the metric: small letters, digits and `_`, starting with a letter; not `length`

        Optional Arguments:

        - `weight_per_km`: The weight of 1 km: the weight of an edge is its weight per km times its km. The lengths of the geograph must be in km
            - A number is the weight per km of every edge, and of the off-graph legs: the straight lines between the points of a query and their nodes
            - A dict is `{mode of a leg: weight of 1 km}`. Its keys are the edge modes (see `classes`) and `"off_graph"`, for the off-graph legs. The dict must have `"off_graph"`, and the edge mode of each class that has an edge and that `class_weight_per_km` does not name. None closes an edge mode
            - With a dict, an edge without a class has the weight of an off-graph leg: its km times the weight of `"off_graph"`. `weight_at_hub` adds nothing to it
        - `class_weight_per_km`: With `weight_per_km`, `{name of a class: weight of 1 km}`: the weight per km of the edges of this class, in place of the weight per km of their edge mode. None closes a class
        - `weight_at_hub`: With `weight_per_km`, `{node mode of a hub: {edge mode: weight}}`: the weight that is added to an edge of this edge mode when it leaves a node of this node mode, and when it enters one. `{"port": {"sea": 12}}` adds 12 to each sea edge that enters a port, and to each sea edge that leaves a port
        - `weighted_sum_of`: `{name of a metric: coefficient}`: the weight of an edge is the sum of its weight in each metric times the coefficient, a finite number above zero. `length` may be one of the metrics. An edge that is closed in one of these metrics is closed in the sum. The sum keeps its weights when one of these metrics is created again
        - `edge_weight_fn`: A function that takes the dictionary of an edge (see `get_edges`) and returns its weight. It is called once for each edge, and for the edges only. It needs `off_graph_weight_per_km`
        - `off_graph_weight_per_km`: With `edge_weight_fn`, the weight of 1 km of an off-graph leg, a finite number of zero or more. The other ways refuse it: a number of `weight_per_km` is also the weight per km of the off-graph legs, a dict of `weight_per_km` has the key `"off_graph"`, and a sum adds the weights per km of the off-graph legs of its metrics
        - `edge_weights`: `{(origin_id, destination_id): weight}`: the weight of these edges, in place of the weight computed above
        - `unit`: The unit of the weights, as free text
        - `description`: Where the weights come from, as free text; the text of this call when None

        Raises:

        - `ValueError`: An argument breaks a rule above. The message names the argument, or the two nodes of the first edge with a weight below zero or not a number
        """
        if (
            not (
                isinstance(name, str) and re.fullmatch("[a-z][a-z0-9_]*", name)
            )
            or name == "length"
        ):
            raise ValueError(
                "The name of a metric has small letters, digits and '_', starts "
                f"with a letter and is not 'length': got {name!r}"
            )
        if [weight_per_km, weighted_sum_of, edge_weight_fn].count(None) != 2:
            raise ValueError(
                "create_metric takes exactly one of weight_per_km, "
                "weighted_sum_of and edge_weight_fn"
            )
        if weight_per_km is None:
            if class_weight_per_km is not None:
                raise ValueError(
                    "class_weight_per_km needs weight_per_km: it replaces the "
                    "weight per km of the edge mode of a class"
                )
            if weight_at_hub is not None:
                raise ValueError(
                    "weight_at_hub needs weight_per_km: a hub weight is added "
                    "to the weight that a weight per km gives"
                )
        elif self.geograph_units != "km":
            raise ValueError(
                "weight_per_km needs lengths in km: the lengths of this "
                f"geograph are in {self.geograph_units!r}"
            )
        if edge_weight_fn is None:
            if off_graph_weight_per_km is not None:
                raise ValueError(
                    "off_graph_weight_per_km needs edge_weight_fn: weight_per_km "
                    "and weighted_sum_of give the weight of 1 km of an off-graph "
                    "leg themselves"
                )
        elif off_graph_weight_per_km is None:
            raise ValueError(
                "edge_weight_fn needs off_graph_weight_per_km: the weight of 1 km "
                "of an off-graph leg. The function is called for the edges only"
            )
        description = description or build_default_description(
            weight_per_km=weight_per_km,
            class_weight_per_km=class_weight_per_km,
            weight_at_hub=weight_at_hub,
            weighted_sum_of=weighted_sum_of,
            edge_weight_fn=edge_weight_fn,
            off_graph_weight_per_km=off_graph_weight_per_km,
            edge_weights=edge_weights,
        )
        offsets, heads, lengths = self._read_edge_arrays()
        units_per_km = get_units_per_km(self.geograph_units)
        if weight_per_km is not None:
            edge_class_ids = self._read_edge_class_ids()
            if edge_class_ids is None:
                # No edge has a class: `weight_per_km` is one weight per km for
                # every edge
                edge_class_ids = array(
                    "B", bytes([network_file.NO_CLASS_ID]) * len(heads)
                )
            # Nodes appended to `nodes` directly are in the first node mode
            node_mode_ids = self.node_mode_ids + array(
                "B", bytes(len(offsets) - 1 - len(self.node_mode_ids))
            )
            class_weights_per_km, hub_weights, off_graph_weight_per_km = (
                resolve_weights_per_km(
                    weight_per_km,
                    class_weight_per_km,
                    weight_at_hub,
                    self.classes,
                    self.node_modes,
                    edge_class_ids,
                )
            )
            weights = compute_weights_from_km(
                offsets,
                heads,
                lengths,
                edge_class_ids,
                node_mode_ids,
                class_weights_per_km,
                hub_weights,
            )
        elif weighted_sum_of is not None:
            weights, off_graph_weight_per_km = compute_weights_from_sum(
                weighted_sum_of, self._metrics, lengths, units_per_km
            )
        else:
            weights = compute_weights_from_function(
                edge_weight_fn, self._iter_edge_dicts(self._iter_edges())
            )
        if edge_weights:
            weights = copy_with_edge_weights(
                weights, edge_weights, offsets, heads
            )
        # The metric is kept when every check has passed
        self._metrics[name] = Metric(
            name,
            unit,
            description,
            weights,
            parse_off_graph_weight_per_km(name, off_graph_weight_per_km),
        )

    def remove_metric(self, name: str) -> None:
        """
        Function:

        - Remove a metric that `create_metric` made, or that a loader read
        - Example: `geograph.remove_metric("hours")`

        Required Arguments:

        - `name`: The name of a metric of `metrics`, other than `length`; an unknown name raises a ValueError
        """
        self._read_metric(name)
        del self._metrics[name]

    def get_graph_object(self, metric: str | None = None) -> Graph:
        """
        Function:

        - Get the `Graph` that a search by a metric runs on: the edges of the geograph, with the weights of the metric. A search called on it returns the total of the metric under the key `length`
        - For `length`, it is `graph_object`. For another metric, the graph is built at the first call and kept until the metric is created again or removed. It is reduced when `graph_object` is reduced (see `reduce`)
        - Example: `geograph.get_graph_object("hours").dijkstra(origin_id=0, destination_id=2)`

        Optional Arguments:

        - `metric`: The name of a metric of `metrics`; an unknown name raises a ValueError. None is the `default_metric` of the geograph, which is 'length' unless a loader or the caller set it
        """
        if metric is None:
            metric = self.default_metric
        if metric == "length":
            return self.graph_object
        metric_record = self._read_metric(metric)
        if metric_record.graph_object is None:
            offsets, heads, _ = self._read_edge_arrays()
            # The graph reads the three arrays in place and keeps them alive
            graph = Graph.from_csr(
                offsets, heads, metric_record.weights, copy=False
            )
            if self.graph_object.is_reduced is not None:
                graph.reduce(
                    -1
                    if self._reduce_iterations is None
                    else self._reduce_iterations
                )
            metric_record.graph_object = graph
        return metric_record.graph_object

    def get_nodes(
        self,
        node_mode: str | None = None,
        bbox: Sequence[float] | None = None,
    ) -> list[dict]:
        """
        Function:

        - Get the nodes of the geograph, or those of one node mode or inside a bounding box

        Optional Arguments:

        - `node_mode`: The name of a node mode of `node_modes`: only the nodes of this node mode are returned; an unknown name raises a ValueError
        - `bbox`: A bounding box `(south, west, north, east)` in degrees: only the nodes with `south <= latitude <= north` and `west <= longitude <= east` are returned

        Returns:

        - A list with one dictionary for each node, in the order of the node ids: `{"node_id", "latitude", "longitude", "node_mode"}`. `node_mode` is the name of the node mode of the node (None on a geograph without named node modes)
        """
        node_mode_names = [row.get("name") for row in self.node_modes]
        if node_mode is not None and node_mode not in node_mode_names:
            raise ValueError(
                f"Unknown node mode {node_mode!r}: the node modes of this "
                f"geograph are {node_mode_names}"
            )
        south, west, north, east = (
            (-inf, -inf, inf, inf) if bbox is None else bbox
        )
        nodes = []
        # A node appended to `nodes` directly is in the first node mode
        for node_id, (point, node_mode_id) in enumerate(
            zip_longest(self.nodes, self.node_mode_ids, fillvalue=0)
        ):
            if (
                node_mode in (None, node_mode_names[node_mode_id])
                and south <= point[0] <= north
                and west <= point[1] <= east
            ):
                nodes.append(
                    {
                        "node_id": node_id,
                        "latitude": point[0],
                        "longitude": point[1],
                        "node_mode": node_mode_names[node_mode_id],
                    }
                )
        return nodes

    def get_edges(
        self,
        origin_id: int | None = None,
        edge_class: str | None = None,
    ) -> list[dict]:
        """
        Function:

        - Get the edges of the geograph, or those of one node or of one class. With both arguments, only the edges that fit both are returned

        Optional Arguments:

        - `origin_id`: The id of a node: only the edges that leave this node are returned; an id that is not in the geograph raises a ValueError
        - `edge_class`: The name of a class of `classes`: only the edges of this class are returned; an unknown name raises a ValueError

        Returns:

        - A list with one dictionary for each edge, in the order of the origins: `{"origin_id", "destination_id", "length", "edge_class", "edge_mode", "metric_weights"}`
        - `length` is in `geograph_units`. `edge_class` is the name of the class of the edge and `edge_mode` is the edge mode of that class; both are None for an edge without a class
        - `metric_weights` is a dictionary `{name: weight}`: the weight of the edge in each metric other than `length`; infinity for an edge that is closed in the metric
        """
        offsets, heads, _ = self._read_edge_arrays()
        if origin_id is not None and not 0 <= origin_id < len(offsets) - 1:
            raise ValueError(f"Node {origin_id} is not in the geograph")
        self._edge_classes.check_class(edge_class)
        edges = self._iter_edges(origin_id)
        if edge_class is not None:
            find_class = self._edge_classes.find_class
            edges = (
                (origin_id, edge_id)
                for origin_id, edge_id in edges
                if find_class(origin_id, heads[edge_id])["name"] == edge_class
            )
        return list(self._iter_edge_dicts(edges))

    def _iter_edges(
        self, origin_id: int | None = None
    ) -> Iterator[tuple[int, int]]:
        """Return each edge of one node, or every edge for None, as (origin id,
        edge id), in the order of the edges."""
        offsets = self._read_edge_arrays()[0]
        origin_ids = (
            range(len(offsets) - 1) if origin_id is None else (origin_id,)
        )
        return (
            (origin_id, edge_id)
            for origin_id in origin_ids
            for edge_id in range(offsets[origin_id], offsets[origin_id + 1])
        )

    def _iter_edge_dicts(
        self, edges: Iterable[tuple[int, int]]
    ) -> Iterator[dict]:
        """Yield the dictionary of each edge, as `get_edges` returns it. `edges`
        gives each edge as (origin id, edge id)."""
        _, heads, lengths = self._read_edge_arrays()
        find_class = self._edge_classes.find_class
        weights_of_metrics = [
            (name, metric_record.weights)
            for name, metric_record in self._metrics.items()
        ]
        for origin_id, edge_id in edges:
            destination_id = heads[edge_id]
            class_row = find_class(origin_id, destination_id)
            yield {
                "origin_id": origin_id,
                "destination_id": destination_id,
                "length": lengths[edge_id],
                "edge_class": class_row["name"],
                "edge_mode": class_row["edge_mode"],
                "metric_weights": {
                    name: weights[edge_id]
                    for name, weights in weights_of_metrics
                },
            }

    def _find_path_edge_ids(self, path: list[int]) -> list[int]:
        # The id of each edge of a path
        offsets, heads, _ = self._read_edge_arrays()
        edge_ids = []
        for origin_id, destination_id in zip(path, path[1:]):
            edge_id = find_edge_id(offsets, heads, origin_id, destination_id)
            if edge_id is None:
                raise ValueError(
                    f"The geograph has no edge from node {origin_id} to node "
                    f"{destination_id}"
                )
            edge_ids.append(edge_id)
        return edge_ids

    def _get_path_total(self, path: list[int], metric: str) -> float:
        # The total of a metric along the edges of a path. The metric may be
        # `length`.
        lengths = self._read_edge_arrays()[2]
        weights = (
            lengths if metric == "length" else self._read_metric(metric).weights
        )
        return sum(
            weights[edge_id] for edge_id in self._find_path_edge_ids(path)
        )

    def get_path_edges(self, path: list[int]) -> list[dict]:
        """
        Function:

        - Get the edges of a path, in the order of the path

        Required Arguments:

        - `path`: The node ids of a path, as the `path` of `get_shortest_path` with `output_path=True`; two consecutive nodes without an edge raise a ValueError

        Returns:

        - A list with one dictionary for each pair of consecutive nodes of the path (see `get_edges`)
        """
        return list(
            self._iter_edge_dicts(zip(path, self._find_path_edge_ids(path)))
        )

    def _get_metric_totals(
        self,
        path: list[int],
        origin: Sequence[float],
        destination: Sequence[float],
        off_graph_circuity: float,
    ) -> dict[str, float]:
        """Return the total of each metric other than `length` along a route: the
        weight of each edge of `path`, plus the off-graph legs from the points
        `origin` and `destination` of the query. The weight of an off-graph leg is
        its km, times `off_graph_circuity`, times `off_graph_weight_per_km` of the
        metric."""
        off_graph_km = off_graph_circuity * self._get_off_graph_km(
            path, origin, destination
        )
        edge_ids = self._find_path_edge_ids(path)
        return {
            name: sum(metric_record.weights[edge_id] for edge_id in edge_ids)
            + off_graph_km * metric_record.off_graph_weight_per_km
            for name, metric_record in self._metrics.items()
        }

    def _get_off_graph_km(
        self,
        path: list[int],
        origin: Sequence[float],
        destination: Sequence[float],
    ) -> float:
        # The km of the two off-graph legs of a route, without circuity. A route
        # without a node is one off-graph leg from the origin to the destination.
        if not path:
            return haversine(origin, destination)
        return haversine(origin, self.nodes[path[0]]) + haversine(
            self.nodes[path[-1]], destination
        )

    def _get_legs(
        self,
        path: list[int],
        origin: Sequence[float],
        destination: Sequence[float],
        off_graph_circuity: float,
        get_intermediate_nodes: bool,
    ) -> tuple[list[dict], list[dict]]:
        """Return the legs and the transfers of a route, as `get_shortest_path`
        describes them. `_cut_legs` makes the legs on the network from the edges of
        `path`. An off-graph leg joins each point of the query to its node
        (`_get_off_graph_legs`). The lengths are in the units of the geograph, and
        each coordinate path is a list of [latitude, longitude]. `_format_leg` then
        gives a leg the units and the format that the query asks for."""
        legs = _cut_legs(self.get_path_edges(path))
        transfers = self._get_transfers(legs)
        for leg in legs:
            leg["coordinate_path"] = self.__get_coordinate_path__(
                leg.pop("path"), get_intermediate_nodes=get_intermediate_nodes
            )
        off_graph_legs = self._get_off_graph_legs(
            path, origin, destination, off_graph_circuity
        )
        return [off_graph_legs[0], *legs, *off_graph_legs[1:]], transfers

    def _get_transfers(self, legs: list[dict]) -> list[dict]:
        """Return the transfers of a route: each node where a leg on the network
        ends and the next one starts. `legs` are the legs of `_cut_legs`, which
        still have the node ids of their `path`."""
        transfers = []
        for leg in legs[1:]:
            node_id = leg["path"][0]
            node_mode = self.node_modes[self.node_mode_ids[node_id]]
            transfers.append(
                {"node_id": node_id, "node_mode": node_mode.get("name")}
            )
        return transfers

    def _get_off_graph_legs(
        self,
        path: list[int],
        origin: Sequence[float],
        destination: Sequence[float],
        off_graph_circuity: float,
    ) -> list[dict]:
        """Return the off-graph legs of a route, with the keys of a leg of
        `_cut_legs` and a `coordinate_path` in place of `path`. A route with an
        edge has two: from `origin` to the first node of `path`, and from its last
        node to `destination`. A route without an edge is one off-graph leg,
        through the node of its path if it has one. An off-graph leg has the
        weight that `_get_metric_totals` gives it in the totals of the route."""
        if len(path) > 1:
            off_graph_paths = [
                [origin, self.nodes[path[0]]],
                [self.nodes[path[-1]], destination],
            ]
        else:
            off_graph_paths = [
                [
                    origin,
                    *(self.nodes[node_id] for node_id in path),
                    destination,
                ]
            ]
        off_graph_legs = []
        for points in off_graph_paths:
            hops = list(zip(points, points[1:]))
            off_graph_km = off_graph_circuity * sum(
                haversine(start, end) for start, end in hops
            )
            off_graph_legs.append(
                {
                    "mode": "off_graph",
                    "length": sum(
                        haversine(
                            start,
                            end,
                            circuity=off_graph_circuity,
                            units=self.geograph_units,
                        )
                        for start, end in hops
                    ),
                    "metric_totals": {
                        name: off_graph_km
                        * metric_record.off_graph_weight_per_km
                        for name, metric_record in self._metrics.items()
                    },
                    "class_lengths": {},
                    "coordinate_path": points,
                }
            )
        return off_graph_legs

    def _format_leg(
        self, leg: dict, output_units: str, output_coordinate_path: str
    ) -> None:
        """Give a leg of `_get_legs` the form that a query asks for: its lengths in
        `output_units`, and its coordinate path in the format
        `output_coordinate_path`. A geograph without a metric gives no
        `metric_totals`. The leg is changed in place."""
        leg["length"] = distance_converter(
            leg["length"],
            input_units=self.geograph_units,
            output_units=output_units,
        )
        leg["class_lengths"] = {
            name: distance_converter(
                length,
                input_units=self.geograph_units,
                output_units=output_units,
            )
            for name, length in leg["class_lengths"].items()
        }
        leg["coordinate_path"] = self.__format_coordinates__(
            coordinate_path=leg["coordinate_path"],
            output_format=output_coordinate_path,
        )
        if not self._metrics:
            del leg["metric_totals"]

    def validate_nodes(self) -> None:
        """

        Function:

        - Validate that self.nodes is properly formatted (see GeoGraph.__init__ docs for more details)
        - Raises an exception if the nodes are invalid
        - Returns None if the nodes are valid

        Required Arguments:

        - None

        Optional Arguments:

        - None
        """
        if not (isinstance(self.nodes, (list, network_file.NodePoints))):
            raise ValueError("Your nodes must be a list")
        if not (all([isinstance(i, list) for i in self.nodes])):
            raise ValueError("Your nodes must be a list of lists")
        if not (all([len(i) == 2 for i in self.nodes])):
            raise ValueError(
                "Your nodes must be a list of lists where each sub list has a length of 2"
            )
        if not (
            all(
                [
                    (
                        isinstance(i[0], (int, float))
                        and isinstance(i[1], (int, float))
                    )
                    for i in self.nodes
                ]
            )
        ):
            raise ValueError(
                "Your nodes must be a list of lists where each sub list has a numeric latitude and longitude value"
            )
        if not (
            all(
                [
                    (
                        i[0] >= -90
                        and i[0] <= 90
                        and i[1] >= -180
                        and i[1] <= 180
                    )
                    for i in self.nodes
                ]
            )
        ):
            raise ValueError(
                "Your nodes must be a list of lists where each sub list has a length of 2 with a latitude [-90,90] and longitude [-180,180] value"
            )

    def __get_node_addition_type__(self, node_addition_type):
        if node_addition_type in ("kdclosest", "kdquadrant"):
            current = node_addition_type.removeprefix("kd")
            warnings.warn(
                f"The node addition type '{node_addition_type}' is deprecated. "
                f"Use '{current}', which gives the same result.",
                DeprecationWarning,
                stacklevel=3,
            )
            return current
        if node_addition_type not in ["closest", "quadrant", "all"]:
            raise ValueError(
                "node_addition_type must be one of 'kdclosest', 'kdquadrant', 'closest', 'quadrant', or 'all'"
            )
        return node_addition_type

    def __snap_node__(
        self,
        node,
        circuity,
        node_addition_type,
        lat_lon_bound,
        node_mode_snap_index=None,
    ):
        if node_addition_type == "closest":
            idx = (node_mode_snap_index or self.snap_index).closest_idx(
                point=node
            )
            return {
                idx: haversine(
                    node,
                    self.nodes[idx],
                    circuity=circuity,
                    units=self.geograph_units,
                )
            }
        elif node_addition_type == "quadrant":
            return {
                idx: haversine(
                    node,
                    self.nodes[idx],
                    circuity=circuity,
                    units=self.geograph_units,
                )
                for idx in self.__get_quadrant_node_indices__(
                    node, node_mode_snap_index
                )
            }
        else:
            return self.__get_node_distances__(
                node=node,
                circuity=circuity,
                node_addition_type=node_addition_type,
                lat_lon_bound=lat_lon_bound,
                node_mode_snap_index=node_mode_snap_index,
            )
        raise ValueError(
            "node_addition_type must be one of 'closest', 'quadrant', or 'all'"
        )

    def get_shortest_path(
        self,
        origin_node: dict[str, float],
        destination_node: dict[str, float],
        *,
        output_units: str = "km",
        algorithm_fn: str | Callable = "bidirectional_buckets",
        algorithm_kwargs: dict | None = None,
        off_graph_circuity: float = 1,
        node_addition_type: str = "closest",
        node_addition_circuity: float = 4,
        output_coordinate_path: str = "list_of_lists",
        output_path: bool = False,
        node_addition_lat_lon_bound: float | Literal["auto"] = "auto",
        node_addition_math: str = "euclidean",
        destination_node_addition_type: str = "closest",
        auto_lat_lon_bound_max: float = 2,
        silent: bool | None = None,
        length_only: bool = False,
        get_intermediate_nodes: bool | None = None,
        metric: str | None = None,
        node_addition_modes: list[str] | None = None,
        output_legs: bool = False,
        **kwargs,
    ) -> dict:
        """
        Function:

        - Identify the shortest path between two nodes in a sparse network graph

        - Return a dictionary of various path information including:
            - `path`: With `output_path=True`, a list of node ids in the order they are visited
            - `coordinate_path`: A list of coordinates (latitude then longitude) in the order they are visited, in the format of `output_coordinate_path`
            - `length`: The length of the path
            - `metric_totals`: On a geograph that has metrics other than `length` (see `metrics`), a dictionary `{name: total}` with the total of each of these metrics along the path
            - `legs`: With `output_legs=True`, the legs of the path in their order. A leg is a part of the path on one mode, as a dictionary `{"mode", "length", "metric_totals", "class_lengths", "coordinate_path"}`
                - `mode` is the edge mode of the edges of the leg (see `classes`). A new leg starts where this edge mode changes. The edges of a geograph without classes make one leg of the mode None
                - The first and the last leg are the off-graph legs, of the mode 'off_graph': the straight lines from the origin to the first node of the path, and from its last node to the destination. A path without an edge is one leg of the mode 'off_graph'
                - `length` and `metric_totals` are the totals of the leg, as those of the path. The length of the path is the sum of the lengths of its legs, and so is each total of `metric_totals`. A leg has the key `metric_totals` only when the path has it
                - `class_lengths` is a dictionary `{class name: length}`: the length of the leg on each class of edges, in `output_units`. It is empty for an off-graph leg
                - `coordinate_path` holds the coordinates of the leg, in the format of `output_coordinate_path`
            - `transfers`: With `output_legs=True`, a list of dictionaries `{"node_id", "node_mode"}`: each node where the path goes from a leg of one edge mode to a leg of another, with the node mode of this node (see `node_modes`). The two nodes where an off-graph leg meets the network are not transfers

         Required Arguments:

        - `origin_node`
            - Type: dict of int | float
            - What: A dictionary with the keys 'latitude' and 'longitude'
        - `destination_node`
            - Type: dict of int | float
            - What: A dictionary with the keys 'latitude' and 'longitude'

        Optional Arguments:

        - `output_units`
            - Type: str
            - What: The units in which to return the length of the path
            - Default: 'km'
            - Options:
                - 'km': Kilometers
                - 'm': Meters
                - 'mi': Miles
                - 'ft': Feet
        - `algorithm_fn`
            - Type: str | callable
            - What: The algorithm to use for shortest path calculation. Can be a string name of a method on the underlying Graph object, or any callable.
            - Default: 'bidirectional_buckets'
            - Options:
                - 'bidirectional_buckets' -> GraphAlgorithms.bidirectional_buckets
                    - Bidirectional Dijkstra with buckets (Dial's algorithm); default algorithm for GeoGraphs, very fast for sparse spatial networks
                - 'dijkstra' -> GraphAlgorithms.dijkstra
                    - Standard Dijkstra's algorithm; general purpose for non-negative edge weights
                - 'bidirectional_dijkstra' -> GraphAlgorithms.bidirectional_dijkstra
                    - Bidirectional Dijkstra's algorithm; searches from both origin and destination simultaneously
                - 'dijkstra_buckets' -> GraphAlgorithms.dijkstra_buckets
                    - Dijkstra with buckets (Dial's algorithm); efficient for non-negative weights
                - 'dijkstra_negative' -> GraphAlgorithms.dijkstra_negative
                    - Modified Dijkstra supporting negative edge weights; detects negative cycles
                - 'a_star' -> GraphAlgorithms.a_star
                    - A* algorithm; requires a heuristic_fn passed via algorithm_kwargs for speedup
                - 'bellman_ford' -> GraphAlgorithms.bellman_ford
                    - Bellman-Ford algorithm; supports negative weights but slower than dijkstra
                - 'bmssp' -> GraphAlgorithms.bmssp
                    - BMSSP algorithm; not actually faster in practice than dijkstra but included for completeness
                - 'cached_shortest_path' -> GraphAlgorithms.cached_shortest_path
                    - Computes and caches the full shortest path tree from the origin on the first call;
                      subsequent calls from the same origin node are near-instant
                    - Only the origin graph node is cached (not the off-graph origin point)
                    - Note: Requires that both node_addition_type and destination_node_addition_type are 'kdclosest'
                - 'contraction_hierarchy' -> GraphAlgorithms.contraction_hierarchy
                    - Bidirectional Dijkstra on a preprocessed Contraction Hierarchy graph
                    - Requires one-time preprocessing via graph_object.create_contraction_hierarchy()
                      (called automatically on first use if not already done)
                    - Very fast for arbitrary origin-destination queries on large graphs
                    - Note: Requires that both node_addition_type and destination_node_addition_type are 'kdclosest'
                - 'tnr' -> TNRGraph.search
                    - Transit Node Routing; extremely fast for global queries on large graphs
                    - Requires preprocessing via TNRGraph initialization or create_tnr_hierarchy()
                    - Note: Requires that both node_addition_type and destination_node_addition_type are 'kdclosest'
                - Any callable that accepts:
                    - `graph`: The graph (list[dict[int, int | float]]) to perform the shortest path on
                    - `origin_id`: The id of the origin node
                    - `destination_id`: The id of the destination node
                    - `**algorithm_kwargs`: Additional keyword arguments
        - `algorithm_kwargs`
            - Type: dict
            - What: Additional keyword arguments to pass to the algorithm function assuming it accepts them
        - `off_graph_circuity`
            - Type: int | float
            - What: The physical distance multiplier applied to final off-graph access legs (origin -> entrance node and exit node -> destination) after the route is solved
            - Default: 1 (more specifically `self.default_off_graph_circuity`)
            - Notes:
                - During pathfinding, `node_addition_circuity` is used to penalize off-graph travel and select the entry/exit nodes
                - Once the optimal route sequence is determined, the actual reported `length` scales the access distance by `off_graph_circuity`
                - Set to 0 if access legs should not contribute to total route length/time
        - `node_addition_type`
            - Type: str
            - What: The snapping strategy used to connect off-graph origin and destination coordinates to the network
            - Default: 'closest'
            - Options:
                - 'kdclosest' / 'closest': Snap to the single closest node using `snap_index`
                - 'kdquadrant' / 'quadrant': Snap to the closest node in each spatial quadrant (up to 4 candidates)
                - 'all': Snap to all nodes within the spatial bounding box
        - `node_addition_circuity`
            - Type: int | float
            - What: The algorithmic search penalty applied to candidate off-graph connection legs *during* pathfinding
            - Default: 4 (more specifically `self.default_node_addition_circuity`)
            - Notes:
                - Penalizes off-network travel relative to on-network routing to prevent shortcuts across impassable terrain (e.g. crossing land in a maritime graph)
                - A higher penalty pushes the route to enter the network at a closer node rather than traveling off-graph towards the destination
                - Active when `node_addition_type` is 'quadrant' or 'all' (not needed for 'closest' where only one entry node exists)
                - Only influences route selection; final reported `length` uses `off_graph_circuity`
        - `output_coordinate_path`
            - Type: str
            - What: The format of the output coordinate path
            - Default: 'list_of_lists'
            - Options:
                - 'list_of_dicts': A list of dictionaries with keys 'latitude' and 'longitude'
                - 'list_of_lists': A list of lists with the first value being latitude and the second being longitude
                - 'list_of_lists_long_first': A list of lists with the first value being longitude and the second being latitude
        - `output_path`
            - Type: bool
            - What: Whether to output the path as a list of geograph node ids (for debugging and other advanced uses)
            - Default: False
        - `node_addition_lat_lon_bound`
            - Type: int | float | Literal["auto"]
            - What: Forms a bounding box around the origin and destination nodes as they are added to graph
                - The bound filters candidates only when node_addition_type is 'all'
            - Default: 'auto'
            - If set to 'auto', the bounding box is set based on the distance between the origin and destination nodes capped at `auto_lat_lon_bound_max` for the origin node
            - Note: This is only used when adding a new node (the specified origin and destination) to the graph
        - `auto_lat_lon_bound_max`
            - Type: int | float
            - What: The maximum value for the automatic latitude/longitude bounding box used only for the origin node when `node_addition_lat_lon_bound` is set to 'auto'
            - Default: 2
            - Note: Only used if `node_addition_lat_lon_bound` is set to 'auto'
        - `node_addition_math`
            - Type: str
            - What: Deprecated but kept for backwards compatibility.
        - `destination_node_addition_type`
            - Type: str
            - What: The method to use when adding the destination node to the graph
            - Default: 'closest'
            - Options:
                - 'kdclosest' / 'closest': Add the closest node with the snapping index (`snap_index`)
                - 'kdquadrant' / 'quadrant': Add the closest node in each quadrant with the snapping index (`snap_index`)
                - 'all': Add the node to all points in the graph within the bounding box
        - `silent`
            - Deprecated and without effect. scgraph reports its messages through `logging`.
        - `length_only`
            - Type: bool
            - What: If True, only returns the length of the path
            - Note: With a `metric` other than 'length', only returns the total of this metric: `{"metric_totals": {metric: total}}`
            - Note: `output_legs` is then ignored, as `output_path` is
            - Default: False
        - `get_intermediate_nodes`
            - Type: bool
            - What: If True, returns the intermediate nodes in the path (if they exist for each segment)
            - Default: self.default_get_intermediate_nodes
        - `metric`
            - Type: str
            - What: The name of the metric to minimise, a name of `metrics`: the path is the one with the smallest total of this metric. `length` in the result stays the length of the path
            - Default: None (the `default_metric` of the geograph, which is 'length' unless a loader or the caller set it)
            - Notes:
                - EG: `geograph.get_shortest_path(origin_node, destination_node, metric="hours")`
                - The search runs on `get_graph_object(metric)`. An unknown name raises a ValueError
                - When no route by the metric joins the two points, the PathNotFoundError names the metric: an edge that is closed in the metric cannot be taken
                - With `algorithm_fn='a_star'`, the bound of `geograph.haversine` or of `geograph.cheap_ruler` is a length: the geograph multiplies it by the smallest weight of 1 km of an edge in the metric. Another `heuristic_fn` is used as it is: it must give a lower bound of the total of the metric between two nodes
                - The weight of an off-graph leg is its km times the weight of 1 km in the metric (`off_graph_weight_per_km` in `metrics`), with `node_addition_circuity` during pathfinding and with `off_graph_circuity` in the reported totals
        - `node_addition_modes`
            - Type: list of str | None
            - What: The names of the node modes (see `node_modes`) that the origin and the destination may snap to: each one is connected only to nodes of these node modes, for every `node_addition_type`
            - Default: None (the node modes of `default_node_addition_modes` that have a node in the geograph, and the nodes without a named node mode, such as a node that `add_coord_node` added without `node_mode`; every node mode if there are none)
            - Notes:
                - EG: `geograph.get_shortest_path(origin_node, destination_node, node_addition_modes=["road"])` starts and ends the path on a road, also when a railway or a sea lane is closer
                - An empty list, a name that is not in `node_modes`, or node modes that no node has, raise a ValueError
                - The first query that snaps to a node mode builds the snapping index of its nodes. The geograph keeps it until its nodes change
        - `output_legs`
            - Type: bool
            - What: Whether to output the legs of the path and its transfers, under the keys `legs` and `transfers` described above
            - Default: False
        - `**kwargs`
            - Additional keyword arguments. These are included for forwards and backwards compatibility reasons, but are not currently used.
        """
        warn_deprecated_parameter("silent", silent)
        algorithm_name = (
            algorithm_fn if isinstance(algorithm_fn, str) else "custom"
        )
        get_intermediate_nodes = (
            get_intermediate_nodes
            if get_intermediate_nodes is not None
            else self.default_get_intermediate_nodes
        )
        off_graph_circuity = (
            off_graph_circuity
            if off_graph_circuity is not None
            else self.default_off_graph_circuity
        )
        node_addition_circuity = (
            node_addition_circuity
            if node_addition_circuity is not None
            else self.default_node_addition_circuity
        )
        algorithm_kwargs = (
            dict(algorithm_kwargs) if algorithm_kwargs is not None else dict()
        )
        if metric is None:
            metric = self.default_metric
        # The graph whose weights are those of the metric
        graph_object = self.get_graph_object(metric)
        is_metric_other_than_length = metric != "length"
        if callable(algorithm_fn):
            algorithm_kwargs["graph"] = graph_object.unreduced_graph
        elif isinstance(algorithm_fn, str):
            heuristic_fn = algorithm_kwargs.get("heuristic_fn")
            # The methods `haversine` and `cheap_ruler` of scgraph, for this
            # geograph: each gives a length between two of its nodes. The function
            # of the caller is equal to one of them only when the caller passed
            # this method of this geograph. A subclass that defines its own
            # `haversine` passes another function, which is used as it is.
            haversine_of_scgraph = types.MethodType(
                GeoGraphDistanceCalculations.haversine, self
            )
            cheap_ruler_of_scgraph = types.MethodType(
                GeoGraphDistanceCalculations.cheap_ruler, self
            )
            if (
                algorithm_fn == "a_star"
                and hasattr(graph_object, "a_star_great_circle")
                and heuristic_fn == haversine_of_scgraph
            ):
                # The built-in haversine heuristic is computed natively in the C++ build
                latitudes, longitudes = self._get_node_radians()
                algorithm_kwargs.pop("heuristic_fn")
                radius = earth_radius.get(self.geograph_units, 6371)
                if is_metric_other_than_length:
                    # The total of a route of the length d is at least d times
                    # `min_weight_per_length_unit`: the radius times it is the bound.
                    radius *= self._read_metric(
                        metric
                    ).get_min_weight_per_length_unit(
                        self._read_edge_arrays()[2]
                    )
                algorithm_fn = partial(
                    graph_object.a_star_great_circle,
                    latitudes=latitudes,
                    longitudes=longitudes,
                    radius=radius,
                )
            elif hasattr(graph_object, algorithm_fn):
                if (
                    is_metric_other_than_length
                    and algorithm_fn == "a_star"
                    and heuristic_fn == cheap_ruler_of_scgraph
                ):
                    # `cheap_ruler` gives a length. The bound of the metric is this
                    # length times `min_weight_per_length_unit`, as for `haversine`.
                    min_weight_per_length_unit = self._read_metric(
                        metric
                    ).get_min_weight_per_length_unit(
                        self._read_edge_arrays()[2]
                    )
                    algorithm_kwargs["heuristic_fn"] = (
                        lambda origin_id, destination_id: min_weight_per_length_unit
                        * heuristic_fn(origin_id, destination_id)
                    )
                algorithm_fn = getattr(graph_object, algorithm_fn)
            else:
                raise ValueError("algorithm_fn must be a string or callable")
        else:
            raise ValueError("algorithm_fn must be a string or callable")

        node_addition_type = self.__get_node_addition_type__(node_addition_type)
        destination_node_addition_type = self.__get_node_addition_type__(
            destination_node_addition_type
        )
        node_mode_snap_index = self._get_node_mode_snap_index(
            node_addition_modes
        )

        # If auto lat lon bounds are needed, then calculate them.
        if "all" in [node_addition_type, destination_node_addition_type]:
            if node_addition_lat_lon_bound == "auto":
                node_addition_lat_lon_bound = min(
                    get_lat_lon_bound_between_pts(origin_node, destination_node)
                    * 1.01,
                    auto_lat_lon_bound_max,
                )
        try:
            # Parse origin and destination
            origin = [
                origin_node.get("latitude"),
                origin_node.get("longitude"),
            ]
            destination = [
                destination_node.get("latitude"),
                destination_node.get("longitude"),
            ]
            if len(origin) < 1 or len(destination) < 1:
                raise ValueError(
                    "Origin and destination must have valid latitude and longitude"
                )

            # Get the node addition direct distance between origin and destination
            direct_node_addition_length = haversine(
                origin,
                destination,
                circuity=node_addition_circuity,
                units=self.geograph_units,
            )

            # Snap the origin and destination to their closest nodes in the graph
            origin_id = self.__snap_node__(
                node=origin,
                circuity=node_addition_circuity,
                node_addition_type=node_addition_type,
                lat_lon_bound=node_addition_lat_lon_bound,
                node_mode_snap_index=node_mode_snap_index,
            )
            destination_id = self.__snap_node__(
                node=destination,
                circuity=node_addition_circuity,
                node_addition_type=destination_node_addition_type,
                lat_lon_bound=node_addition_lat_lon_bound,
                node_mode_snap_index=node_mode_snap_index,
            )

            # Calculate the circuity ratio for the node addition
            circuity_ratio = (
                off_graph_circuity / node_addition_circuity
                if node_addition_circuity != 0
                else 1.0
            )

            # If direct distance is better than any entry or exit distance, bypass graph search
            min_entry_exit = min(
                min(origin_id.values()), min(destination_id.values())
            )
            is_direct = direct_node_addition_length <= min_entry_exit
            if is_metric_other_than_length:
                # In the search, the weight of an off-graph leg is its km times the
                # weight of 1 km. The test above compares lengths: a metric whose
                # off-graph legs have a weight of zero must not make every route direct.
                off_graph_weight_per_unit = self._read_metric(
                    metric
                ).off_graph_weight_per_km / get_units_per_km(
                    self.geograph_units
                )
                direct_node_addition_length *= off_graph_weight_per_unit
                origin_id = {
                    node_id: length * off_graph_weight_per_unit
                    for node_id, length in origin_id.items()
                }
                destination_id = {
                    node_id: length * off_graph_weight_per_unit
                    for node_id, length in destination_id.items()
                }

            if logger.isEnabledFor(logging.DEBUG):
                self.graph_object._reset_node_scans()
            if is_direct:
                output = {
                    "path": [],
                    "length": direct_node_addition_length * circuity_ratio,
                }
            else:
                output = algorithm_fn(
                    origin_id=origin_id,
                    destination_id=destination_id,
                    **algorithm_kwargs,
                )
                if circuity_ratio != 1.0:
                    entry_node = (
                        output["path"][0]
                        if output.get("path")
                        else next(iter(origin_id.keys()))
                    )
                    exit_node = (
                        output["path"][-1]
                        if output.get("path")
                        else next(iter(destination_id.keys()))
                    )
                    output["length"] += (
                        origin_id[entry_node] + destination_id[exit_node]
                    ) * (circuity_ratio - 1.0)
            if logger.isEnabledFor(logging.DEBUG):
                self._log_query_indicators(
                    algorithm_name,
                    origin,
                    destination,
                    origin_id,
                    destination_id,
                )

            if is_metric_other_than_length:
                # The search returned the total of the metric. `length` stays the
                # length of the route.
                metric_total = output["length"]
                if length_only:
                    return {"metric_totals": {metric: metric_total}}
                output["length"] = self.get_path_weight(
                    {
                        "path": output["path"],
                        "coordinate_path": [origin, destination],
                    },
                    off_graph_circuity=off_graph_circuity,
                    output_units=self.geograph_units,
                    metric="length",
                )
            # Convert the length to the desired output units
            output["length"] = distance_converter(
                output["length"],
                input_units=self.geograph_units,
                output_units=output_units,
            )
            # Early return if only length is needed
            if length_only:
                return {"length": output["length"]}
            if self._read_metrics():
                output["metric_totals"] = self._get_metric_totals(
                    output["path"], origin, destination, off_graph_circuity
                )
                if is_metric_other_than_length:
                    output["metric_totals"][metric] = metric_total

            # Get the coordinate path
            output["coordinate_path"] = (
                [origin]
                + self.__get_coordinate_path__(
                    output["path"],
                    get_intermediate_nodes=get_intermediate_nodes,
                )
                + [destination]
            )

            # Format the coordinate path to the desired output format
            if output_coordinate_path != "list_of_lists":
                output["coordinate_path"] = self.__format_coordinates__(
                    coordinate_path=output["coordinate_path"],
                    output_format=output_coordinate_path,
                )
                if output_coordinate_path == "list_of_lists_long_first":
                    output["long_first"] = True

            if output_legs:
                output["legs"], output["transfers"] = self._get_legs(
                    output["path"],
                    origin,
                    destination,
                    off_graph_circuity,
                    get_intermediate_nodes,
                )
                for leg in output["legs"]:
                    self._format_leg(leg, output_units, output_coordinate_path)
            if not output_path:
                del output["path"]
            return output

        except PathNotFoundError as error:
            if is_metric_other_than_length:
                raise PathNotFoundError(
                    f"No route by the metric {metric!r} joins the two points. An "
                    "edge that is closed in this metric cannot be taken: check the "
                    "weights of the metric, and `node_addition_modes`, which names "
                    "the node modes that the points snap to."
                ) from error
            error.add_note(
                "This is likely caused by a disconnect in the graph. Setting"
                " destination_node_addition_type='all' and"
                " node_addition_lat_lon_bound=180 ensures a solution, at a much"
                " longer runtime per query."
            )
            raise

    def _log_query_indicators(
        self,
        algorithm_name: str,
        origin: Sequence[float],
        destination: Sequence[float],
        origin_entries: dict[int, int | float],
        destination_entries: dict[int, int | float],
    ) -> None:
        """
        Logs at DEBUG the indicators of a shortest-path query: what the query did, which
        its result does not show.

        - `algorithm_name`: the name of the search, or "custom" for a search function
        - `origin`, `destination`: the [latitude, longitude] of the two ends of the query
        - `origin_entries`, `destination_entries`: the graph nodes that each end was
          joined to, with the cost to reach each node
        - The snapping distance of an end is the great-circle distance to its closest
          entry node, in the units of the geograph, without circuity
        - `node_scans` is present only if the query ran a search that counts them
        - A query builds this record only when DEBUG is on, and does not use `log_step`:
          a query must pay nothing for logging when DEBUG is off. It logs no duration,
          which the caller can measure around its own call
        """
        origin_node = min(origin_entries, key=origin_entries.__getitem__)
        destination_node = min(
            destination_entries, key=destination_entries.__getitem__
        )
        step = "find the shortest path"
        indicators = {
            "algorithm": algorithm_name,
            "distance_units": self.geograph_units,
            "origin_snap_distance": round(
                haversine(
                    origin, self.nodes[origin_node], units=self.geograph_units
                ),
                3,
            ),
            "destination_snap_distance": round(
                haversine(
                    destination,
                    self.nodes[destination_node],
                    units=self.geograph_units,
                ),
                3,
            ),
        }
        node_scans = self.graph_object._get_last_node_scans()
        if node_scans is not None:
            indicators["node_scans"] = node_scans
        logger.debug(
            "%s: %s",
            step,
            indicators,
            extra={"scgraph": {"step": step, **indicators}},
        )

    def distance_matrix(
        self,
        nodes: list[dict[str, float]],
        off_graph_circuity: float = 1,
        output_units: str = "km",
        silent: bool | None = None,
        *,
        metric: str | None = None,
        output_metric: str | None = None,
        node_addition_modes: list[str] | None = None,
    ) -> list[list[int | float | None]]:
        """
        Function:

        - Calculate the distance matrix for a list of nodes in a very efficient way using cached shortest path trees and cached node addition distances
        - This should run in O(((n+m)*log(n)*i) + (i*i)) time where i is the number of nodes in the distance matrix, n is the number of nodes in the graph, and m is the number of edges in the graph
           - Compare this to a naive matrix implementation time of O(((n+m)*log(n)*(i*i)) where paths are fetched for each pair of nodes in the distance matrix without caching
        - This is useful for calculating the distance between multiple nodes at the same time

        Required Arguments:

        - `nodes`
            - Type: list[dict[str, float | int]]
            - What: A list of dictionaries with the keys 'latitude' and 'longitude'
            - EG: [{"latitude": 39.2904, "longitude": -76.6122}, {"latitude": 39.2905, "longitude": -76.6123}]

        Optional Arguments:

        - `off_graph_circuity`
            - Type: float | int
            - What: The circuity to apply to the distance calculations for nodes that are not in the graph
            - Default: 1
        - `output_units`
            - Type: str
            - What: The units of the output distance matrix
            - Default: 'km'
            - Options: 'km', 'm', 'mi', 'ft'
            - Note: Ignored when the matrix holds the totals of a metric other than 'length'
        - `silent`
            - Deprecated and without effect. scgraph reports its messages through `logging`.
        - `metric`
            - Type: str
            - What: The name of the metric to minimise, a name of `metrics`: the path between two nodes is the one with the smallest total of this metric
            - Default: None (the `default_metric` of the geograph, which is 'length' unless a loader or the caller set it)
        - `output_metric`
            - Type: str | None
            - What: The name of the metric that the matrix holds: the entry at (i, j) is the total of this metric along the path between node i and node j
            - Default: None (the metric of `metric`)
            - Notes:
                - EG: `geograph.distance_matrix(nodes, metric="hours", output_metric="length")` gives the lengths of the fastest paths
                - With an `output_metric` other than `metric`, the call is slower: it reads the path of each pair, where it otherwise reads only its total
        - `node_addition_modes`
            - Type: list of str | None
            - What: The names of the node modes (see `node_modes`) that the nodes of the matrix may snap to, as in `get_shortest_path`
            - Default: None (as in `get_shortest_path`)

        Returns:

        - A list of lists representing the distance matrix between the nodes
        - The distance matrix is a square matrix where the entry at (i, j) is the distance between node i and node j
        - A pair of nodes without a path has the distance None, and the call warns once with the number of such pairs
        - The distances are in the units specified by `output_units`
        - An unknown `metric` or `output_metric` raises a ValueError
        - EG:
        ```
        [
            [0.0, 0.1, ...],
            [0.1, 0.0, ...],
            ...
        ]
        """
        warn_deprecated_parameter("silent", silent)
        failed_pairs = 0
        output_matrix = [[None] * len(nodes) for _ in range(len(nodes))]
        if metric is None:
            metric = self.default_metric
        graph_object = self.get_graph_object(metric)
        if output_metric is None:
            output_metric = metric
        if output_metric == "length":
            dist_multiplier = distance_converter(
                distance=1,
                input_units=self.geograph_units,
                output_units=output_units,
            )
            off_graph_units, off_graph_weight_per_unit = output_units, 1
        else:
            # The total of a metric is not converted. The weight of an off-graph leg
            # is its km times the weight of 1 km in the metric.
            dist_multiplier, off_graph_units = 1, "km"
            off_graph_weight_per_unit = self._read_metric(
                output_metric
            ).off_graph_weight_per_km
        snap_index = (
            self._get_node_mode_snap_index(node_addition_modes)
            or self.snap_index
        )
        # Get the entry idx for each node as well as the distance to that node given the off-graph circuity
        # [(entry_idx, distance), ...]
        entry_idx_and_distance = []
        for node in nodes:
            node_idx = snap_index.closest_idx(
                point=[node["latitude"], node["longitude"]]
            )
            distance = (
                haversine(
                    [node["latitude"], node["longitude"]],
                    self.nodes[node_idx],
                    circuity=off_graph_circuity,
                    units=off_graph_units,  # Store directly as output units since this is a post processing step
                )
                * off_graph_weight_per_unit
            )
            entry_idx_and_distance.append((node_idx, distance))

        for node_idx_start, (entry_idx_start, entry_length_start) in enumerate(
            entry_idx_and_distance
        ):
            for node_idx_end, (entry_idx_end, entry_length_end) in enumerate(
                entry_idx_and_distance
            ):
                if entry_idx_start == entry_idx_end:
                    output_matrix[node_idx_start][node_idx_end] = 0.0
                    continue
                try:
                    if output_metric == metric:
                        length = graph_object.cached_shortest_path(
                            origin_id=entry_idx_start,
                            destination_id=entry_idx_end,
                            length_only=True,
                        )["length"]
                    else:
                        path = graph_object.cached_shortest_path(
                            origin_id=entry_idx_start,
                            destination_id=entry_idx_end,
                        )["path"]
                        length = self._get_path_total(path, output_metric)
                    output_matrix[node_idx_start][node_idx_end] = (
                        (length * dist_multiplier)
                        + entry_length_start
                        + entry_length_end
                    )
                except PathNotFoundError:
                    failed_pairs += 1
        if failed_pairs:
            warnings.warn(
                f"{failed_pairs} pair(s) of nodes have no path between them:"
                " their distance is None",
                stacklevel=2,
            )
        return output_matrix


class LazyGeoGraph(GeoGraph):
    """
    A lazy-loading proxy for GeoGraph that delays loading/fetching the graph
    until its first attribute access or method invocation.
    """

    def __init__(self, loader_fn) -> None:
        object.__setattr__(self, "_loader_fn", loader_fn)
        object.__setattr__(self, "_initialized", False)

    def _load(self) -> "GeoGraph":
        if not object.__getattribute__(self, "_initialized"):
            loader_fn = object.__getattribute__(self, "_loader_fn")
            real_geo = loader_fn()
            object.__setattr__(self, "_initialized", True)
            object.__getattribute__(self, "__dict__").update(real_geo.__dict__)
        return self

    def load(self) -> "GeoGraph":
        """Explicitly load the underlying GeoGraph if not already loaded."""
        return self._load()

    def __getattribute__(self, name: str):
        if name in (
            "_loader_fn",
            "_initialized",
            "_load",
            "load",
            "__class__",
        ):
            return object.__getattribute__(self, name)
        if not object.__getattribute__(self, "_initialized"):
            object.__getattribute__(self, "_load")()
        return object.__getattribute__(self, name)

    def __setattr__(self, name: str, value) -> None:
        if name in ("_loader_fn", "_initialized"):
            object.__setattr__(self, name, value)
        else:
            if not object.__getattribute__(self, "_initialized"):
                object.__getattribute__(self, "_load")()
            super().__setattr__(name, value)

    def __delattr__(self, name: str) -> None:
        if name in ("_loader_fn", "_initialized"):
            object.__delattr__(self, name)
        else:
            if not object.__getattribute__(self, "_initialized"):
                object.__getattribute__(self, "_load")()
            super().__delattr__(name)

    def __repr__(self) -> str:
        if not object.__getattribute__(self, "_initialized"):
            return f"<LazyGeoGraph (not loaded) at {hex(id(self))}>"
        return f"<LazyGeoGraph (loaded) at {hex(id(self))}>"

    def __dir__(self) -> list[str]:
        self._load()
        return super().__dir__()
