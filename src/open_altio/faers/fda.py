"""FDA's quarterly files: which quarters FDA has published, and downloading them.

    latest = latest_quarter(date.today())                 # '2026q2'
    path = download(latest, folder, on_bytes=show)        # folder/faers_ascii_2026q2.zip

FDA publishes one zip per quarter: the legacy AERS files from 2004Q1 to 2012Q3
(`aers_ascii_2004q1.zip`) and FAERS from 2012Q4 (`faers_ascii_2012q4.zip`). It publishes no
checksums beside them, so a download is checked against the size FDA's server gives and against
the CRC-32 every zip holds for each file in it. A download goes to `<name>.part` first, so a
stopped one carries on from where it stopped and a damaged one never takes a quarter's name.
"""

from __future__ import annotations

import re
import time
import zipfile
import zlib
from collections.abc import Callable
from datetime import date
from http.client import HTTPException, HTTPResponse
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .sources import QUARTER, quarter_key

# Read at each call, so a test can point it elsewhere.
EXPORTS = "https://fis.fda.gov/content/Exports/"
FIRST_QUARTER = "2004q1"
FIRST_FAERS_QUARTER = "2012q4"
TIMEOUT_SECONDS = 60
ATTEMPTS = 3  # a dropped connection is picked up again where it stopped
RETRY_WAIT_SECONDS = 1.0  # times the attempt number
CHUNK = 1 << 20
PART = ".part"

# done, total: bytes of one file so far and in all
OnBytes = Callable[[int, int], None]


class FetchError(Exception):
    """FDA's files could not be fetched; the message says why and what to do, in plain words."""


def zip_name(quarter: str) -> str:
    era = "faers" if quarter_key(quarter) >= quarter_key(FIRST_FAERS_QUARTER) else "aers"
    return f"{era}_ascii_{quarter}.zip"


def _quarter_of(day: date) -> str:
    return f"{day.year}q{(day.month - 1) // 3 + 1}"


def _previous(quarter: str) -> str:
    year, q = int(quarter[:4]), int(quarter[5])
    return f"{year - 1}q4" if q == 1 else f"{year}q{q - 1}"


def quarters_until(last: str) -> list[str]:
    """Every quarter from FDA's first to `last`, oldest first."""
    found = [last]
    while found[-1] != FIRST_QUARTER:
        found.append(_previous(found[-1]))
    return found[::-1]


def _get(url: str, start: int) -> HTTPResponse:
    """FDA's answer for `url` from byte `start` on."""
    return urlopen(Request(url, headers={"Range": f"bytes={start}-"}), timeout=TIMEOUT_SECONDS)


def _total_size(response: HTTPResponse) -> int:
    """The whole file's size: from Content-Range on a partial answer, else Content-Length."""
    found = re.search(r"/(\d+)$", response.headers.get("Content-Range", ""))
    return int(found.group(1)) if found else int(response.headers["Content-Length"])


def published_size(quarter: str) -> int | None:
    """The size of FDA's zip for `quarter`, or None when FDA has not published it.

    FDA's server answers HEAD with no size and a missing file with a server error, so this asks
    for the file's first byte and reads the size from the answer."""
    try:
        with urlopen(
            Request(EXPORTS + zip_name(quarter), headers={"Range": "bytes=0-0"}),
            timeout=TIMEOUT_SECONDS,
        ) as response:
            return _total_size(response)
    except HTTPError:
        return None
    except URLError as e:
        raise FetchError(
            f"Could not reach FDA at {EXPORTS} ({e.reason}). "
            "Check this machine's internet connection, then try again."
        ) from e


def latest_quarter(today: date) -> str:
    """The newest quarter FDA has published, looking back from today's quarter. FDA publishes
    a quarter a month or two after it ends, so the search goes back a year at most."""
    quarter = _quarter_of(today)
    for _ in range(5):
        if published_size(quarter) is not None:
            return quarter
        quarter = _previous(quarter)
    raise FetchError(
        f"FDA has published no quarterly file at {EXPORTS} for the last year. "
        "FDA may have moved its files; please report this with: open-altio report"
    )


def downloaded(folder: Path) -> list[str]:
    """The quarters whose zips are whole in `folder`, oldest first (a stopped one is `.part`)."""
    found = (QUARTER.search(p.name) for p in folder.glob("*_ascii_*.zip"))
    return sorted((f"{m.group(1)}q{m.group(2)}" for m in found if m), key=quarter_key)


def verify(path: Path) -> None:
    """Raise FetchError unless `path` is a whole zip whose files all match their CRC-32."""
    try:
        with zipfile.ZipFile(path) as z:
            bad = z.testzip()
    except (zipfile.BadZipFile, zlib.error, EOFError, OSError) as e:
        raise FetchError(f"{path.name} is damaged ({e}).") from e
    if bad is not None:
        raise FetchError(f"{path.name} is damaged: {bad} does not match its checksum.")


def download(quarter: str, folder: Path, *, on_bytes: OnBytes | None = None) -> Path:
    """FDA's zip for `quarter` in `folder`, downloaded unless it is there already."""
    target = folder / zip_name(quarter)
    if target.is_file():
        return target
    folder.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + PART)
    for attempt in range(1, ATTEMPTS + 1):
        try:
            _download_into(EXPORTS + target.name, part, on_bytes)
            break
        except (URLError, HTTPException, TimeoutError, ConnectionError) as e:
            if attempt == ATTEMPTS:
                have = part.stat().st_size if part.is_file() else 0
                raise FetchError(
                    f"The download of {target.name} stopped after {have / 1e6:.0f} MB ({e}). "
                    "Run the same command again to carry on from there."
                ) from e
            time.sleep(attempt * RETRY_WAIT_SECONDS)
    try:
        verify(part)
    except FetchError as e:
        part.unlink()
        raise FetchError(f"{e} Run the same command again to download it afresh.") from e
    part.replace(target)
    return target


def _download_into(url: str, part: Path, on_bytes: OnBytes | None) -> None:
    have = part.stat().st_size if part.is_file() else 0
    try:
        response = _get(url, have)
    except HTTPError as e:
        if e.code == 416:  # nothing past `have`: the part is whole
            return
        raise FetchError(f"FDA answered {e.code} for {url}.") from e
    with response:
        if response.status != 206:  # the server sent the whole file: start again
            have = 0
        total = _total_size(response)
        with open(part, "ab" if have else "wb") as out:
            # read1 hands over what has arrived, so it is kept even if the rest never does
            while chunk := response.read1(CHUNK):
                out.write(chunk)
                have += len(chunk)
                if on_bytes:
                    on_bytes(have, total)
    if have < total:
        raise ConnectionError(f"the connection closed at {have} of {total} bytes")
