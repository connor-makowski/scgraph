"""The runner of the pipelines: download the sources of a network, build it and keep it in
the cache (`GeoGraph.build_geograph`).

`python -m scgraph.pipelines.build NAME [--region R] [--cache-dir D]` builds a network
without loading it and prints the path of its file.
"""

import argparse
import difflib
import hashlib
import importlib
import json
import logging
import os
import re
import shutil
import tempfile
import types
import warnings
from datetime import datetime, timezone
from pathlib import Path

import requests

from scgraph import network_file
from scgraph.geograph import GeoGraph, _cached_file, _joined
from scgraph.utils import resolve_cache_dir

# The runner's messages keep the name they had in geograph.py
logger = logging.getLogger(__name__)

# Written in networks/ of the cache: backup and archiving tools skip a tagged directory
_CACHEDIR_TAG = (
    "Signature: 8a477f597d28d172789f06886806bc55\n"
    "# This file is a cache directory tag created by scgraph."
    " For information about cache directory tags, see https://bford.info/cachedir/\n"
)


def build_file(
    name: str | types.ModuleType,
    region: str | None = None,
    cache_dir: str | None = None,
    *,
    refresh: bool = False,
    local_files_only: bool | None = None,
    validate: bool = False,
    stream: bool = False,
) -> str:
    """Build the network into the local cache and return its file path.

    Args:
        name: Name of a buildable pipeline or imported pipeline module.
        region: Geographic sub-region identifier (e.g. 'europe/denmark').
        cache_dir: Optional custom cache directory.
        refresh: Force rebuild even if a current cached artifact exists.
        local_files_only: Forbid downloading missing network sources.
        validate: Run Stage 4 validation checks against declarative cases.
        stream: Stream OSM extracts via HTTP byte ranges instead of downloading.

    Returns:
        Absolute path to the built .scgraph network file.

    Raises:
        ValueError: On unknown pipeline names or invalid region parameters.
        FileNotFoundError: If the network is uncached in offline mode.
        RuntimeError: If Stage 4 validation fails.
    """
    if local_files_only is None:
        local_files_only = os.environ.get("SCGRAPH_OFFLINE") == "1"
    from scgraph import pipelines

    if isinstance(name, types.ModuleType):
        network, name = name, name.__name__.rpartition(".")[2]
        # Its cache entry would be a built-in's (each would load the other), or a
        # path outside the cache
        if not re.fullmatch(r"\w+", name) or (
            name in pipelines.NAMES
            and network.__name__ != f"scgraph.pipelines.{name}"
        ):
            raise ValueError(
                f"Invalid pipeline module name '{network.__name__}'"
            )
    elif name not in pipelines.NAMES:
        close = difflib.get_close_matches(name, pipelines.NAMES, n=3)
        hint = f" Did you mean {', '.join(map(repr, close))}?" if close else ""
        raise ValueError(
            f"Unknown network '{name}'.{hint} Available: {', '.join(pipelines.NAMES)}"
        )
    else:
        network = importlib.import_module(f"scgraph.pipelines.{name}")
    regional = any(
        "{region}" in source["url"] for source in network.SOURCES.values()
    )
    where = f"the path of a Geofabrik extract, for example 'europe/luxembourg' (see https://download.geofabrik.de)"
    if regional and region is None:
        raise ValueError(f"'{name}' needs a region: {where}")
    if not regional and region is not None:
        raise ValueError(f"'{name}' has no region")
    # Region names are Geofabrik paths; nothing else may reach the cache path
    if region is not None and not re.fullmatch(
        r"[a-z0-9-]+(/[a-z0-9-]+)*", region
    ):
        raise ValueError(f"Invalid region '{region}': {where}")
    cache = resolve_cache_dir(cache_dir)
    folder = cache.joinpath("networks", name, region or "")
    pointer = folder.joinpath("cache.json")
    # cache.json names the network file, which is named by its content
    cached_file = _cached_file(pointer)
    cached = cached_file is not None
    # Built again for another pipeline version, or a file this scgraph can't read
    if cached:
        try:
            built_by = network_file.get_scgraph_info(cached_file)["pipeline"][
                "version"
            ]
        except (
            ValueError,
            KeyError,
            TypeError,
        ):  # damaged, or another format
            built_by = None
    stale = cached and built_by != network.PIPELINE_VERSION
    offline = "local_files_only=True (or SCGRAPH_OFFLINE=1)"
    if local_files_only:
        if refresh:
            raise ValueError(f"refresh=True downloads: not with {offline}")
        if not cached:
            raise FileNotFoundError(
                f"{name} is not in the cache ({folder}) and {offline} "
                "forbids building it"
            )
        if built_by is None:
            raise ValueError(
                f"The cached {name} can't be read (damaged, or a file format other "
                f"than {network_file.VERSION}): build it again without {offline}"
            )
        if stale:
            warnings.warn(
                f"The cached {name} was built with pipeline version "
                f"{built_by}, now {network.PIPELINE_VERSION}; loading it as {offline}"
            )
    elif stale:
        logger.warning(
            "The cached %s was built by another version of its pipeline or "
            "of the file format; building it again",
            name,
        )
    if not local_files_only and (refresh or not cached or stale):
        # The tag goes in networks/, scgraph's own folder: a cache_dir given by the user
        # may hold other files, which backups must not skip
        cache.joinpath("networks").mkdir(parents=True, exist_ok=True)
        cache.joinpath("networks", "CACHEDIR.TAG").write_text(_CACHEDIR_TAG)
        # The only clock time: in cache.json, not in the file
        downloaded = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        files, sources = {}, []
        # One folder per build, so that builds in parallel do not share files; at the
        # root of the cache, outside `networks/`, where no GeoGraph may be saved
        work = Path(tempfile.mkdtemp(prefix=".building-", dir=cache))
        building = work.joinpath(f"{name}.scgraph")
        try:
            for source, about in network.SOURCES.items():
                template = about["url"]
                url = template.format(region=region)
                # Same extension as the URL, by which readers such as osmium detect the format
                files[source] = work.joinpath(
                    source + "".join(Path(url).suffixes)
                )
                # A source's own hook, else the module's, else a plain download
                hook = about.get("download")
                if stream and about.get("url", "").endswith(".osm.pbf"):
                    from scgraph.pipelines.steps.stage1_extract import osm

                    download = osm.download_streamed
                else:
                    download = hook or getattr(
                        network, "download", pipelines.download_file
                    )
                try:
                    # It may return what it learnt of the source: its `version`
                    learnt = download(url, str(files[source]))
                except requests.HTTPError as error:
                    if (
                        "{region}" in template
                        and error.response.status_code == 404
                    ):
                        raise ValueError(
                            f"No extract '{region}' on Geofabrik; the region is {where}"
                        ) from error
                    raise
                # A source's own hook says what identifies it (a streamed file is
                # not on disk); else, or if it says nothing, the downloaded file
                measured = {}
                if hook is None or not learnt:
                    with open(files[source], "rb") as file:
                        measured = {
                            "sha256": hashlib.file_digest(
                                file, "sha256"
                            ).hexdigest(),
                            "bytes": files[source].stat().st_size,
                        }
                sources.append(
                    {
                        "name": source,
                        "url": url,
                        **measured,
                        "credit": about["credit"],
                        "license": about["license"],
                        "license_url": about["license_url"],
                        **(
                            {"version": about["version"]}
                            if "version" in about
                            else {}
                        ),
                        **(learnt or {}),
                    }
                )
            logger.info("Building %s", name)
            network_built = network.build(
                {source: str(path) for source, path in files.items()}
            )
            network_built, steps = (
                network_built
                if isinstance(network_built, tuple)
                else (network_built, None)
            )
            # Everything that describes the network, except clock times, so that
            # the same rules, sources and software give the same file
            metadata = pipelines.build_metadata(
                name,
                region,
                network.PIPELINE_VERSION,
                sources,
                network.__doc__,
                steps,
            )
            if isinstance(network_built, GeoGraph):
                # Written in Hilbert order within each mode: nodes close on the
                # globe get close ids
                digest = network_built.save_as_scgraph(
                    str(building), metadata=metadata
                )
            else:  # the network file's arrays, already in that order
                arrays, modes = network_built
                header_meta = network_file.header_metadata(
                    metadata,
                    units="km",
                    default_off_graph_circuity=1,
                    default_node_addition_circuity=4,
                    modes=modes,
                )
                digest = network_file.write(str(building), arrays, header_meta)
            built_file = folder.joinpath(f"{digest}.scgraph")
            work.joinpath("cache.json").write_text(
                json.dumps(
                    {"file": built_file.name, "downloaded": downloaded},
                    indent=2,
                )
            )
            # cache.json appears last, so that it always names a whole file
            folder.mkdir(parents=True, exist_ok=True)
            try:
                building.replace(built_file)
            # Open (Windows), so whole: a file of that name has the same content
            except PermissionError:
                pass
            work.joinpath("cache.json").replace(pointer)
            if cached_file is not None and cached_file != built_file:
                try:
                    cached_file.unlink(missing_ok=True)
                except OSError:  # still open (Windows): left as an orphan
                    pass
            cached_file = built_file
            logger.info(
                "Built %s. Credit: %s (%s)",
                name,
                _joined(network, "credit"),
                _joined(network, "license"),
            )
        except OSError as error:  # requests' errors included
            if cached:
                error.add_note(
                    f"The cache still holds {name}: build_geograph(..., "
                    "local_files_only=True) loads it"
                )
            raise
        finally:
            # A failed download or build leaves no large file behind
            shutil.rmtree(work, ignore_errors=True)
    if validate and hasattr(network, "VALIDATION_CASES"):
        cases = [
            case
            for case in network.VALIDATION_CASES
            if case.get("region") is None or case.get("region") == region
        ]
        if cases:
            from scgraph.pipelines.steps.stage4_validation import (
                validate_network,
            )

            logger.info(
                "Validating %s against %d test case(s)...", name, len(cases)
            )
            geograph = GeoGraph.load_from_scgraph(str(cached_file))
            result = validate_network(geograph, cases, silent=False)
            if not result.is_success:
                raise RuntimeError(
                    f"Pipeline validation failed for {name}: {result.summary()}"
                )
            logger.info("Validation %s", result.summary())
    return str(cached_file)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python -m scgraph.pipelines.build",
        description="Build a network from its online sources into the cache, without "
        "loading it, and print the path of its network file.",
    )
    parser.add_argument(
        "name", help="a name of GeoGraph.list_buildable_geographs()"
    )
    parser.add_argument("--region", help="the path of a Geofabrik extract")
    parser.add_argument("--cache-dir", help="the cache directory")
    parser.add_argument(
        "--validate",
        action="store_true",
        help="run Stage 4 validation test cases on the built network",
    )
    parser.add_argument(
        "--stream",
        action="store_true",
        help="stream OSM extracts via HTTP byte ranges instead of downloading",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO)  # each step, and the credit to cite
    try:
        print(
            build_file(
                args.name,
                args.region,
                args.cache_dir,
                validate=args.validate,
                stream=args.stream,
            )
        )
    except (
        ValueError,
        FileNotFoundError,
        RuntimeError,
    ) as error:  # the message is the answer
        parser.exit(2, f"{error}\n")


if __name__ == "__main__":
    main()
