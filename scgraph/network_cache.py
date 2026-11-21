"""The files of the released networks in the cache directory.

This module is internal. It holds three things:

- `RELEASED_GEOGRAPHS`, the names of the released networks. `scgraph.network_release`
  lists them, with what the network release says of each one;
- `fetch_released_file`, which downloads the file of a released network into the
  cache directory;
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
