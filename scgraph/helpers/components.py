"""Find the strongly connected components of a graph, and keep the largest one.

In a strongly connected component, every node can reach every other node along the
edges. `GeoGraph.load_from_osm` keeps the largest component of the graph that it reads.
The pipelines call these functions through `scgraph.pipelines.steps.step3_network_assembly`.

`build_csr_from_adjacency_list` and `keep_largest_strongly_connected_component` take
the layout of a GeoGraph, for `load_from_osm`.

`find_strongly_connected_components` has a C++ version
(`cpp/src/pipelines/assembly.hpp`). The function calls the C++ version when the
extension is built and the inputs are `array` or `memoryview` buffers.
"""

from array import array
from collections.abc import Sequence

try:
    from scgraph.cpp import (
        find_strongly_connected_components as _cpp_strongly_connected_components,
    )
except ImportError:
    _cpp_strongly_connected_components = None

from scgraph.helpers.douglas_peucker import _is_monotonically_increasing


def find_strongly_connected_components_python(
    offsets: Sequence[int], heads: Sequence[int]
) -> tuple[array, array]:
    """Pure-Python version of `find_strongly_connected_components`."""
    n = len(offsets) - 1
    if (
        n < 0
        or offsets[n] != len(heads)
        or not _is_monotonically_increasing(offsets)
    ):
        raise ValueError("offsets must rise from 0 to the number of items")
    if heads and not (0 <= min(heads) and max(heads) < n):
        raise IndexError("head out of range")

    def successors(node):
        return iter(heads[offsets[node] : offsets[node + 1]])

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
    offsets: array | memoryview, heads: array | memoryview
) -> tuple[array | memoryview, array | memoryview]:
    """Find the strongly connected components of a graph, with Kosaraju's algorithm.

    In a strongly connected component, every node can reach every other node along the
    edges.

    Args:
        offsets: The CSR offsets of the graph, one more than its nodes (int32).
        heads: The head of each edge (int32).

    Returns:
        `(labels, sizes)`. `labels[u]` is the number of the component of node `u`. The
        components are numbered in the order of their lowest node. `sizes[c]` is the
        number of nodes of component `c`.
    """
    if _cpp_strongly_connected_components is not None and isinstance(
        offsets, (array, memoryview)
    ):
        return _cpp_strongly_connected_components(offsets, heads)
    return find_strongly_connected_components_python(offsets, heads)


def build_csr_from_adjacency_list(
    adjacency_list: list[dict[int, int | float]],
) -> tuple[array, array, array]:
    """Store a graph in the layout of a GeoGraph as CSR arrays.

    Args:
        adjacency_list: For each node, a dict that gives the weight of the edge to each
            head.

    Returns:
        `(offsets, heads, weights)`: int32, int32 and float64. The edges of a node are
        sorted by head.
    """
    offsets, heads, weights = array("i", [0]), array("i"), array("d")
    for row in adjacency_list:
        for head in sorted(row):
            heads.append(head)
            weights.append(row[head])
        offsets.append(len(heads))
    return offsets, heads, weights


def keep_strongly_connected_components(
    offsets: array | memoryview,
    heads: array | memoryview,
    min_component_nodes: int | None = None,
) -> tuple[array, array | memoryview]:
    """Choose the nodes to keep, by strongly connected component.

    A node outside the kept components is a one-way dead end, a place that no route can
    enter, or a fragment that the border of an extract cut off.

    Args:
        offsets: The CSR offsets of the graph, one more than its nodes (int32).
        heads: The head of each edge (int32).
        min_component_nodes: The smallest number of nodes of a kept component. None keeps
            only the largest component. Example: `osm_world_multimodal` gives 1000, so that
            an island with roads of its own stays in the network.

    Returns:
        `(kept_nodes, labels)`. `kept_nodes` lists the kept nodes in rising order.
        `labels[u]` is the number of the component of node `u`, kept or not.
    """
    labels, sizes = find_strongly_connected_components(offsets, heads)
    if min_component_nodes is None:
        largest = max(range(len(sizes)), key=sizes.__getitem__, default=-1)
        wanted = [c == largest for c in range(len(sizes))]
    else:
        wanted = [size >= min_component_nodes for size in sizes]
    return array("i", (u for u, c in enumerate(labels) if wanted[c])), labels


def keep_largest_strongly_connected_component(
    graph: list[dict[int, int | float]],
    nodes: list[list[float]],
    shapes: list[dict[int, list[list[float]]]],
    source_node_ids: list[int],
    edge_class_names: list[dict[int, str]],
) -> tuple[
    list[dict[int, int | float]],
    list[list[float]],
    list[dict[int, list[list[float]]]],
    list[int],
    list[dict[int, str]],
]:
    """Keep the largest strongly connected component of a graph in the layout of a
    GeoGraph. Return `(graph, nodes, shapes, source_node_ids, edge_class_names)` with the kept
    nodes only.
    """
    kept, _ = keep_strongly_connected_components(
        *build_csr_from_adjacency_list(graph)[:2]
    )
    index = {old: new for new, old in enumerate(kept)}

    def row(values):
        return {index[v]: x for v, x in values.items() if v in index}

    return (
        [row(graph[u]) for u in kept],
        [nodes[u] for u in kept],
        [row(shapes[u]) for u in kept],
        [source_node_ids[u] for u in kept],
        [row(edge_class_names[u]) for u in kept],
    )
