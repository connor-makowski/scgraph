"""
Read and write `.scgraph` network files. `ARCHITECTURE.md`, section 7 (*Network File
Format*), specifies the format.

A file has these parts, in this order:

1. the 8 bytes `SCGRAPH1`;
2. the SHA-256 digest of every byte from byte 40 to the end of the file (32 bytes);
3. the length of the JSON header, as a little-endian uint64;
4. the JSON header, then zeros up to a multiple of 64 bytes;
5. the arrays, in little-endian order. The header gives the offset of each array,
   and each array starts at a multiple of 64 bytes.

The edges are stored by origin, in Compressed Sparse Row (CSR) arrays. The edges of
node `u` go to the nodes `heads[offsets[u]:offsets[u + 1]]`, in the order that a
search visits them. `weights` holds the weight of each edge at the same positions.

The public functions are `read`, `write`, `get_scgraph_info` and `check_content`.
"""

import hashlib
import json
import math
import mmap
import os
import secrets
import sys
from array import array
from collections.abc import Iterable, MutableSequence, Sequence
from itertools import chain, starmap
from operator import eq, index
from types import MappingProxyType

from scgraph.helpers.hilbert import NODE_ORDER
from scgraph._internal import is_sorted

try:
    from scgraph.cpp import coordinate_lists as _coordinate_lists
    from scgraph.cpp import shape_path as _shape_path
except ImportError:
    _coordinate_lists = _shape_path = None
try:
    from scgraph.cpp import select_edges
except ImportError:
    from scgraph.helpers.edge_selection import select_edges

__all__ = ["check_content", "get_scgraph_info", "read", "write"]

MAGIC = b"SCGRAPH1"
FORMAT_VERSION = 1
# dtype -> array typecode
DTYPES = {"int32": "i", "int64": "q", "float64": "d", "uint8": "B"}
# array name -> the dtypes it may have; shape_* hold the edge shapes, if any; node_ids and
# node_modes (optional): each node's id in its source and its row of metadata["modes"].
# edge_classes (optional): each edge's row of metadata["classes"].
# node_points and shape_points are arrays of points: the latitude of a point, then its
# longitude. Both arrays have the same dtype: float64 degrees, or int32 units of 1e-7
# degree (see `encode_coordinates`).
ARRAYS = {
    "offsets": ("int32",),
    "heads": ("int32",),
    "weights": ("float64",),
    "node_points": ("int32", "float64"),
    "shape_offsets": ("int32",),
    "shape_points": ("int32", "float64"),
    "node_ids": ("int32", "int64"),
    "node_modes": ("uint8",),
    "edge_classes": ("uint8",),
}
POINT_ARRAYS = ("node_points", "shape_points")
_ALIGN = 64
_PREAMBLE = 48  # magic, digest, header length


def encode_coordinates(
    point_arrays: Sequence[Sequence[float]], dtype: str
) -> list[Sequence[float]]:
    """Return arrays of points in the form that a network file stores.

    Args:
        point_arrays: Arrays of points, in float64 degrees.
        dtype: "float64" keeps the arrays as they are. "int32" converts each value to
            units of 1e-7 degree and rounds it. This is the encoding of OpenStreetMap,
            and one unit is about 1 cm.

    Returns:
        One array for each array of `point_arrays`, in `dtype`.

    Raises:
        ValueError: `dtype` is not one of the two names, a value is not a finite
            number, or an int32 value is beyond ±214.7483647 degrees.
    """
    if dtype not in ARRAYS["node_points"]:
        raise ValueError(
            f"coordinate_dtype must be 'float64' or 'int32', not {dtype!r}"
        )
    if dtype == "int32":
        try:
            return [
                array("i", (round(x * 1e7) for x in v)) for v in point_arrays
            ]
        # Not finite, or beyond the int32 range
        except (OverflowError, ValueError):
            raise ValueError(
                "Coordinates stored as int32 must be finite numbers within"
                " ±214.7483647 degrees"
            ) from None
    if not all(all(map(math.isfinite, values)) for values in point_arrays):
        raise ValueError("Coordinates must be finite numbers")
    return list(point_arrays)


def get_coordinate_dtype(arrays: dict[str, array | memoryview]) -> str:
    """Return the dtype of the coordinates in the arrays that `read` returns: "int32"
    or "float64"."""
    return (
        "int32"
        if _get_units_per_degree(arrays["node_points"]) != 1
        else "float64"
    )


def _get_units_per_degree(values):
    # Units of a coordinate array per degree: 1e7 for int32 (OSM's), 1 for float64
    return 1e7 if memoryview(values).format == "i" else 1.0


# Header keys that scgraph writes or computes itself, which build metadata cannot set
RESERVED_METADATA_KEYS = frozenset(
    {
        "crs",
        "units",
        "modes",
        "classes",
        "symmetric",
        "node_order",
        "content_sha256",
        "format_version",
        "nodes",
        "edges",
        "coordinate_dtype",
        "shapes",
        "node_ids",
        "attribution",
        "data_up_to",
    }
)


def build_header_metadata(
    build_metadata: dict,
    *,
    units: str,
    modes: list[dict],
    classes: Sequence[str] | None = None,
) -> dict:
    """Return the metadata that `write` takes, for a network whose nodes are in the
    order of a network file: by mode, then along a Hilbert curve (`helpers.hilbert`).

    Args:
        build_metadata: What built the network: the pipeline, the sources and the
            software (docstring of `scgraph.pipelines`).
        units: The unit of the edge weights, such as "km".
        modes: The modes table: one dict for each mode, with its `name` and, if a
            source gave the node ids of the mode, the name of that `source`.
        classes: The names of the classes, for a network with `edge_classes`.

    Returns:
        The keys that scgraph sets itself (`crs`, `units`, `modes`, `classes`,
        `node_order`), then the keys of `build_metadata`.

    Raises:
        ValueError: `build_metadata` sets a key that scgraph writes itself, or a mode
            names a source that is not in the `sources` of `build_metadata`.
    """
    if RESERVED_METADATA_KEYS & set(build_metadata):
        raise ValueError(
            f"metadata may not set {sorted(RESERVED_METADATA_KEYS & set(build_metadata))}"
        )
    # A mode cites the source of its node ids by name
    names = {source.get("name") for source in build_metadata.get("sources", [])}
    for mode in modes:
        if "source" in mode and mode["source"] not in names:
            raise ValueError(
                f"Mode {mode} names no source: pass metadata with a source of "
                f"that name in its 'sources'"
            )
    return {
        "crs": "EPSG:4326",
        "units": units,
        **({"modes": modes} if modes != [{"name": None}] else {}),
        **({"classes": list(classes)} if classes is not None else {}),
        "node_order": NODE_ORDER,
        **build_metadata,
    }


def write(
    filename: str | os.PathLike,
    arrays: dict[str, array | memoryview],
    metadata: dict,
) -> str:
    """Write the arrays and the metadata of a network to a `.scgraph` file.

    Args:
        filename: The path of the `.scgraph` file to write.
        arrays: The arrays of the network, by name (`offsets`, `heads`, `weights`,
            `node_points`, ...). `ARRAYS` gives the names and the dtypes that a file
            may hold.
        metadata: The metadata of the network (modes, sources, ...). It must be
            serializable as JSON.

    Returns:
        The `content_sha256` of the file: the SHA-256 digest of its content, in
        hexadecimal.

    Raises:
        TypeError: The values of an array do not have a dtype that the array may have.
        PermissionError: On Windows, a process has mapped the file at `filename`, so
            the file cannot be replaced.
    """
    symmetric = _is_symmetric(
        arrays["offsets"], arrays["heads"], arrays["weights"]
    )

    header = {
        "format_version": FORMAT_VERSION,
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
        shape = [len(values) // 2, 2] if name in POINT_ARRAYS else [len(values)]
        header["arrays"][name] = {
            "dtype": dtype,
            "shape": shape,
            "offset": position,
        }
        position = _align(position + len(values) * values.itemsize)
    # Sorted, so that in one build the same network and metadata give the same file
    text = json.dumps(header, sort_keys=True).encode()
    start = _align(_PREAMBLE + len(text))
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
                put(memoryview(_to_little_endian(values)).cast("B"))
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


def read(
    filename: str | os.PathLike,
    mapped: bool = False,
    modes: str | list[str] | None = None,
) -> tuple[dict[str, array | memoryview], dict]:
    """Read the arrays and the metadata of a network from a `.scgraph` file.

    Args:
        filename: The path of the `.scgraph` file to read.
        mapped: If True, on a little-endian computer, the arrays are views of the
            file mapped into memory, not copies. The default is False.
        modes: The names of the modes to read. The arrays then hold only the nodes
            of these modes and the edges between them, in the order of the file. With
            `mapped`, an array is a view of the file when its values are consecutive
            in the file, and a new array otherwise. The default, None, reads every
            mode.

    Returns:
        `(arrays, metadata)`. `arrays` holds the arrays of the network by name
        (`offsets`, `heads`, `weights`, ...). `metadata` holds the metadata of the
        header, and the `content_sha256` of the file.

    Raises:
        ValueError: The header or the layout of the arrays is not valid. `read` does
            not check the digest (see `check_content`).
        FileNotFoundError: The file does not exist.
    """
    mapped = mapped and sys.byteorder == "little"
    try:
        with open(filename, "rb") as file:
            arrays, metadata, is_mode_kept = _read(
                filename, file, mapped, modes
            )
    except ValueError:
        raise
    except (AttributeError, KeyError, OverflowError, TypeError) as error:
        raise ValueError(f"{filename}: invalid header ({error!r})") from error
    if is_mode_kept is None:
        _check(filename, arrays, metadata, should_check_values=not mapped)
    else:
        # The selection checks the values of the edges, where it reads them
        _check(filename, arrays, metadata, should_check_values=False)
        arrays = _select_modes(
            filename, arrays, metadata, is_mode_kept, in_place=mapped
        )
    return arrays, metadata


def get_scgraph_info(filename: str | os.PathLike) -> dict:
    """Return what a `.scgraph` file holds, without loading its arrays.

    Args:
        filename: The path of the `.scgraph` file.

    Returns:
        The keys of the metadata of the file, then `content_sha256`,
        `format_version`, `nodes`, `edges`, `coordinate_dtype`, `shapes` and
        `node_ids`. `nodes` and `edges` are counts. `shapes` and `node_ids` say whether
        the file holds these arrays.

    Raises:
        ValueError: The header of the file is not valid.
    """
    arrays, metadata = read(filename, mapped=True)
    return {
        **metadata,
        "format_version": FORMAT_VERSION,
        "nodes": len(arrays["node_points"]) // 2,
        "edges": len(arrays["heads"]),
        "coordinate_dtype": get_coordinate_dtype(arrays),
        "shapes": "shape_points" in arrays,
        "node_ids": "node_ids" in arrays,
    }


def check_content(filename: str | os.PathLike) -> str:
    """Check that the content of a network file has the digest that its writer
    recorded. Return that digest.

    The first 40 bytes of a file hold the magic number and `content_sha256`. This
    digest is the SHA-256 of the bytes from byte 40 to the end of the file. `read`
    does not check it. This function reads the whole file and computes the digest
    again. A file that was cut or changed after it was written has another digest.

    Args:
        filename: The path of the `.scgraph` file.

    Returns:
        The `content_sha256` of the file.

    Raises:
        ValueError: The content does not have the recorded digest. A file that is
            not a network file raises it too.
    """
    with open(filename, "rb") as file:
        file.seek(len(MAGIC))
        recorded = file.read(32)
        if hashlib.file_digest(file, "sha256").digest() != recorded:
            raise ValueError(
                f"{filename}: the content does not have the recorded "
                "content_sha256 (the file was cut or changed)"
            )
    return recorded.hex()


def _read(filename, file, mapped, modes):
    """The arrays of the whole file and its metadata. With `modes`, the third value
    says, for each mode of the file, whether `modes` names it. This value is None
    when the read keeps every mode."""
    if file.read(8) != MAGIC:
        raise ValueError(f"{filename} is not a scgraph network file")
    digest = file.read(32)
    length = int.from_bytes(file.read(8), "little")
    file_size = os.fstat(file.fileno()).st_size
    if length > file_size - _PREAMBLE:
        raise ValueError(f"{filename}: invalid header length")
    header = json.loads(file.read(length))
    base = _align(_PREAMBLE + length)
    if header.get("format_version") != FORMAT_VERSION:
        raise ValueError(
            f"{filename} has format version {header.get('format_version')}; "
            f"this version of scgraph reads version {FORMAT_VERSION}"
        )
    is_mode_kept = None
    if modes is not None:
        modes = (modes,) if isinstance(modes, str) else modes
        mode_names = [
            mode["name"]
            for mode in header["metadata"].get("modes") or [{"name": None}]
        ]
        unknown = [mode for mode in modes if mode not in mode_names]
        if unknown:
            raise ValueError(f"{filename}: unknown modes {unknown}")
        if not all(name in modes for name in mode_names):
            is_mode_kept = [name in modes for name in mode_names]
    # A selection also reads the file in place, and copies only what it keeps
    view = None
    if mapped or (is_mode_kept is not None and sys.byteorder == "little"):
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
            _count_values(entry["shape"]),
            base + entry["offset"],
        )
        if (
            entry["offset"] < 0
            or start % _ALIGN
            or start + count * values.itemsize > file_size
        ):
            raise ValueError(f"{filename}: invalid array '{name}'")
        if view is not None:
            end = start + count * values.itemsize
            arrays[name] = view[start:end].cast(typecode)
            continue
        file.seek(start)
        values.fromfile(file, count)
        arrays[name] = _to_little_endian(values)
    metadata = dict(header["metadata"])
    metadata["content_sha256"] = digest.hex()
    return arrays, metadata, is_mode_kept


def _select_modes(filename, arrays, metadata, is_mode_kept, in_place):
    """The arrays of the nodes of the kept modes, and of the edges between them.

    `arrays` holds the whole file, and `_check` has checked the lengths.
    `is_mode_kept` says, for each mode of the file, whether the read keeps it.
    `select_edges` computes the arrays whose values change. For the other arrays, it
    gives runs: the ranges of positions of the file that the selection keeps
    (`scgraph/cpp/src/edge_selection.hpp` explains them). With `in_place`, an array
    that keeps one run is a slice of the array of the file, not a copy."""
    node_count = len(arrays["offsets"]) - 1
    try:
        (
            offsets,
            heads,
            shape_offsets,
            node_runs,
            edge_runs,
            shape_point_runs,
        ) = select_edges(
            arrays["offsets"],
            arrays["heads"],
            # Without node_modes, every node is in the first mode
            arrays.get("node_modes", bytes(node_count)),
            is_mode_kept,
            arrays.get("shape_offsets"),
        )
    except ValueError as error:
        raise ValueError(f"{filename}: {error}") from error
    selected = {"offsets": offsets, "heads": heads}
    if shape_offsets is not None:
        selected["shape_offsets"] = shape_offsets
    # Each other array, the runs that it follows, and its values per position
    for name, runs, width in (
        ("weights", edge_runs, 1),
        ("edge_classes", edge_runs, 1),
        ("node_points", node_runs, 2),
        ("node_ids", node_runs, 1),
        ("node_modes", node_runs, 1),
        ("shape_points", shape_point_runs, 2),
    ):
        if name in arrays:
            selected[name] = _take_runs(arrays[name], runs, in_place, width)
    if "node_ids" not in arrays:
        # The id of a node is its position in the file
        positions = chain.from_iterable(starmap(range, node_runs))
        selected["node_ids"] = array("q", positions)
    if "edge_classes" in arrays:
        # `_check` does not read the classes of a mapped file. `translate` deletes
        # the valid classes in one pass in C: a byte that is left is not a class.
        valid = bytes(range(256))[: len(metadata["classes"])]
        if bytes(selected["edge_classes"]).translate(None, valid):
            raise ValueError(f"{filename}: invalid edge classes")
    return selected


def _take_runs(values, runs, in_place, width=1):
    """The values of `values` at the positions of `runs`, in order. A run
    (first, last) holds the positions first to last - 1, and a position holds
    `width` values (2 in an array of points). With `in_place`, one run is a slice of
    `values`. Otherwise, the runs are copied one after the other into a new array.
    """
    if in_place and len(runs) == 1:
        first, last = runs[0]
        return values[width * first : width * last]
    values = memoryview(values)
    taken = array(values.format)
    for first, last in runs:
        taken.frombytes(values[width * first : width * last].cast("B"))
    return taken


class EdgeShapes(Sequence):
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
        self._scale = _get_units_per_degree(self._points)

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
                heads[edge]: self._read_shape(starts[edge], starts[edge + 1])
                for edge in range(
                    self._offsets[origin], self._offsets[origin + 1]
                )
                if starts[edge + 1] != starts[edge]
            }
        )

    def _read_shape(self, first, last):
        # A mapped file's shape offsets are checked here, where they are read
        if not 0 <= first <= last <= len(self._points) // 2:
            raise ValueError("invalid shape offsets")
        flat, scale = self._points[2 * first : 2 * last].tolist(), self._scale
        return [
            [flat[i] / scale, flat[i + 1] / scale]
            for i in range(0, len(flat), 2)
        ]

    def coordinate_path(
        self, path: Sequence[int], coordinates: list[list[float]]
    ) -> list[list[float]]:
        """`coordinates` (one [latitude, longitude] per node of `path`) with the shape of
        each edge of the path between them; in one C loop in the C++ build"""
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
                for edge in range(offsets[origin], offsets[origin + 1]):
                    if heads[edge] == destination:
                        result += self._read_shape(
                            starts[edge], starts[edge + 1]
                        )
                        break
            result.append(coordinates[i + 1])
        return result

    def __eq__(self, other):
        if not isinstance(other, (list, EdgeShapes)):
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

    def take(self, positions: Iterable[int]) -> array:
        """The ids of the nodes at `positions`, as an int64 array."""
        ids = self._ids
        if len(ids) < len(self):  # nodes were added since
            return array("q", (self[i] for i in positions))
        if ids == range(len(ids)):
            return array("q", positions)
        return array("q", (ids[i] for i in positions))

    def array(self, order: Iterable[int] | None = None) -> array | None:
        """The ids (in `order`, `order[new] = old`, if given) as an int64 array, int32
        if every id fits, or None if every node's id is its position."""
        ids, count = self._ids, len(self)
        if order is not None:
            result = self.take(order)
        elif count <= len(ids) and ids == range(len(ids)):
            return None
        else:
            result = array("q", ids[:count])
            result.extend(self[i] for i in range(len(result), count))
        try:  # half the size when every id fits, as those of the built-in networks
            return array("i", result)
        except OverflowError:
            return result


class NodePoints(MutableSequence):
    """
    The `nodes` of a GeoGraph read from a network file: a list of [latitude, longitude],
    read from the file's points instead of one Python list per node, then the nodes
    added since. `nodes[i]` gives a new list each time: replace a node with
    `nodes[i] = [latitude, longitude]` (changing the list it gives changes nothing).
    An edit before the last node first turns every node into a list.
    """

    def __init__(self, node_points):
        # The C++ kernels read the points directly. The Python loops read two views of
        # the points: one holds the latitudes, the other the longitudes. Reading a value
        # from a view is as fast as reading it from an array. It is faster than computing
        # 2 * i and 2 * i + 1 for each node.
        self._points = memoryview(node_points)
        self._latitudes = self._points[0::2]
        self._longitudes = self._points[1::2]
        self._added = []
        self._scale = _get_units_per_degree(node_points)

    def __len__(self):
        return len(self._latitudes) + len(self._added)

    def __getitem__(self, i):
        if type(i) is int and 0 <= i < len(self._latitudes):
            return [
                self._latitudes[i] / self._scale,
                self._longitudes[i] / self._scale,
            ]
        if isinstance(i, slice):
            return [self[j] for j in range(*i.indices(len(self)))]
        j = self._in_added(i, edit=False)
        if j < 0:  # a node of the file, given from the end
            return [
                self._latitudes[j] / self._scale,
                self._longitudes[j] / self._scale,
            ]
        return self._added[j]

    def __setitem__(self, i, value):
        self._added[self._in_added(i)] = value

    def __delitem__(self, i):
        del self._added[self._in_added(i)]

    def insert(self, i: int, value: list[float]) -> None:
        if i < len(self):
            self._own()
        self._added.insert(i - len(self._latitudes), value)

    def take(self, ids: Iterable[int]) -> list[list[float]]:
        """`[nodes[i] for i in ids]` (a route's path), without a method call per node: in one
        C loop in the C++ build when no node was added"""
        if _coordinate_lists is not None and not self._added:
            return _coordinate_lists(
                self._points, ids if type(ids) is list else list(ids)
            )
        latitudes, longitudes = self._latitudes, self._longitudes
        count, scale = len(latitudes), self._scale
        return [
            (
                [latitudes[i] / scale, longitudes[i] / scale]
                if 0 <= i < count
                else self[i]
            )
            for i in ids
        ]

    def __iter__(self):
        scale = self._scale
        for latitude, longitude in zip(self._latitudes, self._longitudes):
            yield [latitude / scale, longitude / scale]
        yield from self._added

    def __eq__(self, other):
        if not isinstance(other, (list, NodePoints)):
            return NotImplemented
        return len(self) == len(other) and all(map(eq, self, other))

    def __repr__(self):
        return repr(list(self))

    def __reduce__(self):
        # Copied and pickled as a list (the file's mapping can't be)
        return list, (list(self),)

    def points(self) -> array | memoryview:
        """The latitude then the longitude of each node, in one array: the file's array
        (int32 in 1e-7 degree or float64 degrees) if no node was added, else a float64
        array."""
        if not self._added:
            return self._points
        scale = self._scale
        result = array("d", (value / scale for value in self._points))
        result.extend(value for node in self._added for value in node[:2])
        return result

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
            scale = self._scale
            self._added[:0] = (
                [latitude / scale, longitude / scale]
                for latitude, longitude in zip(
                    self._latitudes, self._longitudes
                )
            )
            self._points = memoryview(array("d"))
            self._latitudes = self._longitudes = self._points
            self._scale = 1.0


def _check(filename, arrays, metadata, should_check_values=True):
    def require(condition, what):
        if not condition:
            raise ValueError(f"{filename}: {what}")

    required = {"offsets", "heads", "weights", "node_points"}
    require(required <= set(arrays), "missing arrays")
    require(
        ("shape_offsets" in arrays) == ("shape_points" in arrays),
        "missing shape arrays",
    )
    offsets, heads = arrays["offsets"], arrays["heads"]
    n, m = len(offsets) - 1, len(heads)
    require(n >= 0 and offsets[0] == 0 and offsets[-1] == m, "invalid offsets")
    require(len(arrays["weights"]) == m, "one weight per edge expected")
    if should_check_values:
        # The loops over the edges run in C (map, min, max), not in Python
        require(is_sorted(offsets), "invalid offsets")
        require(
            not m or (min(heads) >= 0 and max(heads) < n),
            "edge to a missing node",
        )
    require(len(arrays["node_points"]) == 2 * n, "one point per node expected")
    require(
        len(
            {
                memoryview(arrays[name]).format
                for name in POINT_ARRAYS
                if name in arrays
            }
        )
        == 1,
        "coordinates of two dtypes",
    )
    if "shape_offsets" in arrays:
        shapes = arrays["shape_offsets"]
        require(
            len(shapes) == m + 1
            and shapes[0] == 0
            and shapes[-1] == len(arrays["shape_points"]) // 2,
            "invalid shape offsets",
        )
        # Mapped, each shape's offsets are checked where it is read (EdgeShapes)
        require(
            not should_check_values or is_sorted(shapes),
            "invalid shape offsets",
        )
    for name, what in (("node_ids", "node id"), ("node_modes", "node mode")):
        require(
            name not in arrays or len(arrays[name]) == n,
            f"one {what} per node expected",
        )
    require(
        "edge_classes" not in arrays or len(arrays["edge_classes"]) == m,
        "one edge class per edge expected",
    )
    # Each value of these arrays is a row of a list of the metadata
    for name, what, key in (
        ("node_modes", "node modes", "modes"),
        ("edge_classes", "edge classes", "classes"),
    ):
        if name in arrays:
            rows = metadata.get(key)
            require(isinstance(rows, list), f"{what} without a list of {key}")
            # A mapped read does not check the values: it does not read the arrays
            require(
                not should_check_values
                or max(arrays[name], default=-1) < len(rows),
                f"invalid {what}",
            )


def _is_symmetric(offsets, heads, weights):
    # Return whether every edge has a reverse edge of the same weight.
    #
    # The degree of a node is its number of edges. For an edge u -> v, the function
    # searches the row of v for the reverse edge, but only when v has at most the
    # degree of u. A hub is a node of high degree. With this rule, the function does
    # not read the long row of a hub once for each of its neighbors.
    #
    # An edge to a node of higher degree is counted in `unmatched`. Its reverse edge is
    # found later, from the side of that node, and takes one from the count. A row
    # holds each head once, so the graph is symmetric when the count ends at zero.
    unmatched = 0
    for origin in range(len(offsets) - 1):
        degree = offsets[origin + 1] - offsets[origin]
        for edge in range(offsets[origin], offsets[origin + 1]):
            head = heads[edge]
            start, end = offsets[head], offsets[head + 1]
            if end - start > degree:
                unmatched += 1
                continue
            unmatched -= end - start < degree
            for back in range(start, end):
                if heads[back] == origin:
                    if weights[back] != weights[edge]:
                        return False
                    break
            else:
                return False
    return unmatched == 0


def _count_values(shape):
    count = 1
    for size in shape:
        count *= size
    return count


def _align(position):
    return -(-position // _ALIGN) * _ALIGN


def _to_little_endian(values):
    if sys.byteorder == "big":
        values.byteswap()
    return values
