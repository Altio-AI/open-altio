"""How /api answers: JSON with dates as yyyy-mm-dd and no NaN, never cached by
the browser, every refusal as {"problem": ...}, every answer counted on a release naming it
(`counted_on`), and each count with the case list's question for its cases (`cases_query`). A
route refuses by raising Problem."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any
from urllib.parse import urlencode

from fastapi import Request, Response


class Problem(Exception):
    """A question that cannot be answered as asked; `status` is the HTTP status."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


def _plain(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def clean(obj: Any) -> Any:
    """Dates as ISO text, NaN and infinity as null, all the way down."""
    if isinstance(obj, dict):
        return {k: clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean(v) for v in obj]
    return _plain(obj)


def counted_on(manifest: dict[str, Any]) -> dict[str, Any]:
    """The release an answer was counted on: its name, its source and its quarters."""
    quarters = manifest["quarters"]
    return {
        "release": manifest["release"],
        "source": manifest["source"],
        "first_quarter": quarters[0],
        "last_quarter": quarters[-1],
    }


# what the case list reads beyond the question a count answered: a page of it, its order, and which
# of the count's cases it lists
CASE_LIST_OWN = ("page", "sort", "event", "period", "field", "value")


def cases_query(query: Mapping[str, Sequence[str]], *left_out: str, **chosen: Sequence[str]) -> str:
    """The /api/cases question that lists exactly a count's cases: the question the count
    answered (`query`, as parse_qs reads it), less the names `left_out`, with `chosen` set, its
    names in order so the same question gives the same text."""
    dropped = {*CASE_LIST_OWN, *left_out, *chosen}
    asked = {k: v for k, v in query.items() if k not in dropped} | dict(chosen)
    return urlencode([(k, v) for k in sorted(asked) for v in asked[k]])


def answer(value: Any, status: int = 200) -> Response:
    body = json.dumps(clean(value), default=str)
    return Response(
        body,
        status_code=status,
        media_type="application/json",
        headers={"Cache-Control": "no-store"},
    )


def problem(status: int, message: str) -> Response:
    return answer({"problem": message}, status)


async def json_body(request: Request) -> dict | Response:
    """The posted JSON object, or the problem to answer. JSON only: another site's
    form cannot send it, so these posts need no form token."""
    if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
        return problem(415, "Send it as JSON.")
    try:
        asked = await request.json()
    except ValueError:
        asked = None
    return asked if isinstance(asked, dict) else problem(400, "Send a JSON object.")


__all__ = [
    "CASE_LIST_OWN",
    "Problem",
    "answer",
    "cases_query",
    "clean",
    "counted_on",
    "json_body",
    "problem",
]
