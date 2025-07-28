import json

from scgraph.utils import hard_round, print_console
from scgraph.helpers.visvalingam import visvalingam

def lessThanAbs(threshold, a):
    return abs(a)%threshold * (1 if a > 0 else -1)

def format_coord_tuple(coord, round_to:int=3):
    return (lessThanAbs(180,hard_round(round_to, coord[0])), lessThanAbs(90,hard_round(round_to, coord[1])))

def format_coord_list(coord, round_to:int=3):
    return [lessThanAbs(180,hard_round(round_to, coord[0])), lessThanAbs(90,hard_round(round_to, coord[1]))]

def simplify_geojson(filename_in, filename_out:str|None=None, precision:int=4, pct_to_keep:int|float=100, min_points=3, silent:bool=False):
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
    if data['type'] == 'FeatureCollection':
        features = data['features']
        geometries = [feature.get('geometry', {}) for feature in features]
    elif data['type'] == 'GeometryCollection':
        geometries = data['geometries']
    else:
        raise ValueError(f"Unsupported GeoJSON type: {data['type']}")

    print_console(f"Loaded {len(geometries)} geometries from {filename_in}", silent=silent)


    # Clean the features
    # Round all coordinates to {precision} decimal places
    print_console("Cleaning geometries and creating a single multi line object...", silent=silent)
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
            continue # Skip non-line geometries

        for line in coordinates:
            idx += 1
            new_line = []
            prev_coord = None
            for coord in line:
                new_coord = format_coord_list(coord, round_to=precision)
                if new_coord != prev_coord:
                    new_line.append(new_coord)
                    prev_coord = new_coord
            if len(new_line)>1:
                single_multi_line.append(visvalingam(new_line, pct_to_keep=pct_to_keep, min_points=min_points))
            if idx % 10000 == 0:
                print_console(f"Cleaned {idx} line geometries", end='\r', silent=silent)
    print_console(f"Cleaned {idx} of {idx} line geometries", silent=silent)
    print_console(f"Kept geometries: {len(single_multi_line)}", silent=silent)

    if isinstance(filename_out, str):
        print_console(f"Writing {filename_out}...", silent=silent)
        with open(filename_out, 'w') as f:
            json.dump({
                'type': 'GeometryCollection',
                'geometries': [{
                    'type': 'MultiLineString',
                    'coordinates': single_multi_line,
                }]
            }, f)
        print_console(f"Finished writing {filename_out}", silent=silent)
    return single_multi_line