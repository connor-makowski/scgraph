"""The child process of `StreamedPbf`.

It downloads byte ranges of an OSM PBF file and writes them to its standard output.
After a network error, it asks again from the first byte that it did not write.
"""

import json
import logging
import sys
import time

import requests

from scgraph.files import (
    MAX_RETRIES,
    check_byte_range_answer,
    create_retry_session,
)

logger = logging.getLogger(__name__)


class PbfRangeStreamer:
    """Writes byte ranges of the file at `url` to the standard output. `tag` is the ETag
    or the Last-Modified date that the file must keep. `size` is its size in bytes.
    """

    def __init__(self, url: str, tag: str, size: int) -> None:
        self.url = url
        self.tag = tag
        self.size = size

    def stream_ranges(self, ranges: list[list[int]]) -> None:
        """Write the byte ranges to the standard output, in order.

        Args:
            ranges: Pairs `[start, end]` of byte offsets. `end` is not included.

        Raises:
            ValueError: The tag or the size of the file changed on the server.
            requests.RequestException: A range failed more than `MAX_RETRIES` times in a
                row.
        """
        wanted = sum(end - start for start, end in ranges)
        done, shown, began = 0, 0, time.time()
        sink = sys.stdout.buffer
        session = create_retry_session()

        try:
            for start, end in ranges:
                failures = 0
                while start < end:
                    headers = {"Range": f"bytes={start}-{end - 1}"}
                    try:
                        with session.get(
                            self.url,
                            headers=headers,
                            stream=True,
                            timeout=(10.0, 60.0),
                        ) as response:
                            response.raise_for_status()
                            check_byte_range_answer(
                                response, self.tag, self.size
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
                        if failures > MAX_RETRIES:
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
