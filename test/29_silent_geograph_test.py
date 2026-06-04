import io
import sys
from scgraph import GeoGraph

_NODES = [
    [0.0, 0.0],
    [0.1, 0.1],
    [50.0, 50.0],
    [50.1, 50.1],
]
_GRAPH = [{1: 15.0}, {0: 15.0}, {3: 15.0}, {2: 15.0}]
_ORIGIN = {"latitude": 0.0, "longitude": 0.0}
_DESTINATION = {"latitude": 50.0, "longitude": 50.0}


def test_silent_produces_no_output():
    geo = GeoGraph(nodes=_NODES, graph=_GRAPH)
    buf = io.StringIO()
    sys.stdout = buf
    try:
        geo.get_shortest_path(_ORIGIN, _DESTINATION, silent=True)
    except Exception:
        pass
    finally:
        sys.stdout = sys.__stdout__
    assert buf.getvalue() == "", f"Expected no output, got: {buf.getvalue()!r}"


def test_non_silent_produces_output():
    geo = GeoGraph(nodes=_NODES, graph=_GRAPH)
    buf = io.StringIO()
    sys.stdout = buf
    try:
        geo.get_shortest_path(_ORIGIN, _DESTINATION, silent=False)
    except Exception:
        pass
    finally:
        sys.stdout = sys.__stdout__
    assert (
        buf.getvalue() != ""
    ), "Expected output with silent=False but got none"
