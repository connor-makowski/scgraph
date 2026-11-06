"""
Read and write `.scgraph` network files (format described in ARCHITECTURE.md, "Network
file").

A file is an 8-byte magic `SCGRAPH1`, the SHA-256 of every byte from byte 40 on (32 bytes),
the length of a JSON header as a little-endian uint64, the header, zeros up to a multiple of 64
bytes, then little-endian arrays at the offsets the header gives from there, each aligned to
64 bytes. Arcs are stored by origin (CSR): the arcs of node `u` are `heads[offsets[u]:
offsets[u + 1]]`, in the order of the graph's dict, with their `weights`.
"""

import hashlib
import json
import mmap
import os
import secrets
import sys
from array import array
from collections.abc import MutableSequence, Sequence
from itertools import islice
from operator import eq, index, le
from types import MappingProxyType

try:
    from scgraph.cpp import coordinate_lists as _coordinate_lists
    from scgraph.cpp import shape_path as _shape_path
except ImportError:
    _coordinate_lists = _shape_path = None

MAGIC = b"SCGRAPH1"
VERSION = 1
SPEC = "https://github.com/connor-makowski/scgraph/blob/main/ARCHITECTURE.md#7-network-file"
# array name -> (dtype, array typecode); shape_* hold the arc shapes, if any, with their
# points in units of 1e-7 degree (OSM's own)
ARRAYS = {
    "offsets": ("int32", "i"),
    "heads": ("int32", "i"),
    "weights": ("float64", "d"),
    "latitudes": ("float64", "d"),
    "longitudes": ("float64", "d"),
    "shape_offsets": ("int32", "i"),
    "shape_points": ("int32", "i"),
}
_ALIGN = 64
_PREAMBLE = 48  # magic, digest, header length


def write(filename, graph, nodes, intermediate_nodes, metadata):
    """Write a graph (list of dicts), its [lat, lon] nodes, the shapes of its arcs (or
    None; their points are rounded to 1e-7 degree) and a JSON-serializable metadata dict.
    Bytes 8 to 39 hold the SHA-256 of every byte after them, the identity of the file,
    returned as hex (`content_sha256`).
    """
    offsets, heads, weights = array("i", [0]), array("i"), array("d")
    shape_offsets, points = array("i", [0]), array("i")
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
            try:
                for latitude, longitude in shapes.get(head, ()):
                    points.append(round(latitude * 1e7))
                    points.append(round(longitude * 1e7))
            except (OverflowError, ValueError) as error:
                raise ValueError(
                    f"The shape of arc {origin} -> {head} has a point that is not a"
                    " number within ±214.7483647 degrees"
                ) from error
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
        "arrays": {},
        "metadata": {**metadata, "symmetric": symmetric},
    }
    position = 0
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
    # Sorted, so that in one build the same network and metadata give the same file
    text = json.dumps(header, sort_keys=True).encode()
    start = _aligned(_PREAMBLE + len(text))
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

            def put(chunk):
                file.write(chunk)
                content.update(chunk)

            file.write(MAGIC + bytes(32))  # the digest, written last
            put(len(text).to_bytes(8, "little") + text)
            for name, values in arrays.items():
                at = start + header["arrays"][name]["offset"]
                put(bytes(at - file.tell()))
                put(_little_endian(values).tobytes())
            file.seek(len(MAGIC))
            file.write(content.digest())
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
    return content.hexdigest()


def read(filename, mapped=False):
    """Return the arrays (by name) and the metadata of a network file, after checking that
    they describe a valid graph; a damaged or foreign file raises a ValueError. The
    metadata also holds the file's `content_sha256` (its bytes 8 to 39, as hex).

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
    digest = file.read(32)
    length = int.from_bytes(file.read(8), "little")
    file_size = os.fstat(file.fileno()).st_size
    if length > file_size - _PREAMBLE:
        raise ValueError(f"{filename}: invalid header length")
    header = json.loads(file.read(length))
    base = _aligned(_PREAMBLE + length)
    if header.get("format_version") != VERSION:
        raise ValueError(
            f"{filename} has format version {header.get('format_version')}; "
            f"this version of scgraph reads version {VERSION}"
        )
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
            base + entry["offset"],
        )
        if (
            entry["dtype"] != dtype
            or entry["offset"] < 0
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
    metadata["content_sha256"] = digest.hex()
    return arrays, metadata


class ArcShapes(Sequence):
    """
    The `intermediate_nodes` of a GeoGraph read from a network file: for each origin, a
    read-only mapping {destination: shape}, read from the file's arrays when asked for
    instead of one Python list per point. A shape is a new list of [latitude, longitude]
    each time.
    """

    def __init__(self, arrays):
        self._offsets, self._heads = arrays["offsets"], arrays["heads"]
        self._starts, self._points = (
            arrays["shape_offsets"],
            arrays["shape_points"],
        )

    def __len__(self):
        return len(self._offsets) - 1

    def __getitem__(self, origin):
        if isinstance(origin, slice):
            return [self[i] for i in range(*origin.indices(len(self)))]
        origin = index(origin)
        if origin < 0:
            origin += len(self)
        if not 0 <= origin < len(self):
            raise IndexError("node index out of range")
        heads, starts = self._heads, self._starts
        return MappingProxyType(
            {
                heads[arc]: self._shape(starts[arc], starts[arc + 1])
                for arc in range(
                    self._offsets[origin], self._offsets[origin + 1]
                )
                if starts[arc + 1] != starts[arc]
            }
        )

    def _shape(self, first, last):
        # A mapped file's shape offsets are checked here, where they are read
        if not 0 <= first <= last <= len(self._points) // 2:
            raise ValueError("invalid shape offsets")
        flat = self._points[2 * first : 2 * last].tolist()
        return [
            [flat[i] / 1e7, flat[i + 1] / 1e7] for i in range(0, len(flat), 2)
        ]

    def coordinate_path(self, path, coordinates):
        """`coordinates` (one [latitude, longitude] per node of `path`) with the shape of
        each arc of the path between them; in one C loop in the C++ build"""
        if _shape_path is not None:
            return _shape_path(
                self._offsets,
                self._heads,
                self._starts,
                self._points,
                path if type(path) is list else list(path),
                coordinates,
            )
        offsets, heads, count = self._offsets, self._heads, len(self)
        starts, result = self._starts, [coordinates[0]]
        for i in range(len(path) - 1):
            origin, destination = path[i], path[i + 1]
            # Nodes added after loading (add_coord_node) have no shapes
            if origin < count:
                for arc in range(offsets[origin], offsets[origin + 1]):
                    if heads[arc] == destination:
                        result += self._shape(starts[arc], starts[arc + 1])
                        break
            result.append(coordinates[i + 1])
        return result

    def __eq__(self, other):
        if not isinstance(other, (list, ArcShapes)):
            return NotImplemented
        return len(self) == len(other) and all(map(eq, self, other))

    def __repr__(self):
        return repr([dict(row) for row in self])

    def __reduce__(self):
        # Copied and pickled as a list of dicts (the file's mapping can't be)
        return list, ([dict(row) for row in self],)


class NodeCoordinates(MutableSequence):
    """
    The `nodes` of a GeoGraph read from a network file: a list of [latitude, longitude],
    read from the file's two arrays instead of one Python list per node, then the nodes
    added since. `nodes[i]` gives a new list each time: replace a node with
    `nodes[i] = [latitude, longitude]` (changing the list it gives changes nothing).
    An edit before the last node first turns every node into a list.
    """

    def __init__(self, latitudes, longitudes):
        self._latitudes, self._longitudes, self._added = (
            latitudes,
            longitudes,
            [],
        )

    def __len__(self):
        return len(self._latitudes) + len(self._added)

    def __getitem__(self, i):
        if type(i) is int and 0 <= i < len(self._latitudes):
            return [self._latitudes[i], self._longitudes[i]]
        if isinstance(i, slice):
            return [self[j] for j in range(*i.indices(len(self)))]
        j = self._in_added(i, edit=False)
        if j < 0:  # a node of the file, given from the end
            return [self._latitudes[j], self._longitudes[j]]
        return self._added[j]

    def __setitem__(self, i, value):
        self._added[self._in_added(i)] = value

    def __delitem__(self, i):
        del self._added[self._in_added(i)]

    def insert(self, i, value):
        if i < len(self):
            self._own()
        self._added.insert(i - len(self._latitudes), value)

    def take(self, ids):
        """`[nodes[i] for i in ids]` (a route's path), without a method call per node: in one
        C loop in the C++ build when no node was added"""
        latitudes, longitudes = self._latitudes, self._longitudes
        if _coordinate_lists is not None and not self._added:
            return _coordinate_lists(
                latitudes, longitudes, ids if type(ids) is list else list(ids)
            )
        count = len(latitudes)
        return [
            [latitudes[i], longitudes[i]] if 0 <= i < count else self[i]
            for i in ids
        ]

    def __iter__(self):
        yield from map(list, zip(self._latitudes, self._longitudes))
        yield from self._added

    def __eq__(self, other):
        if not isinstance(other, (list, NodeCoordinates)):
            return NotImplemented
        return len(self) == len(other) and all(map(eq, self, other))

    def __repr__(self):
        return repr(list(self))

    def __reduce__(self):
        # Copied and pickled as a list (the file's mapping can't be)
        return list, (list(self),)

    def arrays(self):
        """The latitudes and the longitudes as two float64 arrays (the file's own if no
        node was added)."""
        if not self._added:
            return self._latitudes, self._longitudes
        result = []
        for column, values in enumerate((self._latitudes, self._longitudes)):
            joined = array("d")
            joined.frombytes(memoryview(values).cast("B"))
            joined.extend(node[column] for node in self._added)
            result.append(joined)
        return tuple(result)

    def _in_added(self, i, edit=True):
        # The position of node i (or of slice i) in `added`. To edit a node of the file,
        # every node is first moved into `added`, as a list holds them
        if isinstance(i, slice):
            self._own()
            return i
        count, i = len(self), index(i)
        if i < 0:
            i += count
        if not 0 <= i < count:
            raise IndexError("node index out of range")
        if i < len(self._latitudes) and edit:
            self._own()
        return i - len(self._latitudes)

    def _own(self):
        if len(self._latitudes):
            self._added[:0] = map(list, zip(self._latitudes, self._longitudes))
            self._latitudes, self._longitudes = array("d"), array("d")


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
            and shapes[-1] == len(arrays["shape_points"]) // 2,
            "invalid shape offsets",
        )
        # Mapped, each shape's offsets are checked where it is read (ArcShapes)
        require(
            not arcs or all(map(le, shapes, islice(shapes, 1, None))),
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
