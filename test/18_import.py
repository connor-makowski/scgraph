from time import time

print("\n===============\nImport Timing:\n===============")
start_time = time()
from scgraph.geographs.marnet import marnet_geograph

print(f"Importing Marnet took {round((time() - start_time) * 1000, 4)} ms")
start_time = time()
from scgraph.geographs.north_america_rail import north_america_rail_geograph

print(
    f"Importing North America Rail took {round((time() - start_time) * 1000, 4)} ms"
)
start_time = time()
from scgraph.geographs.oak_ridge_maritime import oak_ridge_maritime_geograph

print(
    f"Importing Oak Ridge Maritime took {round((time() - start_time) * 1000, 4)} ms"
)
start_time = time()
from scgraph.geographs.us_freeway import us_freeway_geograph

print(f"Importing US Freeway took {round((time() - start_time) * 1000, 4)} ms")
