"""Find the strongly connected components of a graph, and choose the ones to keep.

In a strongly connected component, every node can reach every other node along the
edges. `GeoGraph.load_from_osm` and the pipelines call these functions through
`scgraph.network_assembly`.

`build_csr_from_adjacency_list` takes a graph in the layout of a GeoGraph.

`find_strongly_connected_components` has a C++ version
(`cpp/src/network_assembly.hpp`). The function calls the C++ version when the
extension is built and the inputs are `array` or `memoryview` buffers.
"""

from array import array
from collections.abc import Sequence

# The C++ kernel takes typed buffers only, so each call chooses its kernel.
try:
    from scgraph.cpp import (
        find_strongly_connected_components as _cpp_strongly_connected_components,
    )
except ImportError:
    _cpp_strongly_connected_components = None

from scgraph.array_checks import is_sorted_from_zero


def find_strongly_connected_components_python(
    node_first_edge_ids: Sequence[int], edge_destination_node_ids: Sequence[int]
) -> tuple[array, array]:
    """Pure-Python version of `find_strongly_connected_components`."""
    n = len(node_first_edge_ids) - 1
    if (
        n < 0
        or node_first_edge_ids[n] != len(edge_destination_node_ids)
        or not is_sorted_from_zero(node_first_edge_ids)
    ):
        raise ValueError(
            "node_first_edge_ids must rise from 0 to the number of items"
        )
    if edge_destination_node_ids and not (
        0 <= min(edge_destination_node_ids)
        and max(edge_destination_node_ids) < n
    ):
        raise IndexError("destination id out of range")

    def successors(node):
        return iter(
            edge_destination_node_ids[
                node_first_edge_ids[node] : node_first_edge_ids[node + 1]
            ]
        )

    # Kosaraju: order the nodes by the end of a depth-first search, then search the
    # reverse graph from the last one finished
    finished, seen = [], [False] * n
    for first in range(n):
        if seen[first]:
            continue
        seen[first] = True
        stack = [(first, successors(first))]
        while stack:
            node, ahead = stack[-1]
            successor = next(ahead, None)
            if successor is None:
                stack.pop()
                finished.append(node)
            elif not seen[successor]:
                seen[successor] = True
                stack.append((successor, successors(successor)))
    reverse = [[] for _ in range(n)]
    for origin in range(n):
        for destination in successors(origin):
            reverse[destination].append(origin)
    component, count = [-1] * n, 0
    for first in reversed(finished):
        if component[first] != -1:
            continue
        component[first], stack = count, [first]
        while stack:
            for predecessor in reverse[stack.pop()]:
                if component[predecessor] == -1:
                    component[predecessor] = count
                    stack.append(predecessor)
        count += 1
    # Number the components in the order of their smallest node
    number, labels, sizes = [-1] * count, array("i", bytes(4 * n)), array("i")
    for node in range(n):
        if number[component[node]] == -1:
            number[component[node]] = len(sizes)
            sizes.append(0)
        labels[node] = number[component[node]]
        sizes[labels[node]] += 1
    return labels, sizes


def find_strongly_connected_components(
    node_first_edge_ids: array | memoryview,
    edge_destination_node_ids: array | memoryview,
) -> tuple[array | memoryview, array | memoryview]:
    """Find the strongly connected components of a graph, with Kosaraju's algorithm.

    In a strongly connected component, every node can reach every other node along the
    edges.

    Args:
        node_first_edge_ids: For each node, the id of its first edge, and one more
            value at the end: the count of the edges (int32).
        edge_destination_node_ids: The destination id of each edge (int32).

    Returns:
        `(labels, sizes)`. `labels[u]` is the number of the component of node `u`. The
        components are numbered in the order of their lowest node. `sizes[c]` is the
        number of nodes of component `c`.
    """
    if _cpp_strongly_connected_components is not None and isinstance(
        node_first_edge_ids, (array, memoryview)
    ):
        return _cpp_strongly_connected_components(
            node_first_edge_ids, edge_destination_node_ids
        )
    return find_strongly_connected_components_python(
        node_first_edge_ids, edge_destination_node_ids
    )


def build_csr_from_adjacency_list(
    adjacency_list: list[dict[int, int | float]],
) -> tuple[array, array, array]:
    """Store a graph in the layout of a GeoGraph as CSR arrays.

    Args:
        adjacency_list: For each node, a dict that gives the weight of the edge to each
            destination_id.

    Returns:
        `(node_first_edge_ids, edge_destination_node_ids, weights)`:
        int32, int32 and float64. The edges of a node are sorted by destination id.
    """
    node_first_edge_ids, edge_destination_node_ids, weights = (
        array("i", [0]),
        array("i"),
        array("d"),
    )
    for row in adjacency_list:
        for destination_id in sorted(row):
            edge_destination_node_ids.append(destination_id)
            weights.append(row[destination_id])
        node_first_edge_ids.append(len(edge_destination_node_ids))
    return node_first_edge_ids, edge_destination_node_ids, weights


def keep_strongly_connected_components(
    node_first_edge_ids: array | memoryview,
    edge_destination_node_ids: array | memoryview,
    min_component_nodes: int | None = None,
) -> tuple[array, array | memoryview]:
    """Choose the nodes to keep, by strongly connected component.

    A node outside the kept components is a one-way dead end, a place that no route can
    enter, or a fragment that the border of an extract cut off.

    Args:
        node_first_edge_ids: For each node, the id of its first edge, and one more
            value at the end: the count of the edges (int32).
        edge_destination_node_ids: The destination id of each edge (int32).
        min_component_nodes: The smallest number of nodes of a kept component. None keeps
            only the largest component. Example: `osm_world_multimodal` gives 1000, so that
            an island with roads of its own stays in the network.

    Returns:
        `(kept_nodes, labels)`. `kept_nodes` lists the kept nodes in rising order.
        `labels[u]` is the number of the component of node `u`, kept or not.
    """
    labels, sizes = find_strongly_connected_components(
        node_first_edge_ids, edge_destination_node_ids
    )
    if min_component_nodes is None:
        largest = max(range(len(sizes)), key=sizes.__getitem__, default=-1)
        wanted = [c == largest for c in range(len(sizes))]
    else:
        wanted = [size >= min_component_nodes for size in sizes]
    return array("i", (u for u, c in enumerate(labels) if wanted[c])), labels
