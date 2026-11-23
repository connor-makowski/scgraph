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
search visits them. `metric_length` holds the length of each edge at the same
positions.

A metric is one weight for every edge, under a name. The header lists the metrics of
the file in `metadata["metrics"]`, and `length` is the first one. The file holds one
array `metric_<name>` for each metric. Example: a file with the metrics `length` and
`travel_time` holds `metric_length` and `metric_travel_time`.

The public functions are `read`, `write`, `get_scgraph_info` and `check_content`.
"""

import hashlib
import json
import math
import mmap
import os
import sys
from array import array
from collections.abc import Sequence
from itertools import chain, starmap

from scgraph import files
from scgraph.helpers.hilbert import NODE_ORDER
from scgraph._internal import is_sorted

try:
    from scgraph.cpp import select_edges
except ImportError:
    from scgraph.helpers.edge_selection import select_edges

__all__ = ["check_content", "get_scgraph_info", "read", "write"]

MAGIC = b"SCGRAPH1"
FORMAT_VERSION = 1
# dtype -> array typecode
DTYPES = {"int32": "i", "int64": "q", "float64": "d", "uint8": "B"}
# array name -> the dtypes it may have; shape_* hold the edge shapes, if any.
# source_node_ids (optional): the id of each node in its source.
# node_mode_ids (optional): for each node, the position of its node mode in
# metadata["node_modes"].
# edge_class_ids (optional): for each edge, the position of its class in
# metadata["classes"], or NO_CLASS_ID for an edge without a class.
# metric_length: the length of each edge. The array `metric_<name>` of another metric
# is not listed here: it has the dtype of metric_length (see `_get_dtypes`).
# node_points and shape_points are arrays of points: the latitude of a point, then its
# longitude. Both arrays have the same dtype: float64 degrees, or int32 units of 1e-7
# degree (see `encode_coordinates`).
ARRAYS = {
    "offsets": ("int32",),
    "heads": ("int32",),
    "metric_length": ("float64",),
    "node_points": ("int32", "float64"),
    "shape_offsets": ("int32",),
    "shape_points": ("int32", "float64"),
    "source_node_ids": ("int32", "int64"),
    "node_mode_ids": ("uint8",),
    "edge_class_ids": ("uint8",),
}
POINT_ARRAYS = ("node_points", "shape_points")
# The value of `edge_class_ids` for an edge without a class. The id of a class is
# below it: a network holds 255 classes at most.
NO_CLASS_ID = 255
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
        if get_units_per_degree(arrays["node_points"]) != 1
        else "float64"
    )


def get_units_per_degree(values):
    # Units of a coordinate array per degree: 1e7 for int32 (OSM's), 1 for float64
    return 1e7 if memoryview(values).format == "i" else 1.0


# Header keys that scgraph writes or computes itself, which build metadata cannot set
RESERVED_METADATA_KEYS = frozenset(
    {
        "crs",
        "metrics",
        "node_modes",
        "classes",
        "default_metric",
        "symmetric",
        "node_order",
        "content_sha256",
        "format_version",
        "nodes",
        "edges",
        "coordinate_dtype",
        "shapes",
        "source_node_ids",
        "attribution",
        "data_up_to",
    }
)


def build_header_metadata(
    build_metadata: dict,
    *,
    node_modes: list[dict],
    metrics: list[dict] | None = None,
    classes: list[dict] | None = None,
    default_metric: str = "length",
) -> dict:
    """Return the metadata that `write` takes, for a network whose nodes are in the
    order of a network file: by node mode, then along a Hilbert curve
    (`helpers.hilbert`).

    Args:
        build_metadata: What built the network: the pipeline, the sources and the
            software (docstring of `scgraph.pipelines`).
        node_modes: The rows of the node modes: one dict for each node mode, with
            its `name` and, if a source gave the node ids of the node mode, the name
            of that `source`.
        metrics: The info of each metric of the network, `length` first: the `name`
            of the metric, its `unit` and its `description`. The info of a metric
            other than `length` also has `off_graph_weight_per_km`: the weight of
            1 km of an off-graph leg, the straight line between a query point and
            its node. The default, None, is the info of lengths in km.
        classes: One row for each class, for a network with `edge_class_ids`. A row
            gives the `name` of the class and the `edge_mode` of its edges.
        default_metric: The name of the metric that a query without `metric`
            minimises. 'length' writes no such key.

    Returns:
        The keys that scgraph sets itself (`crs`, `metrics`, `node_modes`, `classes`,
        `default_metric`, `node_order`), then the keys of `build_metadata`.

    Raises:
        ValueError: `build_metadata` sets a key that scgraph writes itself, or a node
            mode names a source that is not in the `sources` of `build_metadata`.
    """
    if RESERVED_METADATA_KEYS & set(build_metadata):
        raise ValueError(
            f"metadata may not set {sorted(RESERVED_METADATA_KEYS & set(build_metadata))}"
        )
    # A node mode cites the source of its node ids by name
    names = {source.get("name") for source in build_metadata.get("sources", [])}
    for mode in node_modes:
        if "source" in mode and mode["source"] not in names:
            raise ValueError(
                f"Node mode {mode} names no source: pass metadata with a source of "
                f"that name in its 'sources'"
            )
    if metrics is None:
        metrics = [
            {
                "name": "length",
                "unit": "km",
                "description": "Length of each edge along its shape.",
            }
        ]
    return {
        "crs": "EPSG:4326",
        "metrics": metrics,
        **(
            {"node_modes": node_modes} if node_modes != [{"name": None}] else {}
        ),
        **({"classes": classes} if classes is not None else {}),
        **(
            {"default_metric": default_metric}
            if default_metric != "length"
            else {}
        ),
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
        arrays: The arrays of the network, by name (`offsets`, `heads`,
            `metric_length`, `node_points`, ...). `ARRAYS` gives the names and the
            dtypes that a file may hold. The file may also hold one array
            `metric_<name>` for each other metric.
        metadata: The metadata of the network (metrics, node modes, sources, ...), as
            `build_header_metadata` returns it. It must be serializable as JSON.

    Returns:
        The `content_sha256` of the file: the SHA-256 digest of its content, in
        hexadecimal.

    Raises:
        TypeError: The values of an array do not have a dtype that the array may have.
        PermissionError: On Windows, a process has mapped the file at `filename`, so
            the file cannot be replaced.
    """
    symmetric = _is_symmetric(
        arrays["offsets"], arrays["heads"], arrays["metric_length"]
    )

    header = {
        "format_version": FORMAT_VERSION,
        "arrays": {},
        "metadata": {**metadata, "symmetric": symmetric},
    }
    position = 0
    for name, values in arrays.items():
        size = memoryview(values).itemsize
        dtypes = _get_dtypes(name)
        dtype = next(
            (d for d in dtypes if array(DTYPES[d]).itemsize == size), None
        )
        if dtype is None:
            raise TypeError(
                f"Array '{name}' must hold {' or '.join(dtypes)} values"
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
    try:
        with files.write_atomically(filename, "saving") as temporary:
            with open(temporary, "xb") as file:
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
    except PermissionError as error:
        if os.name != "nt":
            raise
        # Windows does not replace a file that a process has mapped
        raise PermissionError(
            f"{filename} is open in a graph (its file is mapped): save to another "
            "name, or release every graph read from it first"
        ) from error
    return content.hexdigest()


def read(
    filename: str | os.PathLike,
    mapped: bool = False,
    node_modes: str | list[str] | None = None,
) -> tuple[dict[str, array | memoryview], dict]:
    """Read the arrays and the metadata of a network from a `.scgraph` file.

    Args:
        filename: The path of the `.scgraph` file to read.
        mapped: If True, on a little-endian computer, the arrays are views of the
            file mapped into memory, not copies. The default is False.
        node_modes: The names of the node modes to read. The arrays then hold only the
            nodes of these node modes and the edges between them, in the order of the
            file. With `mapped`, an array is a view of the file when its values are
            consecutive in the file, and a new array otherwise. The default, None, reads
            every node mode.

    Returns:
        `(arrays, metadata)`. `arrays` holds the arrays of the network by name
        (`offsets`, `heads`, `metric_length`, ...), with the array `metric_<name>`
        of each other metric. `metadata` holds the metadata of the header, and the
        `content_sha256` of the file.

    Raises:
        ValueError: The header or the layout of the arrays is not valid. Or an
            earlier development version of scgraph wrote the file. `read` does not
            check the digest (see `check_content`).
        FileNotFoundError: The file does not exist.
    """
    mapped = mapped and sys.byteorder == "little"
    try:
        with open(filename, "rb") as file:
            arrays, metadata, is_node_mode_kept = _read(
                filename, file, mapped, node_modes
            )
        # A selection checks the values of the edges itself, where it reads them
        _check(
            filename,
            arrays,
            metadata,
            should_check_values=not mapped and is_node_mode_kept is None,
        )
    except ValueError:
        raise
    except (AttributeError, KeyError, OverflowError, TypeError) as error:
        raise ValueError(f"{filename}: invalid header ({error!r})") from error
    if is_node_mode_kept is not None:
        arrays = _select_modes(
            filename, arrays, metadata, is_node_mode_kept, in_place=mapped
        )
    return arrays, metadata


def get_scgraph_info(filename: str | os.PathLike) -> dict:
    """Return what a `.scgraph` file holds, without loading its arrays.

    Args:
        filename: The path of the `.scgraph` file.

    Returns:
        The keys of the metadata of the file, then `content_sha256`,
        `format_version`, `nodes`, `edges`, `coordinate_dtype`, `shapes` and
        `source_node_ids`. `nodes` and `edges` are counts. `shapes` and
        `source_node_ids` are True when the file holds these arrays.

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
        "source_node_ids": "source_node_ids" in arrays,
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


def _read(filename, file, mapped, node_modes):
    """The arrays of the whole file and its metadata. With `node_modes`, the third value
    holds one boolean for each node mode of the file: True when `node_modes` names it.
    This value is None when the read keeps every node mode."""
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
    # A file of an earlier development version has `units` and no `metrics`, or a
    # name that this version no longer reads. Without this message, the error would
    # only name the missing array or key.
    metadata = header["metadata"]
    if (
        ("units" in metadata and "metrics" not in metadata)
        or {"node_ids", "node_modes", "edge_classes", "weights_length"}
        & set(header["arrays"])
        or any(
            isinstance(row, dict)
            and ("mode" in row or row.get("name", "") is None)
            for row in metadata.get("classes", ())
        )
        or any("off_graph_per_km" in row for row in metadata.get("metrics", ()))
    ):
        raise ValueError(
            f"{filename} has the format of an earlier development version of "
            "scgraph: build or download the network again"
        )
    is_node_mode_kept = None
    if node_modes is not None:
        node_modes = (
            (node_modes,) if isinstance(node_modes, str) else node_modes
        )
        node_mode_names = [
            mode["name"]
            for mode in header["metadata"].get("node_modes") or [{"name": None}]
        ]
        unknown = [mode for mode in node_modes if mode not in node_mode_names]
        if unknown:
            raise ValueError(f"{filename}: unknown node modes {unknown}")
        if not all(name in node_modes for name in node_mode_names):
            is_node_mode_kept = [name in node_modes for name in node_mode_names]
    # A selection also reads the file in place, and copies only what it keeps
    view = None
    if mapped or (is_node_mode_kept is not None and sys.byteorder == "little"):
        view = memoryview(mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_READ))
    arrays = {}
    for name, entry in header["arrays"].items():
        dtypes = _get_dtypes(name)
        if dtypes is None:
            continue  # added by a later version, not needed to read the graph
        if entry["dtype"] not in dtypes:
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
    return arrays, metadata, is_node_mode_kept


def _select_modes(filename, arrays, metadata, is_node_mode_kept, in_place):
    """The arrays of the nodes of the kept node modes, and of the edges between them.

    `arrays` holds the whole file, and `_check` has checked the lengths.
    `is_node_mode_kept` is True for each node mode of the file that the read keeps.
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
            # Without node_mode_ids, every node is in the first node mode
            arrays.get("node_mode_ids", bytes(node_count)),
            is_node_mode_kept,
            arrays.get("shape_offsets"),
        )
    except ValueError as error:
        raise ValueError(f"{filename}: {error}") from error
    selected = {"offsets": offsets, "heads": heads}
    if shape_offsets is not None:
        selected["shape_offsets"] = shape_offsets
    # Each other array, the runs that it follows, and its values per position
    for name, runs, width in (
        *((name, edge_runs, 1) for name in arrays if _is_weights_array(name)),
        ("edge_class_ids", edge_runs, 1),
        ("node_points", node_runs, 2),
        ("source_node_ids", node_runs, 1),
        ("node_mode_ids", node_runs, 1),
        ("shape_points", shape_point_runs, 2),
    ):
        if name in arrays:
            selected[name] = _take_runs(arrays[name], runs, in_place, width)
    if "source_node_ids" not in arrays:
        # The id of a node is its position in the file
        positions = chain.from_iterable(starmap(range, node_runs))
        selected["source_node_ids"] = array("q", positions)
    if "edge_class_ids" in arrays:
        # `_check` does not read the class ids of a mapped file. `translate`
        # deletes the valid ids in one pass in C: a byte that is left is no id of a
        # class and not NO_CLASS_ID.
        valid = bytes([*range(len(metadata["classes"])), NO_CLASS_ID])
        if bytes(selected["edge_class_ids"]).translate(None, valid):
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


def _check(filename, arrays, metadata, should_check_values=True):
    def require(condition, what):
        if not condition:
            raise ValueError(f"{filename}: {what}")

    required = {"offsets", "heads", "metric_length", "node_points"}
    require(required <= set(arrays), "missing arrays")
    require(
        ("shape_offsets" in arrays) == ("shape_points" in arrays),
        "missing shape arrays",
    )
    offsets, heads = arrays["offsets"], arrays["heads"]
    n, m = len(offsets) - 1, len(heads)
    require(n >= 0 and offsets[0] == 0 and offsets[-1] == m, "invalid offsets")
    # Each metric has its info in the header and one array of weights
    metrics = metadata["metrics"]
    require(
        metrics and metrics[0]["name"] == "length" and "unit" in metrics[0],
        "the first metric must be length, with its unit",
    )
    weights_array_names = sorted(filter(_is_weights_array, arrays))
    require(
        sorted(f"metric_{row['name']}" for row in metrics)
        == weights_array_names,
        "one array of weights per metric expected",
    )
    require(
        all(len(arrays[name]) == m for name in weights_array_names),
        "one weight per edge expected",
    )
    require(
        all("off_graph_weight_per_km" in row for row in metrics[1:]),
        "a metric other than length must give off_graph_weight_per_km",
    )
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
        # Mapped, each shape's offsets are checked where it is read (`scgraph.columns.EdgeShapes`)
        require(
            not should_check_values or is_sorted(shapes),
            "invalid shape offsets",
        )
    for name, what in (
        ("source_node_ids", "node id"),
        ("node_mode_ids", "node mode"),
    ):
        require(
            name not in arrays or len(arrays[name]) == n,
            f"one {what} per node expected",
        )
    require(
        "edge_class_ids" not in arrays or len(arrays["edge_class_ids"]) == m,
        "one edge class per edge expected",
    )
    # Each value of these arrays is the position of a row in a list of the
    # metadata. A class id may also be NO_CLASS_ID.
    for name, what, key, other_valid_ids in (
        ("node_mode_ids", "node modes", "node_modes", set()),
        ("edge_class_ids", "edge classes", "classes", {NO_CLASS_ID}),
    ):
        if name in arrays:
            rows = metadata.get(key)
            require(isinstance(rows, list), f"{what} without a list of {key}")
            # A mapped read does not check the values: it does not read the arrays
            require(
                not should_check_values
                or max(set(arrays[name]) - other_valid_ids, default=-1)
                < len(rows),
                f"invalid {what}",
            )
    require(
        "edge_class_ids" not in arrays
        or all(
            isinstance(row, dict)
            and isinstance(row.get("name"), str)
            and "edge_mode" in row
            for row in metadata["classes"]
        ),
        "each class must be a row with a name and an edge mode",
    )
    require(
        "edge_class_ids" not in arrays
        or len(metadata["classes"]) <= NO_CLASS_ID,
        f"a network file holds {NO_CLASS_ID} classes at most",
    )
    require(
        metadata.get("default_metric", "length")
        in [row["name"] for row in metrics],
        "default_metric names a metric that the file does not have",
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


def _is_weights_array(name):
    # Whether `name` is the array of the weights of a metric
    return name.startswith("metric_")


def _get_dtypes(name):
    # The dtypes that the array `name` may have. None for an array that this version
    # of scgraph does not know. The weights of every metric have the same dtype.
    return ARRAYS.get("metric_length" if _is_weights_array(name) else name)


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
