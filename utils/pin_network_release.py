"""Pin the network release that this version of scgraph loads.

Usage: python utils/pin_network_release.py TAG

A network release is a set of network files published as the assets of one GitHub
release. `GeoGraph.load_geograph` loads the files of one network release: the release
that `scgraph/network_release.py` names. To pin a network release is to write its tag,
and the `content_sha256` of each of its files, into this module.

A maintainer first publishes a network release (DEVELOPMENT.md, *Network releases*).
The maintainer then runs this script with the tag of that release, for example
`networks-2026.11.20`, and commits the module in a PR, with the update of the documents
(`scgraph/pipelines/README.md`, Part 3, *Publishing the Draft*, step 4). Until this PR is
merged, scgraph loads the release that was pinned before.

The script downloads `networks.json`, the index of the release, and writes the module
again: the tag, the digest of each file, and what `list_geographs` says of each network.
"""

import json
import sys
from pathlib import Path

import requests

URL = "https://github.com/connor-makowski/scgraph/releases/download"
MODULE = '''"""The network release that this version of scgraph loads.

A network release is a set of network files that scgraph publishes together, as the
assets of one GitHub release. Its tag names it, for example `networks-2026.11.20`. A
published network release is never changed.

This module pins one network release. `GeoGraph.load_geograph("europe")` loads the
file `europe` of this release, unless the caller passes another `network_release`. The same
version of scgraph therefore loads the same networks on every machine and at any date.
The module also records the digest of each file, so that `load_geograph` refuses a
download that is not the published file.

`utils/pin_network_release.py TAG` writes this module. Do not edit it by hand.
"""

# The tag of the pinned network release
TAG = "{tag}"
# The `content_sha256` of each network file of this release. A key is the name of a
# network. It ends with `.no_shapes` for the file without the shapes of the edges.
# `load_geograph` checks each file that it downloads from this release against its
# value here.
CONTENT_SHA256 = {{
{rows}
}}
# What `GeoGraph.list_geographs` says of each network of this release: its numbers of
# nodes and of edges, the size in MB of its download with and without the shapes of the
# edges, the time of its newest source data (None when no source gives a time), and its
# description.
NETWORKS = {{
{networks}
}}
'''


def format_module(tag: str, networks: list[dict]) -> str:
    """Return the text of the module `scgraph/network_release.py` for a network
    release.

    Args:
        tag: The tag of the network release.
        networks: The rows of `networks` in the `networks.json` of the release, one
            for each file.

    Returns:
        The module as `black` formats it: `utils/prettify.py` then changes no line.
    """
    rows = "\n".join(
        f'    "{network["file"].removesuffix(".scgraph.gz")}": '
        f'"{network["content_sha256"]}",'
        for network in sorted(networks, key=lambda network: network["file"])
    )
    files = {
        network["file"].removesuffix(".scgraph.gz"): network
        for network in networks
    }
    # `json.dumps` writes a text between double quotes, as black does
    data_up_to = {
        name: json.dumps(file["data_up_to"]) if file["data_up_to"] else "None"
        for name, file in files.items()
    }
    described = "\n".join(
        f'    "{name}": {{\n'
        f'        "nodes": {files[name]["nodes"]},\n'
        f'        "edges": {files[name]["edges"]},\n'
        f'        "download_mb": {files[name]["compressed_bytes"] / 1e6:.1f},\n'
        f'        "download_mb_without_intermediate_nodes": '
        f'{files[name + ".no_shapes"]["compressed_bytes"] / 1e6:.1f},\n'
        f'        "data_up_to": {data_up_to[name]},\n'
        f'        "description": '
        f'{json.dumps(files[name]["description"], ensure_ascii=False)},\n'
        f"    }},"
        for name in sorted(files)
        if not name.endswith(".no_shapes")
    )
    return MODULE.format(tag=tag, rows=rows, networks=described)


def main(tag: str) -> None:
    response = requests.get(f"{URL}/{tag}/networks.json", timeout=60)
    response.raise_for_status()
    module = Path(__file__).parent.parent / "scgraph" / "network_release.py"
    module.write_text(format_module(tag, response.json()["networks"]))
    print(f"Wrote {module}")


if __name__ == "__main__":
    main(*sys.argv[1:])
