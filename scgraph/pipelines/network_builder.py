"""The runner of the pipelines. `build_network_file` downloads the sources of a network, builds
the network and keeps it in the cache. `GeoGraph.build_geograph` calls it.

`python -m scgraph.pipelines.network_builder NAME [--region R] [--cache-dir D] [--validate]`
builds a network without loading it, and prints the path of its file. `--help` lists
the other options.
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
from scgraph.files import download_file, is_offline
from scgraph.geograph import GeoGraph
from scgraph.geograph_networks import find_cached_file, join_source_values
from scgraph.utils import resolve_cache_dir

logger = logging.getLogger(__name__)

__all__ = ["build_network_file"]

# Written in networks/ of the cache: backup and archiving tools skip a tagged directory
_CACHEDIR_TAG = (
    "Signature: 8a477f597d28d172789f06886806bc55\n"
    "# This file is a cache directory tag created by scgraph."
    " For information about cache directory tags, see https://bford.info/cachedir/\n"
)


def _clean_work(work: Path, cache: Path) -> None:
    """Remove the work folder, and each folder above it that is then empty, up to the
    cache directory."""
    shutil.rmtree(work, ignore_errors=True)
    parent = work.parent
    while parent != cache and parent.exists() and not any(parent.iterdir()):
        try:
            parent.rmdir()
            parent = parent.parent
        except OSError:
            break


def _validate_pipeline(pipeline, name, region, filename):
    """Check the network file against the cases that the pipeline lists for the
    region. Raise a RuntimeError when a case fails. A pipeline without cases passes.
    """
    validation = getattr(pipeline, "VALIDATION", None)
    if not validation:
        return
    from scgraph.pipelines.steps.step4_validation_cases import (
        load_validation_cases,
        validate_network,
    )

    cases = load_validation_cases(validation, region=region)
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


_OFFLINE = "local_files_only=True (or SCGRAPH_OFFLINE=1)"


def _resolve_pipeline(
    name: str | None, pipeline: types.ModuleType | None
) -> tuple[types.ModuleType, str]:
    """Return the pipeline module and its name. The caller gives one of the two:
    `name`, the name of a pipeline of scgraph, or `pipeline`, a pipeline module.
    """
    if pipeline is not None and name is None:
        module_name = pipeline.__name__.rpartition(".")[2]
        # A module named like a pipeline of scgraph would share its cache entry,
        # and each would load the network of the other. A name with other
        # characters could give a path outside the cache.
        if not re.fullmatch(r"\w+", module_name) or (
            module_name in pipelines.BUILDABLE_NETWORKS
            and pipeline.__name__ != f"scgraph.pipelines.{module_name}"
        ):
            raise ValueError(
                f"Invalid pipeline module name '{pipeline.__name__}'"
            )
        return pipeline, module_name
    if name is None or pipeline is not None:
        raise ValueError(
            "Give one of name, a network of scgraph, and pipeline, a pipeline "
            "module of your own"
        )
    if name not in pipelines.BUILDABLE_NETWORKS:
        # `str`: a caller may give a module as the name
        close = difflib.get_close_matches(
            str(name), pipelines.BUILDABLE_NETWORKS, n=3
        )
        hint = f" Did you mean {', '.join(map(repr, close))}?" if close else ""
        raise ValueError(
            f"Unknown network {name!r}.{hint} Available: "
            f"{', '.join(pipelines.BUILDABLE_NETWORKS)}. Pass a pipeline module of your own "
            "as pipeline=<module>"
        )
    return importlib.import_module(f"scgraph.pipelines.{name}"), name


def find_region_url(pipeline: types.ModuleType) -> str | None:
    """Return the first source URL of the pipeline that holds `{region}`, or None.
    A pipeline declares this way that it needs a region (`scgraph.pipelines`).
    """
    return next(
        (s["url"] for s in pipeline.SOURCES.values() if "{region}" in s["url"]),
        None,
    )


def _check_region(
    pipeline: types.ModuleType, name: str, region: str | None
) -> None:
    """Raise a ValueError when `region` does not fit what the pipeline declares."""
    region_url = find_region_url(pipeline)
    if region_url is not None and region is None:
        raise ValueError(
            f"The pipeline '{name}' needs a region: the value of {{region}} in "
            f"{region_url}"
        )
    if region_url is None and region is not None:
        raise ValueError(
            f"The pipeline '{name}' takes no region: no URL of its sources "
            "holds {region}"
        )
    # The region becomes a part of the path of the cache, so it holds nothing else
    if region is not None and not re.fullmatch(
        r"[a-z0-9-]+(/[a-z0-9-]+)*", region
    ):
        raise ValueError(
            f"Invalid region '{region}': lowercase letters, digits and hyphens, "
            "in parts joined by '/'"
        )


def _should_build(
    pipeline: types.ModuleType,
    name: str,
    folder: Path,
    cached_file: Path | None,
    refresh: bool,
    local_files_only: bool,
) -> bool:
    """Return True when the network must be built.

    There are four cases: the cache does not hold the network; another version of the
    pipeline built the cached file; scgraph cannot read the cached file; the caller asks
    for a refresh.

    With `local_files_only`, the function never returns True. It raises when `refresh`
    is true, when the cache does not hold the network, or when scgraph cannot read the
    cached file. It warns when another version of the pipeline built the file.
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
                f"than {network_file.FORMAT_VERSION}): build it again without {_OFFLINE}"
            )
        if stale:
            warnings.warn(
                f"The cached {name} was built with pipeline version "
                f"{built_by}, now {pipeline.PIPELINE_VERSION}; loading it as {_OFFLINE}",
                stacklevel=5,  # the line that called GeoGraph.build_geograph
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
    """Download the sources of the pipeline into `sources_dir`. A source that an earlier
    build left there with its record is not downloaded again.

    Returns:
        `(files, records)`. `files` maps the name of each source to the path of its
        file. `records` lists the record of each source, which goes into the header of
        the network file.
    """
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
        download = own_download or getattr(pipeline, "download", download_file)
        try:
            learnt = download(url, str(source_path))
        except requests.HTTPError as error:
            if "{region}" in about["url"] and error.response.status_code == 404:
                raise ValueError(
                    f"The region '{region}' has no source: {url} does not exist"
                ) from error
            raise
        # A source may have a download function of its own. When that function
        # returns a dict, the dict identifies the source. Otherwise the runner
        # identifies the file by its digest and its size.
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
    pipeline: types.ModuleType,
) -> str:
    """Write the network that the `build` of `pipeline` returned to `filename`, with
    the metadata of the build in its header. Return the digest of the file."""
    if isinstance(network, GeoGraph):
        # The file has the nodes of each node mode in Hilbert order, so that nodes
        # close on the globe get close ids
        return network.save_as_scgraph(str(filename), metadata=metadata)
    arrays, node_modes = (
        network  # the arrays of the file, already in that order
    )
    classes = None
    if "edge_class_ids" in arrays:
        # A value of `edge_class_ids` is the id of a class of the classes table of the
        # pipeline
        classes = [
            {"name": name, "edge_mode": edge_mode}
            for name, edge_mode in getattr(
                pipeline, "CLASSES", pipelines.CLASSES
            ).items()
        ]
    # A file gives the count of the nodes of each node mode, and not the node mode
    # id of each node
    return network_file.write(
        str(filename),
        {name: arrays[name] for name in arrays if name != "node_mode_ids"},
        network_file.build_header_metadata(
            metadata,
            node_modes=node_modes,
            node_mode_ids=arrays.get(
                "node_mode_ids", bytes(len(arrays["node_first_edge_ids"]) - 1)
            ),
            classes=classes,
        ),
    )


def _move_into_cache(
    building: Path,
    digest: str,
    folder: Path,
    downloaded: str,
    earlier_file: Path | None,
) -> Path:
    """Move the network file `building` into `folder` of the cache, under the name of
    its digest. Write the `cache.json` that names it, and remove the file of the
    earlier build. Return the new path of the file.
    """
    built_file = folder.joinpath(f"{digest}.scgraph")
    folder.mkdir(parents=True, exist_ok=True)
    # The file arrives beside its final place, then takes its name in one step. A
    # work folder may be on another disk than the cache. A move between two disks
    # is a copy, and an interruption would leave a cut file under the final name.
    arriving = built_file.with_name(built_file.name + ".part")
    shutil.move(building, arriving)
    try:
        arriving.replace(built_file)
    # On Windows, the rename fails when a process holds a file of that name open.
    # That file is whole and has the same content: its name is its digest.
    except PermissionError:
        arriving.unlink()
    # cache.json appears last, and the same way, so that it always names a whole
    # file.
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


def build_network_file(
    name: str | None = None,
    region: str | None = None,
    cache_dir: str | os.PathLike | None = None,
    *,
    pipeline: types.ModuleType | None = None,
    work_dir: str | os.PathLike | None = None,
    refresh: bool = False,
    local_files_only: bool | None = None,
    run_validation_cases: bool = False,
) -> str:
    """Build a network into the local cache and return the path of its file.

    When the cache holds the network, built by the same `PIPELINE_VERSION`, the
    function builds nothing and returns the cached file.

    Args:
        name: The name of a pipeline of scgraph. Give `name` or `pipeline`.
        region: The region, for a pipeline with regions: the value of `{region}` in
            its source URLs, for example 'europe/denmark'.
        cache_dir: The cache directory. None takes `SCGRAPH_CACHE_DIR`, then the
            cache directory of the platform.
        pipeline: A pipeline module of the caller, in place of `name`.
        work_dir: The work folder, where the build keeps the downloaded sources and
            the files of its steps. None takes a folder in the cache directory, which
            the function removes after a build that succeeds. The function does not
            remove a folder that the caller gives. A build that fails keeps its work
            folder, and the next call resumes from it. An earlier build of another
            `PIPELINE_VERSION`, region or version of scgraph may have left the folder:
            the function then empties its own folder first, and refuses a folder
            that the caller gives.
        refresh: Download the sources and build again, even if the cache holds a
            current network. The function empties the work folder first, also a
            `work_dir` that the caller gives.
        local_files_only: Use the cache only, and download nothing. None takes True
            when the environment variable `SCGRAPH_OFFLINE` is `1`.
        run_validation_cases: Check the network against its validation cases. A network that is
            built is checked before it enters the cache. If it fails, the cache stays
            unchanged. A network that the cache already holds is checked as it is.
            With `local_files_only=True`, the call checks the cached network and
            downloads nothing.

    Returns:
        The path of the network file in the cache.

    Raises:
        ValueError: Not one of `name` and `pipeline`. The name is unknown, or the
            module has the name of a pipeline of scgraph. The region is missing for a
            pipeline with regions, given to another pipeline, not valid, or has no
            source. With `local_files_only`: `refresh` is true, or scgraph cannot read
            the cached file.
        FileNotFoundError: The network is not in the cache, with `local_files_only`.
        RuntimeError: The network fails its validation. Or `work_dir` holds the files
            of a build of another version, and `refresh` is false.
        requests.HTTPError: A source cannot be downloaded.
    """
    if local_files_only is None:
        local_files_only = is_offline()
    pipeline, name = _resolve_pipeline(name, pipeline)
    _check_region(pipeline, name, region)
    cache = resolve_cache_dir(cache_dir)
    folder = cache.joinpath("networks", name, region or "")
    # cache.json names the network file, which is named by its content
    cached_file = find_cached_file(folder.joinpath("cache.json"))
    if not _should_build(
        pipeline, name, folder, cached_file, refresh, local_files_only
    ):
        if run_validation_cases:
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
    # A work folder serves one pipeline, version, region and scgraph version. After
    # an upgrade, its files may follow old rules, so the build does not resume from
    # them. It empties its own folder. A folder of the caller may hold other files:
    # the caller empties it with `refresh`.
    stamp = work.joinpath("scgraph_work.json")
    built_by = pipelines.build_metadata(
        name, region, pipeline.PIPELINE_VERSION, []
    )
    built_by = {
        **built_by["pipeline"],
        "scgraph": built_by["software"]["scgraph"],
    }
    try:
        is_stale = json.loads(stamp.read_text()) != built_by
    except (OSError, ValueError):
        is_stale = False
    if is_stale and work_dir and not refresh:
        raise RuntimeError(
            f"{work} holds the files of another build (see {stamp.name}). Pass "
            "refresh=True to empty this folder, or give another work_dir"
        )
    if refresh or is_stale:
        shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)
    stamp.write_text(json.dumps(built_by))
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
        digest = _write_network(network, building, metadata, pipeline)
        if run_validation_cases:
            _validate_pipeline(pipeline, name, region, building)
        built_file = _move_into_cache(
            building, digest, folder, downloaded, cached_file
        )
        logger.info(
            "Built %s. Credit: %s (%s)",
            name,
            join_source_values(pipeline, "credit"),
            join_source_values(pipeline, "license"),
        )
    except (Exception, KeyboardInterrupt) as error:
        if work_dir is None and not any(
            path.is_file() and path != stamp for path in work.rglob("*")
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
        prog="python -m scgraph.pipelines.network_builder",
        description="Build a network from its online sources into the cache, without "
        "loading it, and print the path of its network file.",
    )
    parser.add_argument(
        "name", help="a name of GeoGraph.list_buildable_geographs()"
    )
    parser.add_argument(
        "--region", help="the region, for a network with regions"
    )
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
            build_network_file(
                args.name,
                args.region,
                args.cache_dir,
                work_dir=args.work_dir,
                refresh=args.refresh,
                # None lets SCGRAPH_OFFLINE decide
                local_files_only=args.local_files_only or None,
                run_validation_cases=args.validate,
            )
        )
    except KeyboardInterrupt:
        parser.exit(
            130,
            "\nInterrupted. A work folder that holds files is kept, and the next "
            "build resumes from it.\n",
        )
    except (
        ValueError,
        FileNotFoundError,
        RuntimeError,
    ) as error:  # the message says what to change: no traceback
        parser.exit(2, f"{error}\n")


if __name__ == "__main__":
    main()
