"""Download an OpenStreetMap file and cut its ways into pieces, for the OpenStreetMap
pipelines.

The module needs the optional dependency `osmium` (`pip install scgraph[osm]`). It
imports `osmium` only when it reads a file.

WHAT IT ANSWERS

`scgraph.helpers.osm` reads the ways of the file: its docstring explains the select
functions and the three passes of `locate_ways`. `build_way_pieces` gives the pieces of
the kept ways (`step3_network_assembly.PieceArrays`), for a pipeline. The kinds are
`ways` and `ferries`. The kind `ferries` is special: `build_way_pieces` does not cut a
ferry by length, and attaches it to the nodes of its node mode. The node mode of a node
is the kind of place where the node is, such as `road` or `rail`.

A select function may return the direction with the class of the way (docstring of
`scgraph.pipelines`, *The classes*). Example: for a one-way trunk road,
`scgraph.helpers.osm.select_main_roads_with_class` returns `(1, "trunk")`.

WHERE THE FILE IS

The file is on disk, or on a server. `StreamedPbf` reads a file on a server by HTTP
byte ranges and never stores it. The planet is read this way.
"""

import json
import logging
import math
import os
import struct
import subprocess
import sys
import time
from collections import defaultdict
from collections.abc import Callable, Iterator
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING

import requests

from scgraph.helpers.osm import (
    MAIN_ROADS as MAIN_ROADS,
    MAX_KM_BETWEEN_NODES as MAX_KM_BETWEEN_NODES,
    _ONE_WAY as _ONE_WAY,
    _Junctions as _Junctions,
    _PagedIdSet as _PagedIdSet,
    _open_source as _open_source,
    _select_ways as _select_ways,
    _split_at_unlocated_nodes as _split_at_unlocated_nodes,
    get_way_direction as get_way_direction,
    locate_ways,
    read_osm as read_osm,
    require_osmium,
    select_main_roads as select_main_roads,
)
from scgraph.helpers.polylines import cut_polylines, build_graph_from_polylines
from scgraph.pipelines import CLASS_IDS, CLASSES, download_file
from scgraph.pipelines.steps.near_nodes import NearNodes
from scgraph.pipelines.steps.step3_network_assembly import (
    PieceArrays,
)
from scgraph.utils import has_cpp
from scgraph._internal import log_step

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

# The farthest that an end of a ferry may be from the road node that it joins, in km
FERRY_END_KM = 2


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


def build_way_pieces(
    source: "str | os.PathLike | StreamedPbf",
    selects: dict[str, dict[str, Callable]],
    tag_keys: tuple[str, ...],
    max_km_between_nodes: float,
    work_dir: str | os.PathLike | None = None,
    optional_modes: tuple[str, ...] = (),
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
    its way, if it gave one. With `work_dir`, the positions of the nodes and the
    pieces are kept in files of that folder, and a later call with the same
    inputs reuses them. Each step logs its counts at DEBUG.

    Returns:
        The pieces of each node mode, by name (`step3_network_assembly.PieceArrays`).

    Raises:
        ValueError: The select functions of a node mode keep no way, and the node mode
            is not in `optional_modes`. The message names the node mode. An optional
            node mode without a way has no piece.
    """
    # `StreamedPbf.download` writes a layout file in place of an OSM file that is
    # read by byte ranges. A layout file is JSON, so it starts with "{". An OSM
    # file starts with "<" (XML) or with a zero byte (PBF).
    if isinstance(source, (str, os.PathLike)):
        with open(source, "rb") as file:
            if file.read(1) == b"{":
                source = StreamedPbf(source)
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
            mode: PieceArrays(work_dir=pieces_dirs[mode]) for mode in selects
        }
        # The ferries of each node mode, by the id of their class
        ferries = {mode: defaultdict(list) for mode in selects}
        for mode, kind, direction, class_name, vertices in ways:
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
                    origin_id, destination_id, km, way, ends, shape, class_id
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
                mode_pieces.append(*end_ids, km, 1, road, shape, class_id)
            mode_pieces.flush()
            counts["edges"] = len(edges)
    if work_dir:
        # The marker is written after the last flush: it says that every piece is on
        # disk
        Path(done_marker).write_text("done\n")
    return pieces


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
