"""FDA's download server, faked on 127.0.0.1 for the tests of open-altio demo and fetch.

    server = FakeFda()                    # point open_altio.faers.fda.EXPORTS at server.url
    server.files["faers_ascii_2026q2.zip"] = zip_bytes
    server.cut_after = 1000               # the next answer stops after 1,000 bytes

It answers as fis.fda.gov does: a range request with 206 and Content-Range, a range past the end
with 416, and a file it does not have with a server error rather than a 404.
"""

from __future__ import annotations

import io
import re
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from open_altio.faers.fda import quarters_until, zip_name


class FakeFda:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.requests: list[tuple[str, str | None]] = []  # (file name, Range header)
        self.cut_after: int | None = None
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(self))
        self.url = f"http://127.0.0.1:{self._server.server_address[1]}/content/Exports/"
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def publish_until(self, last: str) -> None:
        """A small, whole zip for every quarter from FDA's first to `last`."""
        for quarter in quarters_until(last):
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
                z.writestr(f"ascii/DEMO{quarter[2:4]}Q{quarter[5]}.txt", f"{quarter}\n" * 50)
            self.files[zip_name(quarter)] = buffer.getvalue()

    def downloads_of(self, name: str) -> list[str | None]:
        """The Range header of every request for `name`, the size probes left out."""
        return [r for n, r in self.requests if n == name and r != "bytes=0-0"]

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()


def _handler(fake: FakeFda) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            name = self.path.rsplit("/", 1)[-1]
            asked = self.headers.get("Range")
            fake.requests.append((name, asked))
            body = fake.files.get(name)
            if body is None:
                self.send_error(500)
                return
            found = re.fullmatch(r"bytes=(\d+)-(\d*)", asked or "")
            start = int(found.group(1)) if found else 0
            end = int(found.group(2)) if found and found.group(2) else len(body) - 1
            if start >= len(body):
                self.send_error(416)
                return
            part = body[start : end + 1]
            self.send_response(206 if found else 200)
            if found:
                self.send_header("Content-Range", f"bytes {start}-{end}/{len(body)}")
            self.send_header("Content-Length", str(len(part)))
            self.end_headers()
            if fake.cut_after is not None:
                part, fake.cut_after = part[: fake.cut_after], None
                self.close_connection = True
            self.wfile.write(part)

    return Handler
