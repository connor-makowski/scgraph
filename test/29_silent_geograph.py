import io, sys
from scgraph import GeoGraph

print("\n===============\nSilent GeoGraph Tests:\n===============")

# Two isolated clusters with no path between them
nodes = [
    [0.0, 0.0],  # 0 — cluster A
    [0.1, 0.1],  # 1 — cluster A
    [50.0, 50.0],  # 2 — cluster B
    [50.1, 50.1],  # 3 — cluster B
]
graph = [
    {1: 15.0},
    {0: 15.0},
    {3: 15.0},
    {2: 15.0},
]
geo = GeoGraph(nodes=nodes, graph=graph)
origin = {"latitude": 0.0, "longitude": 0.0}
destination = {"latitude": 50.0, "longitude": 50.0}

# silent=True — no output expected
buf = io.StringIO()
sys.stdout = buf
try:
    geo.get_shortest_path(origin, destination, silent=True)
except Exception:
    pass
finally:
    sys.stdout = sys.__stdout__
assert (
    buf.getvalue() == ""
), f"Expected no output with silent=True, got: {buf.getvalue()!r}"

# silent=False — output expected
buf = io.StringIO()
sys.stdout = buf
try:
    geo.get_shortest_path(origin, destination, silent=False)
except Exception:
    pass
finally:
    sys.stdout = sys.__stdout__
assert buf.getvalue() != "", "Expected output with silent=False but got none"

print("Silent GeoGraph Disconnect Tests: PASSED")
