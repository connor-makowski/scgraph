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

from scgraph import network_file
from scgraph.geograph import GeoGraph, _cached_file, _joined
from scgraph.utils import resolve_cache_dir

logger = logging.getLogger(__name__)

# Written in networks/ of the cache: backup and archiving tools skip a tagged directory
_CACHEDIR_TAG = (
    "Signature: 8a477f597d28d172789f06886806bc55\n"
    "# This file is a cache directory tag created by scgraph."
    " For information about cache directory tags, see https://bford.info/cachedir/\n"
)


# What `from_stage` removes from the work folder, by the step of the OSM
# extraction to run again: all of it, the node locations (pass 2), or the cut
# of the ways (pass 3). The later stages keep no file.
STAGE_INVALIDATIONS = {
    "stage1": ["*.done", "*_junctions.bin", "*_ways.bin", "nodes"],
    "pass2": ["pass2.done", "stage1.done", "nodes"],
    "pass3": ["stage1.done"],
}


def _clean_work(work: Path, cache: Path) -> None:
    shutil.rmtree(work, ignore_errors=True)
    parent = work.parent
    while parent != cache and parent.exists() and not any(parent.iterdir()):
        try:
            parent.rmdir()
            parent = parent.parent
        except OSError:
            break


def _validate_pipeline(network, name, region, cached_file):
    contract = getattr(network, "VALIDATION", None)
    if not contract:
        return
    from scgraph.pipelines.steps.stage4_validation import (
        load_cases,
        validate_network,
    )

    cases = load_cases(contract, region=region)
    if not cases:
        return
    logger.info("Validating %s against %d test case(s)...", name, len(cases))
    geograph = GeoGraph.load_from_scgraph(str(cached_file))
    result = validate_network(geograph, cases, silent=False)
    if not result.is_success:
        raise RuntimeError(
            f"Pipeline validation failed for {name}: {result.summary()}"
        )
    logger.info("Validation %s", result.summary())


def build_file(
    name: str | types.ModuleType,
    region: str | None = None,
    cache_dir: str | None = None,
    *,
    resume: bool = True,
    clean: bool = False,
    from_stage: str | None = None,
    keep_work: bool = False,
    work_dir: str | Path | None = None,
    refresh: bool = False,
    local_files_only: bool | None = None,
    validate: bool = False,
    validate_only: bool = False,
    stream: bool = False,
) -> str:
    """Build the network into the local cache and return its file path.

    Args:
        name: Name of a buildable pipeline or imported pipeline module.
        region: Geographic sub-region identifier (e.g. 'europe/denmark').
        cache_dir: Optional custom cache directory.
        resume: Resume build using existing intermediate checkpoints (default: True).
        clean: Purge working directory and intermediate artifacts before building.
        from_stage: Run the OSM extraction again from a step ('stage1', 'pass2', 'pass3'), in a kept work folder.
        keep_work: Retain intermediate working directory after successful build.
        work_dir: Custom directory for intermediate build artifacts and checkpoints.
        refresh: Force rebuild even if a current cached artifact exists.
        local_files_only: Forbid downloading missing network sources.
        validate: Check the built network against its validation cases; a failure raises RuntimeError and leaves the file in the cache.
        validate_only: Validate cached network without rebuilding or downloading.
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
    where = "the path of a Geofabrik extract, for example 'europe/luxembourg' (see https://download.geofabrik.de)"
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

    if validate_only:
        if not cached or not cached_file or not Path(cached_file).is_file():
            raise FileNotFoundError(
                f"{name} is not in the cache ({folder}): build it first before validating"
            )
        _validate_pipeline(network, name, region, cached_file)
        return str(cached_file)
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
                f"{built_by}, now {network.PIPELINE_VERSION}; loading it as {offline}",
                stacklevel=3,  # the caller of GeoGraph.build_geograph
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
        custom_work = work_dir is not None
        work = (
            Path(work_dir)
            if work_dir
            else cache.joinpath(".work", name, region or "")
        )

        if clean or not resume:
            if work.exists():
                shutil.rmtree(work, ignore_errors=True)

        if from_stage:
            patterns = STAGE_INVALIDATIONS.get(from_stage)
            if not patterns:
                raise ValueError(
                    f"Unknown stage '{from_stage}'. Valid: {', '.join(STAGE_INVALIDATIONS)}"
                )
            for pattern in patterns:
                for p in work.rglob(pattern):
                    p.unlink(missing_ok=True)

        work.mkdir(parents=True, exist_ok=True)
        building = work.joinpath(f"{name}.scgraph")
        try:
            sources_dir = work.joinpath("sources")
            sources_dir.mkdir(parents=True, exist_ok=True)
            for source, about in network.SOURCES.items():
                template = about["url"]
                url = template.format(region=region)
                source_path = sources_dir.joinpath(
                    source + "".join(Path(url).suffixes)
                )
                meta_path = sources_dir.joinpath(f"{source}.meta.json")
                files[source] = source_path
                hook = about.get("download")
                if stream and about.get("url", "").endswith(".osm.pbf"):
                    from scgraph.pipelines.steps.stage1_extract import osm

                    download = osm.download_streamed
                else:
                    download = hook or getattr(
                        network, "download", pipelines.download_file
                    )

                if (
                    resume
                    and not clean
                    and source_path.is_file()
                    and meta_path.is_file()
                ):
                    try:
                        sources.append(json.loads(meta_path.read_text()))
                        continue
                    except (json.JSONDecodeError, OSError):
                        pass

                try:
                    learnt = download(url, str(source_path))
                except requests.HTTPError as error:
                    if (
                        "{region}" in template
                        and error.response.status_code == 404
                    ):
                        raise ValueError(
                            f"No extract '{region}' on Geofabrik; the region is {where}"
                        ) from error
                    raise

                measured = {}
                if hook is None or not isinstance(learnt, dict):
                    with open(source_path, "rb") as file:
                        measured = {
                            "sha256": hashlib.file_digest(
                                file, "sha256"
                            ).hexdigest(),
                            "bytes": source_path.stat().st_size,
                        }
                source_record = {
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
                    **(learnt if isinstance(learnt, dict) else {}),
                }
                sources.append(source_record)
                try:
                    meta_path.write_text(json.dumps(source_record))
                except OSError:
                    pass

            logger.info("Building %s", name)
            sig = inspect.signature(network.build)
            build_kwargs = {}
            if "work_dir" in sig.parameters:
                build_kwargs["work_dir"] = str(work)
            network_built = network.build(
                {source: str(path) for source, path in files.items()},
                **build_kwargs,
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
                # A work folder may be on another disk than the cache
                shutil.move(building, built_file)
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
        except (Exception, KeyboardInterrupt) as error:
            if keep_work or custom_work or isinstance(error, KeyboardInterrupt):
                logger.info(
                    "Intermediate files retained in %s for resumption", work
                )
            else:
                _clean_work(work, cache)
            if cached and isinstance(error, OSError):
                error.add_note(
                    f"The cache still holds {name}: build_geograph(..., "
                    "local_files_only=True) loads it"
                )
            raise
        else:
            if not keep_work and not custom_work:
                _clean_work(work, cache)
    if validate:
        _validate_pipeline(network, name, region, cached_file)
    return str(cached_file)


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
        "--resume",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="resume build from existing checkpoints (default: True, use --no-resume to disable)",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="clean working directory and intermediate artifacts before building",
    )
    parser.add_argument(
        "--from",
        dest="from_stage",
        choices=list(STAGE_INVALIDATIONS),
        help="resume build starting from a specific stage, invalidating later stages",
    )
    parser.add_argument(
        "--keep-work",
        action="store_true",
        help="keep intermediate working directory even after successful build",
    )
    parser.add_argument(
        "--work-dir",
        help="custom directory for intermediate build artifacts and checkpoints",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="run Stage 4 validation test cases on the built network",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="validate an already cached network without re-building it",
    )
    parser.add_argument(
        "--stream",
        action="store_true",
        help="stream OSM extracts via HTTP byte ranges instead of downloading",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO)  # each step, and the credit to cite
    try:
        print(  # noqa: T201
            build_file(
                args.name,
                args.region,
                args.cache_dir,
                resume=args.resume,
                clean=args.clean,
                from_stage=args.from_stage,
                keep_work=args.keep_work,
                work_dir=args.work_dir,
                validate=args.validate,
                validate_only=args.validate_only,
                stream=args.stream,
            )
        )
    except KeyboardInterrupt:
        parser.exit(
            130,
            "\nBuild interrupted by user. Intermediate checkpoints preserved.\n",
        )
    except (
        ValueError,
        FileNotFoundError,
        RuntimeError,
    ) as error:  # the message is the answer
        parser.exit(2, f"{error}\n")


if __name__ == "__main__":
    main()
