import json

from scgraph.utils import hard_round, print_console, haversine
from scgraph.helpers.visvalingam import visvalingam


def lessThanAbs(threshold, a):
    return abs(a) % threshold * (1 if a > 0 else -1)


def format_coord_tuple(coord, round_to: int = 3):
    return (
        lessThanAbs(180, hard_round(round_to, coord[0])),
        lessThanAbs(90, hard_round(round_to, coord[1])),
    )


def format_coord_list(coord, round_to: int = 3):
    return [
        lessThanAbs(180, hard_round(round_to, coord[0])),
        lessThanAbs(90, hard_round(round_to, coord[1])),
    ]


def simplify_geojson(
    filename_in,
    filename_out: str | None = None,
    precision: int = 4,
    pct_to_keep: int | float = 100,
    min_points=3,
    silent: bool = False,
):
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
        - Note: See `visvalingam` function for how this is applied.
    - min_points: Minimum number of points to keep in the simplified line
        - Note: See `visvalingam` function for how this is applied.
    - silent: Whether to suppress console output
        - Type: bool
        - Default: False
        - Defaults to False, meaning console output will not be suppressed.

    Returns:

    - All cleaned coordinates as a single MultiLineString.
        - If `filename_out` is provided, this will be written into a GeoJSON file.
        - Note: Always returns a GeometryCollection with a single MultiLineString containing all cleaned coordinates.
    """

    print_console(f"Loading {filename_in}...", silent=silent)
    data = json.load(open(filename_in, "r"))
    if data["type"] == "FeatureCollection":
        features = data["features"]
        geometries = [feature.get("geometry", {}) for feature in features]
    elif data["type"] == "GeometryCollection":
        geometries = data["geometries"]
    else:
        raise ValueError(f"Unsupported GeoJSON type: {data['type']}")

    print_console(
        f"Loaded {len(geometries)} geometries from {filename_in}", silent=silent
    )

    # Clean the features
    # Round all coordinates to {precision} decimal places
    print_console(
        "Cleaning geometries and creating a single multi line object...",
        silent=silent,
    )
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
                single_multi_line.append(
                    visvalingam(
                        new_line, pct_to_keep=pct_to_keep, min_points=min_points
                    )
                )
            if idx % 10000 == 0:
                print_console(
                    f"Simplified {idx} line geometries", end="\r", silent=silent
                )
    print_console(f"Simplified {idx} of {idx} line geometries", silent=silent)
    print_console(f"Kept geometries: {len(single_multi_line)}", silent=silent)

    if isinstance(filename_out, str):
        print_console(f"Writing {filename_out}...", silent=silent)
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
        print_console(f"Finished writing {filename_out}", silent=silent)
    return single_multi_line


def parse_geojson(
    filename_in,
    filename_out: str | None = None,
    precision: int = 4,
    pct_to_keep: int | float = 100,
    min_points=3,
    silent: bool = False,
):
    """
    Parse and simplify a GeoJSON file.

    Args:

    - filename_in (str): Input GeoJSON file path.
    - filename_out (str|None): Output GeoJSON file path. If None, no output file is created.
    - precision (int): Decimal places to round coordinates.
    - pct_to_keep (int|float): Percentage of the interior line points to keep.
    - min_points (int): Minimum number of points to keep in the simplified line.
    - silent (bool): Whether to suppress console output.

    Returns:
        list: List of cleaned coordinates as a single MultiLineString.
    """
    single_multi_line = simplify_geojson(
        filename_in, precision, pct_to_keep, min_points, silent
    )
    total_geometries = len(single_multi_line)

    odd_dict = {}
    for idx, line in enumerate(single_multi_line):
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
        if idx % 10000 == 0:
            print_console(
                f"Processed {idx} of {total_geometries} geometries",
                end="\r",
                silent=silent,
            )
    print_console(
        f"Processed {total_geometries} of {total_geometries} geometries",
        silent=silent,
    )

    nodes = [key for key in odd_dict.keys()]
    node_map = {key: idx for idx, key in enumerate(nodes)}
    graph = []
    for idx, (key, value) in enumerate(odd_dict.items()):
        graph_sub = {}
        start_node = key
        for end_node in value:
            graph_sub[node_map[end_node]] = hard_round(
                3, haversine(origin=start_node, destination=end_node)
            )
        graph.append(graph_sub)
        if idx % 1000 == 0:
            print_console(
                f"Processed {idx} of {len(odd_dict)} nodes",
                end="\r",
                silent=silent,
            )
    nodes = [[i[1], i[0]] for i in nodes]
    print_console(
        f"Processed {len(odd_dict)} of {len(odd_dict)} nodes", silent=silent
    )

    return {"nodes": nodes, "graph": graph}
