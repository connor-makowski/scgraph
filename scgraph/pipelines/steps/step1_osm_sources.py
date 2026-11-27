"""Download an OpenStreetMap file, or read it on its server, for the OpenStreetMap
pipelines.

The module needs the optional dependency `osmium` (`pip install scgraph[osm]`). It
imports `osmium` only when it reads a file.

WHAT IT ANSWERS

`download` and `write_pbf_layout_file` are the download functions of the OpenStreetMap
sources. `get_source` gives the source that `scgraph.helpers.osm.build_way_pieces`
reads. The docstring of `scgraph.helpers.osm` explains the select functions and the
pieces.

WHERE THE FILE IS

The file is on disk, or on a server. `StreamedPbf` reads a file on a server by HTTP
byte ranges and never stores it. The planet is read this way.
"""

import json
import os
import struct
import subprocess
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

import requests

from scgraph import files
from scgraph.helpers.osm import (
    MAX_KM_BETWEEN_NODES as MAX_KM_BETWEEN_NODES,
    require_osmium,
)
from scgraph.pipelines import download_file

if TYPE_CHECKING:  # annotations only: osmium stays optional at run time
    import osmium

__all__ = [
    "GEOFABRIK",
    "PLANET",
    "download",
    "write_pbf_layout_file",
]

# The OpenStreetMap extracts of Geofabrik, `{region}` being the path of an extract
GEOFABRIK = {
    "url": "https://download.geofabrik.de/{region}-latest.osm.pbf",
    "credit": "© OpenStreetMap contributors",
    "license": "ODbL-1.0",
    "license_url": "https://www.openstreetmap.org/copyright",
}


def download(url: str, filename: str | os.PathLike) -> dict[str, str]:
    """Download an OSM file to `filename`.

    Args:
        url: The URL of the OSM file.
        filename: The path where the function writes the file.

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

        Args:
            url: The URL of the PBF file. The server must answer byte ranges.
            filename: The path where the function writes the layout file.

        Returns:
            `{version, bytes, md5}`, without the values that the server does not give.
        """
        osmium = require_osmium()
        session = files.create_retry_session()
        head = session.head(url, allow_redirects=True, timeout=(10.0, 60.0))
        head.raise_for_status()
        url = head.url
        size = int(head.headers["Content-Length"])
        tag = head.headers.get("ETag") or head.headers["Last-Modified"]

        def get(start, end):  # bytes [start, end) of the same file
            ask = {"Range": f"bytes={start}-{min(end, size) - 1}"}
            # A request is tried again: one slow answer must not stop a build that
            # takes hours
            for attempt in range(files.MAX_RETRIES + 1):
                try:
                    answer = session.get(url, headers=ask, timeout=(10.0, 60.0))
                    answer.raise_for_status()
                    content = answer.content
                    break
                except (requests.RequestException, OSError, TimeoutError):
                    if attempt == files.MAX_RETRIES:
                        raise
                    time.sleep(min(60, 2**attempt))
            files.check_byte_range_answer(answer, tag, size)
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
                    url + ".md5", allow_redirects=True, timeout=(10.0, 60.0)
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
        for `osmium.osm.WAY`, and the relations otherwise.
        """
        if sys.platform == "win32":
            raise NotImplementedError(
                "StreamedPbf via /dev/fd pipe is only supported on POSIX systems (Linux, macOS)."
            )
        osmium = require_osmium()
        header, ways, relations = self.about["layout"]
        if entities & osmium.osm.NODE:
            section = [header, ways]
        elif entities & osmium.osm.WAY:
            section = [ways, relations]
        else:
            section = [relations, self.about["size"]]
        job = json.dumps({**self.about, "ranges": [[0, header], section]})
        self._pipe, write = os.pipe()
        # -P: not the modules of the current folder
        command = [sys.executable, "-P", _RANGE_STREAMER_SCRIPT, job]
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


def get_source(
    filename: str | os.PathLike,
) -> "str | os.PathLike | StreamedPbf":
    """Return the source that `scgraph.helpers.osm.build_way_pieces` reads for the file
    that a download function wrote: a `StreamedPbf` for a layout file, and `filename`
    for an OSM file.
    """
    # `StreamedPbf.download` writes a layout file in place of an OSM file that is
    # read by byte ranges. A layout file is JSON, so it starts with "{". An OSM
    # file starts with "<" (XML) or with a zero byte (PBF).
    with open(filename, "rb") as file:
        if file.read(1) == b"{":
            return StreamedPbf(filename)
    return filename


def write_pbf_layout_file(
    url: str, filename: str | os.PathLike
) -> dict[str, str | int]:
    """Write the layout file of an OSM PBF file, so that a build reads the file by HTTP
    byte ranges (`StreamedPbf.download`).

    Args:
        url: The URL of the PBF file.
        filename: The path where the function writes the layout file.

    Returns:
        The dict that `StreamedPbf.download` returns.
    """
    return StreamedPbf.download(url, filename)


# The planet file of one date. A dated file never changes, so a build can read it by
# byte ranges. Change the URL to take newer data. This mirror serves byte ranges.
PLANET = {
    **GEOFABRIK,
    "url": "https://osm-planet-eu-central-1.s3.dualstack.eu-central-1.amazonaws.com/planet/pbf/2026/planet-261102.osm.pbf",
    "download": write_pbf_layout_file,
}
# In bytes. Below this distance, the start of a section is found blob by blob.
_SCAN = 1 << 23
_RANGE_STREAMER_SCRIPT = str(
    Path(__file__).resolve().parent / "step1_osm_range_streamer.py"
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
