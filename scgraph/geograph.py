from scgraph.utils import (
    haversine,
    distance_converter,
    get_line_path,
    cheap_ruler,
    print_console,
    get_lat_lon_bound_between_pts,
    resolve_cache_dir,
    earth_radius,
    radians_per_degree,
)
from scgraph.helpers.geojson import parse_geojson, simplify_geojson
from scgraph.helpers.lines import lines_to_graph
from scgraph.helpers.hilbert import NODE_ORDER, hilbert_order
from scgraph import network_file
import difflib, hashlib, importlib, json, logging, os, re, requests, secrets, shutil
import tempfile
import warnings
from array import array
from collections import Counter
from operator import eq
from copy import deepcopy
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from functools import partial
from pathlib import Path
from typing import Literal
from scgraph import Graph

try:
    from scgraph.cpp import SnapIndex
except ImportError:
    from scgraph.helpers.snap_index import SnapIndex

logger = logging.getLogger(__name__)


def _names_a_file(manifest_file: Path) -> bool:
    # A built network counts as cached only if the file its manifest names is there
    try:
        name = Path(json.loads(manifest_file.read_text())["file"]).name
    except (OSError, ValueError, KeyError, TypeError):
        return False
    return manifest_file.parent.joinpath(name).is_file()


# Written in networks/ of the cache: backup and archiving tools skip a tagged directory
_CACHEDIR_TAG = (
    "Signature: 8a477f597d28d172789f06886806bc55\n"
    "# This file is a cache directory tag created by scgraph."
    " For information about cache directory tags, see https://bford.info/cachedir/\n"
)


_GEOGRAPH_URL = (
    "https://raw.githubusercontent.com/connor-makowski/scgraph/main/geographs"
)
# The built-in geographs published for load_geograph (contents.txt of the geograph URL); they are
# no longer updated
_PUBLISHED_GEOGRAPHS = (
    "marnet",
    "north_america_rail",
    "oak_ridge_maritime",
    "us_freeway",
    "world_highways_and_marnet",
    "world_highways",
    "world_railways",
)


class GeoGraphIO:
    def __get_edge_coordinates__(
        self,
        origin_idx: int,
        destination_idx: int,
        sequence: str,
        save_intermediate_nodes: bool,
    ) -> list[list[float | int]]:
        """Build the coordinates for one exported edge."""
        origin = self.nodes[origin_idx]
        destination = self.nodes[destination_idx]
        if sequence == "lon_lat":
            coordinates = [[origin[1], origin[0]]]
            final_coordinate = [destination[1], destination[0]]
        else:
            coordinates = [origin]
            final_coordinate = destination

        if self.intermediate_nodes is not None and save_intermediate_nodes:
            coordinates.extend(
                self.__get_intermediate_nodes__(
                    origin_idx=origin_idx,
                    destination_idx=destination_idx,
                    sequence=sequence,
                )
            )
        coordinates.append(final_coordinate)
        return coordinates

    # Save Methods

    def save_as_geojson(
        self,
        filename: str,
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
        self, filename: str, save_intermediate_nodes: bool = True
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
        if not filename.endswith(".graphjson"):
            raise ValueError("Filename must end with .graphjson")
        # A cached network must stay the one its manifest describes
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
        filename: str,
        save_intermediate_nodes: bool = True,
        sources: list[dict] | None = None,
    ) -> str:
        """
        Function:

        - Save the current geograph as a binary network file, much faster to load than graphjson
        - The format is described in ARCHITECTURE.md, section "Network file", and in the header of each file
        - Only the graph, the nodes, their ids and modes, their intermediate nodes and the GeoGraph defaults are saved
        - The nodes are written in Hilbert order within each mode (nodes close on the globe get close ids); the geograph itself is not renumbered, and each node keeps its id in `node_ids`

        Required Arguments:

        - `filename`
            - Type: str
            - What: The filename to save the network file as
            - Note: The filename must end with .scgraph
            - Note: A file inside the `networks/` folder of the cache directory (`build_geograph`'s) raises a ValueError: save it elsewhere
            - Note: On Windows (C++ build), a file that a live GeoGraph was loaded from raises a PermissionError: save to another name

        Optional Arguments:

        - `save_intermediate_nodes`
            - Type: bool
            - What: Whether to include the intermediate nodes in the saved file (if they exist)
            - Default: True
            - Note: Their points are stored to 1e-7 degree (about 1 cm) and must lie within ±214.7483647° (otherwise a ValueError is raised)
        - `sources`
            - Type: list[dict] | None
            - What: Where the data comes from, stored in the file header so that it travels with the file: for each source, for example its `url`, `credit` and `license` (as `build_geograph` records them)
            - Default: None

        Returns:

        - The `content_sha256` of the file: the SHA-256 of every byte after its first 40, also stored in its bytes 8 to 39
        """
        if not filename.endswith(".scgraph"):
            raise ValueError("Filename must end with .scgraph")
        # A cached network must stay the one its manifest describes
        built = resolve_cache_dir().joinpath("networks").resolve()
        if Path(filename).resolve().is_relative_to(built):
            raise ValueError(
                f"{filename} is in scgraph's cache ({built}); save it elsewhere"
            )
        # Written in Hilbert order within each mode (nodes close on the globe get close
        # ids, and the nodes of a mode stay together); the geograph is not renumbered
        nodes, node_modes = self.nodes, self.node_modes
        # Nodes appended to `nodes` directly are in the first mode
        node_modes.extend(bytes(len(nodes) - len(node_modes)))
        # (by mode only if there are several: the key is cheaper without)
        multimodal = len(self.modes) > 1
        order = hilbert_order(nodes, node_modes if multimodal else None)
        if all(map(eq, order, range(len(order)))):
            order = None  # already in that order: written as it is
        old = range(len(nodes)) if order is None else order
        # In the order searches visit the arcs, so that the file gives the same paths
        offsets, heads, weights = self.graph_object._csr(order)
        arrays = {
            "offsets": offsets,
            "heads": heads,
            "weights": weights,
            "latitudes": array("d", (nodes[i][0] for i in old)),
            "longitudes": array("d", (nodes[i][1] for i in old)),
        }
        # None: each node's id is its position
        node_ids = self.node_ids.array(order)
        if node_ids is not None:
            arrays["node_ids"] = node_ids
        if multimodal:
            arrays["node_modes"] = array("B", (node_modes[i] for i in old))
        shapes = self.intermediate_nodes if save_intermediate_nodes else None
        if shapes is not None:
            starts, points = array("i", [0]), array("i")
            for new, origin in enumerate(old):
                # Nodes added after loading (add_coord_node, merges) have no shapes
                row = shapes[origin] if origin < len(shapes) else {}
                for arc in range(offsets[new], offsets[new + 1]):
                    head = old[heads[arc]]
                    try:
                        for latitude, longitude in row.get(head, ()):
                            points.append(round(latitude * 1e7))
                            points.append(round(longitude * 1e7))
                    except (OverflowError, ValueError) as error:
                        raise ValueError(
                            f"The shape of arc {origin} -> {head} has a point "
                            "that is not a number within ±214.7483647 degrees"
                        ) from error
                    starts.append(len(points) // 2)
            arrays["shape_offsets"], arrays["shape_points"] = starts, points
        return network_file.write(
            filename,
            arrays,
            metadata={
                "crs": "EPSG:4326",
                "units": self.geograph_units,
                "default_off_graph_circuity": self.default_off_graph_circuity,
                "default_node_addition_circuity": self.default_node_addition_circuity,
                **(
                    {"modes": self.modes}
                    if self.modes != [{"name": None}]
                    else {}
                ),
                **({"sources": sources} if sources is not None else {}),
            },
        )

    # Load Methods
    @staticmethod
    def load_from_geojson(
        filename: str,
        precision: int = 5,
        pct_to_keep: int | float = 100,
        min_points=3,
        load_intermediate_nodes: bool = True,
        silent: bool = False,
        reduce_iterations: int = 0,
        lazy: bool = False,
        max_km_between_nodes: float | int | None = None,
    ):
        """
        Function:

        - Load a GeoGraph from an arbitrary geojson file (GeometryCollection or FeatureCollection)
        - This function
            - Merges all LineStrings and MultiLineStrings into a single MultiLineString
            - Simplifies the MultiLineString to reduce the number of points using a percentage based Visvalengam simplification algorithm
            - Rounds the coordinates to the specified precision
            - Merges lines that start and end at the same location after rounding
            - Converts the MultiLineString into a GeoGraph object
            - Numbers the nodes along a Hilbert curve (nodes close on the globe get close ids); without `max_km_between_nodes`, `node_ids[i]` is node i's id before this ordering (the numbering of earlier versions)
        - Note:
            - All arcs read in will be undirected


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
            - What: Whether to keep the shape of each arc (its intermediate points) in the GeoGraph object
            - Default: True
            - Note: Only used with `max_km_between_nodes`; otherwise every point is a node and arcs have no intermediate points.
        - `silent`
            - Type: bool
            - What: Whether to suppress progress output to the console when loading the geojson
            - Default: False
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
            - What: If set, nodes are only the points where lines meet or end, and a line is also cut at the first point where the arc since the previous node reaches `max_km_between_nodes`; the other points become the shape of the arcs, whose length is the length of their full line
            - Default: None (every point is a node)
            - Note: Useful for sources with many points per line, such as rail or road networks, to keep the graph small
        """
        if lazy:
            return LazyGeoGraph(
                lambda: GeoGraph.load_from_geojson(
                    filename=filename,
                    precision=precision,
                    pct_to_keep=pct_to_keep,
                    min_points=min_points,
                    load_intermediate_nodes=load_intermediate_nodes,
                    silent=silent,
                    reduce_iterations=reduce_iterations,
                    lazy=False,
                    max_km_between_nodes=max_km_between_nodes,
                )
            )
        if max_km_between_nodes is not None:
            # Each point: its id, the (longitude, latitude) tuple of the file, and its
            # [latitude, longitude] location
            lines = [
                [(tuple(point), [point[1], point[0]]) for point in line]
                for line in simplify_geojson(
                    filename_in=filename,
                    precision=precision,
                    pct_to_keep=pct_to_keep,
                    min_points=min_points,
                    silent=silent,
                )
            ]
            uses = Counter(point for line in lines for point, _ in line)
            junctions = {point for point, count in uses.items() if count > 1}
            # Points are identified by their coordinates: the nodes keep positions as ids
            graph, nodes, shapes, _ = lines_to_graph(
                ((0, line) for line in lines), junctions, max_km_between_nodes
            )
            geograph = GeoGraph(
                graph=graph,
                nodes=nodes,
                intermediate_nodes=shapes if load_intermediate_nodes else None,
            )
            geograph.graph_object.reduce(reduce_iterations)
            return geograph
        data = parse_geojson(
            filename_in=filename,
            precision=precision,
            pct_to_keep=pct_to_keep,
            min_points=min_points,
            # load_intermediate_nodes=load_intermediate_nodes,
            silent=silent,
        )
        # In Hilbert order: nodes close on the globe get close ids
        geograph = _in_hilbert_order(
            GeoGraph(graph=data["graph"], nodes=data["nodes"])
        )
        geograph.graph_object.reduce(reduce_iterations)
        return geograph

    @staticmethod
    def load_from_osm(
        filename: str,
        keep: dict[str, set[str | None]] | None = None,
        directed: bool = True,
        max_km_between_nodes: float | int = 2,
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
        - Each arc has the length of its full line, in kilometers, so it is never shorter than the straight line between its ends
        - Nodes are the OSM nodes where kept ways meet or end; a way is also cut at the first point where the arc since the previous node reaches `max_km_between_nodes`
        - Nodes are numbered along a Hilbert curve (nodes close on the globe get close ids), and `node_ids[i]` is node i's OSM id
        - Ways tagged `oneway=yes` or `-1`, motorways and roundabouts are one way (with `directed=True`)
        - Memory: osmium's node filter takes about 1.5 GB, whatever the size of the file

        Required Arguments:

        - `filename`
            - Type: str
            - What: The path of the OpenStreetMap file, for example an extract downloaded from https://download.geofabrik.de

        Optional Arguments:

        - `keep`
            - Type: dict[str, set[str]] | None
            - What: The ways to keep: a way is kept if, for every key, its tag value is in the set; `None` in a set stands for a missing tag
            - Default: None (main roads: `{"highway": scgraph.osm.MAIN_ROADS}`, motorway to primary and their links)
            - Example: `{"railway": {"rail"}, "service": {None}}` for railway lines without yards, sidings and spurs
        - `directed`
            - Type: bool
            - What: Whether one-way streets (`oneway=*`, roundabouts) give arcs in one direction only
            - Default: True
        - `max_km_between_nodes`
            - Type: float | int
            - What: Length in kilometers at which a way is cut into a new arc (at the next point of the way), so that origins and destinations can attach close to where they are
            - Default: 2
        - `largest_component`
            - Type: bool
            - What: Whether to keep only the largest part of the network where every node can reach every other, so that origins and destinations are never placed on a one-way dead end or on a fragment cut by the border of the extract
            - Default: True
            - Note: Parts not connected to the largest one, such as islands without a road link, are dropped
        - `load_intermediate_nodes`
            - Type: bool
            - What: Whether to keep the shape of each arc, to draw routes
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
        - `ValueError` if no way of the file matches `keep`
        """
        if lazy:
            return LazyGeoGraph(
                lambda: GeoGraph.load_from_osm(
                    filename=filename,
                    keep=keep,
                    directed=directed,
                    max_km_between_nodes=max_km_between_nodes,
                    largest_component=largest_component,
                    load_intermediate_nodes=load_intermediate_nodes,
                    reduce_iterations=reduce_iterations,
                    lazy=False,
                )
            )
        from scgraph.osm import MAIN_ROADS, keep_largest_component, read_osm

        graph, nodes, shapes, ids = read_osm(
            filename,
            keep if keep is not None else {"highway": MAIN_ROADS},
            directed,
            max_km_between_nodes,
        )
        if not nodes:
            raise ValueError(f"No way of {filename} matches keep={keep}")
        if largest_component:
            graph, nodes, shapes, ids = keep_largest_component(
                graph, nodes, shapes, ids
            )
        geograph = GeoGraph(
            graph=graph,
            nodes=nodes,
            intermediate_nodes=shapes if load_intermediate_nodes else None,
            node_ids=ids,
        )
        geograph.graph_object.reduce(reduce_iterations)
        return geograph

    @staticmethod
    def load_from_graphjson(
        filename: str,
        reduce_iterations: int = 0,
        lazy: bool = False,
    ) -> "GeoGraph":
        """
        Function:

        - Load a GeoGraph from a JSON file that was saved using the `save_as_graphjson` method
        - Arc shapes are read as the points between their arc's two nodes, from origin to destination: nodes they repeat (files saved by released versions) are dropped, a shape running from destination to origin is reversed, and an arc left without points has no shape

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
            # Files saved by scgraph 3.0 to 3.6 repeat each arc's two nodes in its shape
            _keep_interior_points(data["intermediate_nodes"], data["nodes"])
        geograph = GeoGraph(**data)
        geograph.graph_object.reduce(reduce_iterations)
        return geograph

    @staticmethod
    def load_from_scgraph(
        filename: str,
        reduce_iterations: int = 0,
        lazy: bool = False,
    ) -> "GeoGraph":
        """
        Function:

        - Load a GeoGraph from a binary network file saved with `save_as_scgraph`
        - The file is checked before use: a damaged or foreign file raises a ValueError (in the C++ build, damaged arc shapes raise it when they are read)
        - In the C++ build, the file is mapped and read in place while the geograph is alive; on Windows it can't be replaced or deleted meanwhile
        - `nodes` reads the file's coordinates: `nodes[i]` is a new list each time, so replace a node with `nodes[i] = [latitude, longitude]`
        - `intermediate_nodes` reads the file's arc shapes when asked for, read-only: `intermediate_nodes[i]` is a new mapping {destination: shape} each time, so editing a shape changes nothing and assigning raises a TypeError
        - `node_ids` reads the file's node ids, if it has them (otherwise each node's id is its position); `node_modes` and `modes` give each node's mode
        - The snapping index (`snap_index`) is built while loading, so that the first query is as fast as the next ones

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
        """
        if lazy:
            return LazyGeoGraph(
                lambda: GeoGraph.load_from_scgraph(
                    filename=filename,
                    reduce_iterations=reduce_iterations,
                    lazy=False,
                )
            )
        if not filename.endswith(".scgraph"):
            raise ValueError("Filename must end with .scgraph")
        # The C++ graph reads the arcs in place, from the mapped file, and checks them
        mapped = Graph.__module__ == "scgraph.cpp"
        arrays, metadata = network_file.read(filename, mapped=mapped)
        try:
            graph = (Graph._from_mapped_csr if mapped else Graph.from_csr)(
                arrays["offsets"], arrays["heads"], arrays["weights"]
            )
        except (IndexError, ValueError) as error:
            raise ValueError(f"{filename}: {error}") from error
        geograph = GeoGraph(
            graph=graph,
            nodes=network_file.NodeCoordinates(
                arrays["latitudes"], arrays["longitudes"]
            ),
            intermediate_nodes=(
                network_file.ArcShapes(arrays)
                if "shape_offsets" in arrays
                else None
            ),
            default_off_graph_circuity=metadata.get(
                "default_off_graph_circuity", 1
            ),
            default_node_addition_circuity=metadata.get(
                "default_node_addition_circuity", 4
            ),
            geograph_units=metadata.get("units", "km"),
            node_ids=arrays.get("node_ids"),
            node_modes=arrays.get("node_modes"),
            modes=metadata.get("modes"),
        )
        geograph.graph_object.reduce(reduce_iterations)
        # Every route snaps its points (node ids depend on how the file was sorted): the
        # index is built now, not at the first query (an empty network has none)
        if len(geograph.nodes):
            try:
                geograph.snap_index
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
        url = f"{geograph_url}/{name}.graphjson"
        response = requests.get(url, timeout=60)
        if response.status_code == 404:
            raise FileNotFoundError(
                f"Geograph '{name}' not found at '{url}'. "
                f"Check that the name is correct and the file exists in the scgraph GitHub repository."
            )
        if not response.ok:
            raise ConnectionError(
                f"Failed to download geograph '{name}' from '{url}'. "
                f"HTTP status: {response.status_code}."
            )
        # Written next to the cache file, then moved onto it: a download that fails while it
        # is written never leaves a partial file that later loads would take as the network
        partial = cached_file.with_name(
            f".{cached_file.name}.{os.getpid()}.{secrets.token_hex(4)}.download"
        )
        try:
            partial.write_bytes(response.content)
            os.replace(partial, cached_file)
        except BaseException:
            partial.unlink(missing_ok=True)
            raise

    @staticmethod
    def load_geograph(
        name: str,
        cache_dir: str | None = None,
        geograph_url: str = _GEOGRAPH_URL,
        reduce_iterations: int = 0,
        lazy: bool = False,
        *,
        local_files_only: bool | None = None,
    ) -> "GeoGraph":
        """
        Function:

        - Load a built-in GeoGraph by name, using a local cache.
        - On first call for a given name, downloads the .graphjson file from GitHub into the cache directory.
        - On subsequent calls, loads directly from cache without any network requests.
        - The first load converts the .graphjson into a network file beside it (`<name>.scgraph`, much faster to load), which later loads read; the .graphjson is kept, and a damaged conversion is made again from it.
        - The conversion orders the nodes along a Hilbert curve, so that nodes close on the globe get close ids: node ids differ from those of the .graphjson (lengths do not; of two routes of exactly equal length, another may be returned), and `node_ids[i]` is node i's id in the .graphjson (its id in scgraph 3.6.0). `load_from_graphjson` on the cached .graphjson keeps its numbering.
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
        """
        if lazy:
            return LazyGeoGraph(
                lambda: GeoGraph.load_geograph(
                    name=name,
                    cache_dir=cache_dir,
                    geograph_url=geograph_url,
                    reduce_iterations=reduce_iterations,
                    lazy=False,
                    local_files_only=local_files_only,
                )
            )
        if local_files_only is None:
            local_files_only = os.environ.get("SCGRAPH_OFFLINE") == "1"
        cache_path = resolve_cache_dir(cache_dir)
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
        # differ from the .graphjson's, which the nodes keep as their node_ids
        geograph = GeoGraph.load_from_graphjson(str(cached_file))
        geograph.modes = [{"name": None, "source": cached_file.name}]
        with open(cached_file, "rb") as file:
            sha256 = hashlib.file_digest(file, "sha256").hexdigest()
        source = {
            "name": cached_file.name,
            "url": f"{geograph_url}/{cached_file.name}",
            "sha256": sha256,
        }
        try:
            geograph.save_as_scgraph(str(converted), sources=[source])
        except OSError:
            # A cache that can't be written: the .graphjson is read at every load, its
            # nodes ordered as the file would have them
            geograph = _in_hilbert_order(geograph)
            geograph.graph_object.reduce(reduce_iterations)
            if len(geograph.nodes):  # as load_from_scgraph
                geograph.snap_index
            return geograph
        del geograph  # one copy of the network in memory at a time
        return GeoGraph.load_from_scgraph(
            str(converted), reduce_iterations=reduce_iterations, lazy=False
        )

    @staticmethod
    def list_geographs(
        cache_dir: str | None = None,
        geograph_url: str = _GEOGRAPH_URL,
    ) -> list[dict]:
        """
        Function:

        - List all built-in GeoGraphs available, indicating which are already cached locally.
        - The published geographs are a fixed list, listed without any network request; for another `geograph_url`, the names are read from the `contents.txt` file at that URL.

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
            - `cached`: bool — whether the file is already in the local cache
        """
        cache_path = resolve_cache_dir(cache_dir)
        available = sorted(_PUBLISHED_GEOGRAPHS)
        if geograph_url != _GEOGRAPH_URL:
            url = f"{geograph_url.rstrip('/')}/contents.txt"
            response = requests.get(url, timeout=60)
            if not response.ok:
                raise ConnectionError(
                    f"Failed to fetch geograph list from '{url}'. "
                    f"HTTP status: {response.status_code}."
                )
            available = sorted(
                line.removesuffix(".graphjson")
                for line in response.text.splitlines()
                if line.strip().endswith(".graphjson")
            )
        return [
            {
                "name": name,
                "cached": cache_path.joinpath(f"{name}.graphjson").exists(),
            }
            for name in available
        ]

    @staticmethod
    def clear_geograph_cache(
        cache_dir: str | None = None,
        *,
        name: str | None = None,
        region: str | None = None,
    ) -> None:
        """
        Function:

        - Remove what scgraph keeps in the local cache directory: the built-in geographs `load_geograph` downloaded (and their `.scgraph` conversions) and the networks `build_geograph` built (under `networks/`)
        - With `name` (and `region`), remove only that network: its built-in geograph and its built networks (of every region, or of `region` only)
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
            - What: The network to remove, as `load_geograph` or `build_geograph` take it
            - Default: None: every network
        - `region`
            - Type: str | None
            - What: With `name`, the region of the built network to remove (its sub-regions are kept)
            - Default: None: every region
        """
        from scgraph import networks

        if name is not None and name not in {
            *_PUBLISHED_GEOGRAPHS,
            *networks.NAMES,
        }:
            raise ValueError(f"Unknown network '{name}'")
        if region is not None and (
            name is None
            or not re.fullmatch(r"[a-z0-9-]+(/[a-z0-9-]+)*", region)
        ):
            raise ValueError(f"Invalid region '{region}', or no name with it")
        cache_path = resolve_cache_dir(cache_dir)
        root = cache_path.joinpath("networks")

        def left(function, path, excinfo):
            # A file still open (Windows: a network loaded in this process) stays, as
            # an orphan that a later clear removes; its folder then stays too
            if function is not os.rmdir:
                logger.warning("Left %s in the cache: %s", path, excinfo[1])

        def remove(path):
            try:
                if path.is_dir():
                    shutil.rmtree(path, onerror=left)
                else:
                    path.unlink(missing_ok=True)
            except OSError as error:
                left(None, path, (None, error, None))

        # Only what scgraph writes there, so that a folder given as the cache keeps the
        # user's own files; then the folder itself if nothing else is left
        for published in _PUBLISHED_GEOGRAPHS:
            if name in (None, published) and region is None:
                for suffix in (".graphjson", ".scgraph"):
                    remove(cache_path.joinpath(published + suffix))
        if name is None:
            remove(root)
            for work in cache_path.glob(".building-*"):  # interrupted builds
                remove(work)
        elif region is None:
            remove(root.joinpath(name))
        else:
            # Only this entry's files: a sub-region is an entry of its own, in a sub-folder
            folder = root.joinpath(name, region)
            for file in [*folder.glob("*.scgraph"), folder / "manifest.json"]:
                remove(file)
        if cache_path.is_dir() and not any(cache_path.iterdir()):
            cache_path.rmdir()

    @staticmethod
    def cache_info(cache_dir: str | None = None) -> list[dict]:
        """
        Function:

        - List what scgraph keeps in the local cache directory, read from disk only, without any network request
        - Unlike `list_geographs` and `list_downloadable_geographs`, which list what can be loaded or built

        Optional Arguments:

        - `cache_dir`
            - Type: str | None
            - What: Path to the local cache directory
            - Default: None: the `SCGRAPH_CACHE_DIR` environment variable if set, else the platform's cache directory (as in `load_geograph`)

        Returns:

        - A list of dicts, one per file or folder:
            - `kind`: str — `"published"` (a built-in geograph `load_geograph` downloaded, `.graphjson`, or its conversion, `.scgraph`), `"built"` (a network `build_geograph` built) or `"building"` (the work folder of a build that is running or was interrupted; `clear_geograph_cache()` removes it)
            - `name`: str | None — the network name (None for `"building"`)
            - `region`: str | None — the region of a built network, if it has one
            - `file`: str — the path of the file or folder
            - `bytes`: int — its size
            - for `"built"` only: `scgraph`, `build_version` and `format_version` — the versions of scgraph, of the network's build script and of the file format that built it
        """
        cache_path = resolve_cache_dir(cache_dir)
        info = [
            {
                "kind": "published",
                "name": name,
                "region": None,
                "file": str(file),
                "bytes": file.stat().st_size,
            }
            for name in _PUBLISHED_GEOGRAPHS
            for suffix in (".graphjson", ".scgraph")
            if (file := cache_path.joinpath(name + suffix)).is_file()
        ]
        for manifest_file in sorted(
            cache_path.joinpath("networks").rglob("manifest.json"),
            key=lambda manifest_file: manifest_file.parent,
        ):
            try:
                manifest = json.loads(manifest_file.read_text())
                file = manifest_file.parent.joinpath(
                    Path(manifest["file"]).name
                )
                info.append(
                    {
                        "kind": "built",
                        "name": manifest["name"],
                        "region": manifest["region"],
                        "file": str(file),
                        "bytes": file.stat().st_size,
                        "scgraph": manifest["scgraph"],
                        "build_version": manifest["build_version"],
                        "format_version": manifest["format_version"],
                    }
                )
            except (OSError, ValueError, KeyError, TypeError):
                continue  # names no file: not cached
        for work in sorted(cache_path.glob(".building-*")):
            info.append(
                {
                    "kind": "building",
                    "name": None,
                    "region": None,
                    "file": str(work),
                    "bytes": sum(
                        f.stat().st_size for f in work.rglob("*") if f.is_file()
                    ),
                }
            )
        return info

    @staticmethod
    def build_geograph(
        name: Literal[
            "eurostat_marnet",
            "marnet",
            "north_america_rail",
            "oak_ridge_maritime",
            "osm_main_roads",
            "osm_main_roads_and_marnet",
            "osm_rail",
            "us_freeway",
        ],
        region: str | None = None,
        cache_dir: str | None = None,
        reduce_iterations: int = 0,
        lazy: bool = False,
        *,
        refresh: bool = False,
        local_files_only: bool | None = None,
    ) -> "GeoGraph":
        """
        Function:

        - Download the online sources of a reference network once, build the network on this machine and keep it in the local cache; later calls load it from the cache, without any network request, until an upgrade of scgraph changes how that network is built
        - With `local_files_only=True` (or the environment variable `SCGRAPH_OFFLINE=1`), nothing is downloaded: a network built with another version of its build script is loaded with a warning (one of another file format is refused), and one that is not in the cache raises a FileNotFoundError
        - Sources can take several GB (an OpenStreetMap extract of a country): a download above 100 MB is announced with a logging warning before it starts; `logging.basicConfig(level=logging.INFO)` shows every step
        - These networks are not the files that `load_geograph` returns: their node numbers differ, and the road and rail networks have more nodes, which `reduce_iterations=-1` removes for routing
        - `GeoGraph.list_downloadable_geographs()` lists the networks, who to credit and what is already in the cache

        Required Arguments:

        - `name`
            - Type: str
            - What: The name of the network
            - Options:
                - 'eurostat_marnet': the sea lanes of Eurostat SeaRoute at 5 km resolution, lanes cut at the antimeridian joined, Arctic passages left out, unlike `marnet` (EUPL-1.2)
                - 'marnet': the sea lanes the published `marnet` was built from (Eurostat SeaRoute via searoute-py, EUPL-1.2)
                - 'north_america_rail': Class I railroads of North America (U.S. Federal Railroad Administration)
                - 'oak_ridge_maritime': the sea lanes the published `oak_ridge_maritime` was built from (Oak Ridge National Laboratory)
                - 'osm_main_roads': main roads of an OpenStreetMap extract (needs `region`; OpenStreetMap contributors, ODbL 1.0; `pip install scgraph[osm]`)
                - 'osm_main_roads_and_marnet': main roads of an OpenStreetMap extract joined to the `marnet` sea lanes at the ports of the World Port Index (needs `region`; `pip install scgraph[osm]`)
                - 'osm_rail': railway lines of an OpenStreetMap extract, sidings and yards included (needs `region`; OpenStreetMap contributors, ODbL 1.0; `pip install scgraph[osm]`)
                - 'us_freeway': freeways of the United States (Esri)

        Optional Arguments:

        - `region`
            - Type: str | None
            - What: For the OpenStreetMap networks, the path of a Geofabrik extract, as in its download URL
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

        Returns:

        - The GeoGraph of the network (a LazyGeoGraph if `lazy`)

        Raises:

        - `ValueError` for an unknown name, a missing or invalid region, or a region Geofabrik does not have, before any large download; with `local_files_only`, for `refresh=True` or a cached network of another file format
        - `FileNotFoundError` with `local_files_only` if the network is not in the cache
        - `ImportError` for the OpenStreetMap networks if `osmium` is not installed (`pip install scgraph[osm]`), before downloading the extract
        - `requests.HTTPError` or `ConnectionError` if a source can't be downloaded; no file of the build is left in the cache, and a network already cached stays there
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
                )
            )
        if local_files_only is None:
            local_files_only = os.environ.get("SCGRAPH_OFFLINE") == "1"
        from scgraph import networks

        if name not in networks.NAMES:
            close = difflib.get_close_matches(name, networks.NAMES, n=3)
            hint = (
                f" Did you mean {', '.join(map(repr, close))}?" if close else ""
            )
            raise ValueError(
                f"Unknown network '{name}'.{hint} Available: {', '.join(networks.NAMES)}"
            )
        network = importlib.import_module(f"scgraph.networks.{name}")
        regional = any(
            "{region}" in source["url"] for source in network.SOURCES.values()
        )
        where = f"the path of a Geofabrik extract, for example 'europe/luxembourg' (see {networks.REGIONS})"
        if regional and region is None:
            raise ValueError(f"'{name}' needs a region: {where}")
        if not regional and region is not None:
            raise ValueError(f"'{name}' has no region")
        # Region names are Geofabrik paths; nothing else may reach the cache path
        if region is not None and not re.fullmatch(
            r"[a-z0-9-]+(/[a-z0-9-]+)*", region
        ):
            raise ValueError(f"Invalid region '{region}': {where}")
        cache = resolve_cache_dir(cache_dir)
        folder = cache.joinpath("networks", name, region or "")
        manifest_file = folder.joinpath("manifest.json")
        # The manifest names the network file, which is named by its content
        try:
            manifest = json.loads(manifest_file.read_text())
            built_by = manifest["build_version"], manifest["format_version"]
            # Only a name: the file removed by a rebuild is never outside the entry
            cached_file = folder.joinpath(Path(manifest["file"]).name)
        except (OSError, ValueError, KeyError, TypeError):
            built_by, cached_file = None, None
        current = network.VERSION, network_file.VERSION
        cached = cached_file is not None and cached_file.is_file()
        stale = cached and built_by != current
        offline = "local_files_only=True (or SCGRAPH_OFFLINE=1)"
        if local_files_only:
            if refresh:
                raise ValueError(f"refresh=True downloads: not with {offline}")
            if not cached:
                raise FileNotFoundError(
                    f"{name} is not in the cache ({folder}) and {offline} "
                    "forbids building it"
                )
            if built_by[1] != network_file.VERSION:
                raise ValueError(
                    f"The cached {name} has file format {built_by[1]}, this scgraph "
                    f"reads {network_file.VERSION}: build it again without {offline}"
                )
            if stale:
                warnings.warn(
                    f"The cached {name} was built with build script version "
                    f"{built_by[0]}, now {network.VERSION}; loading it as {offline}"
                )
        elif stale:
            logger.warning(
                "The cached %s was built by another version of its build script or "
                "of the file format; building it again",
                name,
            )
        if not local_files_only and (refresh or not cached or stale):
            # The tag goes in networks/, scgraph's own folder: a cache_dir given by the user
            # may hold other files, which backups must not skip
            cache.joinpath("networks").mkdir(parents=True, exist_ok=True)
            cache.joinpath("networks", "CACHEDIR.TAG").write_text(_CACHEDIR_TAG)
            downloaded = datetime.now(timezone.utc).isoformat(
                timespec="seconds"
            )
            files, sources = {}, []
            # One folder per build, so that builds in parallel do not share files; at the
            # root of the cache, outside `networks/`, where no GeoGraph may be saved
            work = Path(tempfile.mkdtemp(prefix=".building-", dir=cache))
            building = work.joinpath(f"{name}.scgraph")
            try:
                for source, about in network.SOURCES.items():
                    template = about["url"]
                    url = template.format(region=region)
                    # Same extension as the URL, by which readers such as osmium detect the format
                    files[source] = work.joinpath(
                        source + "".join(Path(url).suffixes)
                    )
                    try:
                        getattr(network, "download", networks.download_file)(
                            url, str(files[source])
                        )
                    except requests.HTTPError as error:
                        if (
                            "{region}" in template
                            and error.response.status_code == 404
                        ):
                            raise ValueError(
                                f"No extract '{region}' on Geofabrik; the region is {where}"
                            ) from error
                        raise
                    with open(files[source], "rb") as file:
                        sha256 = hashlib.file_digest(file, "sha256").hexdigest()
                    sources.append(
                        {
                            "name": source,
                            "url": url,
                            "sha256": sha256,
                            "bytes": files[source].stat().st_size,
                            "credit": about["credit"],
                            "license": about["license"],
                            "license_url": about["license_url"],
                        }
                    )
                logger.info("Building %s", name)
                # Written in Hilbert order within each mode: nodes close on the globe
                # get close ids
                geograph = network.build(
                    {source: str(path) for source, path in files.items()}
                )
                digest = geograph.save_as_scgraph(
                    str(building), sources=sources
                )
                built_file = folder.joinpath(f"{digest}.scgraph")
                work.joinpath("manifest.json").write_text(
                    json.dumps(
                        {
                            "name": name,
                            "region": region,
                            "downloaded": downloaded,
                            "sources": sources,
                            "scgraph": GeoGraph.__scgraph_version__(),
                            "build_version": network.VERSION,
                            "format_version": network_file.VERSION,
                            "file": built_file.name,
                            "node_order": NODE_ORDER,
                        },
                        indent=2,
                    )
                )
                # The manifest appears last, so that it always names a whole file and
                # the versions of the build script and file format that wrote it
                folder.mkdir(parents=True, exist_ok=True)
                # A file of that name has the same content, and may be open (Windows)
                if not built_file.exists():
                    building.replace(built_file)
                work.joinpath("manifest.json").replace(manifest_file)
                if cached_file is not None and cached_file != built_file:
                    try:
                        cached_file.unlink(missing_ok=True)
                    except OSError:  # still open (Windows): left as an orphan
                        pass
                cached_file = built_file
                logger.info(
                    "Built %s. Credit: %s (%s)",
                    name,
                    _joined(network, "credit"),
                    _joined(network, "license"),
                )
            except OSError as error:  # requests' errors included
                if cached:
                    error.add_note(
                        f"The cache still holds {name}: build_geograph(..., "
                        "local_files_only=True) loads it"
                    )
                raise
            finally:
                # A failed download or build leaves no large file behind
                shutil.rmtree(work, ignore_errors=True)
        return GeoGraph.load_from_scgraph(
            str(cached_file), reduce_iterations=reduce_iterations, lazy=False
        )

    @staticmethod
    def __scgraph_version__() -> str:
        try:
            return version("scgraph")
        except (
            PackageNotFoundError
        ):  # run from a source tree that is not installed
            return "unknown"

    @staticmethod
    def list_downloadable_geographs(cache_dir: str | None = None) -> list[dict]:
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
        from scgraph import networks

        root = resolve_cache_dir(cache_dir).joinpath("networks")
        listing = []
        for name in networks.NAMES:
            network = importlib.import_module(f"scgraph.networks.{name}")
            needs_region = any(
                "{region}" in source["url"]
                for source in network.SOURCES.values()
            )
            folder = root.joinpath(name)
            built = [
                m for m in folder.rglob("manifest.json") if _names_a_file(m)
            ]
            listing.append(
                {
                    "name": name,
                    "description": " ".join(
                        network.__doc__.split("\n\n")[0].split()
                    ),
                    "credit": _joined(network, "credit"),
                    "license": _joined(network, "license"),
                    "needs_region": needs_region,
                    "cached": bool(built),
                    "cached_regions": (
                        sorted(
                            path.parent.relative_to(folder).as_posix()
                            for path in built
                        )
                        if needs_region
                        else []
                    ),
                }
            )
        return listing

    @staticmethod
    def load_from_osmnx_graph(
        osmnx_graph,
        coord_precision: int = 5,
        weight_precision: int = 3,
        weight_key: Literal["length", "travel_time"] = "length",
        off_graph_travel_speed: int | float | None = None,
        load_intermediate_nodes: bool = True,
        silent: bool = False,
        reduce_iterations: int = 0,
        lazy: bool = False,
    ):
        """
        Function:

        - Load a GeoGraph from an OSMnx graph object
        - This function:
            - Will convert the OSMnx graph into a GeoGraph object
            - Rounds the coordinates to the specified precision
            - Rounds the weights to the specified precision (in kilometers)
            - This preserves directionality of edges from the OSMnx graph
            - Numbers the nodes along a Hilbert curve (nodes close on the globe get close ids); `node_ids[i]` is node i's OSMnx id (its OSM id), when the ids are integers

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
            - What: The edge attribute to use as the weight for the graph
            - Options:
                - 'length': Use the length attribute (in kilometers)
                - 'travel_time': Use the travel_time attribute (in seconds)
            - Default: 'length'
        - `off_graph_travel_speed`
            - Type: int | float | None
            - What: The travel speed (km/h) to assume for off-graph travel when using travel_time (seconds) as the weight key
            - Default: None
            - Options:
                - If None and weight_key is 'travel_time'
                    - The default_off_graph_circiuity will be set to 0 (assuming instant travel off graph)
                    - The default_node_addition_circuity will be set to 240
                        - This assumes 15 km/h off graph travel speed when optimizing for entry
                        - This is not included in final returned length, but only used to choose an optimal entry node into the graph
                - If None and weight_key is 'length', the function will ignore this parameter
                - If a number, the function will use this speed to convert off-graph distances to travel times in seconds
        - `load_intermediate_nodes`
            - Type: bool
            - What: Whether to load the intermediate nodes for each edge (if they exist)
            - Default: True
            - Note: The shape kept for an edge is the points of its geometry between its two nodes, from origin to destination (a geometry listed from destination to origin is reversed, repeated end nodes are dropped); an edge without such points has no shape
        - `silent`
            - Type: bool
            - What: Whether to suppress progress output to the console when loading the graph
            - Default: False
        - `reduce_iterations`
            - Type: int
            - What: Number of reduction iterations to perform upon loading. If 0, no reduction is done. If -1, reduces iteratively until convergence.
            - Default: 0
        - `lazy`
            - Type: bool
            - What: Whether to delay loading the geograph until its first use
            - Default: False

        """
        if lazy:
            return LazyGeoGraph(
                lambda: GeoGraph.load_from_osmnx_graph(
                    osmnx_graph=osmnx_graph,
                    coord_precision=coord_precision,
                    weight_precision=weight_precision,
                    weight_key=weight_key,
                    off_graph_travel_speed=off_graph_travel_speed,
                    load_intermediate_nodes=load_intermediate_nodes,
                    silent=silent,
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
        weight_divisor = 1000 if weight_key == "length" else 1
        for u, v, data in osmnx_graph.edges(data=True):
            i = node_to_idx[u]
            j = node_to_idx[v]
            weight = round(
                float(data.get(weight_key)) / weight_divisor, weight_precision
            )
            # Keep only the shortest of parallel edges, with its own geometry
            if weight >= graph[i].get(j, float("inf")):
                continue
            graph[i][j] = weight
            if load_intermediate_nodes and "geometry" in data:
                intermediate_nodes[i][j] = [
                    [
                        round(coord[1], coord_precision),
                        round(coord[0], coord_precision),
                    ]
                    for coord in data["geometry"].coords
                ]
            elif load_intermediate_nodes:
                intermediate_nodes[i].pop(j, None)

        nodes = [located[node] for node in node_list]
        # OSMnx identifies its nodes by their OSM ids (integers, numpy's included)
        try:
            kwargs = {"node_ids": array("q", node_list)}
        except (TypeError, OverflowError):
            kwargs = {}
        if load_intermediate_nodes:
            # An edge's geometry should run from its first node to its second
            _keep_interior_points(intermediate_nodes, nodes)
            kwargs["intermediate_nodes"] = intermediate_nodes
        # Handle travel_time specific parameters
        if weight_key == "travel_time":
            if off_graph_travel_speed is None:
                print_console(
                    "No off_graph_travel_speed provided but weight_key = 'travel_time'. Assuming instant travel off graph. Setting default_off_graph_circuity to 0 and default_node_addition_circuity to 240.",
                    silent=silent,
                )
                kwargs["default_off_graph_circuity"] = 0
                kwargs["default_node_addition_circuity"] = 240
            else:
                off_graph_speed_km_per_s = off_graph_travel_speed / 3600
                kwargs["default_off_graph_circuity"] = (
                    1 / off_graph_speed_km_per_s
                )
                kwargs["default_node_addition_circuity"] = (
                    1 / off_graph_speed_km_per_s
                )

        # TODO: Handle time based geograph units in a better way by default.
        # See: self.geograph_units
        geograph = GeoGraph(graph=graph, nodes=nodes, **kwargs)
        geograph.graph_object.reduce(reduce_iterations)
        return geograph

    # Misc IO Methods
    @staticmethod
    def get_multi_path_geojson(
        routes: list[dict],
        filename: str | None = None,
        show_progress: bool = False,
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
        - `show_progress`: bool
            - Whether to show basic progress information
            - Default: False
        - `silent`: bool
            - Whether to suppress console output
            - Default: False
        - `get_intermediate_nodes`: bool
            - Whether to include intermediate nodes in the shortest path calculation
            - Default: False

        Returns

        - `output`: dict
            - Dictionary with the GeoJSON file content.
        """
        assert isinstance(routes, list), "Routes must be a list"
        assert all(
            [isinstance(i, dict) for i in routes]
        ), "Routes must be a list of dictionaries"
        assert all(
            [isinstance(i.get("geograph"), GeoGraph) for i in routes]
        ), "All routes must have a 'geograph' key with a GeoGraph object"
        assert all(
            [isinstance(i.get("origin"), dict) for i in routes]
        ), "All routes must have an 'origin' key with a dictionary"
        assert all(
            [isinstance(i.get("destination"), dict) for i in routes]
        ), "All routes must have a 'destination' key with a dictionary"
        assert all(
            [isinstance(i.get("properties"), dict) for i in routes]
        ), "All routes must have a 'properties' key with a dictionary"
        assert all(
            [
                isinstance(i["origin"].get("latitude"), (int, float))
                for i in routes
            ]
        ), "All origins must have a 'latitude' key with a number"
        assert all(
            [
                isinstance(i["origin"].get("longitude"), (int, float))
                for i in routes
            ]
        ), "All origins must have a 'longitude' key with a number"
        assert all(
            [
                isinstance(i["destination"].get("latitude"), (int, float))
                for i in routes
            ]
        ), "All destinations must have a 'latitude' key with a number"
        assert all(
            [
                isinstance(i["destination"].get("longitude"), (int, float))
                for i in routes
            ]
        ), "All destinations must have a 'longitude' key with a number"
        assert all(
            [
                (
                    i["origin"].get("latitude") >= -90
                    and i["origin"].get("latitude") <= 90
                )
                for i in routes
            ]
        ), "All origin latitudes must be between -90 and 90"
        assert all(
            [
                (
                    i["origin"].get("longitude") >= -180
                    and i["origin"].get("longitude") <= 180
                )
                for i in routes
            ]
        ), "All origin longitudes must be between -180 and 180"
        assert all(
            [
                (
                    i["destination"].get("latitude") >= -90
                    and i["destination"].get("latitude") <= 90
                )
                for i in routes
            ]
        ), "All destination latitudes must be between -90 and 90"
        assert all(
            [
                (
                    i["destination"].get("longitude") >= -180
                    and i["destination"].get("longitude") <= 180
                )
                for i in routes
            ]
        ), "All destination longitudes must be between -180 and 180"

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
            if show_progress:
                print(
                    f"[{'='*(int((idx+1)/len_routes*20))}>{' '*(20-int((idx+1)/len_routes*20))}] {idx+1}/{len_routes}",
                    end="\r",
                )
        if show_progress:
            print()
        if filename is not None:
            json.dump(output, open(filename, "w"))
        return output


class GeoGraphModifiers:
    def add_edge(
        self,
        origin_id: int,
        destination_id: int,
        distance: int | float,
        symmetric: bool = False,
    ) -> None:
        return self.graph_object.add_edge(
            origin_id=origin_id,
            destination_id=destination_id,
            distance=distance,
            symmetric=symmetric,
        )

    def remove_node(
        self, symmetric_node: bool = False
    ) -> dict[int, int | float]:
        return self.graph_object.remove_node(symmetric_node=symmetric_node)

    def remove_edge(
        self, origin_id: int, destination_id: int, symmetric: bool = False
    ) -> int | float | None:
        return self.graph_object.remove_edge(
            origin_id=origin_id,
            destination_id=destination_id,
            symmetric=symmetric,
        )

    def add_coord_edge(
        self,
        origin_coord_dict: dict[str, float | int],
        destination_coord_dict: dict[str, float | int],
        symmetric: bool = True,
        distance: float | int | None = None,
        circuity: float | int = 1,
    ) -> None:
        """
        Function:

        - Add an edge to the graph between two nodes specified by their coordinates
        - Finds the closest nodes in the graph to the provided coordinates and adds an edge between them

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
        """
        assert isinstance(
            origin_coord_dict, dict
        ), "Origin node must be a dictionary"
        assert isinstance(
            destination_coord_dict, dict
        ), "Destination node must be a dictionary"
        assert (
            "latitude" in origin_coord_dict.keys()
        ), "Origin node must have a latitude"
        assert (
            "longitude" in origin_coord_dict.keys()
        ), "Origin node must have a longitude"
        assert (
            "latitude" in destination_coord_dict.keys()
        ), "Destination node must have a latitude"
        assert (
            "longitude" in destination_coord_dict.keys()
        ), "Destination node must have a longitude"
        assert (
            origin_coord_dict["latitude"] >= -90
            and origin_coord_dict["latitude"] <= 90
        ), "Origin latitude must be between -90 and 90"
        assert (
            origin_coord_dict["longitude"] >= -180
            and origin_coord_dict["longitude"] <= 180
        ), "Origin longitude must be between -180 and 180"
        assert (
            destination_coord_dict["latitude"] >= -90
            and destination_coord_dict["latitude"] <= 90
        ), "Destination latitude must be between -90 and 90"
        assert (
            destination_coord_dict["longitude"] >= -180
            and destination_coord_dict["longitude"] <= 180
        ), "Destination longitude must be between -180 and 180"
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
        )

    def add_coord_node(
        self,
        coord_dict: dict[str, float | int],
        auto_edge: bool = True,
        circuity: float | int = 1,
        node_addition_type: str = "quadrant",
        node_addition_math: str = "euclidean",
        lat_lon_bound: float | int = 5,
        silent: bool = False,
        temp_node: bool = False,
        mode: str | None = None,
    ) -> int:
        """
        Function:

        - Add a node to the network
        - Returns the id of the new node
        - Automatically updates the distance matrix to include distances to/from the new node (symmetric)

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
            - Type: bool
            - What: If True, suppresses all output from the function
            - Default: False
        - `temp_node`
            - Type: bool
            - What: If True, the node is considered temporary and will not be used to increase the __original_graph_length__ value
            - Default: False
        - `mode`
            - Type: str | None
            - What: The name of the node's mode: the first mode of that name in `modes`, added if there is none
            - Default: None (the mode without a name)

        Returns:

        - The id of the new node

        """
        # Validate the inputs
        assert isinstance(coord_dict, dict), "Node must be a dictionary"
        assert "latitude" in coord_dict.keys(), "Node must have a latitude"
        assert "longitude" in coord_dict.keys(), "Node must have a longitude"
        assert (
            coord_dict["latitude"] >= -90 and coord_dict["latitude"] <= 90
        ), "Latitude must be between -90 and 90"
        assert (
            coord_dict["longitude"] >= -180 and coord_dict["longitude"] <= 180
        ), "Longitude must be between -180 and 180"
        node = [coord_dict["latitude"], coord_dict["longitude"]]
        if auto_edge:
            assert circuity >= 1, "Circuity must be greater than or equal to 1"
            assert node_addition_type in [
                "quadrant",
                "all",
                "closest",
                "kdclosest",
                "kdquadrant",
            ], f"Invalid node addition type provided ({node_addition_type}), valid options are: ['kdclosest', 'closest', 'kdquadrant', 'quadrant', 'all']"
            assert isinstance(
                lat_lon_bound, (int, float)
            ), "Lat_lon_bound must be a number"
            assert lat_lon_bound > 0, "Lat_lon_bound must be greater than 0"
            # Get the distances to all relevant nodes
            node_dict = self.__get_node_distances__(
                node=node,
                circuity=circuity,
                node_addition_type=node_addition_type,
                lat_lon_bound=lat_lon_bound,
                silent=silent,
            )
        else:
            node_dict = {}

        if not temp_node:
            self.__original_graph_length__ += 1

        mode_row = self.__mode_row__(mode)  # before any change: may raise
        # Create the node
        new_node_id = self.graph_object.add_node(
            node_dict=node_dict, symmetric=True
        )
        self.nodes.append(node)
        self.node_modes.append(mode_row)
        self.snap_index = None
        return new_node_id

    def __mode_row__(self, name: str | None) -> int:
        # The row of the first mode named `name`, added if there is none
        for row, mode in enumerate(self.modes):
            if mode.get("name") == name:
                return row
        if len(self.modes) == 256:
            raise ValueError("A geograph has at most 256 modes")
        self.modes.append({"name": name})
        return len(self.modes) - 1

    def remove_coord_node(self) -> None:
        """
        Function:

        - Remove the last coord node that was appended to the graph
        - Assumes that this node has symmetric flows
            - EG: If node A has a distance of 10 to node B, then node B has a distance of 10 to node A
        """
        self.remove_node(symmetric_node=True)
        self.nodes.pop()
        del self.node_modes[len(self.nodes) :]
        self.snap_index = None

    def add_haversine_edge(
        self,
        origin_idx: int,
        destination_idx: int,
        symmetric: bool = True,
    ) -> None:
        """
        Function:

        - Add an arc to the graph

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
        """
        assert origin_idx < len(
            self.graph_object.graph
        ), "Origin node does not exist"
        assert destination_idx < len(
            self.graph_object.graph
        ), "Destination node does not exist"
        self.add_edge(
            origin_id=origin_idx,
            destination_id=destination_idx,
            distance=haversine(
                self.nodes[origin_idx], self.nodes[destination_idx]
            ),
            symmetric=symmetric,
        )

    def merge_with_other_geograph(
        self,
        other_geograph,
        connection_nodes: list[list[int | float]],
        circuity_to_current_geograph: float | int = 1.2,
        circuity_to_other_geograph: float | int = 1.2,
        node_addition_type_current_geograph: str = "closest",
        node_addition_type_other_geograph: str = "closest",
        node_addition_math: str = "euclidean",
        mode: str | None = None,
    ) -> None:
        """
        Function:

        - Merge the current geograph with another geograph
        - This is useful for combining multiple geographs into one
        - This modifies the current geograph in place

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
        - `mode`
            - Type: str | None
            - What: The name of the connection nodes' mode (see `add_coord_node`); the other geograph's modes are added after this geograph's, so that its nodes keep theirs
            - Default: None (the mode without a name)
        """
        node_connection_mapper = {}
        original_other_graph_length = len(other_geograph.nodes)
        original_other_modes = len(other_geograph.modes)
        if len(self.modes) + original_other_modes + 1 > 256:
            raise ValueError("A geograph has at most 256 modes")
        # Connection nodes connect to the two networks as they were before
        # the merge, not to each other
        current_index = self.snap_index
        other_index = other_geograph.snap_index
        for idx, node in enumerate(connection_nodes):
            node_dict = {
                "latitude": node[0],
                "longitude": node[1],
            }
            self.snap_index = current_index
            other_geograph.snap_index = other_index
            # Add the connection node to the current geograph
            new_node_id = self.add_coord_node(
                coord_dict=node_dict,
                circuity=circuity_to_current_geograph,
                node_addition_type=node_addition_type_current_geograph,
                node_addition_math=node_addition_math,
                mode=mode,
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
        node_ids = self.node_ids.take(range(graph_length))
        floor = min(0, min(node_ids, default=0))
        node_ids.extend(
            i if i >= 0 else i + floor
            for i in other_geograph.node_ids.take(
                range(original_other_graph_length)
            )
        )
        # Add the other graph nodes to the current geograph (removing the connection nodes since they are already added to the current geograph)
        self.nodes += deepcopy(other_geograph.nodes)[
            :original_other_graph_length
        ]
        self.node_ids = network_file.NodeIds(node_ids, self.nodes)
        # Its modes follow this graph's, renumbered
        offset = len(self.modes)
        self.modes += [
            dict(row) for row in other_geograph.modes[:original_other_modes]
        ]
        self.node_modes.extend(
            offset + row
            for row in other_geograph.node_modes[:original_other_graph_length]
        )
        self.snap_index = None

        # Clean up the other geograph to remove any appended nodes
        while len(other_geograph.nodes) > original_other_graph_length:
            other_geograph.remove_coord_node()
        del other_geograph.modes[original_other_modes:]

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


def _keep_interior_points(shapes, nodes):
    # Arc shapes hold the points between the arc's two nodes, from origin to destination:
    # reverse a shape that runs from the destination to the origin, remove the points
    # equal to the origin at its start and to the destination at its end, and the arcs
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


def _in_hilbert_order(geograph):
    # A copy of the geograph with its nodes in Hilbert order within each mode: ids
    # change, lengths do not (where two routes tie, another may be returned)
    multimodal = len(geograph.modes) > 1
    order = hilbert_order(
        geograph.nodes, geograph.node_modes if multimodal else None
    )
    # Each node keeps its id (its position before ordering, if it had none)
    node_ids = geograph.node_ids.take(order)
    new_id = [0] * len(order)
    for new, old in enumerate(order):
        new_id[old] = new
    if Graph.__module__ == "scgraph.cpp":
        # Renumbered as arrays (read as dicts, the C++ graph would be copied whole), which
        # the new graph keeps instead of copying them again
        graph = Graph._from_mapped_csr(*geograph.graph_object._csr(order))
    else:
        # Renumbered dicts, sharing the graph's weight objects (from_csr would not)
        rows = geograph.graph_object.unreduced_graph
        graph = [
            {new_id[head]: weight for head, weight in rows[old].items()}
            for old in order
        ]
    shapes = geograph.intermediate_nodes
    return GeoGraph(
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
        node_ids=(
            None if node_ids == array("q", range(len(order))) else node_ids
        ),
        node_modes=[geograph.node_modes[old] for old in order],
        modes=geograph.modes,
    )


def _joined(network, key):
    """One field (credit, license) of the sources of a network, each value once."""
    return "; ".join(dict.fromkeys(s[key] for s in network.SOURCES.values()))


class GeoGraphUtils:
    def __get_quadrant_node_indices__(self, node: list) -> set[int]:
        indices = self.snap_index.closest_idx_per_quadrant(point=node)
        node_indices = {idx for idx in indices.values() if idx is not None}
        if not node_indices:
            node_indices.add(self.snap_index.closest_idx(point=node))
        return node_indices

    def __get_node_distances__(
        self,
        node: list,
        circuity: float | int,
        node_addition_type: str,
        lat_lon_bound: float | int,
        silent: bool = False,
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
                - 'closest' / 'kdclosest': Connect to the nearest node with the snapping index (`snap_index`)
                - 'quadrant' / 'kdquadrant': Connect to nearest nodes in each quadrant with the snapping index (`snap_index`)
                - 'all': Connect to every node inside the latitude/longitude bound
            - Notes:
                - The snapping index searches the full graph; the bound applies only to 'all'
        - `lat_lon_bound`
            - Type: int | float
            - What: Forms a bounding box around the node that is to be added to graph. Only selects graph nodes to consider joining that are within this bounding box.

        Optional Arguments:

        - `silent`
            - Type: bool
            - What: Whether to suppress output messages
            - Default: False
        """
        if node_addition_type in ["kdclosest", "closest"]:
            closest_idx = self.snap_index.closest_idx(point=node)
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
                for idx in self.__get_quadrant_node_indices__(node)
            }
        assert (
            node_addition_type == "all"
        ), f"Invalid node addition type provided ({node_addition_type})"
        # Get only bounded nodes
        # Find the only keep nodes that are within the bounding latitude
        top_lat = node[0] + lat_lon_bound
        bottom_lat = node[0] - lat_lon_bound
        top_lon = node[1] + lat_lon_bound
        bottom_lon = node[1] - lat_lon_bound
        nodes = {
            node_idx: node_i
            for node_idx, node_i in enumerate(self.nodes)
            if node_i[0] >= bottom_lat
            and node_i[0] <= top_lat
            and node_i[1] >= bottom_lon
            and node_i[1] <= top_lon
        }
        if len(nodes) == 0:
            print_console(
                f"When adding your origin or destination node to the graph, no nodes found within the bounding box of {lat_lon_bound} degrees around the node {node}.",
                silent=silent,
            )
            print_console(
                "Using the snapping index to find the closest node instead.",
                silent=silent,
            )
            closest_idx = self.snap_index.closest_idx(point=node)
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
    ) -> list[list[float | int]]:
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
            assert sequence in [
                "lat_lon",
                "lon_lat",
            ], f"Invalid sequence provided ({sequence}), valid options are: ['lat_lon', 'lon_lat']"
            out = self.intermediate_nodes[origin_idx].get(destination_idx, [])
            if sequence == "lon_lat":
                out = [[coord[1], coord[0]] for coord in out]
            return out
        else:
            return []

    def __format_coordinates__(
        self,
        coordinate_path: list[list[float | int]],
        output_format: str = "list_of_lists",
    ) -> list:
        """
        Function:

        Arguments:

        - `coordinate_path`
            - Type: list of lists
            - What: A list of lists where each sublist is a coordinate [latitude, longitude]
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
    ) -> list[list[float | int]]:
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
            if isinstance(nodes, network_file.NodeCoordinates)
            else [nodes[node_id] for node_id in path]
        )
        if (
            get_intermediate_nodes
            and self.intermediate_nodes is not None
            and path
        ):
            if isinstance(self.intermediate_nodes, network_file.ArcShapes):
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
        off_graph_circuity: float | int = None,
        output_units: str = "km",
    ) -> float:
        """
        Function:

        - Compute the total weight of a pre-computed path in this geograph's units

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

        Returns:

        - The total weight of the path in this geograph's edge units, converted
          to `output_units`
        """
        if off_graph_circuity is None:
            off_graph_circuity = self.default_off_graph_circuity
        path = path_result.get("path")
        coordinate_path = path_result.get("coordinate_path")
        assert (
            path is not None
        ), "path_result must contain a 'path' key; call get_shortest_path with output_path=True"
        assert (
            coordinate_path is not None
        ), "path_result must contain a 'coordinate_path' key"

        origin = coordinate_path[0]
        destination = coordinate_path[-1]

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
    ):
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
    ):
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
        nodes: list[list[float | int]],
        validate: bool = False,
        intermediate_nodes: list[list[list[float | int]]] = None,
        default_off_graph_circuity: float | int = 1,
        default_node_addition_circuity: float | int = 4,
        geograph_units: Literal["km", "m", "mi", "ft"] = "km",
        node_ids: list[int] | None = None,
        node_modes: list[int] | None = None,
        modes: list[dict] | None = None,
    ) -> None:
        """
        Function:

        - Create a GeoGraph object

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
            - What: One dict per node, {destination: [[latitude, longitude], ...]}: the coordinates of each arc's shape, between its two nodes (not repeated), from origin to destination
            - Note: Allows for more detailed path plotting along arcs without needing to increase the number of nodes in the graph
            - Default: None
        - `node_ids`
            - Type: list of ints | None
            - What: The stable id of each node, for example its id in the source the network was built from; read back as `node_ids`
            - Note: Node ids in paths and graph methods stay positions; `[geograph.node_ids[p] for p in path]` translates a path
            - Note: Nodes added later (`add_coord_node`, merges) get negative ids, below all the others; extend `nodes` in place (replacing it leaves `node_ids` counting the former list)
            - Default: None (each node's id is its position)
        - `node_modes`
            - Type: list of ints | None
            - What: The mode of each node (road, sea, port, ...), as its row in `modes`; read back as `node_modes`
            - Note: `(mode, node id)` identifies a node: node ids of different modes may come from different sources
            - Default: None (every node in the first mode)
        - `modes`
            - Type: list of dicts | None
            - What: The modes, each a dict with its `name` (str or None) and, optionally, the `source` of its node ids (the name of an entry of the network's sources); read back as `modes`
            - Note: At most 256 modes; two modes may have the same name (two sea networks merged)
            - Default: None (one mode, without a name: `[{"name": None}]`)
        - `default_off_graph_circuity`
            - Type: float | int
            - What: The default circuity factor to apply to any distance calculations between your origin and destination nodes and their connecting nodes in the graph
            - Note: This can be used to account for graphs in different units than kilometers (like time).
                - EG: For time, you may opt to just make this 0 so that the off graph distance is not counted towards the total path length (time)
                - EG: For travel_time in seconds, you could assume that the off graph travel speed is 30 km/h, so the off graph circuity should be 3600 / 30 = 120
            - See: `off_graph_circuity` notes in `get_shortest_path` for more information on how to set this value appropriately for your use case
            - Default: 1
        - `default_node_addition_circuity`
            - Type: float | int
            - What: The default circuity factor to apply when adding your origin and destination nodes to the distance matrix
            - See: `default_off_graph_circuity` notes above for more information on how to set this value appropriately for your use case
            - See: `node_addition_circuity` notes in `get_shortest_path` for more information on how to set this value appropriately for your use case
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
        if node_ids is not None and len(node_ids) != len(nodes):
            raise ValueError("node_ids must give one id per node")
        self.node_ids = network_file.NodeIds(
            range(len(nodes)) if node_ids is None else node_ids, nodes
        )
        self.modes = (
            [dict(mode) for mode in modes] if modes else [{"name": None}]
        )
        self.node_modes = array(
            "B", bytes(len(nodes) if node_modes is None else node_modes)
        )
        if node_modes is not None and (
            len(self.node_modes) != len(nodes)
            or max(self.node_modes, default=0) >= len(self.modes)
        ):
            raise ValueError("node_modes must give each node a row of modes")
        self.intermediate_nodes = intermediate_nodes
        self.default_off_graph_circuity = default_off_graph_circuity
        self.default_node_addition_circuity = default_node_addition_circuity
        self.default_get_intermediate_nodes = (
            True if intermediate_nodes is not None else False
        )
        self.geograph_units = geograph_units
        # Built at the first snap, not here: a GeoGraph that never snaps never pays for it
        self.snap_index = None
        # len(nodes), not len(graph): a C++ graph would be copied to Python to count it
        self.__original_graph_length__ = len(self.nodes)

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
    def snap_index(self) -> SnapIndex:
        """
        The index that snaps coordinates to their nearest nodes (`closest_idx(point)`,
        `closest_idx_per_quadrant(point)`), built when a network file is loaded or else at
        the first snap, and again after nodes were added or removed.
        """
        # Dropped by add_coord_node, remove_coord_node and merge_with_other_geograph (merge
        # keeps the index of the networks before the merge while it connects them); direct
        # edits of nodes are not detected
        if self.__snap_index__ is None:
            nodes = self.nodes
            self.__snap_index__ = (
                SnapIndex.from_arrays(*nodes.arrays())
                if isinstance(nodes, network_file.NodeCoordinates)
                else SnapIndex(nodes)
            )
        return self.__snap_index__

    @snap_index.setter
    def snap_index(self, snap_index: SnapIndex | None) -> None:
        self.__snap_index__ = snap_index
        # Node coordinates in radians for the native A* heuristic, rebuilt with the index
        self.__node_radians__ = None
        if snap_index is None:
            self.__geokdtree__ = None

    @property
    def geokdtree(self):
        """
        Deprecated: a `geokdtree.GeoKDTree` of the nodes. GeoGraph snaps with `snap_index`,
        which has the same `closest_idx` and `closest_idx_per_quadrant` methods.
        """
        warnings.warn(
            "GeoGraph.geokdtree is deprecated: GeoGraph snaps with snap_index, which has "
            "the same closest_idx and closest_idx_per_quadrant methods",
            DeprecationWarning,
            stacklevel=2,
        )
        if self.__geokdtree__ is None:
            from geokdtree import GeoKDTree

            self.__geokdtree__ = GeoKDTree(points=self.nodes)
        return self.__geokdtree__

    @geokdtree.setter
    def geokdtree(self, geokdtree) -> None:
        # Setting it to None asked for a rebuild after editing the nodes: drop the index too
        if geokdtree is None:
            self.snap_index = None
        self.__geokdtree__ = geokdtree

    def __get_node_radians__(self) -> tuple[array, array]:
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

        Optional Arguments:

        - `iterations`:
            - Type: int
            - What: Number of reduction iterations to perform. If -1, reduces iteratively until convergence. If 0, no reduction is done.
            - Default: -1

        Returns:

        - None
        """
        if iterations != 0:
            self.graph_object.reduce(iterations)

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
        assert isinstance(
            self.nodes, (list, network_file.NodeCoordinates)
        ), "Your nodes must be a list"
        assert all(
            [isinstance(i, list) for i in self.nodes]
        ), "Your nodes must be a list of lists"
        assert all(
            [len(i) == 2 for i in self.nodes]
        ), "Your nodes must be a list of lists where each sub list has a length of 2"
        assert all(
            [
                (
                    isinstance(i[0], (int, float))
                    and isinstance(i[1], (int, float))
                )
                for i in self.nodes
            ]
        ), "Your nodes must be a list of lists where each sub list has a numeric latitude and longitude value"
        assert all(
            [
                (i[0] >= -90 and i[0] <= 90 and i[1] >= -180 and i[1] <= 180)
                for i in self.nodes
            ]
        ), "Your nodes must be a list of lists where each sub list has a length of 2 with a latitude [-90,90] and longitude [-180,180] value"

    def __get_node_addition_type__(self, node_addition_type):
        if node_addition_type == "kdclosest":
            return "closest"
        elif node_addition_type == "kdquadrant":
            return "quadrant"
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
        silent=False,
    ):
        if node_addition_type == "closest":
            idx = self.snap_index.closest_idx(point=node)
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
                for idx in self.__get_quadrant_node_indices__(node)
            }
        else:
            return self.__get_node_distances__(
                node=node,
                circuity=circuity,
                node_addition_type=node_addition_type,
                lat_lon_bound=lat_lon_bound,
                silent=silent,
            )
        raise ValueError(
            "node_addition_type must be one of 'closest', 'quadrant', or 'all'"
        )

    def get_shortest_path(
        self,
        origin_node: dict[str, float | int],
        destination_node: dict[str, float | int],
        output_units: str = "km",
        algorithm_fn: str = "bidirectional_buckets",
        algorithm_kwargs: dict = None,
        off_graph_circuity: float | int = 1,
        node_addition_type: str = "kdclosest",
        node_addition_circuity: float | int = 4,
        output_coordinate_path: str = "list_of_lists",
        output_path: bool = False,
        node_addition_lat_lon_bound: float | int | Literal["auto"] = "auto",
        node_addition_math: str = "euclidean",
        destination_node_addition_type: str = "kdclosest",
        auto_lat_lon_bound_max: float | int = 2,
        silent: bool = False,
        length_only: bool = False,
        get_intermediate_nodes: bool = None,
        **kwargs,
    ) -> dict:
        """
        Function:

        - Identify the shortest path between two nodes in a sparse network graph

        - Return a dictionary of various path information including:
            - `id_path`: A list of node ids in the order they are visited
            - `path`: A list of nodes  (list of lat then long) in the order they are visited
            - `length`: The length of the path

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
                    - Only the origin graph node is cached (not the off-graph origin coordinate)
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
            - What: The circuity factor to apply to any distance calculations between your origin and destination nodes and their connecting nodes in the graph
            - Default: 1 (more specifically self.default_off_graph_circuity)
            - Notes:
                - For alogrithmic solving purposes, the node_addition_circuity is applied to the origin and destination nodes when they are added to the graph
                - This is only applied after an `optimal solution` using the `node_addition_circuity` has been found when it is then adjusted to equal the `off_graph_circuity`
                - The off graph KM multiplied by this value is added to the total path length to account for the distance traveled off the graph
        - `node_addition_type`
            - Type: str
            - What: The type of node addition to use when adding your origin node to the distance matrix
            - Default: 'kdclosest'
            - Options:
                - 'kdclosest' / 'closest': Add the closest node with the snapping index (`snap_index`)
                - 'kdquadrant' / 'quadrant': Add the closest node in each quadrant with the snapping index (`snap_index`)
                - 'all': Add all nodes within the bounding box to the distance matrix for this node
        - `node_addition_circuity`
            - Type: int | float
            - What: The circuity factor to apply when adding your origin and destination nodes to the distance matrix
            - Default: 4 (more specifically self.default_node_addition_circuity)
            - Note:
                - This defaults to 4 to prevent the algorithm from taking a direct route in direction of the destination over some impassible terrain (EG: a maritime network that goes through land)
                - A higher value will push the algorithm to join the network at a closer node to avoid the extra distance from the circuity factor
                - This factor affects 'all' and 'quadrant' connections but is not necessary for 'closest' since there is only one entry point.
                - This factor is used to calculate the node sequence for the `optimal route`, however the reported `length` of the path will be calculated using the `off_graph_circuity` factor
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
            - Default: 'kdclosest'
            - Options:
                - 'kdclosest' / 'closest': Add the closest node with the snapping index (`snap_index`)
                - 'kdquadrant' / 'quadrant': Add the closest node in each quadrant with the snapping index (`snap_index`)
                - 'all': Add the node to all points in the graph within the bounding box
        - `silent`
            - Type: bool
            - What: If True, suppresses all output from the function
            - Default: False
        - `length_only`
            - Type: bool
            - What: If True, only returns the length of the path
            - Default: False
        - `get_intermediate_nodes`
            - Type: bool
            - What: If True, returns the intermediate nodes in the path (if they exist for each segment)
            - Default: self.default_get_intermediate_nodes
        - `**kwargs`
            - Additional keyword arguments. These are included for forwards and backwards compatibility reasons, but are not currently used.
        """
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
        if callable(algorithm_fn):
            algorithm_kwargs["graph"] = self.graph_object.unreduced_graph
        elif isinstance(algorithm_fn, str):
            heuristic_fn = algorithm_kwargs.get("heuristic_fn")
            if (
                algorithm_fn == "a_star"
                and hasattr(self.graph_object, "a_star_great_circle")
                and getattr(heuristic_fn, "__self__", None) is self
                and getattr(heuristic_fn, "__func__", None)
                is GeoGraphDistanceCalculations.haversine
            ):
                # The built-in haversine heuristic is computed natively in the C++ build
                latitudes, longitudes = self.__get_node_radians__()
                algorithm_kwargs.pop("heuristic_fn")
                algorithm_fn = partial(
                    self.graph_object.a_star_great_circle,
                    latitudes=latitudes,
                    longitudes=longitudes,
                    radius=earth_radius.get(self.geograph_units, 6371),
                )
            elif hasattr(self.graph_object, algorithm_fn):
                algorithm_fn = getattr(self.graph_object, algorithm_fn)
            else:
                raise ValueError("algorithm_fn must be a string or callable")
        else:
            raise ValueError("algorithm_fn must be a string or callable")

        node_addition_type = self.__get_node_addition_type__(node_addition_type)
        destination_node_addition_type = self.__get_node_addition_type__(
            destination_node_addition_type
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

            # Snap the origin and destination to their nearest nodes in the graph
            origin_id = self.__snap_node__(
                node=origin,
                circuity=node_addition_circuity,
                node_addition_type=node_addition_type,
                lat_lon_bound=node_addition_lat_lon_bound,
                silent=silent,
            )
            destination_id = self.__snap_node__(
                node=destination,
                circuity=node_addition_circuity,
                node_addition_type=destination_node_addition_type,
                lat_lon_bound=node_addition_lat_lon_bound,
                silent=silent,
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

            if direct_node_addition_length <= min_entry_exit:
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

            # Convert the length to the desired output units
            output["length"] = distance_converter(
                output["length"],
                input_units=self.geograph_units,
                output_units=output_units,
            )
            # Early return if only length is needed
            if length_only:
                return {"length": output["length"]}

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

            if not output_path:
                del output["path"]
            return output

        except Exception as e:
            print_console(
                (
                    "An error occurred while calculating the shortest path:\n"
                    "This is likely caused by a disconnect in the graph.\n"
                    "You can ensure a solution by setting destination_node_addition_type='all' and setting your lat_lon_bound=180.\n"
                    "This will, however, result in a much longer runtime per shortest path query.\n"
                    "If not in an exception block, see the stacktrace below for more details:\n"
                ),
                silent=silent,
            )
            raise e

    def distance_matrix(
        self,
        nodes: list[dict[str, float | int]],
        off_graph_circuity: float | int = 1,
        output_units: str = "km",
        silent: bool = False,
    ) -> list[list[float | int | None]]:
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
            - Options: 'km', 'miles', 'meters', 'feet'

        Returns:

        - A list of lists representing the distance matrix between the nodes
        - The distance matrix is a square matrix where the entry at (i, j) is the distance between node i and node j
        - The distances are in the units specified by `output_units`
        - EG:
        ```
        [
            [0.0, 0.1, ...],
            [0.1, 0.0, ...],
            ...
        ]
        """
        output_matrix = [[None] * len(nodes) for _ in range(len(nodes))]
        dist_multiplier = distance_converter(
            distance=1,
            input_units=self.geograph_units,
            output_units=output_units,
        )
        # Get the entry idx for each node as well as the distance to that node given the off-graph circuity
        # [(entry_idx, distance), ...]
        entry_idx_and_distance = []
        for node in nodes:
            node_idx = self.snap_index.closest_idx(
                point=[node["latitude"], node["longitude"]]
            )
            distance = haversine(
                [node["latitude"], node["longitude"]],
                self.nodes[node_idx],
                circuity=off_graph_circuity,
                units=output_units,  # Store directly as output units since this is a post processing step
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
                    length = self.graph_object.cached_shortest_path(
                        origin_id=entry_idx_start,
                        destination_id=entry_idx_end,
                        length_only=True,
                    )["length"]
                    output_matrix[node_idx_start][node_idx_end] = (
                        (length * dist_multiplier)
                        + entry_length_start
                        + entry_length_end
                    )
                except Exception as e:
                    print_console(
                        f"Error calculating distance between nodes {node_idx_start} and {node_idx_end} with entry indices {entry_idx_start} and {entry_idx_end}.",
                        silent=silent,
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
