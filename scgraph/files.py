"""What every module needs to fetch and write a file safely: a write under a temporary
name that is then renamed, the download of a file, the session and the check of a
download by byte ranges, and the reader of `SCGRAPH_OFFLINE`.

This module is internal.
"""

import logging
import os
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter, Retry

# The records of a download keep the logger name that the documents show.
logger = logging.getLogger("scgraph.pipelines")

# In bytes. A larger download is logged at WARNING, which shows without a logging
# setup.
LARGE_DOWNLOAD_BYTES = 100e6
# The failures in a row that one request may have. A build reads the planet for
# hours, so one slow answer of the server must not stop it.
MAX_RETRIES = 10


def is_offline() -> bool:
    """Return True if the environment variable `SCGRAPH_OFFLINE` is `1`: scgraph then
    makes no download unless the caller asks for one."""
    return os.environ.get("SCGRAPH_OFFLINE") == "1"


@contextmanager
def write_atomically(
    filename: str | os.PathLike,
    suffix: str,
    folder: str | os.PathLike | None = None,
) -> Iterator[Path]:
    """Give the path of a temporary file, and move it onto `filename` when the block
    ends without an error.

    A block that fails removes the temporary file, so that a failed write leaves the
    previous `filename` whole and never leaves a part of a file under the name that a
    later read uses. The block creates the temporary file itself.

    Args:
        filename: The path of the file to write. Its folder is created if it is
            missing when the block ends.
        suffix: The end of the name of the temporary file, such as `saving`.
        folder: The folder of the temporary file. The default is the folder of
            `filename`.

    Yields:
        The path of the temporary file.

    Raises:
        PermissionError: On Windows, a process has mapped `filename`, so the move
            cannot replace it.
    """
    target = Path(os.path.abspath(filename))
    folder = target.parent if folder is None else Path(folder)
    temporary = folder.joinpath(
        f".{target.name}.{os.getpid()}.{secrets.token_hex(4)}.{suffix}"
    )
    try:
        yield temporary
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temporary, target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def create_retry_session() -> requests.Session:
    """Return a session that sends the User-Agent `scgraph`, and that tries a request
    again up to `MAX_RETRIES` times when the server answers 429 or 5xx."""
    session = requests.Session()
    session.headers["User-Agent"] = "scgraph"
    adapter = HTTPAdapter(
        max_retries=Retry(
            total=MAX_RETRIES,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
    )
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def check_byte_range_answer(
    response: requests.Response, tag: str, size: int
) -> None:
    """Refuse an answer that is not a byte range of the expected version of a file.

    Args:
        response: The answer to a request with a `Range` header.
        tag: The ETag, or the Last-Modified date, that the file had at the start.
        size: The size of the file at the start, in bytes.

    Raises:
        ValueError: The server ignored the byte range, or the file has another tag
            or another size. The server then replaced the file during the download.
    """
    headers = response.headers
    answer_tag = headers.get("ETag") or headers.get("Last-Modified")
    total = headers.get("Content-Range", "").rpartition("/")[2]
    if response.status_code != 206 or answer_tag != tag or total != str(size):
        raise ValueError(f"{response.url} changed or ignores byte ranges")


def download_file(url: str, filename: str | os.PathLike) -> None:
    """Download `url` to `filename`. The function first logs the size of the file: at
    WARNING above `LARGE_DOWNLOAD_BYTES`, at INFO below. When the server gives the size, it
    then logs at INFO the megabytes done at each tenth of the download.

    Raises:
        requests.HTTPError: The server refuses the request.
    """
    with requests.get(url, stream=True, timeout=60) as response:
        response.raise_for_status()
        size = int(response.headers.get("Content-Length", 0))
        logger.log(
            logging.WARNING if size > LARGE_DOWNLOAD_BYTES else logging.INFO,
            "Downloading %s (%.1f MB)",
            url,
            size / 1e6,
        )
        next_tenth = 1
        with open(filename, "wb") as file:
            for chunk in response.iter_content(chunk_size=1 << 20):
                file.write(chunk)
                # The raw stream counts the bytes received, as Content-Length does,
                # also when requests decompresses them.
                done = response.raw.tell()
                if size and done >= next_tenth * size / 10:
                    logger.info(
                        "Downloaded %.1f of %.1f MB", done / 1e6, size / 1e6
                    )
                    next_tenth = done * 10 // size + 1
