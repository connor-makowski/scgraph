import json
from array import array

import pytest
from helpers import great_circle_km

from scgraph import Graph
from scgraph.pipelines.steps.stage2_intermodal import landmask

KERNELS = [landmask.python.find_water_path_cells]
try:
    from scgraph.cpp import find_water_path_cells

    KERNELS.append(find_water_path_cells)
except ImportError:
    pass


def _square(west, south, east, north):
    return [[west, south], [east, south], [east, north], [west, north], [west, south]]  # fmt: skip


def _geojson(path, type, coordinates):
    geometry = {"type": type, "coordinates": coordinates}
    features = [{"type": "Feature", "geometry": geometry}] if type else []
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}))  # fmt: skip
    return str(path)


_LAKE = _square(0.03, 56.02, 0.07, 56.05)
CASES = {
    # 0.005-degree cells over (0, 56)-(0.2, 56.2) (longitude, latitude): a mainland to the
    # south with two holes, a lagoon and a lake drawn again in the lakes (as the Great
    # Lakes), a river from the lake to the sea, and an island between the river's mouth
    # and the target, a cell of the island's shore. Probes: lake, lagoon, river, island,
    # and the cell west of the lake (its centre on land)
    "island": dict(
        land=(
            "MultiPolygon",
            [
                [
                    _square(0, 56, 0.2, 56.08),
                    _LAKE,
                    _square(0.1, 56.02, 0.15, 56.05),
                ],
                [_square(0.06, 56.11, 0.16, 56.15)],
            ],
        ),
        lakes=("Polygon", [_LAKE]),
        rivers=("LineString", [[0.05, 56.05], [0.05, 56.09]]),
        cells_per_degree=200,
        bbox=(56, 0, 56.2, 0.2),
        port=[56.011, 0.0505],
        target=[56.148, 0.12],
        start_on_land_km=6,
        max_km=100,
        probes={
            (56.04, 0.05): False,
            (56.04, 0.12): False,
            (56.06, 0.05): False,
            (56.13, 0.1): True,
            (56.035, 0.0275): True,
        },
    ),
    # 1-degree cells around the globe, land everywhere but within 10 degrees of the
    # antimeridian: the path crosses it
    "antimeridian": dict(
        land=("Polygon", [_square(-170, 0, 170, 10)]),
        lakes=(None, None),
        rivers=(None, None),
        cells_per_degree=1,
        bbox=(0, -180, 10, 180),
        port=[5.2, 172.2],
        target=[5.5, -172.5],
        start_on_land_km=100,
        max_km=5000,
        probes={(5, 0): True, (5, 179): False},
    ),
}


@pytest.mark.parametrize("kernel", KERNELS)
@pytest.mark.parametrize("case", CASES)
def test_water_path_is_the_shortest_over_water_from_a_port_on_land(
    tmp_path, monkeypatch, kernel, case
):
    monkeypatch.setattr(landmask, "find_water_path_cells", kernel)
    c = CASES[case]
    mask = landmask.LandMask.from_natural_earth(
        *(_geojson(tmp_path / f, *c[f]) for f in ("land", "lakes", "rivers")),
        cells_per_degree=c["cells_per_degree"],
        bbox=c["bbox"],
    )
    assert {p: mask.is_on_land(*p) for p in c["probes"]} == c["probes"]
    port, target = c["port"], mask.get_cell(*c["target"])
    targets = array("q", [target])

    # Oracle: Dijkstra over the water cells (and the target), with great-circle steps,
    # from the water cell nearest to the port
    width, cells = mask.width, range(mask.height * mask.width)
    water = {
        i for i in cells if not mask.is_on_land(*mask.get_cell_centre(i))
    } | {target}
    graph = [{} for _ in cells]
    for i in water:
        row, column = divmod(i, width)
        for r, j in (
            (row, column + 1),
            *((row + 1, column + d) for d in (-1, 0, 1)),
        ):
            near = r * width + j % width
            if near in water and (mask.wrap or 0 <= j < width):
                km = great_circle_km(
                    mask.get_cell_centre(i), mask.get_cell_centre(near)
                )
                graph[i][near] = graph[near][i] = km
    leg, first = min(
        (great_circle_km(port, mask.get_cell_centre(i)), i) for i in water
    )
    expected = leg + Graph(graph).dijkstra(first, target)["length"]

    km, points = mask.find_water_path(
        port, targets, c["max_km"], c["start_on_land_km"]
    )
    assert km == pytest.approx(expected, rel=1e-6)
    assert points[0] == mask.get_cell_centre(first) and points[
        -1
    ] == mask.get_cell_centre(target)
    # Drawn along the path (around the island)
    drawn = sum(great_circle_km(a, b) for a, b in zip(points, points[1:]))
    assert leg + drawn == pytest.approx(km, rel=1e-4)
    assert (
        mask.find_water_path(port, targets, km * 0.999, c["start_on_land_km"])
        is None
    )
    assert mask.find_water_path(port, targets, c["max_km"], leg * 0.99) is None
    # A search may not hold more cells than allowed: fewer than its path's, none
    monkeypatch.setattr(landmask, "MAX_CELLS", len(points) - 1)
    near = c["start_on_land_km"]
    assert mask.find_water_path(port, targets, c["max_km"], near) is None
