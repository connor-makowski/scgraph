import json
import logging
import os

from scgraph.utils import _warn_deprecated_parameter, hard_round, haversine
from scgraph.helpers.douglas_peucker import douglas_peucker
from scgraph.helpers.visvalingam import visvalingam
from collections.abc import Callable, Sequence

logger = logging.getLogger(__name__)


def lessThanAbs(  # noqa: N802 (public since 3.6.0)
    threshold: float, a: float
) -> int | float:
    """Bring a longitude within [-threshold, threshold]: longitudes beyond 180 wrap around
    the globe; values in the range, including -threshold and threshold, are unchanged.
    """
    if -threshold <= a <= threshold:
        return a
    return (a + threshold) % (2 * threshold) - threshold


def _latitude(value):
    if not -90 <= value <= 90:
        raise ValueError(f"Latitude {value} is outside [-90, 90]")
    return value


def format_coord_tuple(
    coord: Sequence[float], round_to: int = 3
) -> tuple[float, float]:
    # Rounded again after the wrap, whose floating point noise (-169.15020000000004 for
    # 190.8498) would make two nodes of one point
    return (
        hard_round(round_to, lessThanAbs(180, hard_round(round_to, coord[0]))),
        _latitude(hard_round(round_to, coord[1])),
    )


def format_coord_list(coord: Sequence[float], round_to: int = 3) -> list[float]:
    # Rounded again after the wrap, whose floating point noise (-169.15020000000004 for
    # 190.8498) would make two nodes of one point
    return [
        hard_round(round_to, lessThanAbs(180, hard_round(round_to, coord[0]))),
        _latitude(hard_round(round_to, coord[1])),
    ]


def simplify_geojson(
    filename_in: str | os.PathLike,
    filename_out: str | os.PathLike | None = None,
    precision: int = 4,
    pct_to_keep: float = 100,
    min_points: int = 3,
    silent: bool | None = None,
    algorithm: str | Callable = "visvalingam",
    tolerance: float = 0.0,
) -> list[list[list[float]]]:
    """
    Simplify the GeoJSON features by rounding coordinates and ensuring all geometries are MultiLineStrings.
    Removes empty features or features with only single points after simplification.
    Merges all LineStrings into a single MultiLineString to cut down on data size.
    Removes all features and properties except for the line / multi line coordinates.

    Args:

    - filename_in: Input GeoJSON file path
        - Type: str
        - Note: Must be either a FeatureCollection or GeometryCollection.

    Optional Args:

    - filename_out: Output GeoJSON file path
        - Defaults to None, meaning the output will not be written to a file.
    - precision: Decimal places to round coordinates
    - pct_to_keep: Percentage of the interior line points to keep (0.0 to 100.0)
        - Note: Used when algorithm is 'visvalingam'. See `visvalingam` function for how this is applied.
    - min_points: Minimum number of points to keep in the simplified line
        - Note: Applied across all simplification algorithms.
    - silent: Deprecated and without effect. scgraph reports its messages through `logging`.
    - algorithm: Simplification algorithm to use
        - Options: 'visvalingam' (default), 'douglas_peucker', or a custom callable `(coords, min_points=...)`
    - tolerance: Distance threshold for 'douglas_peucker'
        - Default: 0.0 (removes strictly colinear points)

    Returns:

    - All cleaned coordinates as a single MultiLineString.
        - If `filename_out` is provided, this will be written into a GeoJSON file.
        - Note: Always returns a GeometryCollection with a single MultiLineString containing all cleaned coordinates.
    """
    _warn_deprecated_parameter("silent", silent)
    data = json.load(open(filename_in, "r"))
    if data["type"] == "FeatureCollection":
        features = data["features"]
        geometries = [feature.get("geometry", {}) for feature in features]
    elif data["type"] == "GeometryCollection":
        geometries = data["geometries"]
    else:
        raise ValueError(f"Unsupported GeoJSON type: {data['type']}")

    # Clean the features
    # Round all coordinates to {precision} decimal places
    single_multi_line = []
    idx = 0
    for geometry in geometries:
        geom_type = geometry.get("type")
        # Get all coordinates as multi line strings
        if geom_type == "LineString":
            coordinates = [geometry.get("coordinates", [])]
        elif geom_type == "MultiLineString":
            coordinates = geometry.get("coordinates", [])
        else:
            continue  # Skip non-line geometries

        for line in coordinates:
            idx += 1
            new_line = []
            prev_coord = None
            for coord in line:
                new_coord = format_coord_list(coord, round_to=precision)
                if new_coord != prev_coord:
                    new_line.append(new_coord)
                    prev_coord = new_coord
            if len(new_line) > 1:
                if algorithm == "visvalingam":
                    simplified = visvalingam(
                        new_line,
                        pct_to_keep=pct_to_keep,
                        min_points=min_points,
                    )
                elif algorithm == "douglas_peucker":
                    simplified = douglas_peucker(
                        new_line,
                        tolerance=tolerance,
                        min_points=min_points,
                    )
                elif callable(algorithm):
                    simplified = algorithm(new_line, min_points=min_points)
                else:
                    raise ValueError(
                        f"Unsupported simplification algorithm: {algorithm}. "
                        "Choose 'visvalingam', 'douglas_peucker', or provide a callable."
                    )
                single_multi_line.append(simplified)
    logger.info(
        "Read %d geometries from %s: kept %d of %d lines",
        len(geometries),
        filename_in,
        len(single_multi_line),
        idx,
    )

    if isinstance(filename_out, str):
        with open(filename_out, "w") as f:
            json.dump(
                {
                    "type": "GeometryCollection",
                    "geometries": [
                        {
                            "type": "MultiLineString",
                            "coordinates": single_multi_line,
                        }
                    ],
                },
                f,
            )
        logger.info("Wrote %s", filename_out)
    return single_multi_line


def parse_geojson(
    filename_in: str | os.PathLike,
    precision: int = 4,
    pct_to_keep: float = 100,
    min_points: int = 3,
    silent: bool | None = None,
) -> dict:
    """
    Parse and simplify a GeoJSON file.

    Args:

    - filename_in (str): Input GeoJSON file path.

    Optional Args:

    - precision (int): Decimal places to round coordinates.
    - pct_to_keep (int|float): Percentage of the interior line points to keep.
    - min_points (int): Minimum number of points to keep in the simplified line.
    - silent: Deprecated and without effect. scgraph reports its messages through `logging`.

    Returns:
        list: List of cleaned coordinates as a single MultiLineString.
    """
    _warn_deprecated_parameter("silent", silent)
    single_multi_line = simplify_geojson(
        filename_in=filename_in,
        filename_out=None,
        precision=precision,
        pct_to_keep=pct_to_keep,
        min_points=min_points,
    )
    total_geometries = len(single_multi_line)

    odd_dict = {}
    for line in single_multi_line:
        line = [tuple(coord) for coord in line]
        for i in range(len(line) - 1):
            start = line[i]
            end = line[i + 1]
            if start == end:
                continue
            else:
                start_item = odd_dict.get(start, [])
                start_item.append(end)
                odd_dict[start] = start_item
                end_item = odd_dict.get(end, [])
                end_item.append(start)
                odd_dict[end] = end_item

    nodes = [key for key in odd_dict.keys()]
    node_map = {key: idx for idx, key in enumerate(nodes)}
    graph = []
    for key, value in odd_dict.items():
        graph_sub = {}
        start_node = key
        for end_node in value:
            # Nodes are (longitude, latitude); haversine takes [latitude, longitude]
            graph_sub[node_map[end_node]] = hard_round(
                3,
                haversine(
                    origin=[start_node[1], start_node[0]],
                    destination=[end_node[1], end_node[0]],
                ),
            )
        graph.append(graph_sub)
    nodes = [[i[1], i[0]] for i in nodes]
    logger.info(
        "Built a graph of %d nodes from %d lines", len(nodes), total_geometries
    )

    return {"nodes": nodes, "graph": graph}
