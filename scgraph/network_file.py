"""
Read and write `.scgraph` network files (format described in ARCHITECTURE.md, "Network
file").

A file is an 8-byte magic `SCGRAPH1`, the SHA-256 of every byte from byte 40 on (32 bytes),
the length of a JSON header as a little-endian uint64, the header, zeros up to a multiple of 64
bytes, then little-endian arrays at the offsets the header gives from there, each aligned to
64 bytes. Arcs are stored by origin (CSR): the arcs of node `u` are `heads[offsets[u]:
offsets[u + 1]]`, in the order searches visit them, with their `weights`.
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
# dtype -> array typecode
DTYPES = {"int32": "i", "int64": "q", "float64": "d", "uint8": "B"}
# array name -> the dtypes it may have; shape_* hold the arc shapes, if any, with their
# points in units of 1e-7 degree (OSM's own); node_ids and node_modes (optional): the
# id of each node in its source (int32 when every id fits) and its mode, an index into
# metadata["modes"]
ARRAYS = {
    "offsets": ("int32",),
    "heads": ("int32",),
    "weights": ("float64",),
    "latitudes": ("float64",),
    "longitudes": ("float64",),
    "shape_offsets": ("int32",),
    "shape_points": ("int32",),
    "node_ids": ("int32", "int64"),
    "node_modes": ("uint8",),
}
_ALIGN = 64
_PREAMBLE = 48  # magic, digest, header length


def write(filename, arrays, metadata):
    """Write the arrays of a graph (by name, as stored: see `ARRAYS`; `shape_points`
    flat, two per point, in 1e-7 degree; any objects with the buffer protocol, not
    copied on little-endian machines) and a JSON-serializable metadata dict. Bytes 8 to
    39 hold the SHA-256 of every byte after them, the identity of the file, returned as
    hex (`content_sha256`). Rows hold each head once.
    """
    symmetric = _symmetric(
        arrays["offsets"], arrays["heads"], arrays["weights"]
    )

    header = {
        "format_version": VERSION,
        "spec": SPEC,
        "arrays": {},
        "metadata": {**metadata, "symmetric": symmetric},
    }
    position = 0
    for name, values in arrays.items():
        size = memoryview(values).itemsize
        dtype = next(
            (d for d in ARRAYS[name] if array(DTYPES[d]).itemsize == size),
            None,
        )
        if dtype is None:
            raise TypeError(
                f"Array '{name}' must hold {' or '.join(ARRAYS[name])} values"
            )
        shape = (
            [len(values) // 2, 2] if name == "shape_points" else [len(values)]
        )
        header["arrays"][name] = {
            "dtype": dtype,
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
                # The arrays may be the graph's own: swapped in a copy (big-endian)
                if sys.byteorder == "big":
                    values = array(
                        DTYPES[header["arrays"][name]["dtype"]], values
                    )
                put(memoryview(_little_endian(values)).cast("B"))
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
    _check(filename, arrays, metadata, arcs=not mapped)
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
        if entry["dtype"] not in ARRAYS[name]:
            raise ValueError(f"{filename}: invalid array '{name}'")
        typecode = DTYPES[entry["dtype"]]
        values, count, start = (
            array(typecode),
            _count(entry["shape"]),
            base + entry["offset"],
        )
        if (
            entry["offset"] < 0
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


class NodeIds(Sequence):
    """
    The `node_ids` of a GeoGraph: the stable id of each node (its id in the source it
    came from, or its position if it has none), then, for each node added since, a
    negative id below all the others. Read-only; pickled with its ids as a list.
    """

    def __init__(self, ids, nodes):
        # `nodes` gives the count: nodes past the end of `ids` were added since
        self._ids, self._nodes, self._floor = ids, nodes, None

    def __len__(self):
        return len(self._nodes)

    def __getitem__(self, i):
        if isinstance(i, slice):
            return [self[j] for j in range(*i.indices(len(self)))]
        count, i = len(self), index(i)
        if i < 0:
            i += count
        if not 0 <= i < count:
            raise IndexError("node index out of range")
        ids = self._ids
        if i < len(ids):
            return ids[i]
        # Computed once: the ids of a large network are long to scan
        if self._floor is None:
            low = ids.start if type(ids) is range else min(ids, default=0)
            self._floor = min(0, low)
        return self._floor - 1 - (i - len(ids))

    def __eq__(self, other):
        if not isinstance(other, (list, NodeIds)):
            return NotImplemented
        return len(self) == len(other) and all(map(eq, self, other))

    def __repr__(self):
        return repr(list(self))

    def __reduce__(self):
        return NodeIds, (list(self), self._nodes)

    def take(self, positions):
        """The ids of the nodes at `positions`, as an int64 array."""
        ids = self._ids
        if len(ids) < len(self):  # nodes were added since
            return array("q", (self[i] for i in positions))
        if ids == range(len(ids)):
            return array("q", positions)
        return array("q", (ids[i] for i in positions))

    def array(self):
        """The ids as an int64 array, or None if every node's id is its position."""
        ids, count = self._ids, len(self)
        if count <= len(ids) and ids == range(len(ids)):
            return None
        result = array("q", ids[:count])
        result.extend(self[i] for i in range(len(result), count))
        try:  # half the size when every id fits, as those of the built-in networks
            return array("i", result)
        except OverflowError:
            return result


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


def _check(filename, arrays, metadata, arcs=True):
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
    for name, what in (("node_ids", "node id"), ("node_modes", "node mode")):
        require(
            name not in arrays or len(arrays[name]) == n,
            f"one {what} per node expected",
        )
    if "node_modes" in arrays:
        modes = metadata.get("modes")
        require(isinstance(modes, list), "node modes without a list of modes")
        # Not read on a mapped file, which opening does not read node by node
        require(
            not arcs or max(arrays["node_modes"], default=-1) < len(modes),
            "invalid node modes",
        )


def _symmetric(offsets, heads, weights):
    # Whether every arc has a reverse arc of the same weight. Arc u -> v is looked up in
    # v's row only if v has at most u's degree, so that no hub's row is read once per arc;
    # an arc to a node of higher degree is counted instead: their number must equal that
    # of the reverse arcs found from the other side (a row holds each head once)
    unmatched = 0
    for origin in range(len(offsets) - 1):
        degree = offsets[origin + 1] - offsets[origin]
        for arc in range(offsets[origin], offsets[origin + 1]):
            head = heads[arc]
            start, end = offsets[head], offsets[head + 1]
            if end - start > degree:
                unmatched += 1
                continue
            unmatched -= end - start < degree
            for back in range(start, end):
                if heads[back] == origin:
                    if weights[back] != weights[arc]:
                        return False
                    break
            else:
                return False
    return unmatched == 0


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
