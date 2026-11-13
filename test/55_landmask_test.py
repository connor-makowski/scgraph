import json
from array import array
from types import SimpleNamespace

import pytest
from helpers import great_circle_km

from scgraph import Graph
from scgraph.pipelines.steps.stage2_intermodal import landmask

# These tests call the land mask, a step of the builds that joins ports to
# water. No public call runs it alone: a build needs the download of its maps.


def _square(west, south, east, north):
    return [[west, south], [east, south], [east, north], [west, north], [west, south]]  # fmt: skip


def _write_geojson(path, geometries):
    """Write `geometries`, a list of (type, coordinates), as the features of a
    GeoJSON file. Return the path as a string."""
    features = [
        {"type": "Feature", "geometry": {"type": kind, "coordinates": points}}
        for kind, points in geometries
    ]
    path.write_text(
        json.dumps({"type": "FeatureCollection", "features": features})
    )
    return str(path)


def _find_shortest_route_over_water(mask, port, target):
    """The oracle of the water paths: Dijkstra on a graph of the water cells
    and of the cell of `target`. Two cells that touch, by a side or by a
    corner, are joined by the great-circle distance between their centres. The
    route starts at the water cell nearest to `port`.

    It gives `first_cell`, `leg_km` (from the port to the centre of that
    cell), `target_cell` and `km` (the leg plus the route between the cells).
    """
    target_cell = mask.get_cell(*target)
    width, cells = mask.width, range(mask.height * mask.width)
    water = {
        cell
        for cell in cells
        if not mask.is_on_land(*mask.get_cell_centre(cell))
    } | {target_cell}
    graph = [{} for _ in cells]
    for cell in water:
        row, column = divmod(cell, width)
        # The cell to the east and the three cells of the row to the north:
        # the links to the other four neighbours are made from those cells.
        for r, c in (
            (row, column + 1),
            (row + 1, column - 1),
            (row + 1, column),
            (row + 1, column + 1),
        ):
            near = r * width + c % width
            if near in water and (mask.wrap or 0 <= c < width):
                km = great_circle_km(
                    mask.get_cell_centre(cell), mask.get_cell_centre(near)
                )
                graph[cell][near] = graph[near][cell] = km
    leg_km, first_cell = min(
        (great_circle_km(port, mask.get_cell_centre(cell)), cell)
        for cell in water
    )
    between_cells_km = Graph(graph).dijkstra(first_cell, target_cell)["length"]
    return SimpleNamespace(
        first_cell=first_cell,
        leg_km=leg_km,
        target_cell=target_cell,
        km=leg_km + between_cells_km,
    )


# The coast map covers longitudes 0 to 0.2 and latitudes 56 to 56.2, in cells
# of 0.005 degree. The mainland lies south of latitude 56.08 and has two
# holes: a lake and a lagoon. The lake is drawn again in the file of lakes, as
# the Great Lakes are in Natural Earth. A river runs north from the lake to
# the sea. An island lies in the sea, north of the mouth of the river.
LAKE = _square(0.03, 56.02, 0.07, 56.05)
LAGOON = _square(0.1, 56.02, 0.15, 56.05)
MAINLAND = _square(0, 56, 0.2, 56.08)
ISLAND = _square(0.06, 56.11, 0.16, 56.15)
RIVER = [[0.05, 56.05], [0.05, 56.09]]
# The port is on the mainland, 1 km south of the lake. The target is a cell of
# the north shore of the island: a water path goes through the lake, down the
# river and around the island.
PORT = [56.011, 0.0505]
TARGET_ON_THE_ISLAND = [56.148, 0.12]


@pytest.fixture(scope="module")
def coast(tmp_path_factory):
    folder = tmp_path_factory.mktemp("coast")
    return landmask.LandMask.from_natural_earth(
        _write_geojson(
            folder / "land.geojson",
            [("MultiPolygon", [[MAINLAND, LAKE, LAGOON], [ISLAND]])],
        ),
        _write_geojson(folder / "lakes.geojson", [("Polygon", [LAKE])]),
        _write_geojson(folder / "rivers.geojson", [("LineString", RIVER)]),
        cells_per_degree=200,
        bbox=(56, 0, 56.2, 0.2),
    )


@pytest.fixture(scope="module")
def route_around_the_island(coast):
    return _find_shortest_route_over_water(coast, PORT, TARGET_ON_THE_ISLAND)


@pytest.mark.parametrize(
    "point, is_land",
    [
        pytest.param([56.04, 0.05], False, id="a lake is water"),
        # The lagoon is a hole of the mainland. It is not in the file of lakes.
        pytest.param([56.04, 0.12], False, id="a hole in the land is water"),
        pytest.param([56.06, 0.05], False, id="a river is water"),
        pytest.param([56.13, 0.1], True, id="an island is land"),
        # The lake starts at longitude 0.03. This point is the centre of the
        # cell that touches the lake on its west side.
        pytest.param(
            [56.035, 0.0275],
            True,
            id="a cell is land when its centre is on land",
        ),
    ],
)
def test_the_map_tells_land_from_water(coast, point, is_land):
    assert coast.is_on_land(*point) == is_land


def test_a_water_path_is_the_shortest_route_over_water_from_the_port(
    coast, route_around_the_island
):
    targets = array("q", [route_around_the_island.target_cell])

    km, points = coast.find_water_path(
        PORT, targets, max_km=100, start_on_land_km=6
    )

    assert km == pytest.approx(route_around_the_island.km, rel=1e-6)
    # The points go from the water cell nearest to the port to the target
    assert points[0] == coast.get_cell_centre(
        route_around_the_island.first_cell
    )
    assert points[-1] == coast.get_cell_centre(
        route_around_the_island.target_cell
    )
    # The length along the points, plus the leg from the port to the first
    # point, is the length of the path. The centres of the cells are rounded
    # differently in the two sums: the lengths agree to 1 in 10,000.
    km_along_the_points = sum(
        great_circle_km(a, b) for a, b in zip(points, points[1:])
    )
    assert route_around_the_island.leg_km + km_along_the_points == (
        pytest.approx(km, rel=1e-4)
    )


def test_no_water_path_is_found_beyond_the_maximum_length(
    coast, route_around_the_island
):
    targets = array("q", [route_around_the_island.target_cell])
    just_too_short_km = route_around_the_island.km * 0.999

    path = coast.find_water_path(
        PORT, targets, max_km=just_too_short_km, start_on_land_km=6
    )

    assert path is None


def test_no_water_path_is_found_when_the_port_is_too_far_from_water(
    coast, route_around_the_island
):
    targets = array("q", [route_around_the_island.target_cell])
    just_too_near_km = route_around_the_island.leg_km * 0.99

    path = coast.find_water_path(
        PORT, targets, max_km=100, start_on_land_km=just_too_near_km
    )

    assert path is None


def test_a_search_finds_no_path_when_it_may_hold_one_cell_less_than_its_path(
    coast, route_around_the_island
):
    # This test calls the kernel of `find_water_path`. A search stops when it
    # holds `max_cells` cells, the last argument of the kernel. This limit
    # bounds the memory of a search.
    targets = array("q", [route_around_the_island.target_cell])
    _, points = coast.find_water_path(
        PORT, targets, max_km=100, start_on_land_km=6
    )
    one_cell_less_than_the_path = len(points) - 1

    found = landmask.find_water_path_cells(
        coast.bits,
        coast.width,
        coast.height,
        coast.wrap,
        route_around_the_island.first_cell,
        targets,
        100,
        coast.east_km,
        coast.diagonal_km,
        coast.north_km,
        one_cell_less_than_the_path,
    )

    assert found is None


# The globe map covers every longitude, from the equator to latitude 10, in
# cells of 1 degree. All is land but the 10 degrees on each side of the
# antimeridian.
LAND_AWAY_FROM_THE_ANTIMERIDIAN = _square(-170, 0, 170, 10)
# The port is west of the antimeridian and the target is east of it.
PORT_AT_172_EAST = [5.2, 172.2]
TARGET_AT_172_WEST = [5.5, -172.5]


@pytest.fixture(scope="module")
def globe(tmp_path_factory):
    folder = tmp_path_factory.mktemp("globe")
    return landmask.LandMask.from_natural_earth(
        _write_geojson(
            folder / "land.geojson",
            [("Polygon", [LAND_AWAY_FROM_THE_ANTIMERIDIAN])],
        ),
        _write_geojson(folder / "lakes.geojson", []),
        _write_geojson(folder / "rivers.geojson", []),
        cells_per_degree=1,
        bbox=(0, -180, 10, 180),
    )


def test_a_map_of_every_longitude_has_land_and_water_where_they_are_drawn(
    globe,
):
    assert globe.is_on_land(5, 0)
    assert not globe.is_on_land(5, 179)


def test_a_water_path_crosses_the_antimeridian(globe):
    # The oracle joins the last column of cells to the first one, as the map
    # covers every longitude. The route then takes 15 steps eastwards. Around the
    # globe the other way, it would cross land.
    route = _find_shortest_route_over_water(
        globe, PORT_AT_172_EAST, TARGET_AT_172_WEST
    )
    targets = array("q", [route.target_cell])

    km, points = globe.find_water_path(
        PORT_AT_172_EAST, targets, max_km=5000, start_on_land_km=100
    )

    assert km == pytest.approx(route.km, rel=1e-6)
    assert points[0] == globe.get_cell_centre(route.first_cell)
    assert points[-1] == globe.get_cell_centre(route.target_cell)
