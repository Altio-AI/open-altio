"""How /api answers: JSON with dates as yyyy-mm-dd and no NaN, never cached by
the browser, and every refusal as {"problem": ...}. A route refuses by raising Problem."""

from __future__ import annotations

import json
import math
from datetime import date, datetime
from typing import Any

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


__all__ = ["Problem", "answer", "clean", "json_body", "problem"]
