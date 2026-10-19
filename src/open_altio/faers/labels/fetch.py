"""Download what the labels step reads into one folder (rule label-source).

python -m open_altio.faers labels-fetch --into ~/faers-labels
"""

from __future__ import annotations

import time
import zipfile
from collections.abc import Callable
from pathlib import Path

import httpx

from open_altio import rulebook

RULE = "label-source"


def new_client() -> httpx.Client:
    return httpx.Client(
        timeout=httpx.Timeout(60.0, read=600.0),
        follow_redirects=True,
        headers={"User-Agent": rulebook.value(RULE, "user_agent")},
    )


def pause() -> None:
    time.sleep(float(rulebook.value(RULE, "seconds_between_requests")))


def size_of(client: httpx.Client, url: str) -> int | None:
    """The file's size, or None when the server says it does not exist."""
    response = client.head(url)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return int(response.headers["content-length"])


def download(client: httpx.Client, url: str, target: Path, size: int) -> bool:
    """Fetch `url` into `target`, carrying on from a partial `.part` file.
    False when `target` was already whole and nothing was fetched."""
    if target.is_file() and target.stat().st_size == size:
        return False
    part = target.with_name(target.name + ".part")
    have = part.stat().st_size if part.is_file() else 0
    if have < size:
        headers = {"Range": f"bytes={have}-"} if have else {}
        with client.stream("GET", url, headers=headers) as response:
            response.raise_for_status()
            if have and response.status_code != 206:  # the server ignored the range
                have = 0
            with open(part, "ab" if have else "wb") as out:
                out.writelines(response.iter_bytes(1 << 20))
    if part.stat().st_size != size:
        raise OSError(f"{url}: got {part.stat().st_size} bytes of {size}; run the fetch again")
    try:
        with zipfile.ZipFile(part):  # opens only when the central directory is whole
            pass
    except zipfile.BadZipFile:
        part.unlink()  # a stale part from an older file; the next run starts afresh
        raise OSError(f"{url}: the download is not a whole zip; run the fetch again") from None
    part.rename(target)
    return True


def wanted(client: httpx.Client) -> list[tuple[str, str, int]]:
    """(url, file name, size) of every file the labels step reads."""
    base = rulebook.value(RULE, "release_files_url")
    pattern = rulebook.value(RULE, "release_file_pattern")
    files = []
    n = 1
    while True:
        name = pattern.format(n=n)
        size = size_of(client, base + name)
        pause()
        if size is None:
            break
        files.append((base + name, name, size))
        n += 1
    if not files:
        raise OSError(f"DailyMed has no {pattern.format(n=1)} at {base}")
    for url in (
        base + rulebook.value(RULE, "mapping_file"),
        rulebook.value(RULE, "rxnorm_url"),
    ):
        size = size_of(client, url)
        pause()
        if size is None:
            raise OSError(f"{url} does not exist")
        files.append((url, url.rsplit("/", 1)[1], size))
    return files


def fetch(into: str | Path, say: Callable[[str], None] | None = None) -> list[Path]:
    """Every file the labels step reads, downloaded into `into` one at a time."""
    say = say or (lambda _line: None)
    folder = Path(into).expanduser()
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    with new_client() as client:
        for url, name, size in wanted(client):
            started = time.monotonic()
            fetched = download(client, url, folder / name, size)
            took = time.monotonic() - started
            say(
                f"{name} {size} bytes " + (f"fetched in {took:.0f}s" if fetched else "already here")
            )
            paths.append(folder / name)
            if fetched:
                pause()
    return paths
