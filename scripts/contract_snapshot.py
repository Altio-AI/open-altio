"""Write the snapshot of the published questions' answers, tests/contract/snapshots/api.json.

    uv run python scripts/contract_snapshot.py

It builds the invented release (open_altio.testing.contract) in a scratch folder, asks each
published route the question `ASKED` gives it, and writes every answer's keys under
`open_altio.CONTRACT_VERSION`. It refuses to drop a route or a key the snapshot lists unless
CONTRACT_VERSION's major is above the snapshot's, and exits 2 saying what would go.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from open_altio import CONTRACT_VERSION
from open_altio.explorer.app import create_app
from open_altio.testing.contract import SnapshotRefused, invented_release, renewed, snapshot

SNAPSHOT = Path(__file__).resolve().parents[1] / "tests" / "contract" / "snapshots" / "api.json"


def main() -> int:
    old = json.loads(SNAPSHOT.read_text(encoding="utf-8")) if SNAPSHOT.is_file() else None
    with (
        tempfile.TemporaryDirectory(prefix="open-altio-contract-") as scratch,
        TestClient(create_app(invented_release(Path(scratch)))) as web,
    ):
        routes = snapshot(web)
    try:
        written = renewed(old, routes, CONTRACT_VERSION)
    except SnapshotRefused as e:
        print(f"contract_snapshot: {e}", file=sys.stderr)
        return 2
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_text(json.dumps(written, indent=2) + "\n", encoding="utf-8")
    print(f"{SNAPSHOT}: {len(routes)} routes under contract {CONTRACT_VERSION}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
