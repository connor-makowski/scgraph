from time import time
from scgraph import GeoGraph

print("\n===============\nImport Timing:\n===============")
start_time = time()
marnet_geograph = GeoGraph.load_geograph("marnet")

print(f"Loading Marnet took {round((time() - start_time) * 1000, 4)} ms")
start_time = time()
north_america_rail_geograph = GeoGraph.load_geograph("north_america_rail")

print(
    f"Loading North America Rail took {round((time() - start_time) * 1000, 4)} ms"
)
start_time = time()
oak_ridge_maritime_geograph = GeoGraph.load_geograph("oak_ridge_maritime")

print(
    f"Loading Oak Ridge Maritime took {round((time() - start_time) * 1000, 4)} ms"
)
start_time = time()
us_freeway_geograph = GeoGraph.load_geograph("us_freeway")

print(f"Loading US Freeway took {round((time() - start_time) * 1000, 4)} ms")
