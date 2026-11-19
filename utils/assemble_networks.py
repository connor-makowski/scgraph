"""Assemble a data release from the networks that the workflow `build_networks.yml` built.

Usage: python utils/assemble_networks.py BUILT PREVIOUS RELEASE TAG COMMIT

A data release is a set of network files published as the assets of one GitHub release.
BUILT holds the network files of this build. PREVIOUS holds the files of the previous
data release, or nothing. The script writes into RELEASE:

- one file per network. A network is carried over when its pipeline and its sources
  did not change since the previous release: the release then keeps the previous file,
  byte for byte. Otherwise the release takes the new file;
- `networks.json`, the index of the release: its tag, and one entry per network with
  the commit that built its file;
- `notes.md`, the notes of the release, with the credit line of each network.

The script stops when the license of a source is `NOASSERTION`: the license could not
be established, so the network is not published.
"""

import json
import os
import shutil
import sys
from pathlib import Path

from scgraph import GeoGraph


def get_build_inputs(info: dict) -> tuple[dict, list[dict]]:
    """Return what decides the graph of a built network: its pipeline and its sources.

    Args:
        info: What `GeoGraph.get_scgraph_info` returns for the network file.

    Returns:
        The pipeline (name, region, version), and the record of each source without
        its URL. The same source can be read from several mirrors, so its URL does not
        identify it: its digest and its version do.
    """
    sources = [
        {key: value for key, value in source.items() if key != "url"}
        for source in info["sources"]
    ]
    return info["pipeline"], sources


def read_previous_release(previous: str | os.PathLike) -> dict[str, dict]:
    """Return the networks of the previous data release that this version of scgraph
    reads.

    Args:
        previous: The directory of the files of the previous data release.

    Returns:
        For each file name: the `info` of the file, as `GeoGraph.get_scgraph_info`
        returns it, and the `commit` that built it. A file in another file format is
        left out, so its network is built again.
    """
    index = Path(previous, "networks.json")
    entries = (
        json.loads(index.read_text())["networks"] if index.is_file() else []
    )
    networks = {}
    for entry in entries:
        try:
            info = GeoGraph.get_scgraph_info(Path(previous, entry["file"]))
        except ValueError:
            continue
        networks[entry["file"]] = {"info": info, "commit": entry["commit"]}
    return networks


def assemble(
    built: str | os.PathLike,
    previous: str | os.PathLike,
    release: str | os.PathLike,
    tag: str,
    commit: str,
) -> None:
    """Write the files, the index and the notes of the data release `tag` into the
    new directory `release`.

    Args:
        built: The directory of the network files of this build.
        previous: The directory of the files of the previous data release. It may be
            empty.
        release: The directory to create.
        tag: The tag of the release.
        commit: The commit that built the files of `built`.

    Raises:
        ValueError: The license of a source of a network is `NOASSERTION`.
    """
    previous_networks = read_previous_release(previous)
    Path(release).mkdir()
    networks = []
    for built_file in sorted(Path(built).glob("*.scgraph")):
        info = GeoGraph.get_scgraph_info(built_file)
        for source in info["sources"]:
            if source["license"] == "NOASSERTION":
                raise ValueError(
                    f"{built_file.name}: the license of the source "
                    f"'{source['name']}' is not established"
                )
        earlier = previous_networks.get(built_file.name)
        is_carried_over = earlier is not None and get_build_inputs(
            earlier["info"]
        ) == get_build_inputs(info)
        kept_file = (
            Path(previous, built_file.name) if is_carried_over else built_file
        )
        kept_info = earlier["info"] if is_carried_over else info
        shutil.copyfile(kept_file, Path(release, built_file.name))
        networks.append(
            {
                "file": built_file.name,
                "status": "carried over" if is_carried_over else "rebuilt",
                "commit": earlier["commit"] if is_carried_over else commit,
                "bytes": kept_file.stat().st_size,
                **{
                    key: kept_info[key]
                    for key in (
                        "content_sha256",
                        "format_version",
                        "nodes",
                        "arcs",
                        "data_up_to",
                        "attribution",
                        "pipeline",
                        "sources",
                    )
                },
            }
        )
    index = {"tag": tag, "networks": networks}
    Path(release, "networks.json").write_text(
        json.dumps(index, indent=1) + "\n"
    )
    Path(release, "notes.md").write_text(format_notes(networks, commit))


def format_notes(networks: list[dict], commit: str) -> str:
    """Return the notes of a data release, in Markdown.

    Args:
        networks: The entries of the index `networks.json`.
        commit: The commit that built the rebuilt networks.

    Returns:
        The text: how the files were built, how to load one, one table row per
        network, then the credit line of each network.
    """
    rows = [
        f"| `{network['file']}` | {network['bytes'] / 1e6:.1f} MB "
        f"| {network['nodes']:,} | {network['arcs']:,} "
        f"| {(network['data_up_to'] or '')[:10] or 'no date'} "
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
            f"The pipelines of scgraph built these network files. A rebuilt "
            f"network comes from commit {commit}, and it passed the validation "
            "cases of its pipeline. A carried-over network is the file of the "
            "previous data release: its pipeline and its sources did not change.",
            "",
            "To use a file, download it and load it with "
            '`GeoGraph.load_from_scgraph("FILE")`. This needs a version of '
            "scgraph that reads the file format version "
            f"{', '.join(map(str, format_versions))}. "
            '`GeoGraph.get_scgraph_info("FILE")` gives the sources of a file and '
            "its `content_sha256`. `networks.json` holds the full digests and the "
            "commit that built each file.",
            "",
            "| File | Size | Nodes | Arcs | Data up to | Status | `content_sha256` |",
            "|---|---|---|---|---|---|---|",
            *rows,
            "",
            "**Credits and licenses.** Cite the credit line of a network with "
            "the results that use it.",
            "",
            *credits,
            "",
        ]
    )


if __name__ == "__main__":
    assemble(*sys.argv[1:])
