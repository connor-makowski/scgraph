"""The cache directory of scgraph: what it holds and how it is filled.

This module is internal. It holds three things:

- `RELEASED_GEOGRAPHS`, the names of the released networks. `scgraph.network_release`
  lists them, with what the network release says of each one;
- `fetch_released_file`, which downloads the file of a released network into the
  cache directory;
- `find_cached_file`, which finds the network file of a build in the cache;
- the code of the methods of `GeoGraph` that load, build, list and clear the networks
  of scgraph: `load_network`, `build_network`, `list_networks`, `clear_cache`,
  `get_cache_info` and `list_buildable_networks`.

The methods of `GeoGraph` call these functions. `ARCHITECTURE.md`, section 6, gives
the layout of the cache directory.
"""

import gzip
import hashlib
import importlib
import json
import logging
import os
import re
import shutil
import types
import zlib
from pathlib import Path
from typing import Literal

import requests

from scgraph import files, network_file, network_release
from scgraph import built_in_geographs
from scgraph import network_release as pinned_network_release
from scgraph.files import is_offline
from scgraph.geograph import GeoGraph, LazyGeoGraph, _order_by_hilbert
from scgraph.utils import resolve_cache_dir
from scgraph._internal import log_step

logger = logging.getLogger(__name__)
# The record of the conversion of a published network keeps the logger name that it had
# in `scgraph.geograph`: the documents show this name, and a user filters on it.
_geograph_logger = logging.getLogger("scgraph.geograph")


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
# The names of the networks that scgraph builds: one module of `scgraph.pipelines` for
# each.
BUILDABLE_NETWORKS = (
    "eurostat_sea_lanes",
    "geofabrik_multimodal",
    "osm_world_multimodal",
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
        compressed = None
        try:
            with files.write_atomically(
                file, "download", folder=releases
            ) as download:
                compressed = download.with_name(f"{download.name}.gz")
                with log_step(
                    logger, "download the released network", {"url": url}
                ):
                    try:
                        files.download_file(url, compressed)
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
                    logger.info("Decompressing %s.scgraph.gz", stem)
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
                    logger.info("Checking the content_sha256 of %s", file.name)
                    found = network_file.check_content(download)
                if tag == network_release.TAG:
                    recorded = network_release.CONTENT_SHA256[stem]
                    if found != recorded:
                        raise ValueError(
                            f"{url} has the content_sha256 {found}, and scgraph "
                            f"records {recorded} for this file"
                        )
        except PermissionError:
            # Windows does not replace a file that a process has mapped. Another
            # process then downloaded the same file first, and the cache has it.
            if not file.is_file():
                raise
        finally:
            if compressed is not None:
                compressed.unlink(missing_ok=True)
    if content_sha256 is not None:
        found = network_file.get_scgraph_info(file)["content_sha256"]
        if found != content_sha256:
            raise ValueError(
                f"{file} has the content_sha256 {found}, not {content_sha256}"
            )
    return file


def join_source_values(pipeline, key: str) -> str:
    """Return one field of the sources of a pipeline, such as `credit` or `license`,
    as one string. Each value appears once."""
    return "; ".join(dict.fromkeys(s[key] for s in pipeline.SOURCES.values()))


def list_networks(
    cache_dir: str | os.PathLike | None = None,
    geograph_url: str = built_in_geographs.GEOGRAPH_URL,
) -> list[dict]:
    """List the networks that `GeoGraph.load_geograph` takes.

    The docstring of `GeoGraph.list_geographs` gives the arguments and the result.
    """
    cache_path = resolve_cache_dir(cache_dir)
    release_folder = cache_path.joinpath("releases", network_release.TAG)
    available = sorted(
        {
            *built_in_geographs.BUILT_IN_GEOGRAPHS,
            *RELEASED_GEOGRAPHS,
        }
    )
    # As in load_geograph: another URL hosts `.graphjson` files only
    released = set(RELEASED_GEOGRAPHS)
    if geograph_url != built_in_geographs.GEOGRAPH_URL:
        url = f"{geograph_url.rstrip('/')}/contents.txt"
        response = requests.get(url, timeout=60)
        if not response.ok:
            raise ConnectionError(
                f"Failed to fetch geograph list from '{url}'. "
                f"HTTP status: {response.status_code}."
            )
        released = set()
        available = sorted(
            line.removesuffix(".graphjson")
            for line in response.text.splitlines()
            if line.strip().endswith(".graphjson")
        )
    rows = []
    for name in available:
        if name in released:
            is_cached = any(
                release_folder.joinpath(name + suffix).is_file()
                for suffix in (".scgraph", ".no_shapes.scgraph")
            )
            about = {
                "kind": "released",
                **network_release.NETWORKS[name],
            }
        else:
            is_cached = cache_path.joinpath(f"{name}.graphjson").exists()
            # Another URL hosts networks that scgraph does not know
            about = (
                {
                    "kind": "built-in",
                    **built_in_geographs.BUILT_IN_GEOGRAPHS[name],
                }
                if geograph_url == built_in_geographs.GEOGRAPH_URL
                else {}
            )
        rows.append({"name": name, "cached": is_cached, **about})
    return rows


def clear_cache(
    cache_dir: str | os.PathLike | None = None,
    *,
    name: str | None = None,
    region: str | None = None,
) -> None:
    """Remove what scgraph keeps in the cache directory.

    The docstring of `GeoGraph.clear_geograph_cache` gives the arguments and the result.
    """
    if name is not None and name not in {
        *built_in_geographs.BUILT_IN_GEOGRAPHS,
        *RELEASED_GEOGRAPHS,
        *BUILDABLE_NETWORKS,
    }:
        raise ValueError(f"Unknown network '{name}'")
    if region is not None and (
        name is None or not re.fullmatch(r"[a-z0-9-]+(/[a-z0-9-]+)*", region)
    ):
        raise ValueError(f"Invalid region '{region}', or no name with it")
    cache_path = resolve_cache_dir(cache_dir)
    root = cache_path.joinpath("networks")

    def left(function, path, excinfo):
        # A file still open (Windows: a network loaded in this process) stays, as
        # an orphan that a later clear removes; its folder then stays too
        if function is not os.rmdir:
            logger.warning("Left %s in the cache: %s", path, excinfo[1])

    def remove(path):
        try:
            if path.is_dir():
                shutil.rmtree(path, onerror=left)
            else:
                path.unlink(missing_ok=True)
        except OSError as error:
            left(None, path, (None, error, None))

    # Only what scgraph writes there, so that a folder given as the cache keeps the
    # user's own files; then the folder itself if nothing else is left
    for published in built_in_geographs.BUILT_IN_GEOGRAPHS:
        if name in (None, published) and region is None:
            for suffix in (".graphjson", ".scgraph"):
                remove(cache_path.joinpath(published + suffix))
    if name is None:
        remove(root)
        remove(cache_path.joinpath("releases"))
        remove(cache_path.joinpath(".work"))  # failed or interrupted builds
    elif region is None:
        remove(root.joinpath(name))
        for stem in (name, f"{name}.no_shapes"):
            for file in cache_path.glob(f"releases/*/{stem}.scgraph"):
                remove(file)
    else:
        # Only this entry's files: a sub-region is an entry of its own, in a sub-folder
        folder = root.joinpath(name, region)
        for file in [*folder.glob("*.scgraph"), folder / "cache.json"]:
            remove(file)
    if cache_path.is_dir() and not any(cache_path.iterdir()):
        cache_path.rmdir()


def get_cache_info(cache_dir: str | os.PathLike | None = None) -> list[dict]:
    """List what the cache directory holds.

    The docstring of `GeoGraph.get_cache_info` gives the arguments and the result.
    """
    cache_path = resolve_cache_dir(cache_dir)
    info = [
        {
            "kind": "published",
            "name": name,
            "region": None,
            "file": str(file),
            "bytes": file.stat().st_size,
        }
        for name in built_in_geographs.BUILT_IN_GEOGRAPHS
        for suffix in (".graphjson", ".scgraph")
        if (file := cache_path.joinpath(name + suffix)).is_file()
    ]
    for file in sorted(cache_path.glob("releases/*/*.scgraph")):
        info.append(
            {
                "kind": "released",
                "name": file.name.split(".")[0],
                "region": None,
                "file": str(file),
                "bytes": file.stat().st_size,
                "network_release": file.parent.name,
            }
        )
    root = cache_path.joinpath("networks")
    for pointer in sorted(
        root.rglob("cache.json"), key=lambda pointer: pointer.parent
    ):
        file = find_cached_file(pointer)
        if file is None:
            continue  # not cached
        name, *region = pointer.parent.relative_to(root).parts
        try:
            header = network_file.get_scgraph_info(file)
            versions = (
                header["pipeline"]["version"],
                header["software"]["scgraph"],
            )
        except (ValueError, KeyError, TypeError):
            versions = None, None
        info.append(
            {
                "kind": "built",
                "name": name,
                "region": "/".join(region) or None,
                "file": str(file),
                "bytes": file.stat().st_size,
                "pipeline_version": versions[0],
                "scgraph": versions[1],
            }
        )
    for work in sorted(cache_path.glob(".work/*")):
        info.append(
            {
                "kind": "building",
                "name": work.name,
                "region": None,
                "file": str(work),
                "bytes": sum(
                    f.stat().st_size for f in work.rglob("*") if f.is_file()
                ),
            }
        )
    return info


def list_buildable_networks(
    cache_dir: str | os.PathLike | None = None,
) -> list[dict]:
    """List the networks that `GeoGraph.build_geograph` builds.

    The docstring of `GeoGraph.list_buildable_geographs` gives the arguments and the result.
    """
    root = resolve_cache_dir(cache_dir).joinpath("networks")
    listing = []
    for name in BUILDABLE_NETWORKS:
        network = importlib.import_module(f"scgraph.pipelines.{name}")
        needs_region = any(
            "{region}" in source["url"] for source in network.SOURCES.values()
        )
        folder = root.joinpath(name)
        built = [m for m in folder.rglob("cache.json") if find_cached_file(m)]
        listing.append(
            {
                "name": name,
                "description": " ".join(
                    network.__doc__.split("\n\n")[0].split()
                ),
                "credit": join_source_values(network, "credit"),
                "license": join_source_values(network, "license"),
                "needs_region": needs_region,
                "cached": bool(built),
                "cached_regions": (
                    sorted(
                        path.parent.relative_to(folder).as_posix()
                        for path in built
                    )
                    if needs_region
                    else []
                ),
            }
        )
    return listing


def load_network(
    name: str,
    cache_dir: str | os.PathLike | None,
    geograph_url: str,
    reduce_iterations: int,
    lazy: bool,
    local_files_only: bool | None,
    network_release: str | None,
    content_sha256: str | None,
    node_modes: list[str] | str | None,
    load_intermediate_nodes: bool,
) -> GeoGraph:
    """Load a network of `GeoGraph.load_geograph`, or a lazy geograph that loads it.

    The docstring of `GeoGraph.load_geograph` gives the arguments, the result and the
    errors. That method gives the deprecation warnings before it calls this function.
    """
    options = {
        "name": name,
        "cache_dir": cache_dir,
        "geograph_url": geograph_url,
        "reduce_iterations": reduce_iterations,
        "local_files_only": local_files_only,
        "network_release": network_release,
        "content_sha256": content_sha256,
        "node_modes": node_modes,
        "load_intermediate_nodes": load_intermediate_nodes,
    }
    if lazy:
        return LazyGeoGraph(lambda: _load_network(**options))
    return _load_network(**options)


def _load_network(
    name: str,
    cache_dir: str | os.PathLike | None,
    geograph_url: str,
    reduce_iterations: int,
    local_files_only: bool | None,
    network_release: str | None,
    content_sha256: str | None,
    node_modes: list[str] | str | None,
    load_intermediate_nodes: bool,
) -> GeoGraph:
    """Load the network of `load_network` now. The arguments are those of
    `GeoGraph.load_geograph`."""
    if local_files_only is None:
        local_files_only = is_offline()
    cache_path = resolve_cache_dir(cache_dir)
    # A caller that passes its own `geograph_url` hosts `.graphjson` files, and
    # one of them may have the name of a released network. That name then loads
    # the file of the caller.
    if (
        name in RELEASED_GEOGRAPHS
        and geograph_url == built_in_geographs.GEOGRAPH_URL
    ):
        released_file = fetch_released_file(
            name=name,
            tag=network_release,
            shapes=load_intermediate_nodes,
            content_sha256=content_sha256,
            cache_path=cache_path,
            local_files_only=local_files_only,
        )
        return GeoGraph.load_from_scgraph(
            str(released_file),
            reduce_iterations=reduce_iterations,
            node_modes=node_modes,
        )
    if (
        network_release,
        content_sha256,
        node_modes,
        load_intermediate_nodes,
    ) != (
        None,
        None,
        None,
        True,
    ):
        raise ValueError(
            f"'{name}' is not loaded from a network release: its name is not in "
            "the network release that this scgraph loads "
            f"({pinned_network_release.TAG}), or `geograph_url` is given. "
            "`network_release`, `content_sha256`, `node_modes` and "
            "`load_intermediate_nodes` do not apply to it"
        )
    cache_path.mkdir(parents=True, exist_ok=True)
    cached_file = cache_path.joinpath(f"{name}.graphjson")
    # Converted once into a network file beside it, which every later load reads
    converted = cache_path.joinpath(f"{name}.scgraph")
    if converted.exists():
        try:
            return GeoGraph.load_from_scgraph(
                str(converted),
                reduce_iterations=reduce_iterations,
                lazy=False,
            )
        except ValueError:  # damaged, or another format: converted again
            pass
    if not cached_file.exists():
        if local_files_only:
            raise FileNotFoundError(
                f"Geograph '{name}' is not in the cache ({cache_path}) and "
                "local_files_only=True (or SCGRAPH_OFFLINE=1) forbids downloading it"
            )
        GeoGraph.__fetch_geograph_to_cache__(name, cached_file, geograph_url)
    # Written in Hilbert order (nodes close on the globe get close ids): node ids
    # differ from the .graphjson's, which the nodes keep as their source_node_ids
    geograph = GeoGraph.load_from_graphjson(str(cached_file))
    geograph.node_modes = [{"name": None, "source": cached_file.name}]
    # To 1e-7 degree, as OSM: the file's compact encoding (a few published ports
    # have 9 decimals, from arcseconds)
    geograph.coordinate_dtype = "int32"
    for node in geograph.nodes:
        node[:] = round(node[0], 7), round(node[1], 7)
    with open(cached_file, "rb") as file:
        sha256 = hashlib.file_digest(file, "sha256").hexdigest()
    source = {
        "name": cached_file.name,
        "url": f"{geograph_url}/{cached_file.name}",
        "sha256": sha256,
    }
    try:
        geograph.metadata = {"sources": [source]}
        with log_step(
            _geograph_logger, "convert the published network", {"name": name}
        ):
            geograph.save_as_scgraph(str(converted))
    except OSError:
        # A cache that can't be written: the .graphjson is read at every load, its
        # nodes ordered as the file would have them
        geograph = _order_by_hilbert(geograph)
        geograph.reduce(reduce_iterations)
        if len(geograph.nodes):  # as load_from_scgraph
            geograph.snap_index  # noqa: B018 (reading it builds the index)
        return geograph
    del geograph  # one copy of the network in memory at a time
    return GeoGraph.load_from_scgraph(
        str(converted), reduce_iterations=reduce_iterations, lazy=False
    )


def build_network(
    name: (
        Literal[
            "eurostat_sea_lanes",
            "geofabrik_multimodal",
            "osm_world_multimodal",
        ]
        | types.ModuleType
    ),
    region: str | None,
    cache_dir: str | os.PathLike | None,
    reduce_iterations: int,
    lazy: bool,
    *,
    refresh: bool,
    local_files_only: bool | None,
    node_modes: list[str] | str | None,
    validate: bool,
) -> GeoGraph:
    """Build a network of `GeoGraph.build_geograph` and load it, or return a lazy
    geograph that does.

    The docstring of `GeoGraph.build_geograph` gives the arguments, the result and the
    errors.
    """
    if lazy:
        return LazyGeoGraph(
            lambda: GeoGraph.build_geograph(
                name=name,
                region=region,
                cache_dir=cache_dir,
                reduce_iterations=reduce_iterations,
                lazy=False,
                refresh=refresh,
                local_files_only=local_files_only,
                node_modes=node_modes,
                validate=validate,
            )
        )
    from scgraph.pipelines.network_builder import build_network_file

    return GeoGraph.load_from_scgraph(
        build_network_file(
            name,
            region,
            cache_dir,
            refresh=refresh,
            local_files_only=local_files_only,
            validate=validate,
        ),
        reduce_iterations=reduce_iterations,
        node_modes=node_modes,
    )
