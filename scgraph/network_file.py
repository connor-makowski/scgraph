"""
Read and write `.scgraph` network files (format described in ARCHITECTURE.md, "Network
file").

A file is an 8-byte magic `SCGRAPH1`, the length of a JSON header as a little-endian uint64,
the header, then little-endian arrays at the offsets the header gives, each aligned to 64
bytes. Arcs are stored by origin (CSR): the arcs of node `u` are `heads[offsets[u]:
offsets[u + 1]]`, in the order of the graph's dict, with their `weights`.
"""

import hashlib
import json
import mmap
import os
import secrets
import sys
from array import array
from itertools import islice
from operator import le

MAGIC = b"SCGRAPH1"
VERSION = 1
SPEC = "https://github.com/connor-makowski/scgraph/blob/main/ARCHITECTURE.md#7-network-file"
# array name -> (dtype, array typecode); shape_* hold the arc shapes, if any
ARRAYS = {
    "offsets": ("int32", "i"),
    "heads": ("int32", "i"),
    "weights": ("float64", "d"),
    "latitudes": ("float64", "d"),
    "longitudes": ("float64", "d"),
    "shape_offsets": ("int64", "q"),
    "shape_points": ("float64", "d"),
}
_ALIGN = 64
_HEADER_END = 4096  # arrays start on a page boundary


def write(filename, graph, nodes, intermediate_nodes, metadata):
    """Write a graph (list of dicts), its [lat, lon] nodes, the shapes of its arcs (or
    None) and a JSON-serializable metadata dict. The header records the SHA-256 of the
    bytes after it (the arrays) as `content_sha256`, the identity of the network, which is
    returned.
    """
    offsets, heads, weights = array("i", [0]), array("i"), array("d")
    shape_offsets, points = array("q", [0]), array("d")
    symmetric = True
    for origin, row in enumerate(graph):
        # Nodes added after loading (add_coord_node, merges) have no shapes
        shapes = (
            intermediate_nodes[origin]
            if intermediate_nodes is not None
            and origin < len(intermediate_nodes)
            else {}
        )
        # In the graph's order, so that a search on the file visits the arcs in the same
        # order, and returns the same path where two have the same length
        for head in row:
            heads.append(head)
            weights.append(row[head])
            symmetric = symmetric and graph[head].get(origin) == row[head]
            for point in shapes.get(head, ()):
                points.extend(point)
            shape_offsets.append(len(points) // 2)
        offsets.append(len(heads))
    arrays = {
        "offsets": offsets,
        "heads": heads,
        "weights": weights,
        "latitudes": array("d", (node[0] for node in nodes)),
        "longitudes": array("d", (node[1] for node in nodes)),
    }
    if intermediate_nodes is not None:
        arrays["shape_offsets"], arrays["shape_points"] = shape_offsets, points

    header = {
        "format_version": VERSION,
        "spec": SPEC,
        # Same length as the digest, written once the arrays are
        "content_sha256": "0" * 64,
        "arrays": {},
        "metadata": {**metadata, "symmetric": symmetric},
    }
    position = _HEADER_END
    for name, values in arrays.items():
        shape = (
            [len(values) // 2, 2] if name == "shape_points" else [len(values)]
        )
        header["arrays"][name] = {
            "dtype": ARRAYS[name][0],
            "shape": shape,
            "offset": position,
        }
        position = _aligned(position + len(values) * values.itemsize)
    text = json.dumps(header).encode()
    if 16 + len(text) > _HEADER_END:
        raise ValueError("The metadata is too large for a network file header")
    # Written next to the target, then moved onto it: a failed save leaves the previous
    # file whole, and the file is never rewritten in place
    folder, base = os.path.split(os.path.abspath(filename))
    temporary = os.path.join(
        folder, f".{base}.{os.getpid()}.{secrets.token_hex(4)}.saving"
    )
    file = open(temporary, "xb")
    try:
        with file:
            content = hashlib.sha256()
            file.seek(_HEADER_END)
            for name, values in arrays.items():
                padding = bytes(header["arrays"][name]["offset"] - file.tell())
                for chunk in (padding, _little_endian(values).tobytes()):
                    file.write(chunk)
                    content.update(chunk)
            header["content_sha256"] = content.hexdigest()
            file.seek(0)
            file.write(MAGIC)
            file.write((_HEADER_END - 16).to_bytes(8, "little"))
            file.write(json.dumps(header).encode().ljust(_HEADER_END - 16))
        try:
            os.replace(temporary, filename)
        except PermissionError as error:
            if os.name != "nt":
                raise
            # Windows does not replace a file that a process has mapped
            raise PermissionError(
                f"{filename} is open in a graph (its file is mapped): save to another "
                "name, or release every graph read from it first"
            ) from error
    except BaseException:
        os.unlink(temporary)
        raise
    return header["content_sha256"]


def read(filename, mapped=False):
    """Return the arrays (by name) and the metadata of a network file, after checking that
    they describe a valid graph; a damaged or foreign file raises a ValueError. The
    metadata also holds the header's `content_sha256`, if the file has one (files written
    by other tools may not).

    With `mapped=True` (on little-endian machines), the file is mapped read-only and the
    arrays are memoryviews of it, not copies: the file stays mapped while they are
    referenced. Offsets and heads are then left to the reader to check (the C++
    `Graph.from_csr` does), so that opening does not read every arc.
    """
    mapped = mapped and sys.byteorder == "little"
    try:
        with open(filename, "rb") as file:
            arrays, metadata = _read(filename, file, mapped)
    except ValueError:
        raise
    except (AttributeError, KeyError, OverflowError, TypeError) as error:
        raise ValueError(f"{filename}: invalid header ({error!r})") from error
    _check(filename, arrays, arcs=not mapped)
    return arrays, metadata


def _read(filename, file, mapped):
    if file.read(8) != MAGIC:
        raise ValueError(f"{filename} is not a scgraph network file")
    length = int.from_bytes(file.read(8), "little")
    header = json.loads(file.read(length))
    if header.get("format_version") != VERSION:
        raise ValueError(
            f"{filename} has format version {header.get('format_version')}; "
            f"this version of scgraph reads version {VERSION}"
        )
    file_size = os.fstat(file.fileno()).st_size
    if mapped:
        view = memoryview(mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_READ))
    arrays = {}
    for name, entry in header["arrays"].items():
        if name not in ARRAYS:
            continue  # added by a later version, not needed to read the graph
        dtype, typecode = ARRAYS[name]
        values, count, start = (
            array(typecode),
            _count(entry["shape"]),
            entry["offset"],
        )
        if (
            entry["dtype"] != dtype
            or start % _ALIGN
            or start + count * values.itemsize > file_size
        ):
            raise ValueError(f"{filename}: invalid array '{name}'")
        if mapped:
            end = start + count * values.itemsize
            arrays[name] = view[start:end].cast(typecode)
            continue
        file.seek(start)
        values.fromfile(file, count)
        arrays[name] = _little_endian(values)
    metadata = dict(header["metadata"])
    if "content_sha256" in header:
        metadata["content_sha256"] = header["content_sha256"]
    return arrays, metadata


def shapes(arrays):
    """The arc shapes of `read`'s arrays as GeoGraph `intermediate_nodes` (one dict per
    origin), or None if the file has none."""
    if "shape_offsets" not in arrays:
        return None
    offsets, heads = arrays["offsets"], arrays["heads"]
    starts, points = arrays["shape_offsets"], arrays["shape_points"]
    result = []
    for origin in range(len(offsets) - 1):
        row = {}
        for arc in range(offsets[origin], offsets[origin + 1]):
            first, last = starts[arc], starts[arc + 1]
            if last > first:
                row[heads[arc]] = [
                    [points[2 * i], points[2 * i + 1]]
                    for i in range(first, last)
                ]
        result.append(row)
    return result


def _check(filename, arrays, arcs=True):
    def require(condition, what):
        if not condition:
            raise ValueError(f"{filename}: {what}")

    required = {"offsets", "heads", "weights", "latitudes", "longitudes"}
    require(required <= set(arrays), "missing arrays")
    require(
        ("shape_offsets" in arrays) == ("shape_points" in arrays),
        "missing shape arrays",
    )
    offsets, heads = arrays["offsets"], arrays["heads"]
    n, m = len(offsets) - 1, len(heads)
    require(n >= 0 and offsets[0] == 0 and offsets[-1] == m, "invalid offsets")
    require(len(arrays["weights"]) == m, "one weight per arc expected")
    if arcs:
        # The loops over the arcs run in C (map, min, max), not in Python
        require(
            all(map(le, offsets, islice(offsets, 1, None))), "invalid offsets"
        )
        require(
            not m or (min(heads) >= 0 and max(heads) < n),
            "arc to a missing node",
        )
    require(
        len(arrays["latitudes"]) == len(arrays["longitudes"]) == n,
        "one latitude and longitude per node expected",
    )
    if "shape_offsets" in arrays:
        shapes = arrays["shape_offsets"]
        require(
            len(shapes) == m + 1
            and shapes[0] == 0
            and shapes[-1] == len(arrays["shape_points"]) // 2
            and all(map(le, shapes, islice(shapes, 1, None))),
            "invalid shape offsets",
        )


def _count(shape):
    count = 1
    for size in shape:
        count *= size
    return count


def _aligned(position):
    return -(-position // _ALIGN) * _ALIGN


def _little_endian(values):
    if sys.byteorder == "big":
        values.byteswap()
    return values
