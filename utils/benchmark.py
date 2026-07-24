#!/usr/bin/env python3
"""
Benchmark runner for scgraph. Outputs a JSON file with nested ms timings.

Usage:
    uv run utils/benchmark.py
    uv run utils/benchmark.py --output path/to/results.json
"""
import argparse
import json
import random
import time

from scgraph import GeoGraph
# Make sure this is imported from scgrpah.graph since from scgrpah can import cpp
from scgraph.graph import Graph
from scgraph.helpers.visvalingam import visvalingam
from scgraph.utils import haversine

DEFAULT_OUTPUT = "benchmark_results.json"

try:
    from scgraph.cpp import Graph as CppGraph

    HAS_CPP = True
except ImportError:
    HAS_CPP = False


def _bench(fn, *args, **kwargs):
    start = time.time()
    fn(*args, **kwargs)
    return round((time.time() - start) * 1000, 4)


def _load_geographs():
    print("Loading geographs...")
    return {
        "marnet": GeoGraph.load_geograph("marnet"),
        "us_freeway": GeoGraph.load_geograph("us_freeway"),
        "oak_ridge_maritime": GeoGraph.load_geograph("oak_ridge_maritime"),
        "north_america_rail": GeoGraph.load_geograph("north_america_rail"),
        "world_highways_and_marnet": GeoGraph.load_geograph(
            "world_highways_and_marnet"
        ),
    }


def _bench_graph_marnet(geo):
    print("  graph_marnet...")
    graph = Graph(geo.graph_object.graph)
    graph.create_contraction_hierarchy()
    return {
        "validation_ms": _bench(
            graph.validate, check_symmetry=True, check_connected=True
        ),
        "dijkstra_1_ms": _bench(graph.dijkstra, origin_id=0, destination_id=5),
        "dijkstra_2_ms": _bench(
            graph.dijkstra, origin_id=100, destination_id=7999
        ),
        "dijkstra_3_ms": _bench(
            graph.dijkstra, origin_id=4022, destination_id=8342
        ),
        "a_star_1_ms": _bench(
            graph.a_star,
            origin_id=0,
            destination_id=5,
            heuristic_fn=lambda x, y: 0,
        ),
        "a_star_2_ms": _bench(
            graph.a_star,
            origin_id=100,
            destination_id=7999,
            heuristic_fn=lambda x, y: 0,
        ),
        "a_star_3_ms": _bench(
            graph.a_star,
            origin_id=4022,
            destination_id=8342,
            heuristic_fn=lambda x, y: 0,
        ),
        "contraction_hierarchy_1_ms": _bench(
            graph.contraction_hierarchy, origin_id=0, destination_id=5
        ),
        "contraction_hierarchy_2_ms": _bench(
            graph.contraction_hierarchy, origin_id=100, destination_id=7999
        ),
        "contraction_hierarchy_3_ms": _bench(
            graph.contraction_hierarchy, origin_id=4022, destination_id=8342
        ),
    }


def _bench_graph_scale():
    print("  graph_scale...")

    def gen_graph(size):
        return Graph(
            [
                {i + j: 1 for j in range(1, 10) if i + j < size}
                for i in range(size)
            ]
        )

    result = {}
    for size in [100, 1000, 10000, 100000]:
        graph = gen_graph(size)
        result[f"n_{size}"] = {
            "validation_ms": _bench(
                graph.validate, check_symmetry=False, check_connected=False
            ),
            "dijkstra_ms": _bench(
                graph.dijkstra, origin_id=0, destination_id=size - 1
            ),
            "a_star_ms": _bench(
                graph.a_star,
                origin_id=0,
                destination_id=size - 1,
                heuristic_fn=lambda x, y: 0,
            ),
        }
    return result


def _bench_geograph_network(geo, name, origin, destination):
    print(f"  geograph_{name}...")
    return {
        "validation_ms": _bench(
            geo.validate, check_symmetry=True, check_connected=False
        ),
        "node_validation_ms": _bench(geo.validate_nodes),
        "dijkstra_ms": _bench(
            geo.get_shortest_path,
            origin_node=origin,
            destination_node=destination,
            algorithm_fn="dijkstra",
        ),
        "a_star_haversine_ms": _bench(
            geo.get_shortest_path,
            origin_node=origin,
            destination_node=destination,
            algorithm_fn="a_star",
            algorithm_kwargs={"heuristic_fn": geo.haversine},
        ),
        "a_star_cheap_ruler_ms": _bench(
            geo.get_shortest_path,
            origin_node=origin,
            destination_node=destination,
            algorithm_fn="a_star",
            algorithm_kwargs={"heuristic_fn": geo.cheap_ruler},
        ),
        "bmssp_ms": _bench(
            geo.get_shortest_path,
            origin_node=origin,
            destination_node=destination,
            algorithm_fn="bmssp",
        ),
    }


def _bench_geograph_marnet(geo):
    print("  geograph_marnet...")
    origin = {"latitude": 31.23, "longitude": 121.47}
    destination = {"latitude": 32.08, "longitude": -81.09}
    base = _bench_geograph_network(geo, "marnet_base", origin, destination)
    base["cached_spt_first_ms"] = _bench(
        geo.get_shortest_path,
        origin_node=origin,
        destination_node=destination,
        algorithm_fn="cached_shortest_path",
    )
    base["cached_spt_second_ms"] = _bench(
        geo.get_shortest_path,
        origin_node=origin,
        destination_node=destination,
        algorithm_fn="cached_shortest_path",
    )
    return base


def _bench_bmssp(geos):
    print("  bmssp...")
    mg = geos["marnet"].graph_object
    uf = geos["us_freeway"].graph_object
    return {
        "marnet_0_5_ms": _bench(mg.bmssp, origin_id=0, destination_id=5),
        "marnet_100_7999_ms": _bench(mg.bmssp, origin_id=100, destination_id=7999),
        "marnet_4022_8342_ms": _bench(
            mg.bmssp, origin_id=4022, destination_id=8342
        ),
        "marnet_spt_ms": _bench(mg.get_shortest_path_tree, origin_id=0),
        "us_freeway_0_5_ms": _bench(uf.bmssp, origin_id=0, destination_id=5),
        "us_freeway_4022_8342_ms": _bench(
            uf.bmssp, origin_id=4022, destination_id=8342
        ),
        "us_freeway_spt_ms": _bench(uf.get_shortest_path_tree, origin_id=0),
    }


def _bench_cache(geo):
    print("  cache_geograph...")
    cities = {
        "Los Angeles": (34.0522, -118.2437),
        "New York City": (40.7128, -74.0060),
        "Chicago": (41.8781, -87.6298),
        "Houston": (29.7604, -95.3698),
        "Phoenix": (33.4484, -112.0740),
        "Denver": (39.7392, -104.9903),
        "Seattle": (47.6062, -122.3321),
        "Miami": (25.7617, -80.1918),
        "Washington D.C.": (38.9072, -77.0369),
        "San Francisco": (37.7749, -122.4194),
        "Omaha": (41.2565, -95.9345),
        "Atlanta": (33.7490, -84.3880),
        "Austin": (30.2672, -97.7431),
        "Boston": (42.3601, -71.0589),
        "Las Vegas": (36.1699, -115.1398),
        "Detroit": (42.3314, -83.0458),
    }
    la = {"longitude": -118.2437, "latitude": 34.0522}
    nyc = {"longitude": -74.0060, "latitude": 40.7128}

    def uncached():
        for c1, v1 in cities.items():
            for c2, v2 in cities.items():
                if c1 != c2:
                    geo.get_shortest_path(
                        {"longitude": v1[1], "latitude": v1[0]},
                        {"longitude": v2[1], "latitude": v2[0]},
                    )

    def cached():
        for c1, v1 in cities.items():
            for c2, v2 in cities.items():
                if c1 != c2:
                    geo.get_shortest_path(
                        {"longitude": v1[1], "latitude": v1[0]},
                        {"longitude": v2[1], "latitude": v2[0]},
                        algorithm_fn="cached_shortest_path",
                    )

    def cached_len():
        for c1, v1 in cities.items():
            for c2, v2 in cities.items():
                if c1 != c2:
                    geo.get_shortest_path(
                        {"longitude": v1[1], "latitude": v1[0]},
                        {"longitude": v2[1], "latitude": v2[0]},
                        algorithm_fn="cached_shortest_path",
                        length_only=True,
                    )

    return {
        "single_uncached_ms": _bench(
            geo.get_shortest_path, origin_node=la, destination_node=nyc
        ),
        "single_cached_ms": _bench(
            geo.get_shortest_path,
            origin_node=la,
            destination_node=nyc,
            algorithm_fn="cached_shortest_path",
        ),
        "single_cached_length_only_ms": _bench(
            geo.get_shortest_path,
            origin_node=la,
            destination_node=nyc,
            algorithm_fn="cached_shortest_path",
            length_only=True,
        ),
        "all_uncached_ms": _bench(uncached),
        "all_cached_ms": _bench(cached),
        "all_cached_length_only_ms": _bench(cached_len),
    }


def _bench_distance_matrix(geo):
    print("  distance_matrix...")
    box = {
        "min_latitude": 34.1,
        "max_latitude": 47.0,
        "min_longitude": -118.0,
        "max_longitude": -80.0,
    }

    def get_nodes(n):
        lats = [
            box["min_latitude"] + i * (box["max_latitude"] - box["min_latitude"]) / n
            for i in range(n)
        ]
        lons = [
            box["min_longitude"]
            + i * (box["max_longitude"] - box["min_longitude"]) / n
            for i in range(n)
        ]
        return [{"latitude": lat, "longitude": lon} for lat in lats for lon in lons]

    def run_haversine(nodes):
        pts = [(n["latitude"], n["longitude"]) for n in nodes]
        for a in pts:
            for b in pts:
                haversine(a, b)

    result = {}
    for n in [5, 10, 20]:
        nodes = get_nodes(n)
        result[f"{n}x{n}"] = {
            "haversine_ms": _bench(run_haversine, nodes),
            "distance_matrix_ms": _bench(
                geo.distance_matrix,
                nodes,
                off_graph_circuity=1,
                output_units="km",
            ),
        }
    return result


def _bench_gridgraph_cache():
    print("  gridgraph_300x300_cache...")
    from scgraph.grid import GridGraph

    size = 300
    blocks = [(150, i) for i in range(5, size)]
    shape = [(0, 0), (0, 1), (1, 0), (1, 1)]
    origin = {"x": 10, "y": size - 10}
    dest = {"x": size - 10, "y": size - 10}

    creation_ms = _bench(
        GridGraph,
        x_size=size,
        y_size=size,
        blocks=blocks,
        shape=shape,
        add_exterior_walls=True,
    )
    grid = GridGraph(
        x_size=size,
        y_size=size,
        blocks=blocks,
        shape=shape,
        add_exterior_walls=True,
    )
    return {
        "creation_ms": creation_ms,
        "a_star_ms": _bench(
            grid.get_shortest_path,
            origin_node=origin,
            destination_node=dest,
            algorithm_fn="a_star",
            heuristic_fn="euclidean",
        ),
        "dijkstra_ms": _bench(
            grid.get_shortest_path,
            origin_node=origin,
            destination_node=dest,
            cache=False,
            algorithm_fn="dijkstra",
        ),
        "spt_ms": _bench(
            grid.get_shortest_path,
            origin_node=origin,
            destination_node=dest,
            algorithm_fn="cached_shortest_path",
        ),
        "cached_spt_ms": _bench(
            grid.get_shortest_path,
            origin_node=origin,
            destination_node=dest,
            algorithm_fn="cached_shortest_path",
        ),
    }


def _bench_gridgraph_export_import():
    print("  gridgraph_300x300_export_import...")
    import tempfile
    from scgraph import GridGraph

    size = 300
    blocks = [(5, i) for i in range(3, size)]
    shape = [(0, 0), (0, 1), (1, 0), (1, 1)]
    origin = {"x": 1, "y": 8}
    dest = {"x": 8, "y": 8}

    creation_ms = _bench(
        GridGraph,
        x_size=size,
        y_size=size,
        blocks=blocks,
        shape=shape,
        add_exterior_walls=True,
    )
    grid = GridGraph(
        x_size=size,
        y_size=size,
        blocks=blocks,
        shape=shape,
        add_exterior_walls=True,
    )
    first_spt_ms = _bench(
        grid.get_shortest_path,
        origin_node=origin,
        destination_node=dest,
        output_coordinate_path="list_of_lists",
        cache=True,
    )
    with tempfile.NamedTemporaryFile(suffix=".gridgraph", delete=False) as f:
        export_path = f.name
    try:
        export_ms = _bench(grid.export_object, filename=export_path)
        import_ms = _bench(GridGraph.import_object, filename=export_path)
        imported = GridGraph.import_object(filename=export_path)
        imported_cached_spt_ms = _bench(
            imported.get_shortest_path,
            origin_node=origin,
            destination_node=dest,
            output_coordinate_path="list_of_lists",
            cache=True,
        )
        imported_uncached_spt_ms = _bench(
            imported.get_shortest_path,
            origin_node=origin,
            destination_node=dest,
            output_coordinate_path="list_of_lists",
            cache=False,
        )
    finally:
        import os

        os.unlink(export_path)
    return {
        "creation_ms": creation_ms,
        "first_spt_ms": first_spt_ms,
        "export_ms": export_ms,
        "import_ms": import_ms,
        "imported_cached_spt_ms": imported_cached_spt_ms,
        "imported_uncached_spt_ms": imported_uncached_spt_ms,
    }


def _bench_visvalingam():
    print("  visvalingam...")
    result = {}
    for exp in range(1, 6):
        n = 10**exp
        data = [[i, i % 2 + (i / n)] for i in range(n)]
        result[f"n_{n}_ms"] = _bench(visvalingam, data, pct_to_keep=0, min_points=3)
    return result


def _bench_import():
    print("  geograph_import...")
    result = {}
    for name in ["marnet", "north_america_rail", "oak_ridge_maritime", "us_freeway"]:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            result[f"{name}_ms"] = _bench(
                GeoGraph.load_geograph, name, cache_dir=tmp
            )
    return result


def _bench_dijkstra_buckets(geos):
    print("  dijkstra_buckets...")
    random.seed(42)

    def make_int_grid(size):
        data = []
        for y in range(size):
            for x in range(size):
                nid = x + y * size
                edges = {}
                if x + 1 < size:
                    edges[nid + 1] = random.randint(1, 10)
                if y + 1 < size:
                    edges[nid + size] = random.randint(1, 10)
                data.append(edges)
        return data

    def make_float_grid(size):
        data = []
        for y in range(size):
            for x in range(size):
                nid = x + y * size
                edges = {}
                if x + 1 < size:
                    edges[nid + 1] = random.uniform(0.1, 10.0)
                if y + 1 < size:
                    edges[nid + size] = random.uniform(0.1, 10.0)
                data.append(edges)
        return data

    result = {}
    int_data = make_int_grid(200)
    float_data = make_float_grid(200)
    dest = 200 * 200 - 1

    for label, data in [("200x200_int", int_data), ("200x200_float", float_data)]:
        py = Graph(data)
        result[f"{label}_python_dijkstra_ms"] = _bench(py.dijkstra, 0, dest)
        result[f"{label}_python_buckets_ms"] = _bench(py.dijkstra_buckets, 0, dest)
        if HAS_CPP:
            cpp = CppGraph(data)
            result[f"{label}_cpp_dijkstra_ms"] = _bench(cpp.dijkstra, 0, dest)
            result[f"{label}_cpp_buckets_ms"] = _bench(cpp.dijkstra_buckets, 0, dest)

    for name, geo in [("marnet", geos["marnet"]), ("us_freeway", geos["us_freeway"])]:
        graph_data = geo.graph_object.graph
        half = len(graph_data) // 2
        py = Graph(graph_data)
        result[f"{name}_python_dijkstra_ms"] = _bench(py.dijkstra, 0, half)
        result[f"{name}_python_buckets_ms"] = _bench(py.dijkstra_buckets, 0, half)
        if HAS_CPP:
            cpp = CppGraph(graph_data)
            result[f"{name}_cpp_dijkstra_ms"] = _bench(cpp.dijkstra, 0, half)
            result[f"{name}_cpp_buckets_ms"] = _bench(cpp.dijkstra_buckets, 0, half)

    return result


def _bench_reduction(geos):
    print("  reduction...")
    marnet_data = geos["marnet"].graph
    us_freeway_data = geos["us_freeway"].graph

    result = {}

    # Define runs for Python
    py_marnet = Graph(marnet_data)
    result["marnet_python_dijkstra_ms"] = _bench(py_marnet.dijkstra, 100, 7999)
    result["marnet_python_reduce_preprocessing_ms"] = _bench(py_marnet.reduce)
    result["marnet_python_reduce_dijkstra_ms"] = _bench(py_marnet.dijkstra, 100, 7999)

    py_freeway = Graph(us_freeway_data)
    result["us_freeway_python_dijkstra_ms"] = _bench(py_freeway.dijkstra, 1000, 9770)
    result["us_freeway_python_reduce_preprocessing_ms"] = _bench(py_freeway.reduce)
    result["us_freeway_python_reduce_dijkstra_ms"] = _bench(py_freeway.dijkstra, 1000, 9770)

    # Define runs for C++
    if HAS_CPP:
        cpp_marnet = CppGraph(marnet_data)
        result["marnet_cpp_dijkstra_ms"] = _bench(cpp_marnet.dijkstra, 100, 7999)
        result["marnet_cpp_reduce_preprocessing_ms"] = _bench(cpp_marnet.reduce)
        result["marnet_cpp_reduce_dijkstra_ms"] = _bench(cpp_marnet.dijkstra, 100, 7999)

        cpp_freeway = CppGraph(us_freeway_data)
        result["us_freeway_cpp_dijkstra_ms"] = _bench(cpp_freeway.dijkstra, 1000, 9770)
        result["us_freeway_cpp_reduce_preprocessing_ms"] = _bench(cpp_freeway.reduce)
        result["us_freeway_cpp_reduce_dijkstra_ms"] = _bench(cpp_freeway.dijkstra, 1000, 9770)

    return result


def _bench_tnr():
    print("  tnr...")
    from scgraph.transit_node_routing import TNRGraph as PyTNRGraph
    from scgraph.graph import Graph as PyGraph

    origin = {"latitude": 31.23, "longitude": 121.47}
    destination = {"latitude": 32.08, "longitude": -81.09}
    result = {}

    for impl_name, graph_class, tnr_available in [
        ("python", PyGraph, True),
        ("cpp", CppGraph if HAS_CPP else None, HAS_CPP),
    ]:
        if not tnr_available:
            continue
        geo = GeoGraph.load_geograph("marnet")
        geo.graph_object = graph_class(graph=geo.graph)
        result[f"{impl_name}_preprocessing_ms"] = _bench(
            geo.graph_object.create_tnr_hierarchy, num_transit_nodes=100
        )
        result[f"{impl_name}_dijkstra_ms"] = _bench(
            geo.get_shortest_path, origin, destination, algorithm_fn="dijkstra"
        )
        geo.graph_object.create_contraction_hierarchy()
        result[f"{impl_name}_ch_ms"] = _bench(
            geo.get_shortest_path,
            origin,
            destination,
            algorithm_fn="contraction_hierarchy",
        )
        result[f"{impl_name}_tnr_path_ms"] = _bench(
            geo.get_shortest_path, origin, destination, algorithm_fn="tnr"
        )
        result[f"{impl_name}_tnr_length_only_ms"] = _bench(
            geo.get_shortest_path,
            origin,
            destination,
            algorithm_fn="tnr",
            length_only=True,
        )

    return result


def run_benchmarks():
    geos = _load_geographs()
    results = {}

    results['cpp'] = HAS_CPP

    print(f"\nSCGgaph ({"cpp" if HAS_CPP else "python"}) benchmarks:")

    print("Running graph benchmarks...")
    results["graph_marnet"] = _bench_graph_marnet(geos["marnet"])
    results["graph_scale"] = _bench_graph_scale()

    print("Running geograph benchmarks...")
    results["geograph_marnet"] = _bench_geograph_marnet(geos["marnet"])
    results["geograph_oak_ridge_maritime"] = _bench_geograph_network(
        geos["oak_ridge_maritime"],
        "oak_ridge",
        {"latitude": 31.23, "longitude": 121.47},
        {"latitude": 32.08, "longitude": -81.09},
    )
    results["geograph_north_america_rail"] = _bench_geograph_network(
        geos["north_america_rail"],
        "north_america_rail",
        {"latitude": 47.6, "longitude": -122.33},
        {"latitude": 25.78, "longitude": -80.21},
    )
    results["geograph_us_freeway"] = _bench_geograph_network(
        geos["us_freeway"],
        "us_freeway",
        {"latitude": 47.6, "longitude": -122.33},
        {"latitude": 25.78, "longitude": -80.21},
    )
    results["geograph_world_highways_marnet"] = _bench_geograph_network(
        geos["world_highways_and_marnet"],
        "world_highways_marnet",
        {"latitude": 47.6, "longitude": -122.33},
        {"latitude": 25.78, "longitude": -80.21},
    )

    print("Running algorithm benchmarks...")
    results["bmssp"] = _bench_bmssp(geos)
    results["cache_geograph"] = _bench_cache(geos["us_freeway"])
    results["distance_matrix"] = _bench_distance_matrix(geos["us_freeway"])

    print("Running GridGraph benchmarks...")
    results["gridgraph_300x300_cache"] = _bench_gridgraph_cache()
    results["gridgraph_300x300_export_import"] = _bench_gridgraph_export_import()

    print("Running helper benchmarks...")
    results["visvalingam"] = _bench_visvalingam()
    results["geograph_import"] = _bench_import()

    print("Running Dijkstra Buckets benchmarks...")
    results["dijkstra_buckets"] = _bench_dijkstra_buckets(geos)

    print("Running Reduction benchmarks...")
    results["reduction"] = _bench_reduction(geos)

    print("Running TNR benchmarks (slow)...")
    results["tnr"] = _bench_tnr()

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help=f"Output JSON path (default: {DEFAULT_OUTPUT})",
    )
    args = parser.parse_args()

    results = run_benchmarks()

    with open(args.output, "w") as f:
        json.dump(results, f, indent=2, sort_keys=True)
    print(f"\nBenchmark results written to {args.output}")
