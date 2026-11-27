"""The table of the node modes of a network, and the node mode id of each node.

The node mode of a node is the kind of place where the node is: road, port, and so
on. The table of the node modes has one row for each node mode: a dict with its
`name` and, if a source gave the node ids of the node mode, the name of that
`source`. The node mode id of a node is the position of its row in the table.

A `GeoGraph` holds this table in its attribute `node_modes`, and a network file
stores it in its header. A network with one node mode without a name has the table
of `get_default_node_modes`. The header of its file holds no table.

This module is internal, except `build_node_mode_ids`.

Example: the table `[{"name": "road"}, {"name": "port"}]` gives the node mode id 0
to a road node and 1 to a port node.
"""

from array import array
from collections.abc import Iterable

__all__ = ["build_node_mode_ids"]


def get_default_node_modes() -> list[dict]:
    """Return the table of a network with one node mode without a name:
    `[{"name": None}]`. Each call returns a new list, so a caller may change it.
    """
    return [{"name": None}]


def list_node_mode_names(
    node_modes: list[dict],
    names: Iterable[str | None] = (),
    argument: str = "node_modes",
) -> list[str | None]:
    """Return the name of each node mode of a table, and refuse a name that is not
    in the table.

    Args:
        node_modes: The table of the node modes.
        names: The names that an argument of the caller gives.
        argument: The name of that argument, for the message of the error.

    Returns:
        The name of each row of `node_modes`, in the order of the rows.

    Raises:
        ValueError: A name of `names` is not the name of a row of `node_modes`.
    """
    node_mode_names = [row.get("name") for row in node_modes]
    unknown = [name for name in names if name not in node_mode_names]
    if unknown:
        raise ValueError(
            f"{argument} names unknown node modes {unknown}: the node modes "
            f"are {node_mode_names}"
        )
    return node_mode_names


def build_node_mode_ids(
    node_modes: list[dict], kept_node_mode_names: str | list[str] | None = None
) -> array:
    """Return the node mode id of each node of a file, from the rows of its header.

    Args:
        node_modes: The rows of `metadata["node_modes"]` that `network_file.read`
            returns, each with its `node_count`.
        kept_node_mode_names: The names of the node modes that a read kept, as
            `network_file.read` takes them. The default, None, gives the ids of
            every node.

    Returns:
        An array of uint8: for each node, in the order of the file, the position of its
        row in `node_modes`. Example: the rows `road` (2 nodes), `port` (1 node) and
        `sea` (2 nodes) give [0, 0, 1, 2, 2], and [0, 0, 2, 2] for the road and the sea.
    """
    if isinstance(kept_node_mode_names, str):
        kept_node_mode_names = [kept_node_mode_names]
    return array(
        "B",
        b"".join(
            bytes([node_mode_id]) * row["node_count"]
            for node_mode_id, row in enumerate(node_modes)
            if kept_node_mode_names is None
            or row["name"] in kept_node_mode_names
        ),
    )
