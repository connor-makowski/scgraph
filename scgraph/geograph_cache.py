"""The layout of the cache directory, where scgraph keeps the networks that it loads
and builds.

The cache directory holds three folders:

| Folder | What it holds | Who writes it |
|---|---|---|
| `networks/` | One folder for each built network and region, with a `cache.json` and the network file that it names | `build_network_file` |
| `releases/` | One folder for each network release, with the files that `load_geograph` downloaded | `fetch_released_file` |
| `.work/` | The work folder of each build that runs or that failed | `build_network_file` |

`cache.json` names the network file of one build, in its own folder. The name of
the file is the digest of its content. Example:
`networks/osm_region_multimodal/europe/denmark/cache.json` holds
`{"file": "3f1c...e2.scgraph", "downloaded": "2026-11-20T08:00:00Z"}`.

The folder `networks/` also holds a `CACHEDIR.TAG` file, so a backup tool can leave
it out. A save refuses a file inside this folder (`check_save_path`).

This module is internal. `ARCHITECTURE.md`, section 6, describes the cache directory.
"""

import json
import os
from pathlib import Path

from scgraph import files
from scgraph.utils import resolve_cache_dir

NETWORKS_FOLDER = "networks"
RELEASES_FOLDER = "releases"
WORK_FOLDER = ".work"
CACHE_JSON = "cache.json"
_CACHEDIR_TAG_NAME = "CACHEDIR.TAG"
# The signature comes from the Cache Directory Tagging Specification
_CACHEDIR_TAG = (
    "Signature: 8a477f597d28d172789f06886806bc55\n"
    "# This file is a cache directory tag created by scgraph."
    " For information about cache directory tags, see https://bford.info/cachedir/\n"
)


def create_networks_folder(cache_path: Path) -> None:
    """Create the folder `networks/` of a cache directory, with its `CACHEDIR.TAG`.

    The tag goes in `networks/`, the own folder of scgraph: a `cache_dir` of the
    user may hold other files, which a backup must not leave out. The tag also
    tells `check_save_path` that the folder holds built networks.
    """
    cache_path.joinpath(NETWORKS_FOLDER).mkdir(parents=True, exist_ok=True)
    cache_path.joinpath(NETWORKS_FOLDER, _CACHEDIR_TAG_NAME).write_text(
        _CACHEDIR_TAG
    )


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


def write_cache_json(folder: Path, file_name: str, downloaded: str) -> None:
    """Write the `cache.json` of a build folder in one step, so that it always
    names a whole file.

    Args:
        folder: The build folder, which holds the network file.
        file_name: The name of the network file.
        downloaded: The time of the download of the sources, in UTC.
    """
    with files.write_atomically(folder / CACHE_JSON, "part") as written:
        written.write_text(
            json.dumps({"file": file_name, "downloaded": downloaded}, indent=2)
        )


def check_save_path(filename: str | os.PathLike) -> None:
    """Refuse a save into the folder `networks/` of a cache directory.

    A built network must stay the file that its `cache.json` names, and
    `clear_geograph_cache` removes the whole folder. A save does not know the
    `cache_dir` of a build. So it refuses a file under the folder `networks/` of
    the default cache directory, or under a folder `networks/` that holds a
    `CACHEDIR.TAG`, which every build writes.

    Raises:
        ValueError: `filename` is inside such a folder.
    """
    path = Path(filename).resolve()
    default = resolve_cache_dir().joinpath(NETWORKS_FOLDER).resolve()
    for folder in path.parents:
        if folder == default or (
            folder.name == NETWORKS_FOLDER
            and folder.joinpath(_CACHEDIR_TAG_NAME).is_file()
        ):
            raise ValueError(
                f"{filename} is in scgraph's cache ({folder}); save it elsewhere"
            )
