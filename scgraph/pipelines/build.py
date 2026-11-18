"""The runner of the pipelines: download the sources of a network, build it and keep it in
the cache (`GeoGraph.build_geograph`).

`python -m scgraph.pipelines.build NAME [--region R] [--cache-dir D]` builds a network
without loading it and prints the path of its file.
"""

import argparse
import difflib
import hashlib
import importlib
import inspect
import json
import logging
import os
import re
import shutil
import types
import warnings
from datetime import datetime, timezone
from pathlib import Path

import requests

from scgraph import network_file, pipelines
from scgraph.geograph import GeoGraph, _cached_file, _joined
from scgraph.utils import resolve_cache_dir

logger = logging.getLogger(__name__)

# Written in networks/ of the cache: backup and archiving tools skip a tagged directory
_CACHEDIR_TAG = (
    "Signature: 8a477f597d28d172789f06886806bc55\n"
    "# This file is a cache directory tag created by scgraph."
    " For information about cache directory tags, see https://bford.info/cachedir/\n"
)


def _clean_work(work: Path, cache: Path) -> None:
    shutil.rmtree(work, ignore_errors=True)
    parent = work.parent
    while parent != cache and parent.exists() and not any(parent.iterdir()):
        try:
            parent.rmdir()
            parent = parent.parent
        except OSError:
            break


def _validate_pipeline(pipeline, name, region, filename):
    validation = getattr(pipeline, "VALIDATION", None)
    if not validation:
        return
    from scgraph.pipelines.steps.stage4_validation import (
        load_cases,
        validate_network,
    )

    cases = load_cases(validation, region=region)
    if not cases:
        return
    logger.info("Validating %s against %d case(s)", name, len(cases))
    # validate_network releases the file before it returns. The caller then
    # moves the file into the cache, and Windows cannot move a mapped file.
    result = validate_network(filename, cases)
    if not result.is_success:
        raise RuntimeError(
            f"Pipeline validation failed for {name}: {result.summary()}"
        )
    logger.info("Validation %s", result.summary())


_REGION_HELP = (
    "the path of a Geofabrik extract, for example 'europe/luxembourg' "
    "(see https://download.geofabrik.de)"
)
_OFFLINE = "local_files_only=True (or SCGRAPH_OFFLINE=1)"


def _resolve_pipeline(
    name: str | types.ModuleType,
) -> tuple[types.ModuleType, str]:
    """Return the pipeline module and its name. `name` is the name of a pipeline of
    scgraph, or a pipeline module of the caller."""
    if isinstance(name, types.ModuleType):
        pipeline, name = name, name.__name__.rpartition(".")[2]
        # A module named like a pipeline of scgraph would share its cache entry,
        # and each would load the network of the other. A name with other
        # characters could give a path outside the cache.
        if not re.fullmatch(r"\w+", name) or (
            name in pipelines.NAMES
            and pipeline.__name__ != f"scgraph.pipelines.{name}"
        ):
            raise ValueError(
                f"Invalid pipeline module name '{pipeline.__name__}'"
            )
        return pipeline, name
    if name not in pipelines.NAMES:
        close = difflib.get_close_matches(name, pipelines.NAMES, n=3)
        hint = f" Did you mean {', '.join(map(repr, close))}?" if close else ""
        raise ValueError(
            f"Unknown network '{name}'.{hint} Available: {', '.join(pipelines.NAMES)}"
        )
    return importlib.import_module(f"scgraph.pipelines.{name}"), name


def _check_region(
    pipeline: types.ModuleType, name: str, region: str | None
) -> None:
    """Raise a ValueError when `region` does not fit the pipeline: a pipeline needs a
    region when one of its source URLs holds `{region}`."""
    regional = any(
        "{region}" in source["url"] for source in pipeline.SOURCES.values()
    )
    if regional and region is None:
        raise ValueError(f"'{name}' needs a region: {_REGION_HELP}")
    if not regional and region is not None:
        raise ValueError(f"'{name}' has no region")
    # A region is the path of a Geofabrik extract. Nothing else may reach the
    # path of the cache.
    if region is not None and not re.fullmatch(
        r"[a-z0-9-]+(/[a-z0-9-]+)*", region
    ):
        raise ValueError(f"Invalid region '{region}': {_REGION_HELP}")


def _should_build(
    pipeline: types.ModuleType,
    name: str,
    folder: Path,
    cached_file: Path | None,
    refresh: bool,
    local_files_only: bool,
) -> bool:
    """Return True when the network must be built: the cache does not hold it, another
    version of its pipeline built the cached file, scgraph cannot read that file, or
    the caller asks for a refresh. With `local_files_only`, nothing is built: the
    function returns False, or raises when the cache holds no network to load.
    """
    cached, built_by = cached_file is not None, None
    if cached:
        try:
            built_by = network_file.get_scgraph_info(cached_file)["pipeline"][
                "version"
            ]
        except (ValueError, KeyError, TypeError):
            pass  # the file is damaged, or it has another format
    stale = cached and built_by != pipeline.PIPELINE_VERSION
    if local_files_only:
        if refresh:
            raise ValueError(f"refresh=True downloads: not with {_OFFLINE}")
        if not cached:
            raise FileNotFoundError(
                f"{name} is not in the cache ({folder}) and {_OFFLINE} "
                "forbids building it"
            )
        if built_by is None:
            raise ValueError(
                f"The cached {name} can't be read (damaged, or a file format other "
                f"than {network_file.VERSION}): build it again without {_OFFLINE}"
            )
        if stale:
            warnings.warn(
                f"The cached {name} was built with pipeline version "
                f"{built_by}, now {pipeline.PIPELINE_VERSION}; loading it as {_OFFLINE}",
                stacklevel=4,  # the line that called GeoGraph.build_geograph
            )
        return False
    if stale:
        logger.warning(
            "The cached %s was built by another version of its pipeline or "
            "of the file format; building it again",
            name,
        )
    return refresh or not cached or stale


def _download_sources(
    pipeline: types.ModuleType, region: str | None, sources_dir: Path
) -> tuple[dict[str, str], list[dict]]:
    """Download the sources of the pipeline into `sources_dir`. Return the path of the
    file of each source, by the name of the source, and the record of each source for
    the header of the network file. A source that an earlier build left there with its
    record is not downloaded again."""
    sources_dir.mkdir(parents=True, exist_ok=True)
    files, records = {}, []
    for source, about in pipeline.SOURCES.items():
        url = about["url"].format(region=region)
        source_path = sources_dir.joinpath(source + "".join(Path(url).suffixes))
        record_path = sources_dir.joinpath(f"{source}.meta.json")
        files[source] = str(source_path)
        if source_path.is_file() and record_path.is_file():
            try:
                records.append(json.loads(record_path.read_text()))
                continue
            except (json.JSONDecodeError, OSError):
                pass
        own_download = about.get("download")
        download = own_download or getattr(
            pipeline, "download", pipelines.download_file
        )
        try:
            learnt = download(url, str(source_path))
        except requests.HTTPError as error:
            if "{region}" in about["url"] and error.response.status_code == 404:
                raise ValueError(
                    f"No extract '{region}' on Geofabrik; the region is {_REGION_HELP}"
                ) from error
            raise
        # The dict that the own download of a source returns identifies the
        # source. Otherwise the file is identified by its digest and its size.
        measured = {}
        if own_download is None or not isinstance(learnt, dict):
            with open(source_path, "rb") as file:
                measured = {
                    "sha256": hashlib.file_digest(file, "sha256").hexdigest(),
                    "bytes": source_path.stat().st_size,
                }
        record = {
            "name": source,
            "url": url,
            **measured,
            "credit": about["credit"],
            "license": about["license"],
            "license_url": about["license_url"],
            **({"version": about["version"]} if "version" in about else {}),
            **(learnt if isinstance(learnt, dict) else {}),
        }
        records.append(record)
        try:
            record_path.write_text(json.dumps(record))
        except OSError:
            pass
    return files, records


def _write_network(
    network: GeoGraph | tuple[dict, list[dict]],
    filename: Path,
    metadata: dict,
) -> str:
    """Write the network that a `build` returned to `filename`, with the metadata of
    the build in its header. Return the digest of the file."""
    if isinstance(network, GeoGraph):
        # The file has the nodes of each mode in Hilbert order, so that nodes
        # close on the globe get close ids
        return network.save_as_scgraph(str(filename), metadata=metadata)
    arrays, modes = network  # the arrays of the file, already in that order
    return network_file.write(
        str(filename),
        arrays,
        network_file.header_metadata(metadata, units="km", modes=modes),
    )


def _move_into_cache(
    building: Path,
    digest: str,
    folder: Path,
    downloaded: str,
    earlier_file: Path | None,
) -> Path:
    """Move the network file `building` into `folder` of the cache, under the name of
    its digest, and remove the file of the earlier build. Return its new path.
    """
    built_file = folder.joinpath(f"{digest}.scgraph")
    folder.mkdir(parents=True, exist_ok=True)
    try:
        # A work folder may be on another disk than the cache
        shutil.move(building, built_file)
    # On Windows, the move fails when a process holds a file of that name open.
    # That file is whole and has the same content: its name is its digest.
    except PermissionError:
        pass
    # cache.json appears last and in one step, so that it always names a whole
    # file. It is written beside its final place: a rename works on one disk only.
    pointer = folder.joinpath("cache.json")
    written = pointer.with_name("cache.json.part")
    written.write_text(
        json.dumps(
            {"file": built_file.name, "downloaded": downloaded}, indent=2
        )
    )
    written.replace(pointer)
    if earlier_file is not None and earlier_file != built_file:
        try:
            earlier_file.unlink(missing_ok=True)
        except OSError:  # still open (Windows): left as an orphan
            pass
    return built_file


def build_file(
    name: str | types.ModuleType,
    region: str | None = None,
    cache_dir: str | os.PathLike | None = None,
    *,
    work_dir: str | os.PathLike | None = None,
    refresh: bool = False,
    local_files_only: bool | None = None,
    validate: bool = False,
) -> str:
    """Build the network into the local cache and return its file path.

    Args:
        name: Name of a buildable pipeline or imported pipeline module.
        region: Geographic sub-region identifier (e.g. 'europe/denmark').
        cache_dir: Optional custom cache directory.
        work_dir: The work folder: the build keeps there the downloaded sources and the files of its steps. None takes a folder in the cache directory, removed after a build that succeeds. A folder that the caller gives is not removed. A build that fails keeps its work folder, and the next call resumes from it.
        refresh: Download the sources and build again, even if the cache holds a current network or a work folder exists. It empties the work folder first, also a `work_dir` that the caller gave.
        local_files_only: Forbid downloading missing network sources.
        validate: Check the network against its validation cases. A failure raises RuntimeError. A network that is built is checked before it enters the cache. If it fails, it is not cached and the cache stays unchanged. A network that the cache already holds is checked as it is: with `local_files_only=True`, the call checks the cached network and downloads nothing.

    Returns:
        Absolute path to the built .scgraph network file.

    Raises:
        ValueError: On unknown pipeline names or invalid region parameters.
        FileNotFoundError: If the network is uncached in offline mode.
        RuntimeError: If Stage 4 validation fails.
    """
    if local_files_only is None:
        local_files_only = os.environ.get("SCGRAPH_OFFLINE") == "1"
    pipeline, name = _resolve_pipeline(name)
    _check_region(pipeline, name, region)
    cache = resolve_cache_dir(cache_dir)
    folder = cache.joinpath("networks", name, region or "")
    # cache.json names the network file, which is named by its content
    cached_file = _cached_file(folder.joinpath("cache.json"))
    if not _should_build(
        pipeline, name, folder, cached_file, refresh, local_files_only
    ):
        if validate:
            _validate_pipeline(pipeline, name, region, cached_file)
        return str(cached_file)

    # The tag goes in networks/, scgraph's own folder: a cache_dir given by the user
    # may hold other files, which backups must not skip
    cache.joinpath("networks").mkdir(parents=True, exist_ok=True)
    cache.joinpath("networks", "CACHEDIR.TAG").write_text(_CACHEDIR_TAG)
    # The time of the download is the only clock time of a build. It goes into
    # cache.json, not into the network file.
    downloaded = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    work = (
        Path(work_dir)
        if work_dir
        else cache.joinpath(".work", name, region or "")
    )
    if refresh:
        shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)
    building = work.joinpath(f"{name}.scgraph")
    try:
        files, sources = _download_sources(
            pipeline, region, work.joinpath("sources")
        )
        logger.info("Building %s", name)
        takes_work_dir = (
            "work_dir" in inspect.signature(pipeline.build).parameters
        )
        network = pipeline.build(
            files, **({"work_dir": str(work)} if takes_work_dir else {})
        )
        # Everything that describes the network, except clock times, so that
        # the same rules, sources and software give the same file
        metadata = pipelines.build_metadata(
            name, region, pipeline.PIPELINE_VERSION, sources, pipeline.__doc__
        )
        digest = _write_network(network, building, metadata)
        if validate:
            _validate_pipeline(pipeline, name, region, building)
        built_file = _move_into_cache(
            building, digest, folder, downloaded, cached_file
        )
        logger.info(
            "Built %s. Credit: %s (%s)",
            name,
            _joined(pipeline, "credit"),
            _joined(pipeline, "license"),
        )
    except (Exception, KeyboardInterrupt) as error:
        if work_dir is None and not any(
            path.is_file() for path in work.rglob("*")
        ):
            # The build stopped before it wrote a file, for example on an
            # unknown region. There is nothing to resume from.
            _clean_work(work, cache)
        else:
            # The work folder is kept. It holds the downloaded sources and
            # the files that the steps saved.
            logger.warning(
                "The build of %s did not finish. Its work folder %s is kept, "
                "and the next build resumes from it. "
                "GeoGraph.clear_geograph_cache() removes a work folder that "
                "is in the cache",
                name,
                work,
            )
        if cached_file is not None and isinstance(error, OSError):
            error.add_note(
                f"The cache still holds {name}: build_geograph(..., "
                "local_files_only=True) loads it"
            )
        raise
    if work_dir is None:
        _clean_work(work, cache)
    return str(built_file)


def main(argv: list[str] | None = None) -> None:
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
        "--work-dir",
        help="the work folder, kept after the build (default: a folder in the "
        "cache directory, removed after a build that succeeds)",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="download the sources and build again; the work folder is emptied "
        "first, also a --work-dir",
    )
    parser.add_argument(
        "--local-files-only",
        action="store_true",
        help="use the cache only and download nothing; with --validate, check "
        "the cached network",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="check the built network against its validation cases; the "
        "network enters the cache only if it passes",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO
    )  # each download, and the credit to cite
    try:
        print(  # noqa: T201 (the output of the command)
            build_file(
                args.name,
                args.region,
                args.cache_dir,
                work_dir=args.work_dir,
                refresh=args.refresh,
                # None lets SCGRAPH_OFFLINE decide
                local_files_only=args.local_files_only or None,
                validate=args.validate,
            )
        )
    except KeyboardInterrupt:
        parser.exit(
            130,
            "\nBuild interrupted. Its work folder is kept, and the next build "
            "resumes from it.\n",
        )
    except (
        ValueError,
        FileNotFoundError,
        RuntimeError,
    ) as error:  # the message is the answer
        parser.exit(2, f"{error}\n")


if __name__ == "__main__":
    main()
