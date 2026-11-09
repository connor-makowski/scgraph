"""Read OpenStreetMap files into a GeoGraph.

Needs the optional dependency `osmium` (`pip install scgraph[osm]`), imported only when a file
is read.
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
from contextlib import contextmanager
from pathlib import Path

import requests

from scgraph.helpers.polylines import cut_polylines, polylines_to_graph
from scgraph.pipelines import download_file
from scgraph.pipelines.steps.stage3_assembly.assembly import (
    NearNodes,
    PieceArrays,
)
from scgraph.utils import has_cpp

logger = logging.getLogger(__name__)

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
# Length in kilometers at which a way is cut into a new arc (at the next point), so that
# origins and destinations attach close to where they are
MAX_KM = 2
FERRY_END_KM = 2  # farthest a ferry end may lie from the road node it joins
_ONE_WAY = {"yes": 1, "true": 1, "1": 1, "-1": -1, "reverse": -1}


def require_osmium():
    try:
        import osmium
    except ImportError as error:
        raise ImportError(
            "Reading OSM files needs the optional dependency osmium: pip install scgraph[osm]"
        ) from error
    return osmium


def download(url, filename):
    """Download an OSM file; return its `version`, the time its data is up to (the
    `osmosis_replication_timestamp` of its header, as Geofabrik writes it), if it has one.
    """
    # Checked before downloading a large extract it could not read
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


def direction(tags):
    """The direction of a way from its tags: 1 (one way, along its drawing) for
    `oneway=yes`, `true` or `1`, and for motorways and roundabouts without `oneway`; -1
    (one way, against it) for `oneway=-1` or `reverse`; 0 (both ways) otherwise.
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


def main_roads(tags):
    """The direction of a main road (`MAIN_ROADS`), None for any other way."""
    return direction(tags) if tags.get("highway") in MAIN_ROADS else None


@contextmanager
def _opened(source, entities):
    # A path, or what the source gives for one pass, closed after it (see located_ways)
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


def _selected_ways(osmium, source, selects, tag_keys, *filters):
    """`(kind, direction, way)` for the ways one of `selects` keeps (the first, in their
    order); ways with none of `tag_keys` are skipped in osmium, before Python sees them,
    and so are `filters`."""
    with _opened(source, osmium.osm.WAY) as file:
        ways = osmium.FileProcessor(file, osmium.osm.WAY)
        if tag_keys:
            ways = ways.with_filter(osmium.filter.KeyFilter(*tag_keys))
        for osmium_filter in filters:
            ways = ways.with_filter(osmium_filter)
        for way in ways:
            for kind, select in selects.items():
                way_direction = select(way.tags)
                if way_direction is not None:
                    break
            else:
                continue
            if type(way_direction) is not int or not -1 <= way_direction <= 1:
                raise ValueError(
                    f"select returned {way_direction!r}: 1, -1, 0 or None"
                )
            yield kind, way_direction, way


class _Junctions:
    """Node ids, sorted, looked up by bisection: 8 bytes per junction once built. While
    it is built (after the id tracker is freed), the sorted list of repeated uses takes
    about 40 B per repeat (a node used k times appears k - 1 times), with no set; with
    the location store still alive, a planet's ~10.8 M repeats would take about 0.43 GB
    next to a ~1.46 GB file store (an estimate, not measured together)."""

    def __init__(self, ids):
        self.ids = array("q")
        for ref in sorted(ids):
            if not self.ids or self.ids[-1] != ref:
                self.ids.append(ref)

    def __contains__(self, ref):
        i = bisect_left(self.ids, ref)
        return i < len(self.ids) and self.ids[i] == ref


def locate_ways(source, selects, tag_keys=(), node_store=None, folder=None):
    """
    Locate the ways of `source` that `selects` keep, in one set of passes for every kind
    of way (roads and ferries, for example).

    `selects` maps a kind of way to its `select(tags)`, which gives the direction of a way:
    1 (one way along its drawing), -1 (against it), 0 (both ways), or None to leave it to
    the next select; a way goes to the first select that keeps it, in the mapping's order.
    If `tag_keys` is given, the ways that have none of these keys are dropped first, in
    osmium.

    `source` is the path of an OSM file, or an object whose `file(entities)` returns what
    `osmium.FileProcessor` reads (an `osmium.io.File` or `FileBuffer`), fresh at each call:
    the file is read in three passes (ways, their nodes, ways again), so a source that is
    not on disk, such as `StreamedPbf`, supplies one input per pass, for the entities
    (`osmium.osm.WAY` or `NODE`) the pass reads; its `close(stop)` is called at the end
    of each pass (`stop` true when the pass ended on an exception).

    The locations of the nodes of kept ways are kept in osmium's `node_store`, an
    `osmium.index.create_map` type: in memory by default (`flex_mem`), or in a file for a
    planet (`"sparse_file_array,<path>"`, emptied first and left for the caller to delete).
    The node ids of kept ways take about 1.5 GB in any case (one bit per possible id),
    and the ids of kept ways about 0.2 GB (one bit per possible way id).

    Returns `(junctions, polylines)`: the OSM ids of the nodes where kept ways meet or a way
    crosses itself, whatever their kind (`in junctions` tests one), and a generator of
    `(kind, direction, points)`, `points` being `[(id, [latitude, longitude]), ...]` and
    `(direction, points)` a polyline as `cut_polylines` takes it, a way being split where
    one of its nodes is missing from the file.
    """
    osmium = require_osmium()
    if folder:
        os.makedirs(folder, exist_ok=True)
    pass2_done = os.path.join(folder, "pass2.done") if folder else None
    junc_file = os.path.join(folder, "pass1_junctions.bin") if folder else None
    ways_file = os.path.join(folder, "pass1_ways.bin") if folder else None
    nodes_file = (
        node_store.partition(",")[2]
        if (node_store and "," in node_store)
        else None
    )

    # Resume: if pass 2 was already completed, reload junctions and kept ways from disk
    if (
        folder
        and pass2_done
        and os.path.isfile(pass2_done)
        and os.path.isfile(junc_file)
        and os.path.isfile(ways_file)
        and nodes_file
        and os.path.isfile(nodes_file)
        and os.path.getsize(nodes_file) > 0
    ):
        junctions = _Junctions.__new__(_Junctions)
        junctions.ids = array("q")
        with open(junc_file, "rb") as f:
            junctions.ids.fromfile(f, os.path.getsize(junc_file) // 8)
        kept = osmium.IdTracker()
        with open(ways_file, "rb") as f:
            kept_ways = array("q")
            kept_ways.fromfile(f, os.path.getsize(ways_file) // 8)
        for wid in kept_ways:
            kept.add_way(wid)
        del kept_ways
        store = osmium.index.create_map(node_store)
    else:
        # First pass: the nodes of kept ways; a node seen again is a junction
        tracker, kept = osmium.IdTracker(), osmium.IdTracker()
        seen, repeats = tracker.node_ids(), array("q")
        kept_ways = array("q") if folder else None
        for _, _, way in _selected_ways(osmium, source, selects, tag_keys):
            kept.add_way(way.id)
            if kept_ways is not None:
                kept_ways.append(way.id)
            for node in way.nodes:
                if seen.get(node.ref):
                    repeats.append(node.ref)
                else:
                    seen.set(node.ref)

        junctions = _Junctions(repeats)
        del repeats
        gc.collect()

        if folder and junc_file and ways_file:
            with open(junc_file, "wb") as f:
                junctions.ids.tofile(f)
            with open(ways_file, "wb") as f:
                kept_ways.tofile(f)
            del kept_ways
            Path(folder, "pass1.done").write_text("done\n")

        # Second pass: locations of kept nodes into store
        node_store = node_store or "flex_mem"
        if nodes_file:
            open(nodes_file, "wb").close()
        store = osmium.index.create_map(node_store)
        with (
            _opened(source, osmium.osm.NODE) as file,
            osmium.io.Reader(file, osmium.osm.NODE) as nodes,
        ):
            osmium.apply(
                nodes, tracker.id_filter(), osmium.NodeLocationsForWays(store)
            )
        del tracker, seen
        gc.collect()

        # Drop OS page cache to avoid memory pressure on large extracts
        if nodes_file and hasattr(os, "posix_fadvise"):
            try:
                fd = os.open(nodes_file, os.O_RDONLY)
                os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
                os.close(fd)
            except OSError:
                pass

        if folder and pass2_done:
            Path(pass2_done).write_text("done\n")

    # Third pass, as the polylines are read: the located pieces of the kept ways
    def polylines(locations):
        locations.ignore_errors()
        for kind, way_direction, way in _selected_ways(
            osmium, source, selects, tag_keys, kept.id_filter(), locations
        ):
            for piece in _located_pieces(way.nodes):
                yield kind, way_direction, piece

    return junctions, polylines(osmium.NodeLocationsForWays(store))


def read_osm(source, select, tag_keys=(), max_km=MAX_KM):
    """
    Build the graph of the ways of `source` that `select` keeps (`locate_ways`, then
    `polylines_to_graph`), a way being also cut where a piece reaches `max_km`
    (`cut_polylines`).

    Returns `(graph, nodes, shapes, node_ids)` in the GeoGraph layout, `node_ids` being
    the OSM ids of the nodes.
    """
    junctions, polylines = locate_ways(source, {"ways": select}, tag_keys)
    polylines = (
        (way_direction, points) for _, way_direction, points in polylines
    )
    return polylines_to_graph(polylines, junctions, max_km)


def build_way_pieces(source, selects, tag_keys, max_km, folder=None):
    """The pieces (`assembly.PieceArrays`) of the ways of `source` that `selects` keep
    (`locate_ways`, one read for every kind), cut at their junctions and where a piece
    reaches `max_km` (`cut_polylines`). The ways of the kind "ferries" are not cut: each
    joins the road nodes nearest its two ends if both lie within FERRY_END_KM
    (`build_ferry_arcs`). Returns `(pieces, steps)`; no way kept raises a ValueError. With a
    `folder`, the node locations and the pieces are kept in files there.
    """
    if folder:
        done_marker = os.path.join(folder, "stage1.done")
        if os.path.isfile(done_marker):
            try:
                with open(done_marker, "r") as f:
                    return PieceArrays(
                        folder=folder, truncate=False
                    ), json.load(f)
            except OSError:
                pass
    nodes = folder and os.path.join(folder, "nodes")
    store = nodes and "sparse_file_array," + nodes
    junctions, ways = locate_ways(
        source, selects, tag_keys, store, folder=folder
    )
    pieces, ferries = PieceArrays(folder=folder), []
    for kind, direction, points in ways:
        if kind == "ferries":
            ferries.append((direction, points))
            continue
        where = dict(points)
        for origin, destination, km, way, shape in cut_polylines(
            [(direction, points)], junctions, max_km
        ):
            ends = where[origin], where[destination]
            pieces.append(origin, destination, km, way, ends, shape)
    pieces.flush()
    if not len(pieces.km):
        raise ValueError(f"No way of {source} is kept by {', '.join(selects)}")
    steps = [{"step": "read", "pieces": len(pieces.km)}]
    if "ferries" in selects:
        # The road nodes: the pieces' ends at 1e-7 degree, read in place, end u being
        # piece u // 2's origin or destination (ties in nearest: the first end)
        lats, lons = pieces.ends[0::2], pieces.ends[1::2]
        ids = (pieces.origins, pieces.destinations)
        near = NearNodes(lats, lons, scale=1e-7)
        rows, ends, shapes, _ = polylines_to_graph(ferries, junctions, math.inf)
        arcs = list(
            build_ferry_arcs(
                rows, ends, shapes, lambda p: near.nearest(p, FERRY_END_KM)
            )
        )
        for u, v, km, shape in arcs:
            road = [[lats[w] * 1e-7, lons[w] * 1e-7] for w in (u, v)]
            pieces.append(
                ids[u % 2][u // 2], ids[v % 2][v // 2], km, 1, road, shape
            )
        steps.append({"step": "ferries", "arcs": len(arcs)})
    if folder:
        with open(os.path.join(folder, "stage1.done"), "w") as f:
            json.dump(steps, f)
    return pieces, steps


def _located_pieces(way_nodes):
    """Split a way where a node is missing from the file (outside an extract) or has no
    location."""
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


def vehicle_ferries(tags):
    """Both ways (0) for a ferry not closed to motor vehicles, None for any other way."""
    if tags.get("route") == "ferry" and "no" not in (
        tags.get("motor_vehicle"),
        tags.get("motorcar"),
    ):
        return 0
    return None


def build_ferry_arcs(ferries, ends, shapes, nearest):
    """`(u, v, km, shape)` of each ferry arc (`polylines_to_graph`'s layout) whose ends
    lie within FERRY_END_KM of road nodes u and v (`nearest(point)` gives `(node, km)`);
    the shape keeps the ferry's ends unless they are u and v."""
    road = [nearest(end) for end in ends]
    for a, row in enumerate(ferries):
        for b, km in row.items():
            (u, to_u), (v, to_v) = road[a], road[b]
            if u != v and max(to_u, to_v) <= FERRY_END_KM:
                shape = [ends[a]] * (to_u > 0) + shapes[a].get(b, [])
                yield u, v, km, shape + [ends[b]] * (to_v > 0)


class StreamedPbf:
    """
    An OSM PBF file read by HTTP byte ranges, never stored (the planet, for example), on
    Linux and macOS: `download` is a source's download hook, and `StreamedPbf(filename)`
    a source of `locate_ways`, each pass reading the header and the section it needs
    from a pipe that a child process fills. A dated file only: a response with another
    size or tag (ETag or Last-Modified) stops the build.
    """

    def __init__(self, filename):
        with open(filename) as file:
            self.about = json.load(file)

    @staticmethod
    def download(url, filename):
        """Write to `filename` the layout of the PBF at `url` (the header, then the node
        and way sections, found by bisection) with its `size`, `tag`, `md5` (the
        published one, not recomputed) and `version`; return `{version, bytes, md5}`.
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
            # Retried: one slow answer must not stop a build of hours
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

        header = get(0, _blob(get(0, 1 << 16)))
        blob = osmium.io.FileBuffer(header, "pbf")
        version = osmium.FileProcessor(blob).header.get(
            "osmosis_replication_timestamp"
        )

        # (start, end, rank) of the first blob at or after offset: rank 0, 1 or 2 for
        # nodes, ways or relations, 3 past the last blob
        def kind(offset):
            while offset < size:
                window = get(offset, offset + (1 << 20))
                found = window.find(b"\x0a\x07OSMData")
                if found >= 0:
                    start = offset + found - 4
                    end = start + _blob(get(start, start + 64))
                    blob = osmium.io.FileBuffer(header + get(start, end), "pbf")
                    for first in osmium.FileProcessor(blob):
                        return start, end, "nwr".index(first.type_str())
                if offset + len(window) >= size:
                    break
                offset += len(window) - 8  # a signature may straddle windows
            return size, size, 3

        # Start of the first blob of a rank >= rank, knowing it is that of the first blob
        # at or after high: bisection, then a scan from low, blob by blob
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
            except Exception:
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

    def file(self, entities):
        """The header and the node (`osmium.osm.NODE`) or way section, from a pipe."""
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
        command = [sys.executable, "-P", _STREAMER_SCRIPT, job]
        self._streamer = subprocess.Popen(command, stdout=write)
        os.close(write)
        return osmium.io.File(f"/dev/fd/{self._pipe}", "pbf")

    def close(self, stop=False):
        """Wait for the child of the last pass, or `stop` it; raise if it failed (then
        osmium read only part of the section, maybe up to a blob boundary, unaware).
        """
        os.close(self._pipe)
        if stop:
            self._streamer.terminate()
        failed = self._streamer.wait()
        if failed > 0 or failed and not stop:
            raise RuntimeError(
                f"Reading {self.about['url']} failed (see above)"
            )


def open_osm_source(source):
    """Resolve an OSM source: returns a StreamedPbf when source is a JSON metadata file
    or layout descriptor, or source unchanged when it is an OSM file path or custom source object.
    """
    if isinstance(source, (str, os.PathLike)):
        path = Path(source)
        if path.suffix == ".json":
            return StreamedPbf(str(path))
        if path.is_file() and path.stat().st_size < 100_000:
            try:
                with open(path, "rb") as f:
                    first = f.read(16)
                if first.startswith(b'{"url":') or first.startswith(
                    b'{\n  "url":'
                ):
                    return StreamedPbf(str(path))
            except OSError:
                pass
    return source


def download_streamed(url, filename):
    """Download layout descriptor of an OSM PBF file for streamed HTTP range reading."""
    if not has_cpp():
        raise RuntimeError(
            "Streaming an OSM extract needs scgraph's C++ backend"
        )
    return StreamedPbf.download(url, filename)


# The planet of a given date (never planet-latest), changed at each data release, read
# by byte ranges from a mirror that serves them
PLANET = {
    **GEOFABRIK,
    "url": "https://osm-planet-eu-central-1.s3.dualstack.eu-central-1.amazonaws.com/planet/pbf/2026/planet-261102.osm.pbf",
    "download": download_streamed,
}
_AGENT = {"User-Agent": "scgraph"}
_SCAN = 1 << 23  # bytes below which the layout of a PBF is found blob by blob
_STREAMER_SCRIPT = str(
    Path(__file__).resolve().parent / "pbf_range_streamer.py"
)


def _blob(data):
    """Length of the PBF blob that `data` starts with, headers included; its BlobHeader
    holds a type then a datasize, as osmium and the planet dumps write it (no index).
    """
    (length,) = struct.unpack(">I", data[:4])
    i, size, shift = 7 + data[5], 0, 0  # past the type
    while True:  # the datasize, a varint
        size |= (data[i] & 127) << shift
        if data[i] < 128:
            return 4 + length + size
        i, shift = i + 1, shift + 7
