"""The methods of `GeoGraph` that load, build, list and clear the networks of scgraph.

This module is internal. A network of scgraph is a network that scgraph loads or builds
by name. `GeoGraphNetworks` is the mixin of `GeoGraph` that holds these methods:
`load_geograph`, `build_geograph`, `list_geographs`, `list_buildable_geographs`,
`clear_geograph_cache` and `list_geograph_cache`. `scgraph.geograph` imports it.

The functions of the module do the work of these methods. They keep the files of the
networks in the cache directory: they find them there and download them. The module
also holds four other things:

- `RELEASED_GEOGRAPHS`, the names of the released networks. `scgraph.network_release`
  lists them, with what the network release says of each one;
- `BUILDABLE_NETWORKS`, the names of the networks that scgraph can build;
- `fetch_released_file`, which downloads the file of a released network into the
  cache directory;
- `find_cached_file`, which finds the network file of a build in the cache.

`ARCHITECTURE.md`, section 6, gives the layout of the cache directory.
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
from typing import TYPE_CHECKING, Literal

import requests

from scgraph import files, network_file
from scgraph import built_in_geographs
from scgraph import network_release as pinned_network_release
from scgraph.files import is_offline
from scgraph.utils import resolve_cache_dir
from scgraph.step_logs import log_step

if TYPE_CHECKING:  # Only for annotations.
    from scgraph.geograph import GeoGraph

logger = logging.getLogger(__name__)
# The record of the conversion of a built-in network keeps the logger name that it had
# in `scgraph.geograph`: the documents show this name, and a user filters on it.
_geograph_logger = logging.getLogger("scgraph.geograph")


def find_cached_file(cache_json_path: Path) -> Path | None:
    """Return the network file that a `cache.json` names, or None if it is not there.

    Args:
        cache_json_path: The path of a `cache.json`. It names a file of its own folder. The
            function keeps only the name, so it never returns a file of another
            folder.
    """
    try:
        file = cache_json_path.parent.joinpath(
            Path(json.loads(cache_json_path.read_text())["file"]).name
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
    for name in pinned_network_release.CONTENT_SHA256
    if not name.endswith(".no_shapes")
)
# The names of the networks that scgraph builds: one module of `scgraph.pipelines` for
# each.
BUILDABLE_NETWORKS = (
    "eurostat_sea_lanes",
    "osm_region_multimodal",
    "osm_world_multimodal",
)
_RELEASE_URL = "https://github.com/connor-makowski/scgraph/releases/download"


def fetch_released_file(
    name: str,
    tag: str | None,
    load_intermediate_nodes: bool,
    content_sha256: str | None,
    cache_path: Path,
    local_files_only: bool,
) -> Path:
    """Return the path, in the cache, of a network file of a network release. Download
    the file if the cache does not hold it.

    Example: `name="europe"` and `load_intermediate_nodes=False`, for the network release
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
        load_intermediate_nodes: False for the file without the intermediate nodes
            of the edges.
        content_sha256: The digest that the file must have, or None.
        cache_path: The cache directory.
        local_files_only: If True, the function never downloads.

    Raises:
        ValueError: `tag` is not a tag, or a step 4 or 6 fails.
        FileNotFoundError: The file is not in the cache and `local_files_only` is
            True, or the network release does not have the file.
        ConnectionError: The server answers the download with another error status.
    """
    tag = pinned_network_release.TAG if tag is None else tag
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", tag):
        raise ValueError(
            f"Invalid network_release '{tag}': a network release is named by its tag, "
            f"such as '{pinned_network_release.TAG}'"
        )
    stem = name if load_intermediate_nodes else f"{name}.no_shapes"
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
                if tag == pinned_network_release.TAG:
                    recorded = pinned_network_release.CONTENT_SHA256[stem]
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
    release_folder = cache_path.joinpath("releases", pinned_network_release.TAG)
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
                **pinned_network_release.NETWORKS[name],
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
    for built_in in built_in_geographs.BUILT_IN_GEOGRAPHS:
        if name in (None, built_in) and region is None:
            for suffix in (".graphjson", ".scgraph"):
                remove(cache_path.joinpath(built_in + suffix))
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


def list_geograph_cache(
    cache_dir: str | os.PathLike | None = None,
) -> list[dict]:
    """List what the cache directory holds.

    The docstring of `GeoGraph.list_geograph_cache` gives the arguments and the result.
    """
    cache_path = resolve_cache_dir(cache_dir)
    info = [
        {
            "kind": "built-in",
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
    from scgraph.pipelines.network_builder import find_region_url

    root = resolve_cache_dir(cache_dir).joinpath("networks")
    listing = []
    for name in BUILDABLE_NETWORKS:
        network = importlib.import_module(f"scgraph.pipelines.{name}")
        needs_region = find_region_url(network) is not None
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
) -> "GeoGraph":
    """Load a network of `GeoGraph.load_geograph`, or a lazy geograph that loads it.

    The docstring of `GeoGraph.load_geograph` gives the arguments, the result and the
    errors. That method gives the deprecation warnings before it calls this function.
    """
    from scgraph.geograph import LazyGeoGraph

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
) -> "GeoGraph":
    """Load the network of `load_network` now. The arguments are those of
    `GeoGraph.load_geograph`."""
    from scgraph.geograph import GeoGraph
    from scgraph.geograph_io import renumber_in_hilbert_order

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
            load_intermediate_nodes=load_intermediate_nodes,
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
    # differ from the .graphjson's, which the nodes keep as their external_node_ids
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
            _geograph_logger, "convert the built-in network", {"name": name}
        ):
            geograph.save_as_scgraph(str(converted))
    except OSError:
        # A cache that can't be written: the .graphjson is read at every load, its
        # nodes ordered as the file would have them
        geograph = renumber_in_hilbert_order(geograph)
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
            "osm_region_multimodal",
            "osm_world_multimodal",
        ]
        | None
    ),
    region: str | None,
    cache_dir: str | os.PathLike | None,
    reduce_iterations: int,
    lazy: bool,
    *,
    pipeline: types.ModuleType | None,
    refresh: bool,
    local_files_only: bool | None,
    node_modes: list[str] | str | None,
    run_validation_cases: bool,
) -> "GeoGraph":
    """Build a network of `GeoGraph.build_geograph` and load it, or return a lazy
    geograph that does.

    The docstring of `GeoGraph.build_geograph` gives the arguments, the result and the
    errors.
    """
    from scgraph.geograph import GeoGraph, LazyGeoGraph

    if lazy:
        return LazyGeoGraph(
            lambda: GeoGraph.build_geograph(
                name=name,
                region=region,
                cache_dir=cache_dir,
                reduce_iterations=reduce_iterations,
                lazy=False,
                pipeline=pipeline,
                refresh=refresh,
                local_files_only=local_files_only,
                node_modes=node_modes,
                run_validation_cases=run_validation_cases,
            )
        )
    from scgraph.pipelines.network_builder import build_network_file

    return GeoGraph.load_from_scgraph(
        build_network_file(
            name,
            region,
            cache_dir,
            pipeline=pipeline,
            refresh=refresh,
            local_files_only=local_files_only,
            run_validation_cases=run_validation_cases,
        ),
        reduce_iterations=reduce_iterations,
        node_modes=node_modes,
    )


class GeoGraphNetworks:
    @staticmethod
    def __fetch_geograph_to_cache__(
        name: str, cached_file: Path, geograph_url: str
    ) -> None:
        """
        Function:

        - Download a built-in GeoGraph file from GitHub into the cache directory.

        Required Arguments:

        - `name`
            - Type: str
            - What: The name of the built-in geograph to fetch
        - `cached_file`
            - Type: Path
            - What: The destination path in the cache to write the file to
        """
        built_in_geographs.fetch_built_in_geograph(
            name, cached_file, geograph_url
        )

    @staticmethod
    def load_geograph(
        name: str,
        cache_dir: str | os.PathLike | None = None,
        geograph_url: str = built_in_geographs.GEOGRAPH_URL,
        reduce_iterations: int = 0,
        lazy: bool = False,
        *,
        local_files_only: bool | None = None,
        network_release: str | None = None,
        content_sha256: str | None = None,
        node_modes: list[str] | str | None = None,
        load_intermediate_nodes: bool = True,
    ) -> "GeoGraph":
        """
        Function:

        - Load a built-in GeoGraph by name, using a local cache.
        - A network release is a set of networks that the maintainers of scgraph build from open sources and publish together under one tag. A network of a network release is a released network. The name of a released network, such as `europe`, `world_sea` or `world_multimodal`, loads that network. `list_geographs` gives every name, and `guides/networks.md` describes each network (section *Released Networks*).
        - For such a name, the first call downloads the network file, decompresses it, checks its content, then keeps it in the cache. Later calls read the cache without any network request. The arguments `network_release`, `content_sha256`, `node_modes` and `load_intermediate_nodes` apply to these networks only.
        - The points below apply to the seven networks of scgraph 3.6.0 (`marnet`, `us_freeway`, ...), which are published as `.graphjson` files.
        - On first call for a given name, downloads the .graphjson file from GitHub into the cache directory.
        - On subsequent calls, loads directly from cache without any network requests.
        - The first load converts the .graphjson into a network file beside it (`<name>.scgraph`, much faster to load), which later loads read; the .graphjson is kept, and a damaged conversion is made again from it.
        - The conversion orders the nodes along a Hilbert curve, so that nodes close on the globe get close ids: node ids differ from those of the .graphjson (lengths do not; of two routes of exactly equal length, another may be returned), and `external_node_ids[i]` is node i's id in the .graphjson (its id in scgraph 3.6.0). `load_from_graphjson` on the cached .graphjson keeps its numbering.
        - With `local_files_only=True` (or the environment variable `SCGRAPH_OFFLINE=1`), never downloads: a geograph that is not in the cache raises a FileNotFoundError.

        Required Arguments:

        - `name`
            - Type: str
            - What: The name of the built-in geograph to load
            - Examples: 'marnet', 'north_america_rail', 'oak_ridge_maritime', 'us_freeway'

        Optional Arguments:

        - `cache_dir`
            - Type: str | None
            - What: Path to the local cache directory where geograph files are stored
            - Default: None: the `SCGRAPH_CACHE_DIR` environment variable if set, else the platform's cache directory
                - Linux:   ~/.cache/scgraph/
                - macOS:   ~/Library/Caches/scgraph/
                - Windows: %LOCALAPPDATA%\\scgraph\\
        - `geograph_url`
            - Type: str
            - What: The base URL where the built-in geograph .graphjson files are hosted
            - Note: With another URL than the default, every name loads `<name>.graphjson` from that URL, also the name of a released network
            - Note: Deprecated. A call that passes another URL than the default gets a `DeprecationWarning`, and scgraph 5.0 removes the parameter. To load your own network, use `load_from_graphjson` or `load_from_scgraph`
        - `reduce_iterations`
            - Type: int
            - What: Number of reduction iterations to perform upon loading. If 0, no reduction is done. If -1, reduces iteratively until convergence.
            - Default: 0
        - `lazy`
            - Type: bool
            - What: Whether to delay loading/fetching the geograph until its first use
            - Default: False
        - `local_files_only`
            - Type: bool | None
            - What: Whether to use only the cache, without any network request
            - Default: None: True if the environment variable `SCGRAPH_OFFLINE` is `1`, else False
        - `network_release`
            - Type: str | None
            - What: The tag of the network release to load, for example 'networks-2026.11.20'
            - Default: None: the network release that this version of scgraph loads (`scgraph.network_release.TAG`)
        - `content_sha256`
            - Type: str | None
            - What: The `content_sha256` that the network file must have. It is the SHA-256 digest of the content of the file, and `get_scgraph_info` gives it. A file with another digest raises a ValueError. Pass it with `network_release` to load exactly the network of an earlier computation.
            - Default: None
        - `node_modes`
            - Type: list[str] | str | None
            - What: The names of the node modes to load, as in `load_from_scgraph`, for example `["road"]`
            - Default: None (every node mode)
        - `load_intermediate_nodes`
            - Type: bool
            - What: Whether to load the shapes of the edges. The shape of an edge is the list of points that draw it on a map between its two nodes. False downloads a file of about half the size. The route lengths are the same, and a `coordinate_path` then goes in a straight line from node to node.
            - Default: True

        Raises:

        - `ValueError` if the downloaded file is damaged, or if it is not the file that scgraph records for the network release that it loads by default. The file does not enter the cache.
        - `ValueError` if the file does not have the digest of `content_sha256`, or if `network_release` is not a tag
        - `ValueError` if `network_release`, `content_sha256`, `node_modes` or `load_intermediate_nodes` is passed for a network that is not loaded from a network release
        - `FileNotFoundError` if the network release does not have the file, or with `local_files_only` if the file is not in the cache
        - `ConnectionError` if the server refuses the download
        """
        # The warnings come from this call, also for a lazy load that reads the network
        # later.
        built_in_geographs.warn_deprecated_load(name, geograph_url)

        return load_network(
            name,
            cache_dir,
            geograph_url,
            reduce_iterations,
            lazy,
            local_files_only,
            network_release,
            content_sha256,
            node_modes,
            load_intermediate_nodes,
        )

    @staticmethod
    def list_geographs(
        cache_dir: str | os.PathLike | None = None,
        geograph_url: str = built_in_geographs.GEOGRAPH_URL,
    ) -> list[dict]:
        """
        Function:

        - List the networks that `load_geograph` takes, indicating which are already cached locally.
        - The published geographs are a fixed list, listed without any network request; for another `geograph_url`, the names are read from the `contents.txt` file at that URL.
        - The list holds the seven networks of scgraph 3.6.0 and the networks of the network release that this version of scgraph loads (`scgraph.network_release.TAG`).

        Optional Arguments:

        - `cache_dir`
            - Type: str | None
            - What: Path to the local cache directory to check for cached files
            - Default: None: the `SCGRAPH_CACHE_DIR` environment variable if set, else the platform's cache directory
                - Linux:   ~/.cache/scgraph/
                - macOS:   ~/Library/Caches/scgraph/
                - Windows: %LOCALAPPDATA%\\scgraph\\
        - `geograph_url`
            - Type: str
            - What: The base URL where the geograph files and contents.txt are hosted
            - Default: https://raw.githubusercontent.com/connor-makowski/scgraph/main/geographs

        Returns:

        - A list of dicts, one per available geograph, sorted by name:
            - `name`: str — the geograph name (without extension)
            - `cached`: bool — whether the file is already in the local cache (for a released network: its file of that release, with or without shapes)
            - With the default `geograph_url`, also:
                - `kind`: str — `"released"` for a network of the network release, `"built-in"` for a network of scgraph 3.6.0
                - `description`: str — what the network holds
                - for `"released"`: `nodes`, `edges`, `download_mb` and `download_mb_without_intermediate_nodes` (the size of the two downloads), and `data_up_to` (the time of the newest source data, or None when no source gives a time)
                - for `"built-in"`: `superseded_by`, the name of the released network that covers the same need with newer data; that network may hold more node modes (load it with `node_modes`), and its results differ
        """
        built_in_geographs.warn_deprecated_url(geograph_url)
        return list_networks(cache_dir=cache_dir, geograph_url=geograph_url)

    @staticmethod
    def clear_geograph_cache(
        cache_dir: str | os.PathLike | None = None,
        *,
        name: str | None = None,
        region: str | None = None,
    ) -> None:
        """
        Function:

        - Remove what scgraph keeps in the local cache directory: the built-in geographs `load_geograph` downloaded (and their `.scgraph` conversions), the network files it downloaded from network releases (under `releases/`) and the networks `build_geograph` built (under `networks/`)
        - With `name` (and `region`), remove only that network: its built-in geograph, its files of every network release, and its built networks (of every region, or of `region` only)
        - Other files in the directory are kept; the directory itself is removed if nothing else is left in it
        - On Windows, the files of a network still loaded in this process can't be removed: they are left in place, with a logging warning that names them, until a later clear

        Optional Arguments:

        - `cache_dir`
            - Type: str | None
            - What: Path to the local cache directory to clear
            - Default: None: the `SCGRAPH_CACHE_DIR` environment variable if set, else the platform's cache directory
                - Linux:   ~/.cache/scgraph/
                - macOS:   ~/Library/Caches/scgraph/
                - Windows: %LOCALAPPDATA%\\scgraph\\
        - `name`
            - Type: str | None
            - What: The network to remove, by the name `load_geograph` or `build_geograph` take (not a pipeline module of one's own)
            - Default: None: every network
        - `region`
            - Type: str | None
            - What: With `name`, the region of the built network to remove (its sub-regions are kept)
            - Default: None: every region
        """
        return clear_cache(cache_dir=cache_dir, name=name, region=region)

    @staticmethod
    def list_geograph_cache(
        cache_dir: str | os.PathLike | None = None,
    ) -> list[dict]:
        """
        Function:

        - List what scgraph keeps in the local cache directory, read from disk only, without any network request
        - Unlike `list_geographs` and `list_buildable_geographs`, which list what can be loaded or built

        Optional Arguments:

        - `cache_dir`
            - Type: str | None
            - What: Path to the local cache directory
            - Default: None: the `SCGRAPH_CACHE_DIR` environment variable if set, else the platform's cache directory (as in `load_geograph`)

        Returns:

        - A list of dicts, one per file or folder:
            - `kind`: str — `"built-in"` (a built-in geograph `load_geograph` downloaded, `.graphjson`, or its conversion, `.scgraph`), `"released"` (a network file `load_geograph` downloaded from a network release), `"built"` (a network `build_geograph` built) or `"building"` (the work folder of a build that is running, has failed or was interrupted; `clear_geograph_cache()` removes it)
            - `name`: str | None — the network name
            - `region`: str | None — the region of a built network, if it has one
            - `file`: str — the path of the file or folder
            - `bytes`: int — its size
            - for `"released"` only: `network_release`, the tag of the network release
            - for `"built"` only: `pipeline_version` and `scgraph`, the versions of the network's pipeline and of scgraph that built it, read from the file (None if it can't be read)
        """
        return list_geograph_cache(cache_dir=cache_dir)

    @staticmethod
    def build_geograph(
        name: (
            Literal[
                "eurostat_sea_lanes",
                "osm_region_multimodal",
                "osm_world_multimodal",
            ]
            | None
        ) = None,
        region: str | None = None,
        cache_dir: str | os.PathLike | None = None,
        reduce_iterations: int = 0,
        lazy: bool = False,
        *,
        pipeline: types.ModuleType | None = None,
        refresh: bool = False,
        local_files_only: bool | None = None,
        node_modes: list[str] | str | None = None,
        run_validation_cases: bool = False,
    ) -> "GeoGraph":
        """
        Function:

        - Download the online sources of a reference network once, build the network on this machine and keep it in the local cache; later calls load it from the cache, without any network request, until an upgrade of scgraph changes how that network is built
        - With `local_files_only=True` (or the environment variable `SCGRAPH_OFFLINE=1`), nothing is downloaded: a network built with another version of its pipeline is loaded with a warning (one of another file format is refused), and one that is not in the cache raises a FileNotFoundError
        - Sources can take several GB (an OpenStreetMap extract of a country): a download above 100 MB is announced with a logging warning before it starts; `logging.basicConfig(level=logging.INFO)` shows each download and the credit to cite, and the DEBUG level shows each step of the build with its counts
        - These networks are not the files that `load_geograph` returns: their node numbers differ, and the road and rail networks have more nodes, which `reduce_iterations=-1` removes for routing
        - The network file's header says what built it (pipeline, sources and the time their data is up to, software): `GeoGraph.get_scgraph_info(file)` reads it
        - `GeoGraph.list_buildable_geographs()` lists the networks, who to credit and what is already in the cache

        Required Arguments: one of `name` and `pipeline`

        - `name`
            - Type: str | None
            - What: The name of a network of scgraph (see `GeoGraph.list_buildable_geographs()`)
        - `pipeline`
            - Type: module | None
            - What: A pipeline module of your own, with the contract of `scgraph.pipelines` (for example a copy of one, adapted); it is cached under its last name (`my.cycleways` in `networks/cycleways/`), which must not be the name of a network of scgraph; two modules with the same last name share that cache entry, and `list_buildable_geographs` does not list it

        - The runner behind this function, `scgraph.pipelines.network_builder.build_network_file`, has one more option: keeping the work folder of a long build to resume it.

        Optional Arguments:

        - `region`
            - Type: str | None
            - What: The region of a network that needs one (`needs_region` in `list_buildable_geographs()`, or a pipeline with `{region}` in a source URL); for `osm_region_multimodal`, the path of a Geofabrik extract, as in its download URL: 'europe/luxembourg', 'north-america/us/texas' (all of them: https://download.geofabrik.de/index-v1-nogeom.json)
            - Default: None
        - `cache_dir`
            - Type: str | None
            - What: Path to the local cache directory
            - Default: None: the `SCGRAPH_CACHE_DIR` environment variable if set, else the platform's cache directory (as in `load_geograph`)
        - `reduce_iterations`
            - Type: int
            - What: Number of reduction iterations to perform upon loading. If 0, no reduction is done. If -1, reduces iteratively until convergence.
            - Default: 0
        - `lazy`
            - Type: bool
            - What: Whether to delay downloading or loading the geograph until its first use
            - Default: False
        - `refresh`
            - Type: bool
            - What: Whether to download the sources and build the network again even if the cache holds a current build
            - Default: False
        - `local_files_only`
            - Type: bool | None
            - What: Whether to use only the cache, without any network request
            - Default: None: True if the environment variable `SCGRAPH_OFFLINE` is `1`, else False
        - `node_modes`
            - Type: list[str] | str | None
            - What: The names of the node modes to load from the built network, as in `load_from_scgraph`, for example `["road"]`
            - Default: None: every node mode
        - `run_validation_cases`
            - Type: bool
            - What: Whether to check the built network against the validation cases of its pipeline; a network that fails is not kept in the cache, and a RuntimeError names the failed cases; a network that the cache already holds is checked as it is, and stays
            - Default: False

        Returns:

        - The GeoGraph of the network (a LazyGeoGraph if `lazy`); `scgraph_file` gives the path of its network file

        Raises:

        - `RuntimeError` with `run_validation_cases` if the network fails a validation case
        - `ValueError` if `node_modes` names a node mode that the network does not have
        - `ValueError` for not one of `name` and `pipeline`, an unknown name, a pipeline module named like a network of scgraph, a missing, refused or invalid region, or a region without a source, before any large download; with `local_files_only`, for `refresh=True` or a cached network of another file format
        - `FileNotFoundError` with `local_files_only` if the network is not in the cache
        - `ImportError` for the OpenStreetMap networks if `osmium` is not installed (`pip install scgraph[osm]`), before downloading the extract
        - `requests.HTTPError` or `ConnectionError` if a source can't be downloaded; a network already cached stays there. A build that fails keeps its downloaded sources in the work folder (`.work/` of the cache directory). The next call resumes from it. `clear_geograph_cache()` removes it
        """
        return build_network(
            name,
            region,
            cache_dir,
            reduce_iterations,
            lazy,
            pipeline=pipeline,
            refresh=refresh,
            local_files_only=local_files_only,
            node_modes=node_modes,
            run_validation_cases=run_validation_cases,
        )

    @staticmethod
    def list_buildable_geographs(
        cache_dir: str | os.PathLike | None = None,
    ) -> list[dict]:
        """
        Function:

        - List the networks that `build_geograph` builds from their online sources, without any network request
        - Unlike `list_geographs`, which lists the published files that `load_geograph` returns

        Optional Arguments:

        - `cache_dir`
            - Type: str | None
            - What: Path to the local cache directory to check for built networks
            - Default: None: the `SCGRAPH_CACHE_DIR` environment variable if set, else the platform's cache directory (as in `load_geograph`)

        Returns:

        - A list of dicts, one per network, sorted by name:
            - `name`: str — the value to pass as `name`
            - `description`: str — what the network is and where it comes from
            - `credit`: str — who to credit with results
            - `license`: str — the licences of the sources (SPDX identifiers; `NOASSERTION` when not established)
            - `needs_region`: bool — whether `build_geograph` needs a `region`
            - `cached`: bool — whether a build is already in the cache (for a network with regions: of any region)
            - `cached_regions`: list[str] — the regions already built (empty for a network without regions)
        """
        return list_buildable_networks(cache_dir=cache_dir)
