import tempfile
from scgraph import GeoGraph
from scgraph.utils import validate

print("\n===============\nGeoGraph Load/Cache Tests:\n===============")

with tempfile.TemporaryDirectory() as tmp:
    # Uncomment and change for branch specific testing

    # list_geographs returns a non-empty list of dicts with the expected keys
    geograph_list = GeoGraph.list_geographs(
        cache_dir=tmp,
    )
    validate(
        name="list_geographs returns a list",
        realized=isinstance(geograph_list, list) and len(geograph_list) > 0,
        expected=True,
    )
    validate(
        name="list_geographs entries have name and cached keys",
        realized=all("name" in g and "cached" in g for g in geograph_list),
        expected=True,
    )

    # marnet is available and not yet cached
    marnet_entry = next(
        (g for g in geograph_list if g["name"] == "marnet"), None
    )
    validate(
        name="marnet is listed as available",
        realized=marnet_entry is not None,
        expected=True,
    )
    validate(
        name="marnet is not cached before load",
        realized=marnet_entry["cached"],
        expected=False,
    )

    # load_geograph downloads and returns a GeoGraph
    geograph = GeoGraph.load_geograph(
        "marnet",
        cache_dir=tmp,
    )
    validate(
        name="load_geograph returns a GeoGraph",
        realized=isinstance(geograph, GeoGraph),
        expected=True,
    )

    # After loading, marnet should be cached
    geograph_list = GeoGraph.list_geographs(
        cache_dir=tmp,
    )
    marnet_entry = next(
        (g for g in geograph_list if g["name"] == "marnet"), None
    )
    validate(
        name="marnet is cached after load",
        realized=marnet_entry["cached"],
        expected=True,
    )

    # Second load uses cache (no network) and still returns a GeoGraph
    geograph_cached = GeoGraph.load_geograph(
        "marnet",
        cache_dir=tmp,
    )
    validate(
        name="load_geograph from cache returns a GeoGraph",
        realized=isinstance(geograph_cached, GeoGraph),
        expected=True,
    )

    # clear_geograph_cache removes the cache
    GeoGraph.clear_geograph_cache(cache_dir=tmp)
    geograph_list = GeoGraph.list_geographs(
        cache_dir=tmp,
    )
    marnet_entry = next(
        (g for g in geograph_list if g["name"] == "marnet"), None
    )
    validate(
        name="marnet is not cached after clear",
        realized=marnet_entry["cached"],
        expected=False,
    )
