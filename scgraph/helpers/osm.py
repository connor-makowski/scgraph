"""Read the ways of an OpenStreetMap file into a graph, for `GeoGraph.load_from_osm`.

The OpenStreetMap pipelines read their ways with this module too.
`scgraph.pipelines.steps.step1_osm_ways` calls `locate_ways`, then cuts the ways into
pieces.

The module needs the optional dependency `osmium` (`pip install scgraph[osm]`). It
imports `osmium` only when it reads a file.

WHAT IT ANSWERS

`read_osm` gives a graph in the layout of a GeoGraph, for `load_from_osm`. A select
function chooses the ways. It takes the tags of a way. It returns
the direction of the way: 1 (one way, in the order of its nodes), -1 (one way, against
that order) or 0 (both ways). It returns None to leave the way out. In place of the
direction, it may return a pair: the direction and the name of the class of the way.

A pipeline gives its select functions as `{mode: {kind: select}}`. A mode is a group
of ways that are cut and joined together. A multimodal pipeline names it as in its
modes table. A mode has one select function for each kind of way.

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
"""

import gc
import os
from array import array
from bisect import bisect_left
from collections import defaultdict
from collections.abc import Callable, Container, Iterator
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING

from scgraph.helpers.polylines import build_graph_from_polylines

if TYPE_CHECKING:  # annotations only: osmium stays optional at run time
    import osmium


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


def select_main_roads_with_class(
    tags: "osmium.osm.TagList",
) -> tuple[int, str] | None:
    """Return the direction and the class of a main road, and None for any other way.
    The class is the `highway` value of the way. Example: a one-way motorway gives
    `(1, "motorway")`.
    """
    direction = select_main_roads(tags)
    return None if direction is None else (direction, tags["highway"])


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


def _select_ways(osmium, source, selects, tag_keys, *filters, class_names=()):
    """Yield `(mode, kind, direction, class_name, way)` for each way, once for each
    mode that keeps it. In a mode, a way goes to the first select function that keeps
    it, in the order of the dict. `class_name` is None when the select function returns
    a direction alone, and one of `class_names` otherwise. osmium drops the ways that
    have none of `tag_keys`, and the ways that `filters` refuse, before Python sees
    them.
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
                            and class_name not in class_names
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
    source: "str | os.PathLike | object",
    selects: dict[str, dict[str, Callable]],
    tag_keys: tuple[str, ...] = (),
    work_dir: str | os.PathLike | None = None,
    class_names: Container[str] = (),
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
        class_names: The class names that a select function may give with the
            direction of a way. A pipeline gives the names of
            `scgraph.pipelines.CLASSES`. Empty by default: a select function then gives
            the direction alone.

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
            osmium, source, selects, tag_keys, class_names=class_names
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
            class_names=class_names,
        ):
            for piece in _split_at_unlocated_nodes(way.nodes):
                yield mode, kind, direction, class_name, piece

    return junctions, polylines(osmium.NodeLocationsForWays(store))


def read_osm(
    source: "str | os.PathLike | object",
    select: Callable,
    tag_keys: tuple[str, ...] = (),
    max_km_between_nodes: float = MAX_KM_BETWEEN_NODES,
    class_names: Container[str] = (),
) -> tuple[
    list[dict[int, float]],
    list[list[float]],
    list[dict[int, list[list[float]]]],
    list[int],
    list[dict[int, str]],
]:
    """Build the graph of the ways of `source` that `select` keeps (`locate_ways`, then
    `build_graph_from_polylines`). A way is cut at its junctions, and at the first point
    where a piece reaches `max_km_between_nodes` (`cut_polylines`). `class_names` holds
    the class names that `select` may give with the direction of a way.

    Returns:
        `(graph, nodes, shapes, source_node_ids, edge_class_names)` in the layout of a
        GeoGraph. `source_node_ids` holds the OSM ids of the nodes.
        `edge_class_names[i][j]` is the class that `select` gave to the way of the edge
        from `i` to `j`, if it gave one.
    """
    selects = {"all": {"ways": select}}
    junctions, polylines = locate_ways(
        source, selects, tag_keys, class_names=class_names
    )
    polylines = (
        (direction, vertices, class_name)
        for _, _, direction, class_name, vertices in polylines
    )
    return build_graph_from_polylines(
        polylines, junctions["all"], max_km_between_nodes
    )


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
