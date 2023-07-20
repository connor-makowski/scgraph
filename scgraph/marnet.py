from .core import GeoGraph
from .data.marnet import marnet_data

marnet_geograph = GeoGraph(
    graph=marnet_data.get("graph"), nodes=marnet_data.get("nodes")
)
