"""Read the ways of an OpenStreetMap file, for `GeoGraph.load_from_osm` and for the
OpenStreetMap pipelines.

The module needs the optional dependency `osmium` (`pip install scgraph[osm]`). It
imports `osmium` only when it reads a file.

WHAT IT ANSWERS

`read_osm` gives a graph in the layout of a GeoGraph, for `load_from_osm`.
`build_way_pieces` gives the pieces of the kept ways (`step3_network_assembly.PieceArrays`), for a
pipeline. A select function chooses the ways. It takes the tags of a way. It returns
the direction of the way: 1 (one way, in the order of its nodes), -1 (one way, against
that order) or 0 (both ways). It returns None to leave the way out.

A pipeline gives its select functions as `{mode: {kind: select}}`. A mode is a group
of ways that are cut and joined together. A multimodal pipeline names it as in its
modes table. A mode has one select function for each kind of way. The kinds are `ways`
and `ferries`. The kind `ferries` is special: `build_way_pieces` does not cut a ferry
by length, and attaches it to the nodes of its mode.

A select function may return the direction with the class of the way (docstring of
`scgraph.pipelines`, *The classes*). Example: for a one-way trunk road,
`geofabrik_multimodal.select_main_roads_with_class` returns `(1, "trunk")`.

HOW A FILE IS READ

An OpenStreetMap file lists the nodes, then the ways. A way lists the ids of its
nodes, not their positions. So `locate_ways` reads the file in three passes:

1. It reads the ways. It notes the ids of the nodes of the kept ways. In each mode, a
   node met a second time is a junction of that mode.
2. It reads the nodes, and stores the position of each noted node.
3. It reads the ways again, and gives each kept way with the positions of its nodes.

These three passes are one read of the file.

`cut_polylines` then cuts each way into pieces: at each junction of its mode, and at
the first point where a piece reaches `max_km_between_nodes`.

Example: two roads share node 7, and no other node. Pass 1 meets node 7 twice, so node
7 is a junction, and each road is cut there.

HOW TWO MODES STAY APART

One read serves every mode. Each mode has its own junctions and its own pieces. So a
piece of a road never joins a piece of a railway.

Example: a road and a railway share node 9, at a level crossing. Pass 1 meets node 9
once in the ways of `road` and once in the ways of `rail`. Node 9 is a junction of
neither mode, and neither way is cut there.

Example: a way with the tags `railway=rail` and `route=shuttle_train` is a railway and
a vehicle ferry, so both modes keep it. Each mode meets each of its nodes once. No node
of the way is a junction for that reason. With one set of met nodes for the two modes,
pass 1 would meet the way twice: each of its nodes would be a junction, and the way
would be cut at every node.

WHERE THE FILE IS

The file is on disk, or on a server. `StreamedPbf` reads a file on a server by HTTP
byte ranges and never stores it. The planet is read this way.
"""

import gc
import json
import logging
import math
import os
import struct
import subprocess
import sys
import time
from array import array
from bisect import bisect_left
from collections import defaultdict
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from functools import partial
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING

import requests

from scgraph.helpers.polylines import cut_polylines, build_graph_from_polylines
from scgraph.pipelines import CLASS_ROWS, CLASSES, download_file
from scgraph.pipelines.steps.near_nodes import NearNodes
from scgraph.pipelines.steps.step3_network_assembly import (
    PieceArrays,
)
from scgraph.utils import _log_step, has_cpp

if TYPE_CHECKING:  # annotations only: osmium stays optional at run time
    import osmium

logger = logging.getLogger(__name__)

__all__ = [
    "GEOFABRIK",
    "PLANET",
    "download",
    "download_streamed",
    "get_way_direction",
    "select_main_roads",
    "select_vehicle_ferries",
]

# The OpenStreetMap extracts of Geofabrik, `{region}` being the path of an extract
GEOFABRIK = {
    "url": "https://download.geofabrik.de/{region}-latest.osm.pbf",
    "credit": "© OpenStreetMap contributors",
    "license": "ODbL-1.0",
    "license_url": "https://www.openstreetmap.org/copyright",
}

MAIN_ROADS = {
    "motorway",
    "motorway_link",
    "trunk",
    "trunk_link",
    "primary",
    "primary_link",
}
# The length in km at which a way is cut, at the next point. With nodes this close,
# the origin and the destination of a route join the network near where they are.
MAX_KM_BETWEEN_NODES = 2
# The farthest that an end of a ferry may be from the road node that it joins, in km
FERRY_END_KM = 2
_ONE_WAY = {"yes": 1, "true": 1, "1": 1, "-1": -1, "reverse": -1}


def require_osmium() -> ModuleType:
    """Return the module `osmium`. Raise an ImportError that says how to install it
    when it is missing."""
    try:
        import osmium
    except ImportError as error:
        raise ImportError(
            "Reading OSM files needs the optional dependency osmium: pip install scgraph[osm]"
        ) from error
    return osmium


def download(url: str, filename: str | os.PathLike) -> dict[str, str]:
    """Download an OSM file to `filename`.

    Returns:
        `{"version": time}` when the header of the file gives the time that its data is
        up to (`osmosis_replication_timestamp`, as Geofabrik writes it), and `{}`
        otherwise.
    """
    # osmium is checked first: without it, a large extract would be downloaded and
    # then not read
    osmium = require_osmium()
    download_file(url, filename)
    try:
        reader = osmium.io.Reader(filename, osmium.osm.osm_entity_bits.NOTHING)
    except RuntimeError:  # not an OSM file: another source of the same network
        return {}
    try:
        version = reader.header().get("osmosis_replication_timestamp")
    finally:
        reader.close()
    return {"version": version} if version else {}


def get_way_direction(tags: "osmium.osm.TagList") -> int:
    """Return the direction of a way from its tags.

    - 1 (one way, in the order of its nodes) for `oneway=yes`, `true` or `1`, and for a
      motorway or a roundabout without a `oneway` tag;
    - -1 (one way, against that order) for `oneway=-1` or `reverse`;
    - 0 (both ways) otherwise.
    """
    if tags.get("oneway") in _ONE_WAY:
        return _ONE_WAY[tags["oneway"]]
    # One way without a tag in OSM: motorways and roundabouts
    if tags.get("oneway") is None and (
        tags.get("highway") == "motorway"
        or tags.get("junction") in ("roundabout", "circular")
    ):
        return 1
    return 0


def select_main_roads(tags: "osmium.osm.TagList") -> int | None:
    """Return the direction of a main road (`MAIN_ROADS`), and None for any other way."""
    return (
        get_way_direction(tags) if tags.get("highway") in MAIN_ROADS else None
    )


@contextmanager
def _open_source(source, entities):
    # `source` is a path, or a source object. A source object gives a new input for
    # each pass, and the pass closes it at its end (see `locate_ways`).
    if isinstance(source, (str, os.PathLike)):
        yield source
        return
    file = source.file(entities)
    try:
        yield file
    except BaseException:
        source.close(stop=True)
        raise
    source.close()


def _select_ways(osmium, source, selects, tag_keys, *filters):
    """Yield `(mode, kind, direction, class_name, way)` for each way, once for each
    mode that keeps it. In a mode, a way goes to the first select function that keeps
    it, in the order of the dict. `class_name` is None when the select function returns
    a direction alone. osmium drops the ways that have none of `tag_keys`, and the ways
    that `filters` refuse, before Python sees them.
    """
    with _open_source(source, osmium.osm.WAY) as file:
        ways = osmium.FileProcessor(file, osmium.osm.WAY)
        if tag_keys:
            ways = ways.with_filter(osmium.filter.KeyFilter(*tag_keys))
        for osmium_filter in filters:
            ways = ways.with_filter(osmium_filter)
        for way in ways:
            for mode, kinds in selects.items():
                for kind, select in kinds.items():
                    selected = select(way.tags)
                    if selected is None:
                        continue
                    direction, class_name = (
                        selected
                        if isinstance(selected, tuple)
                        else (selected, None)
                    )
                    if (
                        type(direction) is not int
                        or not -1 <= direction <= 1
                        or (
                            class_name is not None
                            and class_name not in CLASS_ROWS
                        )
                    ):
                        raise ValueError(
                            f"select returned {selected!r}: 1, -1, 0, a pair "
                            "(direction, name of scgraph.pipelines.CLASSES) or None"
                        )
                    yield mode, kind, direction, class_name, way
                    break


class _Junctions:
    """The ids of the junctions, sorted, in one array: 8 bytes per junction.
    `id in junctions` looks an id up by bisection.

    Memory while the object is built: the list of the repeated node ids takes about 40
    bytes per repeat. A node that the ways of a mode use k times appears k - 1 times in
    this list.
    """

    def __init__(self, ids):
        self.ids = array("q")
        for ref in sorted(ids):
            if not self.ids or self.ids[-1] != ref:
                self.ids.append(ref)

    def __contains__(self, ref):
        i = bisect_left(self.ids, ref)
        return i < len(self.ids) and self.ids[i] == ref


class _PagedIdSet:
    """A set of node ids, as one bit for each id. The bits are in pages of 4 kB. A page
    covers 32,768 ids, and exists only when one of them is set. `get` and `set` are
    those of an osmium `IdSet`.

    An osmium `IdSet` takes too much memory for one set per mode. It allocates 4 MB for
    each range of 33.5 million ids that holds a node: 1.5 GB for the 41,009 rail node
    ids of Denmark. This set takes about 15 MB for them (3,609 pages), and about 61 MB
    for the 107,968 node ids of the main roads and ferries of Denmark (14,782 pages).
    On the planet, a set takes at most about 1.9 GB, when every page exists: 14.4
    billion ids / 32,768 ids per page * 4,096 bytes, and the Python object of each
    page. A Python `set` is not used, because it takes about 70 bytes per id. For the
    main roads of the planet, estimated at 57 million node ids, that is about 4 GB.

    Example: id 70,000 is bit 4,464 of page 2, because 70,000 = 2 * 32,768 + 4,464.
    """

    def __init__(self):
        self.pages = defaultdict(lambda: bytearray(4096))

    def get(self, ref):
        page = self.pages.get(ref >> 15)
        if page is None:
            return False
        return bool(page[(ref >> 3) & 4095] & (1 << (ref & 7)))

    def set(self, ref):
        self.pages[ref >> 15][(ref >> 3) & 4095] |= 1 << (ref & 7)


def locate_ways(
    source: "str | os.PathLike | StreamedPbf",
    selects: dict[str, dict[str, Callable]],
    tag_keys: tuple[str, ...] = (),
    work_dir: str | os.PathLike | None = None,
) -> tuple[
    dict[str, _Junctions],
    Iterator[tuple[str, str, int, str | None, list[tuple[int, list[float]]]]],
]:
    """Locate the ways of `source` that the select functions keep.

    The function reads the file in three passes (ways, nodes, ways again), as the module
    docstring explains. One call serves every mode. Example: the modes `road` and
    `rail`, and the kinds `ways` and `ferries` of the mode `road`.

    Args:
        source: The path of an OSM file, or a source object such as `StreamedPbf`. A
            source object has a method `file(entities)`. It returns a new input for
            `osmium.FileProcessor` at each call: one per pass, for the entities that the
            pass reads (`osmium.osm.WAY` or `NODE`). The function calls `close(stop)` at
            the end of each pass. `stop` is true when the pass ended on an exception.
        selects: The select functions, as `{mode: {kind: select}}`. In a mode, a way
            goes to the first function that keeps it, in the order of the dict. A way
            that two modes keep goes to each of them.
        tag_keys: If given, osmium drops the ways that have none of these tag keys,
            before a select function sees them.
        work_dir: A folder for the files of the function. Without it, the positions of
            the nodes are in memory (osmium index `flex_mem`). With it, they are in the
            file `nodes` of the folder (`sparse_file_array`), which a planet file needs.
            The folder also keeps the junctions and the ids of the kept ways. When its
            marker `pass2.done` is there, the function reuses these files and skips
            passes 1 and 2. Otherwise it empties `nodes` first. The caller deletes the
            folder.

    Returns:
        `(junctions, polylines)`. `junctions[mode]` holds the OSM ids of the nodes
        where kept ways of the mode meet, or where one of them crosses itself.
        `id in junctions[mode]` tests one id. `polylines` is a generator of
        `(mode, kind, direction, class_name, vertices)`. `class_name` is the class
        that the select function gave to the way, or None. `vertices` is a list of
        `(id, [latitude, longitude])`. The pair `(direction, vertices)` is a
        polyline, in the form that `cut_polylines` takes. A way is split where one
        of its nodes is missing from the file.

    Memory: the ids of the nodes of the kept ways take about 1.5 GB, whatever the file
    (one bit for each possible id). With several modes, pass 1 also holds the ids of
    the nodes of each mode (`_PagedIdSet`): at most about 1.9 GB for each mode on the
    planet. The ids of the kept ways take about 0.2 GB.
    """
    osmium = require_osmium()
    if work_dir:
        os.makedirs(work_dir, exist_ok=True)
    pass2_done = os.path.join(work_dir, "pass2.done") if work_dir else None
    junction_files = (
        {
            mode: os.path.join(work_dir, f"pass1_junctions_{mode}.bin")
            for mode in selects
        }
        if work_dir
        else {}
    )
    ways_file = os.path.join(work_dir, "pass1_ways.bin") if work_dir else None
    nodes_file = os.path.join(work_dir, "nodes") if work_dir else None
    node_store = "sparse_file_array," + nodes_file if nodes_file else "flex_mem"

    # Resume: if pass 2 was already completed, reload junctions and kept ways from disk
    if (
        work_dir
        and pass2_done
        and os.path.isfile(pass2_done)
        and all(map(os.path.isfile, junction_files.values()))
        and os.path.isfile(ways_file)
        and nodes_file
        and os.path.isfile(nodes_file)
        and os.path.getsize(nodes_file) > 0
    ):
        junctions = {}
        for mode, junction_file in junction_files.items():
            ids = array("q")
            with open(junction_file, "rb") as f:
                ids.fromfile(f, os.path.getsize(junction_file) // 8)
            junctions[mode] = _Junctions.__new__(_Junctions)
            junctions[mode].ids = ids
        kept = osmium.IdTracker()
        with open(ways_file, "rb") as f:
            kept_ways = array("q")
            kept_ways.fromfile(f, os.path.getsize(ways_file) // 8)
        for wid in kept_ways:
            kept.add_way(wid)
        del kept_ways
        store = osmium.index.create_map(node_store)
    else:
        # First pass: the nodes of kept ways. In each mode, a node met a second time
        # is a junction of that mode.
        tracker, kept = osmium.IdTracker(), osmium.IdTracker()
        # `noted_ids` holds the nodes of every mode, for the second pass.
        # `seen_ids[mode]` holds the nodes of one mode. With one mode, the two sets
        # hold the same ids, so `seen_ids[mode]` is `noted_ids`.
        noted_ids = tracker.node_ids()
        seen_ids = {
            mode: noted_ids if len(selects) == 1 else _PagedIdSet()
            for mode in selects
        }
        repeats = {mode: array("q") for mode in selects}
        kept_ways = array("q") if work_dir else None
        # The set and the repeats of the mode of the way that is read
        mode_seen_ids = mode_repeats = None
        for mode, _, _, _, way in _select_ways(
            osmium, source, selects, tag_keys
        ):
            kept.add_way(way.id)
            if kept_ways is not None:
                kept_ways.append(way.id)
            mode_seen_ids, mode_repeats = seen_ids[mode], repeats[mode]
            for node in way.nodes:
                if mode_seen_ids.get(node.ref):
                    mode_repeats.append(node.ref)
                else:
                    mode_seen_ids.set(node.ref)
                    noted_ids.set(node.ref)

        # The sets of the modes are freed before the junctions are built
        del seen_ids, mode_seen_ids
        junctions = {mode: _Junctions(ids) for mode, ids in repeats.items()}
        del repeats, mode_repeats
        gc.collect()

        if work_dir and ways_file:
            for mode, junction_file in junction_files.items():
                with open(junction_file, "wb") as f:
                    junctions[mode].ids.tofile(f)
            with open(ways_file, "wb") as f:
                kept_ways.tofile(f)
            del kept_ways

        # Second pass: locations of kept nodes into store
        if nodes_file:
            open(nodes_file, "wb").close()
        store = osmium.index.create_map(node_store)
        with (
            _open_source(source, osmium.osm.NODE) as file,
            osmium.io.Reader(file, osmium.osm.NODE) as nodes,
        ):
            osmium.apply(
                nodes, tracker.id_filter(), osmium.NodeLocationsForWays(store)
            )
        del tracker, noted_ids
        gc.collect()

        # Drop OS page cache to avoid memory pressure on large extracts
        if nodes_file and hasattr(os, "posix_fadvise"):
            try:
                fd = os.open(nodes_file, os.O_RDONLY)
                os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
                os.close(fd)
            except OSError:
                pass

        if work_dir and pass2_done:
            Path(pass2_done).write_text("done\n")

    # Third pass, as the polylines are read: the located pieces of the kept ways
    def polylines(locations):
        locations.ignore_errors()
        for mode, kind, direction, class_name, way in _select_ways(
            osmium,
            source,
            selects,
            tag_keys,
            kept.id_filter(),
            locations,
        ):
            for piece in _split_at_unlocated_nodes(way.nodes):
                yield mode, kind, direction, class_name, piece

    return junctions, polylines(osmium.NodeLocationsForWays(store))


def read_osm(
    source: "str | os.PathLike | StreamedPbf",
    select: Callable,
    tag_keys: tuple[str, ...] = (),
    max_km_between_nodes: float = MAX_KM_BETWEEN_NODES,
) -> tuple[
    list[dict[int, float]],
    list[list[float]],
    list[dict[int, list[list[float]]]],
    list[int],
]:
    """Build the graph of the ways of `source` that `select` keeps (`locate_ways`, then
    `build_graph_from_polylines`). A way is cut at its junctions, and at the first point
    where a piece reaches `max_km_between_nodes` (`cut_polylines`).

    Returns:
        `(graph, nodes, shapes, node_ids)` in the layout of a GeoGraph. `node_ids` holds
        the OSM ids of the nodes.
    """
    selects = {"all": {"ways": select}}
    junctions, polylines = locate_ways(source, selects, tag_keys)
    polylines = (
        (direction, vertices) for _, _, direction, _, vertices in polylines
    )
    return build_graph_from_polylines(
        polylines, junctions["all"], max_km_between_nodes
    )


def build_way_pieces(
    source: "str | os.PathLike | StreamedPbf",
    selects: dict[str, dict[str, Callable]],
    tag_keys: tuple[str, ...],
    max_km_between_nodes: float,
    work_dir: str | os.PathLike | None = None,
    optional_modes: tuple[str, ...] = (),
) -> dict[str, PieceArrays]:
    """Read the ways of `source` that the select functions keep, and cut them into pieces.

    `selects` gives the select functions as `{mode: {kind: select}}`, as
    `locate_ways` takes them. One call reads the file once for all the modes. A
    way is cut at the junctions of its mode, and at the first point where a piece
    reaches `max_km_between_nodes` (`cut_polylines`). A way of the kind "ferries"
    is cut at its junctions only, not by length. Each piece of a ferry joins the
    nodes nearest its two ends, if both are within FERRY_END_KM
    (`build_ferry_arcs`). A ferry joins nodes of its own mode: the ends of the
    pieces of that mode. A piece has the class that the select function gave to
    its way, if it gave one. With `work_dir`, the positions of the nodes and the
    pieces are kept in files of that folder, and a later call with the same
    inputs reuses them. Each step logs its counts at DEBUG.

    Returns:
        The pieces of each mode (`step3_network_assembly.PieceArrays`), by the name of the mode.

    Raises:
        ValueError: The select functions of a mode keep no way, and the mode is not in
            `optional_modes`. The message names the mode. An optional mode without a
            way has no piece.
    """
    # `StreamedPbf.download` writes a layout file in place of an OSM file that is
    # read by byte ranges. A layout file is JSON, so it starts with "{". An OSM
    # file starts with "<" (XML) or with a zero byte (PBF).
    if isinstance(source, (str, os.PathLike)):
        with open(source, "rb") as file:
            if file.read(1) == b"{":
                source = StreamedPbf(source)
    # `PieceArrays` names its files by column, so two modes cannot share a folder.
    pieces_dirs = {
        mode: os.path.join(work_dir, f"pieces_{mode}") if work_dir else None
        for mode in selects
    }
    if work_dir:
        os.makedirs(work_dir, exist_ok=True)
        done_marker = os.path.join(work_dir, "ways.done")
        # A work directory serves one build: what it holds is reused only for
        # the same source, selection and cut
        inputs = {
            "source": (
                os.fspath(source)
                if isinstance(source, (str, os.PathLike))
                else source.about
            ),
            "selects": {
                mode: {
                    kind: getattr(select, "__qualname__", type(select).__name__)
                    for kind, select in kinds.items()
                }
                for mode, kinds in selects.items()
            },
            "tag_keys": list(tag_keys),
            "max_km_between_nodes": max_km_between_nodes,
            # The pieces hold rows of this table
            "classes": list(CLASSES),
        }
        inputs_file = os.path.join(work_dir, "ways.inputs.json")
        try:
            with open(inputs_file) as f:
                same_inputs = json.load(f) == inputs
        except (OSError, ValueError):
            same_inputs = False
        if not same_inputs:
            for marker in ("pass2.done", "ways.done"):
                Path(work_dir, marker).unlink(missing_ok=True)
            with open(inputs_file, "w") as f:
                json.dump(inputs, f)
        if os.path.isfile(done_marker):
            return {
                mode: PieceArrays(work_dir=pieces_dirs[mode], truncate=False)
                for mode in selects
            }
    with _log_step(logger, "read and cut the ways", {}) as counts:
        junctions, ways = locate_ways(
            source, selects, tag_keys, work_dir=work_dir
        )
        pieces = {
            mode: PieceArrays(work_dir=pieces_dirs[mode]) for mode in selects
        }
        # The ferries of each mode, by the row of their class
        ferries = {mode: defaultdict(list) for mode in selects}
        for mode, kind, direction, class_name, vertices in ways:
            # A way without a class has no row
            class_row = CLASS_ROWS.get(class_name)
            if kind == "ferries":
                ferries[mode][class_row].append((direction, vertices))
                continue
            vertex_points = dict(vertices)
            for origin_id, destination_id, km, way, shape in cut_polylines(
                [(direction, vertices)], junctions[mode], max_km_between_nodes
            ):
                ends = vertex_points[origin_id], vertex_points[destination_id]
                pieces[mode].append(
                    origin_id, destination_id, km, way, ends, shape, class_row
                )
        for mode_pieces in pieces.values():
            mode_pieces.flush()
        counts["pieces"] = sum(
            len(mode_pieces.km) for mode_pieces in pieces.values()
        )
    for mode, mode_pieces in pieces.items():
        if not len(mode_pieces.km) and mode not in optional_modes:
            raise ValueError(f"No way of {source} is kept for the mode {mode}")
    for mode, mode_pieces in pieces.items():
        if "ferries" not in selects[mode]:
            continue
        with _log_step(logger, "attach the ferries", {}) as counts:
            # The road nodes are the ends of the pieces, in units of 1e-7 degree. They
            # are read in place. Each piece has two ends, and the ends are numbered in
            # a row: end `2 * i` is the origin of piece `i`, and end `2 * i + 1` is
            # its destination. When two ends are as near, the first one is taken.
            latitudes = mode_pieces.ends[0::2]
            longitudes = mode_pieces.ends[1::2]
            ids = (mode_pieces.origins, mode_pieces.destinations)
            near = NearNodes(latitudes, longitudes, scale=1e-7)
            # The ferries of one class give the arcs of that class
            arcs = []
            for class_row, polylines in ferries[mode].items():
                rows, ends, shapes, _ = build_graph_from_polylines(
                    polylines, junctions[mode], math.inf
                )
                arcs += (
                    (*arc, class_row)
                    for arc in build_ferry_arcs(
                        rows,
                        ends,
                        shapes,
                        partial(near.find_nearest, km=FERRY_END_KM),
                    )
                )
            for u, v, km, shape, class_row in arcs:
                road = [
                    [latitudes[w] * 1e-7, longitudes[w] * 1e-7] for w in (u, v)
                ]
                end_ids = ids[u % 2][u // 2], ids[v % 2][v // 2]
                mode_pieces.append(*end_ids, km, 1, road, shape, class_row)
            mode_pieces.flush()
            counts["arcs"] = len(arcs)
    if work_dir:
        # The marker is written after the last flush: it says that every piece is on
        # disk
        Path(done_marker).write_text("done\n")
    return pieces


def _split_at_unlocated_nodes(way_nodes):
    """Split a way where a node has no position: the node is missing from the file, for
    example outside an extract.
    """
    piece = []
    for node in way_nodes:
        if node.location.valid():
            piece.append((node.ref, [node.lat, node.lon]))
            continue
        if len(piece) > 1:
            yield piece
        piece = []
    if len(piece) > 1:
        yield piece


def select_vehicle_ferries(tags: "osmium.osm.TagList") -> int | None:
    """Return 0 (both ways) for a vehicle ferry, and None for any other way. A vehicle
    ferry is a ferry, or a shuttle train that carries cars and lorries (as in the Channel
    Tunnel), that is not closed to motor vehicles.
    """
    if tags.get("route") in ("ferry", "shuttle_train") and "no" not in (
        tags.get("motor_vehicle"),
        tags.get("motorcar"),
    ):
        return 0
    return None


def build_ferry_arcs(
    ferries: list[dict[int, float]],
    ends: list[list[float]],
    shapes: list[dict[int, list[list[float]]]],
    nearest: Callable,
) -> Iterator[tuple[int, int, float, list[list[float]]]]:
    """Yield `(u, v, km, shape)` for each ferry arc that joins two road nodes.

    `ferries`, `ends` and `shapes` are the graph of the ferries, as
    `build_graph_from_polylines` returns it. `nearest(point)` returns `(km, road node)`
    for an end of a ferry. An arc is kept when both its ends are within FERRY_END_KM of a
    road node, and these two road nodes differ. `u` and `v` are these road nodes. `km` is
    the length of the ferry route. `shape` starts and ends with the ends of the ferry,
    unless they are the road nodes themselves.
    """
    road = [nearest(end) for end in ends]
    for a, row in enumerate(ferries):
        for b, km in row.items():
            (to_u, u), (to_v, v) = road[a], road[b]
            if u != v and max(to_u, to_v) <= FERRY_END_KM:
                shape = [ends[a]] * (to_u > 0) + shapes[a].get(b, [])
                yield u, v, km, shape + [ends[b]] * (to_v > 0)


class StreamedPbf:
    """An OSM PBF file on a server, read by HTTP byte ranges and never stored.

    The planet is read this way. Linux and macOS only.

    A PBF file is a header, then blobs (blocks of data). The blobs of the nodes come
    first, then the blobs of the ways, then the blobs of the relations. The layout of a
    file is the byte offset where each of these three sections starts.

    - `StreamedPbf.download(url, filename)` is the download function of a source. It
      finds the layout and writes it to `filename`, a small JSON file: the layout file.
    - `StreamedPbf(filename)` is a source object for `locate_ways`. For each pass,
      `file(entities)` starts a child process. The child downloads the header and the
      section that the pass needs, and writes them to a pipe that osmium reads.

    The file on the server must not change during a build. `download` notes the size of
    the file and its ETag, or its Last-Modified date. A later answer with another size or
    tag stops the build. A dated file never changes. The server replaces a `latest` file
    when it publishes new data. A build that is reading the file at that time stops
    with an error.
    """

    def __init__(self, filename):
        with open(filename) as file:
            self.about = json.load(file)

    @staticmethod
    def download(url: str, filename: str | os.PathLike) -> dict[str, str | int]:
        """Find the layout of the PBF file at `url` and write it to `filename`, with the
        `size` of the file, its `tag`, its `md5` and its `version`. The `md5` is the one
        that the server publishes: the function does not compute it.

        Returns:
            `{version, bytes, md5}`, without the values that the server does not give.
        """
        osmium = require_osmium()
        session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            max_retries=requests.adapters.Retry(
                total=5,
                backoff_factor=1,
                status_forcelist=[429, 500, 502, 503, 504],
            )
        )
        session.mount("https://", adapter)
        session.mount("http://", adapter)

        head = session.head(
            url, headers=_AGENT, allow_redirects=True, timeout=(10.0, 60.0)
        )
        head.raise_for_status()
        url = head.url
        size = int(head.headers["Content-Length"])
        tag = head.headers.get("ETag") or head.headers["Last-Modified"]

        def get(start, end):  # bytes [start, end) of the same file
            ask = {**_AGENT, "Range": f"bytes={start}-{min(end, size) - 1}"}
            # A request is tried again: one slow answer must not stop a build that
            # takes hours
            for attempt in range(6):
                try:
                    answer = session.get(url, headers=ask, timeout=(10.0, 60.0))
                    answer.raise_for_status()
                    content = answer.content
                    break
                except (requests.RequestException, OSError, TimeoutError):
                    if attempt == 5:
                        raise
                    time.sleep(2**attempt)
            headers = answer.headers
            total = headers.get("Content-Range", "").rpartition("/")[2]
            same = (headers.get("ETag") or headers.get("Last-Modified")) == tag
            if answer.status_code != 206 or not same or total != str(size):
                raise ValueError(f"{url} changed or ignores byte ranges")
            return content

        header = get(0, _get_blob_length(get(0, 1 << 16)))
        blob = osmium.io.FileBuffer(header, "pbf")
        version = osmium.FileProcessor(blob).header.get(
            "osmosis_replication_timestamp"
        )

        # Return `(start, end, rank)` of the first blob at or after `offset`. `rank` is
        # 0 for a blob of nodes, 1 for ways, 2 for relations, and 3 when no blob
        # follows.
        def kind(offset):
            while offset < size:
                window = get(offset, offset + (1 << 20))
                found = window.find(b"\x0a\x07OSMData")
                if found >= 0:
                    start = offset + found - 4
                    end = start + _get_blob_length(get(start, start + 64))
                    blob = osmium.io.FileBuffer(header + get(start, end), "pbf")
                    for first in osmium.FileProcessor(blob):
                        return start, end, "nwr".index(first.type_str())
                if offset + len(window) >= size:
                    break
                offset += len(window) - 8  # a signature may straddle windows
            return size, size, 3

        # Return the start of the first blob whose rank is `rank` or higher. The ranks
        # never decrease along the file, so the function bisects between `low` and
        # `high`. Below `_SCAN` bytes, it reads the blobs one by one from `low`.
        def section(rank, low, high):
            while high - low > _SCAN:
                middle = (low + high) // 2
                start, end, found = kind(middle)
                low, high = (low, middle) if found >= rank else (end, high)
            while (blob := kind(low))[2] < rank:
                low = blob[1]
            return blob[0]

        try:
            ways = section(1, len(header), size)
            layout = [len(header), ways, section(2, ways, size)]
            md5_val = None
            try:
                md5 = session.get(
                    url + ".md5",
                    headers=_AGENT,
                    allow_redirects=True,
                    timeout=(10.0, 60.0),
                )
                if md5.ok:
                    md5_val = md5.text.split()[0]
            except (requests.RequestException, OSError, IndexError):
                md5_val = None
            about = {"url": url, "size": size, "tag": tag, "layout": layout}
            if md5_val:
                about["md5"] = md5_val
            if version:
                about["version"] = version
            with open(filename, "w") as file:
                json.dump(about, file)
            return {
                **({"version": version} if version else {}),
                "bytes": size,
                **({"md5": md5_val} if md5_val else {}),
            }
        finally:
            session.close()

    def file(self, entities: "osmium.osm.osm_entity_bits") -> "osmium.io.File":
        """Start the child process of one pass. Return an input that gives osmium the
        header and one section of the file: the nodes for `osmium.osm.NODE`, the ways
        otherwise.
        """
        if sys.platform == "win32":
            raise NotImplementedError(
                "StreamedPbf via /dev/fd pipe is only supported on POSIX systems (Linux, macOS)."
            )
        osmium = require_osmium()
        header, ways, relations = self.about["layout"]
        section = (
            [header, ways] if entities & osmium.osm.NODE else [ways, relations]
        )
        job = json.dumps({**self.about, "ranges": [[0, header], section]})
        self._pipe, write = os.pipe()
        # -P: not the modules of the current folder
        command = [sys.executable, "-P", _PLANET_READER_SCRIPT, job]
        self._streamer = subprocess.Popen(command, stdout=write)
        os.close(write)
        return osmium.io.File(f"/dev/fd/{self._pipe}", "pbf")

    def close(self, stop: bool = False) -> None:
        """Wait for the child process of the last pass, or stop it when `stop` is true.
        Raise a RuntimeError when the child failed: osmium then read only a part of the
        section, and did not report it.
        """
        os.close(self._pipe)
        if stop:
            self._streamer.terminate()
        failed = self._streamer.wait()
        if failed > 0 or failed and not stop:
            raise RuntimeError(
                f"Reading {self.about['url']} failed (see above)"
            )


def download_streamed(
    url: str, filename: str | os.PathLike
) -> dict[str, str | int]:
    """Write the layout file of an OSM PBF file, so that a build reads the file by HTTP
    byte ranges (`StreamedPbf.download`). Raise a RuntimeError without the C++ extension.
    """
    if not has_cpp():
        raise RuntimeError(
            "Reading an OSM file by byte ranges needs the C++ extension of scgraph"
        )
    return StreamedPbf.download(url, filename)


# The planet file of one date. A dated file never changes, so a build can read it by
# byte ranges. Change the URL to take newer data. This mirror serves byte ranges.
PLANET = {
    **GEOFABRIK,
    "url": "https://osm-planet-eu-central-1.s3.dualstack.eu-central-1.amazonaws.com/planet/pbf/2026/planet-261102.osm.pbf",
    "download": download_streamed,
}
_AGENT = {"User-Agent": "scgraph"}
# In bytes. Below this distance, the start of a section is found blob by blob.
_SCAN = 1 << 23
_PLANET_READER_SCRIPT = str(
    Path(__file__).resolve().parent / "step1_osm_planet_reader.py"
)


def _get_blob_length(data):
    """Return the length of the PBF blob that `data` starts with, headers included. Its
    BlobHeader holds a type, then a datasize, as osmium and the planet files write it
    (no index).
    """
    (length,) = struct.unpack(">I", data[:4])
    i, size, shift = 7 + data[5], 0, 0  # past the type
    while True:  # the datasize, a varint
        size |= (data[i] & 127) << shift
        if data[i] < 128:
            return 4 + length + size
        i, shift = i + 1, shift + 7
