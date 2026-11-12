"""HTTP byte-range streamer child process for StreamedPbf.

Streams requested byte ranges of a remote OSM PBF file into stdout,
resuming automatically after transient network errors.
"""

import json
import logging
import sys
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)
_MAX_RETRIES = 10  # consecutive failures accepted per range


class PbfRangeStreamer:
    """Streams byte ranges from a remote URL to stdout."""

    def __init__(self, url: str, tag: str, size: int) -> None:
        """Initialize the range streamer.

        Args:
            url: Remote resource URL.
            tag: Target ETag or Last-Modified identifier.
            size: Total file size in bytes.
        """
        self.url = url
        self.tag = tag
        self.size = size

    def _create_session(self) -> requests.Session:
        """Create a requests session with connection pooling and retries."""
        session = requests.Session()
        retries = Retry(
            total=_MAX_RETRIES,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(
            max_retries=retries,
            pool_connections=4,
            pool_maxsize=4,
        )
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def stream_ranges(self, ranges: list[list[int]]) -> None:
        """Stream byte ranges into stdout.

        Args:
            ranges: List of [start, end] byte offset pairs.

        Raises:
            SystemExit: If the remote file tag or size changes during streaming.
            requests.RequestException: If transient network retries are exhausted.
        """
        wanted = sum(end - start for start, end in ranges)
        done, shown, began = 0, 0, time.time()
        sink = sys.stdout.buffer
        session = self._create_session()

        try:
            for start, end in ranges:
                failures = 0
                while start < end:
                    headers = {
                        "User-Agent": "scgraph",
                        "Range": f"bytes={start}-{end - 1}",
                    }
                    try:
                        with session.get(
                            self.url,
                            headers=headers,
                            stream=True,
                            timeout=(10.0, 60.0),
                        ) as response:
                            response.raise_for_status()
                            tag = response.headers.get(
                                "ETag"
                            ) or response.headers.get("Last-Modified")
                            total = response.headers.get(
                                "Content-Range", ""
                            ).rpartition("/")[2]

                            if (
                                response.status_code != 206
                                or tag != self.tag
                                or total != str(self.size)
                            ):
                                sys.exit(
                                    f"{self.url} changed or ignores byte ranges"
                                )

                            for chunk in response.iter_content(1 << 20):
                                sink.write(chunk)
                                start += len(chunk)
                                failures = 0
                                done += len(chunk)
                                if (
                                    done - shown >= 1 << 31
                                ):  # Progress every 2 GiB
                                    shown = done
                                    elapsed = max(0.1, time.time() - began)
                                    rate = done / 1e6 / elapsed
                                    logger.info(
                                        "%d of %d GB read (%.1f MB/s)",
                                        int(done / 1e9),
                                        int(wanted / 1e9),
                                        rate,
                                    )
                    except BrokenPipeError:
                        # Reader closed downstream pipe: exit cleanly
                        sys.exit(0)
                    except (
                        requests.RequestException,
                        OSError,
                        TimeoutError,
                    ) as error:
                        failures += 1
                        if failures > _MAX_RETRIES:
                            raise
                        logger.warning(
                            "Transient read error at byte offset %d: %r. Retrying...",
                            start,
                            error,
                        )
                        time.sleep(min(60, 2**failures))
            sink.flush()
        finally:
            session.close()


def main() -> None:
    """CLI entry point for the child streamer process."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if len(sys.argv) > 1:
        job = json.loads(sys.argv[1])
        streamer = PbfRangeStreamer(
            url=job["url"],
            tag=job["tag"],
            size=job["size"],
        )
        streamer.stream_ranges(job["ranges"])


if __name__ == "__main__":
    main()
