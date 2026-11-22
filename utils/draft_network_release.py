"""Assemble a network release from the files that the workflow `build_networks.yml` made.

Usage: python utils/draft_network_release.py FILES PREVIOUS RELEASE TAG COMMIT

A network release is a set of network files published as the assets of one GitHub release.
FILES holds the network files of this run: the world network, and the files that
`scgraph.pipelines.derived_networks` derived from it. PREVIOUS holds `networks.json` of the
previous network release, or nothing. The script writes into RELEASE:

- each network file, compressed with gzip. A user decompresses a file before loading
  it;
- `networks.json`, the index of the release: its tag, and one entry per file. An entry
  gives the `content_sha256` of the file once decompressed, and the commit of the run
  that made the file. A file is carried over when a file of the previous release has
  the same `content_sha256`: its entry keeps the commit of that release;
- `notes.md`, the notes of the release, with the credit line of each file.

The script stops when the license of a source is `NOASSERTION`: the license could not
be established, so the network is not published.
"""

import gzip
import json
import os
import shutil
import sys
from pathlib import Path

from scgraph import GeoGraph
from scgraph.pipelines.derived_networks import (
    DERIVED_NETWORKS,
    describe_derived_network,
)


def read_previous_commits(previous: str | os.PathLike) -> dict[str, str]:
    """Return, for each `content_sha256` of the previous network release, the commit of
    the run that made the file.

    Args:
        previous: The directory that holds `networks.json` of the previous network
            release. It may be empty.
    """
    index = Path(previous, "networks.json")
    entries = (
        json.loads(index.read_text())["networks"] if index.is_file() else []
    )
    return {entry["content_sha256"]: entry["commit"] for entry in entries}


def compress(file: Path, compressed_file: Path) -> None:
    """Write `file` compressed with gzip. The compressed file records no time and no
    name, so the same file always gives the same bytes."""
    with (
        open(file, "rb") as source,
        open(compressed_file, "wb") as target,
        gzip.GzipFile(
            filename="", mode="wb", fileobj=target, mtime=0
        ) as packed,
    ):
        shutil.copyfileobj(source, packed)


def describe_network(file: Path) -> str:
    """Return the sentence that describes the network of a file, for the index.

    Args:
        file: The network file. Its name starts with the name of the network.

    Returns:
        For a derived network, the sentence of `describe_derived_network`. For a built
        network, the first paragraph of the docstring of its pipeline. The file with
        shapes of the network records this docstring as `description`. The file
        without shapes is in the same folder and does not record it.
    """
    name = file.name.split(".")[0]
    if name in DERIVED_NETWORKS:
        return describe_derived_network(name)
    file_with_shapes = file.with_name(f"{name}.scgraph")
    description = GeoGraph.get_scgraph_info(file_with_shapes)["description"]
    return " ".join(description.split("\n\n")[0].split())


def write_release_draft(
    files: str | os.PathLike,
    previous: str | os.PathLike,
    release: str | os.PathLike,
    tag: str,
    commit: str,
) -> None:
    """Write the files, the index and the notes of the network release `tag` into the
    new directory `release`.

    Args:
        files: The directory of the network files of this run.
        previous: The directory that holds `networks.json` of the previous network
            release. It may be empty.
        release: The directory to create.
        tag: The tag of the release.
        commit: The commit of this run.

    Raises:
        ValueError: The license of a source of a network is `NOASSERTION`.
    """
    previous_commits = read_previous_commits(previous)
    Path(release).mkdir()
    networks = []
    for file in sorted(Path(files).glob("*.scgraph")):
        info = GeoGraph.get_scgraph_info(file)
        for source in info["sources"]:
            if source["license"] == "NOASSERTION":
                raise ValueError(
                    f"{file.name}: the license of the source "
                    f"'{source['name']}' is not established"
                )
        compressed_file = Path(release, file.name + ".gz")
        compress(file, compressed_file)
        is_carried_over = info["content_sha256"] in previous_commits
        networks.append(
            {
                "file": compressed_file.name,
                "compressed_bytes": compressed_file.stat().st_size,
                "bytes": file.stat().st_size,
                "status": "carried over" if is_carried_over else "new",
                "commit": previous_commits.get(info["content_sha256"], commit),
                **{
                    key: info[key]
                    for key in (
                        "content_sha256",
                        "format_version",
                        "nodes",
                        "edges",
                        "data_up_to",
                        "attribution",
                        "pipeline",
                        "sources",
                    )
                },
                # Only a derived file has a derivation: its parent, modes and bbox
                "derivation": info.get("derivation"),
                "description": describe_network(file),
            }
        )
    index = {"tag": tag, "networks": networks}
    Path(release, "networks.json").write_text(
        json.dumps(index, indent=1) + "\n"
    )
    Path(release, "notes.md").write_text(format_notes(networks, commit))


def format_notes(networks: list[dict], commit: str) -> str:
    """Return the notes of a network release, in Markdown.

    Args:
        networks: The entries of the index `networks.json`.
        commit: The commit of this run.

    Returns:
        The text: where the files come from, how to load one, one table row per
        file, then the credit line of each file.
    """
    rows = [
        f"| `{network['file']}` | {network['compressed_bytes'] / 1e6:.1f} MB "
        f"| {network['bytes'] / 1e6:.1f} MB "
        f"| {network['nodes']:,} | {network['edges']:,} "
        f"| {network['status']} | `{network['content_sha256'][:16]}` |"
        for network in networks
    ]
    credits = [
        f"- `{network['file']}`: {network['attribution']}"
        for network in networks
    ]
    format_versions = sorted(
        {network["format_version"] for network in networks}
    )
    return "\n".join(
        [
            "`world_multimodal.scgraph` holds the roads, the railways, the sea "
            "lanes and the flights of the world. Ports, airports and rail "
            "terminals join them. Every other file is a part of this network. A "
            "file named for a part of the world holds the roads, the railways and "
            "the rail terminals inside a rectangle. It also holds every sea lane, "
            "port and airport of the world. A route of such a file stays inside "
            "the rectangle on land, so it can be longer than in the world file. A "
            "file with `no_shapes` in its name holds the same network without the "
            "shapes of its edges. The lengths of its routes are the same.",
            "",
            f"A new file comes from commit {commit}. The world network passed the "
            "validation cases of its pipeline when it was built. A derived file "
            "fails no case that the world file passes, among the cases on its "
            "modes that have two ends inside its rectangle. A carried-over file "
            "has the content of the same file in the previous network release.",
            "",
            "To use a file, download it and decompress it (`gunzip FILE.gz`). Load "
            'it with `GeoGraph.load_from_scgraph("FILE")`, and keep some modes '
            'only with `node_modes=["road"]`. This needs a version of scgraph that reads '
            "the file format version "
            f"{', '.join(map(str, format_versions))}. "
            '`GeoGraph.get_scgraph_info("FILE")` gives the sources of a file and '
            "its `content_sha256`. `networks.json` holds the full digests, the "
            "rectangle of each derived file and the commit of each file.",
            "",
            "| File | Download | Decompressed | Nodes | Edges | Status | `content_sha256` |",
            "|---|---|---|---|---|---|---|",
            *rows,
            "",
            "**Credits and licenses.** Cite the credit line of a file with the "
            "results that use it.",
            "",
            *credits,
            "",
        ]
    )


if __name__ == "__main__":
    write_release_draft(*sys.argv[1:])
