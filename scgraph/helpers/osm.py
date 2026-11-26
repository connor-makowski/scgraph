"""Read the ways of an OpenStreetMap file and cut them into pieces, for
`GeoGraph.load_from_osm` and for the OpenStreetMap pipelines.

`build_way_pieces` calls `locate_ways`, then cuts the ways into pieces.

The module needs the optional dependency `osmium` (`pip install scgraph[osm]`). It
imports `osmium` only when it reads a file.

WHAT IT ANSWERS

`locate_ways` gives the ways of a file that select functions keep, each with the
positions of its nodes. A select function takes the tags of a way. It returns
the direction of the way: 1 (one way, in the order of its nodes), -1 (one way, against
that order) or 0 (both ways). It returns None to exclude the way. In place of the
direction, it may return a pair: the direction and the name of the class of the way.

A pipeline gives its select functions as `{node mode: {kind: select}}`. A node mode is
the kind of place where a node is, such as `road` or `rail`. The ways of one node mode
are cut and joined together: their nodes get this node mode. A node mode has one select
function for each kind of way. `load_from_osm` gives one select function for all its
ways.

`build_way_pieces` gives the pieces of the kept ways
(`scgraph.helpers.polylines.PieceArrays`). The kinds are `ways` and `ferries`. The kind
`ferries` is special: `build_way_pieces` does not cut a ferry by length, and attaches
it to the nodes of its node mode.

A select function may return the direction with the class of the way (docstring of
`scgraph.pipelines`, *The classes*). Example: for a one-way trunk road,
`select_main_roads_with_class` returns `(1, "trunk")`.

HOW A FILE IS READ

An OpenStreetMap file lists the nodes, then the ways. A way lists the ids of its
nodes, not their positions. So `locate_ways` reads the file in three passes:

1. It reads the ways. It notes the ids of the nodes of the kept ways. In the ways of
   each node mode, a node met a second time is a junction of that node mode.
2. It reads the nodes, and stores the position of each noted node.
3. It reads the ways again, and gives each kept way with the positions of its nodes.

These three passes are one read of the file.

`cut_polylines` then cuts each way into pieces: at each junction of its node mode, and
at the first point where a piece reaches `max_km_between_nodes`.

Example: two roads share node 7, and no other node. Pass 1 meets node 7 twice, so node
7 is a junction, and each road is cut there.

HOW A TURN RESTRICTION IS READ

A "turn restriction" says which turn a driver may not make at a junction, or the only
turn that the driver may make. OpenStreetMap stores it as a relation with the tag
`type=restriction`. Its members have three roles:

- `from`: the way by which the driver arrives;
- `via`: the node where the driver turns, or one or more ways that the driver follows
  between the `from` way and the `to` way;
- `to`: the way by which the driver leaves.

Its tag `restriction` gives its kind. A value that starts with `no_`, such as
`no_left_turn`, forbids the turn from the `from` way to the `to` way. A value that
starts with `only_`, such as `only_straight_on`, forbids every other turn from the
`from` way.

The turn restrictions are read for a car, whatever ways the select functions keep. A
select function says which ways a network keeps. It does not say which vehicle drives
on them. So `read_turn_restrictions` takes the vehicle that most road networks are
built for. The tag `except` of a relation lists the vehicles that may make the turn,
with `;` between them. A relation that excepts a car (`_EXCEPTED_VEHICLES`) is not
read.

`read_turn_restrictions` reads a relation when all of these are true:

1. Its tag `restriction` starts with `no_` or `only_`. So a relation that holds for
   some hours (`restriction:conditional`) or for one kind of vehicle
   (`restriction:hgv`) is not read.
2. Its tag `except` does not name `motorcar` or `motor_vehicle`. Example:
   `except=psv; motorcar` excepts buses and cars, so the relation is not read.
3. It has one `from` way, one `to` way, and one `via` node or some `via` ways.

Example: a relation with `restriction=no_left_turn` has the way 10 as `from`, the
node 3 as `via` and the way 11 as `to`. It is read as
`TurnRestriction(is_only=False, from_way_id=10, via_node_id=3, via_way_ids=[],
to_way_id=11)`.

A turn restriction names its ways by their ids. `scgraph.turn_restrictions.list_forbidden_turns` finds the
edges of these ways in a graph, and gives each turn restriction as forbidden turns. A
"forbidden turn" is a list of node ids that no route may follow in this order.
`scgraph/turn_restrictions.py` explains what a build does with a forbidden turn.

The graph is a dict of arrays, as `network_assembly.build_graph_from_pieces` returns
it. `edge_way_ids` gives the id of the way of each edge, and `external_node_ids`
gives the OpenStreetMap id of each node. A way is cut at each junction, and at some
other nodes when it is long. So a way is one edge or more, one after the other.

A forbidden turn is built in four steps:

1. The "turn nodes" are the nodes where the driver turns. With a `via` node, it is
   this node alone. With `via` ways, they are the nodes of these ways, from the node
   where the driver leaves the `from` way to the node where the driver enters the
   `to` way.
2. The "node before the turn" is the origin of the edge of the `from` way that ends
   at the first turn node.
3. The "node after the turn" is the destination of the edge of the `to` way that
   leaves the last turn node.
4. The forbidden turn is the node before the turn, the turn nodes, then the node
   after the turn.

Example: the way 10 goes through the nodes 1, 2 and 3 of OpenStreetMap, and the way 11
goes from node 3 to node 4. Node 2 is a shape point, so the graph has the nodes 1, 3
and 4. A relation forbids the turn from the way 10 to the way 11 at node 3. The turn
node is node 3. The node before the turn is node 1: the edge from node 1 to node 3 is
the edge of the way 10 that ends at node 3. The node after the turn is node 4. The
forbidden turn is the nodes 1, 3 and 4, given by their ids in the graph.

An `only_` restriction gives one forbidden turn for each other edge that leaves the
last turn node. In the example, with `only_left_turn` and one more edge from node 3
to a node 5, the forbidden turn is the nodes 1, 3 and 5.

A relation with the same way as `from` and as `to`, and a `via` node, forbids a
U-turn at this node: the driver arrives along the way and may not go back along it.
Each edge of the way that ends at the `via` node gives one forbidden turn: back to
the node that the edge comes from. Example: the two-way way 10 goes through the
nodes 1, 3 and 6, and the `via` node is node 3. The forbidden turns are the nodes
1, 3, 1 and the nodes 6, 3, 6. A one-way way has no edge back, so no route can make
its forbidden turn. A driver may still go straight on along the way.

A turn restriction gives no forbidden turn in these cases:

- The graph does not have one of its edges. Example: the graph does not keep the `to`
  way, or the `from` way is a one-way street that leaves the `via` node.
- A step above has two answers or more. Example: the `via` node is in the middle of
  the `from` way, so two edges of this way end there.
- Its `via` ways do not follow each other. The `from` way and the first `via` way
  meet at one node only. From there, each `via` way is followed edge after edge to
  its other end, where the next `via` way or the `to` way leaves.
- It is an `only_` restriction with the same way as `from` and as `to`.

HOW THE WAYS OF TWO NODE MODES ARE KEPT SEPARATE

One read is used for every node mode. Each node mode has its own junctions and its own
pieces. So a piece of a road is never joined to a piece of a railway.

Example: a road and a railway share node 9, at a level crossing. Pass 1 meets node 9
once in the ways of `road` and once in the ways of `rail`. Node 9 is a junction of
neither node mode, and neither way is cut there.

Example: a way with the tags `railway=rail` and `route=shuttle_train` is a railway and
a vehicle ferry, so both node modes keep it. In the ways of each node mode, pass 1 meets
each node of this way once. No node of the way is a junction for that reason. With one
set of met nodes for the two node modes, pass 1 would meet the way twice: each of its
nodes would be a junction, and the way would be cut at every node.
"""

import gc
import json
import logging
import math
import os
from array import array
from bisect import bisect_left
from collections import defaultdict
from collections.abc import Callable, Container, Iterator
from typing import NamedTuple
from contextlib import contextmanager
from functools import partial
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING

from scgraph.edge_classes import CLASS_IDS, CLASSES
from scgraph.helpers.near_nodes import NearNodes
from scgraph.helpers.polylines import (
    PieceArrays,
    build_graph_from_polylines,
    cut_polylines,
)
from scgraph.step_logs import log_step

if TYPE_CHECKING:  # annotations only: osmium stays optional at run time
    import osmium

__all__ = [
    "get_way_direction",
    "select_main_roads",
    "select_main_roads_with_class",
]

# The steps of a build log under one logger name, wherever their module is.
logger = logging.getLogger("scgraph.pipelines")


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

# The values of the tag `except` that except a car. A turn restriction with one of
# them does not hold for a car, so it is not read.
_EXCEPTED_VEHICLES = {"motorcar", "motor_vehicle"}
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
    """Yield `(node mode, kind, direction, class_name, way)` for each way, once for
    each node mode that keeps it. In a node mode, a way goes to the first select
    function that keeps it, in the order of the dict. `class_name` is None when the
    select function returns a direction alone, and one of `class_names` otherwise.
    osmium drops the ways that have none of `tag_keys`, and the ways that `filters`
    refuse, before Python sees them.
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
    `id in junctions` finds an id by bisection.

    Memory while the object is built: the list of the repeated node ids takes about 40
    bytes per repeat. A node that the ways of a node mode use k times appears k - 1
    times in this list.
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

    An osmium `IdSet` takes too much memory for one set per node mode. It allocates 4 MB
    for each range of 33.5 million ids that holds a node: 1.5 GB for the 41,009 rail
    node ids of Denmark. This set takes about 15 MB for them (3,609 pages), and about
    61 MB for the 107,968 node ids of the main roads and ferries of Denmark (14,782
    pages). On the planet, a set takes at most about 1.9 GB, when every page exists:
    14.4 billion ids / 32,768 ids per page * 4,096 bytes, and the Python object of each
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
    Iterator[
        tuple[str, str, int, str | None, list[tuple[int, list[float]]], int]
    ],
]:
    """Locate the ways of `source` that the select functions keep.

    The function reads the file in three passes (ways, nodes, ways again), as the module
    docstring explains. One call reads the ways of every node mode. Example: the node
    modes `road` and `rail`, and the kinds `ways` and `ferries` of the node mode `road`.

    Args:
        source: The path of an OSM file, or a source object such as `StreamedPbf`. A
            source object has a method `file(entities)`. It returns a new input for
            `osmium.FileProcessor` at each call: one per pass, for the entities that the
            pass reads (`osmium.osm.WAY` or `NODE`). The function calls `close(stop)` at
            the end of each pass. `stop` is true when the pass ended on an exception.
        selects: The select functions, as `{node mode: {kind: select}}`. In a node
            mode, a way goes to the first function that keeps it, in the order of the
            dict. A way that two node modes keep goes to each of them.
        tag_keys: If given, osmium drops the ways that have none of these tag keys,
            before a select function sees them.
        work_dir: A folder for the files of the function. Without it, the positions of
            the nodes are in memory (osmium index `flex_mem`). With it, they are in the
            file `nodes` of the folder (`sparse_file_array`), which a planet file needs.
            The folder also keeps the junctions and the ids of the kept ways. When its
            marker `pass2.done` is there, the function reuses these files and skips
            passes 1 and 2. Otherwise it empties `nodes` first. The caller deletes the
            folder.
        class_names: The class names that a select function may give with the direction
            of a way. A pipeline gives the names of `scgraph.pipelines.CLASSES`. Empty
            by default: a select function then gives the direction alone.

    Returns:
        `(junctions, polylines)`. `junctions[mode]` holds the OSM ids of the nodes
        where kept ways of the node mode `mode` meet, or where one of them crosses
        itself. `id in junctions[mode]` tests one id. `polylines` is a generator of
        `(node mode, kind, direction, class_name, vertices, way_id)`. `class_name` is
        the class that the select function gave to the way, or None. `vertices` is a
        list of `(id, [latitude, longitude])`. The pair `(direction, vertices)` is a
        polyline, in the form that `cut_polylines` takes. `way_id` is the id of the
        way in the file. A way is split where one of its nodes is missing from the
        file.

    Memory: the ids of the nodes of the kept ways take about 1.5 GB, whatever the file
    (one bit for each possible id). With several node modes, pass 1 also holds the ids
    of the nodes of each node mode (`_PagedIdSet`): at most about 1.9 GB for each node
    mode on the planet. The ids of the kept ways take about 0.2 GB.
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
        # First pass: the nodes of kept ways. In the ways of each node mode, a node met
        # a second time is a junction of that node mode.
        tracker, kept = osmium.IdTracker(), osmium.IdTracker()
        # `noted_ids` holds the nodes of every node mode, for the second pass.
        # `seen_ids[mode]` holds the nodes of one node mode. When `selects` has one
        # key, the two sets hold the same ids, so `seen_ids[mode]` is `noted_ids`.
        noted_ids = tracker.node_ids()
        seen_ids = {
            mode: noted_ids if len(selects) == 1 else _PagedIdSet()
            for mode in selects
        }
        repeats = {mode: array("q") for mode in selects}
        kept_ways = array("q") if work_dir else None
        # The set and the repeats of the node mode of the way that is read
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

        # The sets of the node modes are freed before the junctions are built
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
                yield mode, kind, direction, class_name, piece, way.id

    return junctions, polylines(osmium.NodeLocationsForWays(store))


def build_way_pieces(
    source: "str | os.PathLike | object",
    selects: dict[str, dict[str, Callable]],
    tag_keys: tuple[str, ...],
    max_km_between_nodes: float,
    work_dir: str | os.PathLike | None = None,
    optional_modes: tuple[str, ...] = (),
    shape_tolerance_meters: float | None = 50,
) -> dict[str, PieceArrays]:
    """Read the ways of `source` that the select functions keep, and cut them into pieces.

    `selects` gives the select functions of each node mode as `{mode: {kind: select}}`,
    as `locate_ways` takes them. One call reads the file once for all the node modes.
    A way is cut at the junctions of its node mode, and at the first point where a piece
    reaches `max_km_between_nodes` (`cut_polylines`). A way of the kind "ferries"
    is cut at its junctions only, not by length. Each piece of a ferry joins the
    nodes closest its two ends, if both are within FERRY_END_KM
    (`build_ferry_edges`). A ferry joins nodes of its own node mode: the ends of the
    pieces of that node mode. A piece has the class that the select function gave to
    its way, if it gave one. The shape of a piece is simplified to within
    `shape_tolerance_meters`, and None keeps every shape point. With `work_dir`, the
    positions of the nodes and the pieces are kept in files of that folder, and a
    later call with the same inputs reuses them. Each step logs its counts at DEBUG.

    Returns:
        The pieces of each node mode, by name (`scgraph.helpers.polylines.PieceArrays`).

    Raises:
        ValueError: The select functions of a node mode keep no way, and the node mode
            is not in `optional_modes`. The message names the node mode. An optional
            node mode without a way has no piece.
    """
    # `PieceArrays` names its files by column, so two node modes cannot share a folder.
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
            "shape_tolerance_meters": shape_tolerance_meters,
            # The pieces hold ids of classes of this table
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
    with log_step(logger, "read and cut the ways", {}) as counts:
        junctions, ways = locate_ways(
            source,
            selects,
            tag_keys,
            work_dir=work_dir,
            class_names=CLASS_IDS,
        )
        pieces = {
            mode: PieceArrays(shape_tolerance_meters, pieces_dirs[mode])
            for mode in selects
        }
        # The ferries of each node mode, by the id of their class
        ferries = {mode: defaultdict(list) for mode in selects}
        for mode, kind, direction, class_name, vertices, way_id in ways:
            # A way without a class has no row
            class_id = CLASS_IDS.get(class_name)
            if kind == "ferries":
                ferries[mode][class_id].append((direction, vertices))
                continue
            vertex_points = dict(vertices)
            for origin_id, destination_id, km, way, shape in cut_polylines(
                [(direction, vertices)], junctions[mode], max_km_between_nodes
            ):
                ends = vertex_points[origin_id], vertex_points[destination_id]
                pieces[mode].append(
                    origin_id,
                    destination_id,
                    km,
                    way,
                    ends,
                    shape,
                    class_id,
                    way_id,
                )
        for mode_pieces in pieces.values():
            mode_pieces.flush()
        counts["pieces"] = sum(
            len(mode_pieces.km) for mode_pieces in pieces.values()
        )
    for mode, mode_pieces in pieces.items():
        if not len(mode_pieces.km) and mode not in optional_modes:
            raise ValueError(
                f"No way of {source} is kept for the node mode {mode}"
            )
    for mode, mode_pieces in pieces.items():
        if "ferries" not in selects[mode]:
            continue
        with log_step(logger, "attach the ferries", {}) as counts:
            # The road nodes are the ends of the pieces, in units of 1e-7 degree. They
            # are read in place. Each piece has two ends, and the ends are numbered in
            # a row: end `2 * i` is the origin of piece `i`, and end `2 * i + 1` is
            # its destination. When two ends are as near, the first one is taken.
            latitudes = mode_pieces.ends[0::2]
            longitudes = mode_pieces.ends[1::2]
            ids = (mode_pieces.origins, mode_pieces.destinations)
            near = NearNodes(latitudes, longitudes, scale=1e-7)
            # The ferries of one class give the edges of that class
            edges = []
            for class_id, polylines in ferries[mode].items():
                rows, ends, shapes, _, _ = build_graph_from_polylines(
                    polylines, junctions[mode], math.inf
                )
                edges += (
                    (*edge, class_id)
                    for edge in build_ferry_edges(
                        rows,
                        ends,
                        shapes,
                        partial(near.find_closest, km=FERRY_END_KM),
                    )
                )
            for u, v, km, shape, class_id in edges:
                road = [
                    [latitudes[w] * 1e-7, longitudes[w] * 1e-7] for w in (u, v)
                ]
                end_ids = ids[u % 2][u // 2], ids[v % 2][v // 2]
                # A ferry edge joins two road nodes: it is the piece of no way
                mode_pieces.append(*end_ids, km, 1, road, shape, class_id, 0)
            mode_pieces.flush()
            counts["edges"] = len(edges)
    if work_dir:
        # The marker is written after the last flush: it says that every piece is on
        # disk
        Path(done_marker).write_text("done\n")
    return pieces


def build_ferry_edges(
    ferries: list[dict[int, float]],
    ends: list[list[float]],
    shapes: list[dict[int, list[list[float]]]],
    closest: Callable,
) -> Iterator[tuple[int, int, float, list[list[float]]]]:
    """Yield `(u, v, km, shape)` for each ferry edge that joins two road nodes.

    `ferries`, `ends` and `shapes` are the graph of the ferries, as
    `build_graph_from_polylines` returns it. `closest(point)` returns `(km, road node)`
    for an end of a ferry. An edge is kept when both its ends are within FERRY_END_KM of
    a road node, and these two road nodes differ. `u` and `v` are these road nodes. `km`
    is the length of the ferry route. `shape` starts and ends with the ends of the
    ferry, unless they are the road nodes themselves.
    """
    road = [closest(end) for end in ends]
    for a, row in enumerate(ferries):
        for b, km in row.items():
            (to_u, u), (to_v, v) = road[a], road[b]
            if u != v and max(to_u, to_v) <= FERRY_END_KM:
                shape = [ends[a]] * (to_u > 0) + shapes[a].get(b, [])
                yield u, v, km, shape + [ends[b]] * (to_v > 0)


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


class TurnRestriction(NamedTuple):
    """A turn restriction of an OpenStreetMap file (module docstring, *How a turn
    restriction is read*)."""

    # True when the restriction gives the only turn that is allowed
    is_only: bool
    from_way_id: int
    # The node where the driver turns, or None when the relation has `via` ways
    via_node_id: int | None
    # The ways between the `from` way and the `to` way, in the order of the relation
    via_way_ids: list[int]
    to_way_id: int


def read_turn_restrictions(
    source: "str | os.PathLike | object",
) -> list[TurnRestriction]:
    """Read the turn restrictions of an OpenStreetMap file.

    Args:
        source: The path of an OSM file, or a source object, as `locate_ways`
            takes. The function calls `source.file(osmium.osm.RELATION)` once.

    Returns:
        The turn restrictions that the rules of the module docstring keep.
    """
    osmium = require_osmium()
    restrictions = []
    with _open_source(source, osmium.osm.RELATION) as file:
        for relation in osmium.FileProcessor(
            file, osmium.osm.RELATION
        ).with_filter(osmium.filter.TagFilter(("type", "restriction"))):
            kind = relation.tags.get("restriction", "")
            # Mappers write `psv;motorcar` and `psv; motorcar`
            excepted = {
                vehicle.strip()
                for vehicle in relation.tags.get("except", "").split(";")
            }
            if not kind.startswith(("no_", "only_")) or (
                _EXCEPTED_VEHICLES & excepted
            ):
                continue
            # The ids of the members of each role, by the type of the member:
            # "n" for a node, "w" for a way
            members = {"from": {}, "via": {}, "to": {}}
            for member in relation.members:
                if member.role in members:
                    members[member.role].setdefault(member.type, []).append(
                        member.ref
                    )
            from_way_ids = members["from"].get("w", [])
            to_way_ids = members["to"].get("w", [])
            via_node_ids = members["via"].get("n", [])
            via_way_ids = members["via"].get("w", [])
            if (
                len(from_way_ids) == len(to_way_ids) == 1
                and len(members["from"]) == len(members["to"]) == 1
                and len(members["via"]) == 1
                and (len(via_node_ids) == 1 or via_way_ids)
            ):
                restrictions.append(
                    TurnRestriction(
                        kind.startswith("only_"),
                        from_way_ids[0],
                        via_node_ids[0] if via_node_ids else None,
                        via_way_ids,
                        to_way_ids[0],
                    )
                )
    return restrictions
