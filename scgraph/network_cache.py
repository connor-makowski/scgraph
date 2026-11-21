"""The networks that `GeoGraph.load_geograph` loads, and their files in the cache.

This module is internal. It holds three things:

- the names of the networks: the seven built-in geographs of scgraph 3.6.0
  (`BUILT_IN_GEOGRAPHS`) and the released networks (`RELEASED_GEOGRAPHS`);
- the two downloads that put a network into the cache directory:
  `fetch_built_in_geograph` and `fetch_released_file`;
- `find_cached_file`, which finds the network file of a build in the cache.

The methods of `GeoGraph` call these functions. `ARCHITECTURE.md`, section 6, gives
the layout of the cache directory.
"""

import gzip
import json
import logging
import os
import re
import secrets
import shutil
import zlib
from pathlib import Path

import requests

from scgraph import network_file, network_release
from scgraph.utils import _log_step

logger = logging.getLogger(__name__)


def find_cached_file(pointer: Path) -> Path | None:
    """Return the network file that a `cache.json` names, or None if it is not there.

    Args:
        pointer: The path of a `cache.json`. It names a file of its own folder. The
            function keeps only the name, so it never returns a file of another
            folder.
    """
    try:
        file = pointer.parent.joinpath(
            Path(json.loads(pointer.read_text())["file"]).name
        )
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return file if file.is_file() else None


GEOGRAPH_URL = (
    "https://raw.githubusercontent.com/connor-makowski/scgraph/main/geographs"
)
# The seven networks of scgraph 3.6.0, published as `.graphjson` files at `GEOGRAPH_URL`,
# and what `list_geographs` says of each one. `superseded_by` names
# the released network that covers the same need with newer data. That network may
# hold more modes, and its results differ.
BUILT_IN_GEOGRAPHS = {
    "marnet": {
        "description": "Sea lanes of the world (Eurostat SeaRoute)",
        "superseded_by": "world_sea",
    },
    "north_america_rail": {
        "description": "Class I railroads of North America",
        "superseded_by": "north_america",
    },
    "oak_ridge_maritime": {
        "description": "Sea lanes of the world (Oak Ridge National Laboratory, 2000)",
        "superseded_by": "world_sea",
    },
    "us_freeway": {
        "description": "Freeways of the United States",
        "superseded_by": "north_america",
    },
    "world_highways_and_marnet": {
        "description": "Highways of the world, joined to the sea lanes of marnet",
        "superseded_by": "world_multimodal",
    },
    "world_highways": {
        "description": "Highways of the world",
        "superseded_by": "world_multimodal",
    },
    "world_railways": {
        "description": "Railways of the world",
        "superseded_by": "world_rail",
    },
}
_WORLD_PART = (
    "The part of world_multimodal between latitudes {} and {} and longitudes {} "
    "and {}, with every sea lane, port and airport of the world"
)
# What `list_geographs` says of each released network
RELEASED_DESCRIPTIONS = {
    "world_multimodal": "Main roads, railways, sea lanes and regular flights of the "
    "world, joined at ports, airports and rail terminals",
    "world_sea": "Sea lanes and ports of the world",
    "world_rail": "Railways and rail terminals of the world",
    "europe": _WORLD_PART.format(34, 72, -25, 45),
    "north_america": _WORLD_PART.format(7, 84, -170, -50),
    "south_america": _WORLD_PART.format(-57, 13, -82, -34),
    "africa": _WORLD_PART.format(-35, 38, -18, 52),
    "west_south_asia": _WORLD_PART.format(5, 45, 25, 98),
    "east_southeast_asia": _WORLD_PART.format(-11, 55, 92, 150),
    "north_asia": _WORLD_PART.format(40, 78, 45, 180),
    "oceania": _WORLD_PART.format(-50, 0, 110, 180),
}
# The names of the released networks: the networks of the network release that
# `network_release` pins. load_geograph downloads them as network files. Each network
# has two files: `network_release` lists the file without shapes under the name of
# the network followed by `.no_shapes`.
RELEASED_GEOGRAPHS = tuple(
    name
    for name in network_release.CONTENT_SHA256
    if not name.endswith(".no_shapes")
)
_RELEASE_URL = "https://github.com/connor-makowski/scgraph/releases/download"


def fetch_released_file(
    name: str,
    tag: str | None,
    shapes: bool,
    content_sha256: str | None,
    cache_path: Path,
    local_files_only: bool,
) -> Path:
    """Return the path, in the cache, of a network file of a network release. Download
    the file if the cache does not hold it.

    Example: `name="europe"` and `shapes=False`, for the network release
    `networks-2026.11.20`.

    1. The cache keeps the file as
       `releases/networks-2026.11.20/europe.no_shapes.scgraph`. If the file is there,
       the function makes no request and goes to step 6.
    2. The function downloads `europe.no_shapes.scgraph.gz` from the network release
       into `releases/`. A file of a network release is compressed with gzip.
    3. It decompresses the download, also into `releases/`.
    4. It checks the decompressed file. `network_file.check_content` computes the
       digest of the content, and compares it with the digest in the header of the
       file. For the pinned network release, the digest must also equal the digest that
       `network_release` records for this file.
    5. It renames the checked file to the path of step 1. The rename is atomic.
    6. If the caller gave `content_sha256`, the digest in the header must equal it.

    A file of the cache is therefore always whole, and a later load does not compute
    its digest again. A download that fails step 4 leaves no file in the cache. A file
    that fails step 6 stays in the cache, because it is a whole file of the network
    release: the caller asked for another content.

    Args:
        name: The name of a network of `RELEASED_GEOGRAPHS`.
        tag: The tag of the network release, or None for `network_release.TAG`.
        shapes: False for the file without the shapes of the edges.
        content_sha256: The digest that the file must have, or None.
        cache_path: The cache directory.
        local_files_only: If True, the function never downloads.

    Raises:
        ValueError: `tag` is not a tag, or a step 4 or 6 fails.
        FileNotFoundError: The file is not in the cache and `local_files_only` is
            True, or the network release does not have the file.
        ConnectionError: The server answers the download with another error status.
    """
    from scgraph.pipelines import download_file

    tag = network_release.TAG if tag is None else tag
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", tag):
        raise ValueError(
            f"Invalid network_release '{tag}': a network release is named by its tag, "
            f"such as '{network_release.TAG}'"
        )
    stem = name if shapes else f"{name}.no_shapes"
    file = cache_path.joinpath("releases", tag, f"{stem}.scgraph")
    if not file.is_file():
        if local_files_only:
            raise FileNotFoundError(
                f"The network '{stem}' of the network release '{tag}' is not in the "
                f"cache ({cache_path}) and local_files_only=True (or "
                "SCGRAPH_OFFLINE=1) forbids downloading it"
            )
        url = f"{_RELEASE_URL}/{tag}/{stem}.scgraph.gz"
        releases = cache_path.joinpath("releases")
        releases.mkdir(parents=True, exist_ok=True)
        download = releases.joinpath(
            f".{file.name}.{os.getpid()}.{secrets.token_hex(4)}.download"
        )
        compressed = download.with_name(f"{download.name}.gz")
        try:
            with _log_step(
                logger, "download the released network", {"url": url}
            ):
                try:
                    download_file(url, compressed)
                except requests.HTTPError as error:
                    if error.response.status_code == 404:
                        raise FileNotFoundError(
                            f"The network release '{tag}' has no file "
                            f"'{stem}.scgraph.gz' ({url})"
                        ) from error
                    raise ConnectionError(
                        f"Failed to download '{url}'. "
                        f"HTTP status: {error.response.status_code}."
                    ) from error
                try:
                    with (
                        gzip.open(compressed) as source,
                        open(download, "wb") as target,
                    ):
                        shutil.copyfileobj(source, target)
                except (EOFError, gzip.BadGzipFile, zlib.error) as error:
                    raise ValueError(
                        f"{url}: damaged download ({error})"
                    ) from error
                compressed.unlink()  # frees the disk before the check
                found = network_file.check_content(download)
            if tag == network_release.TAG:
                recorded = network_release.CONTENT_SHA256[stem]
                if found != recorded:
                    raise ValueError(
                        f"{url} has the content_sha256 {found}, and scgraph "
                        f"records {recorded} for this file"
                    )
            file.parent.mkdir(exist_ok=True)
            try:
                os.replace(download, file)
            except PermissionError:
                # Windows does not replace a file that a process has mapped. Another
                # process then downloaded the same file first, and the cache has it.
                if not file.is_file():
                    raise
        finally:
            compressed.unlink(missing_ok=True)
            download.unlink(missing_ok=True)
    if content_sha256 is not None:
        found = network_file.get_scgraph_info(file)["content_sha256"]
        if found != content_sha256:
            raise ValueError(
                f"{file} has the content_sha256 {found}, not {content_sha256}"
            )
    return file


def fetch_built_in_geograph(
    name: str, cached_file: Path, geograph_url: str
) -> None:
    """Download the `.graphjson` file of a built-in geograph into the cache.

    Args:
        name: The name of the built-in geograph.
        cached_file: The path of the file to write, in the cache.
        geograph_url: The URL of the folder that holds `<name>.graphjson`.

    Raises:
        FileNotFoundError: The URL has no file of this name.
        ConnectionError: The server answers with another error status.
    """
    url = f"{geograph_url}/{name}.graphjson"
    response = requests.get(url, timeout=60)
    if response.status_code == 404:
        raise FileNotFoundError(
            f"Geograph '{name}' not found at '{url}'. "
            f"Check that the name is correct and the file exists in the scgraph GitHub repository."
        )
    if not response.ok:
        raise ConnectionError(
            f"Failed to download geograph '{name}' from '{url}'. "
            f"HTTP status: {response.status_code}."
        )
    # The download is written next to the cache file, then moved onto it. A download that
    # fails never leaves a part of a file under the name that later loads read.
    download = cached_file.with_name(
        f".{cached_file.name}.{os.getpid()}.{secrets.token_hex(4)}.download"
    )
    try:
        download.write_bytes(response.content)
        os.replace(download, cached_file)
    except BaseException:
        download.unlink(missing_ok=True)
        raise
