from __future__ import annotations

import json
from typing import Any

import click

from autodl_cli.__version__ import __version__


def make_envelope(
    *,
    module: str,
    data_source: str,
    ok: bool,
    items: list[Any] | None = None,
    run_id: str | None = None,
    job_id: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "module": module,
        "version": __version__,
        "data_source": data_source,
        "ok": ok,
        "items": items or [],
    }
    payload["count"] = len(payload["items"])
    if run_id:
        payload["run_id"] = run_id
    if job_id:
        payload["job_id"] = job_id
    for key, value in extra.items():
        if value is not None:
            payload[key] = value
    return payload


def emit(envelope: dict[str, Any], fmt: str) -> None:
    if fmt == "table":
        skip = {"items"}
        for key, value in envelope.items():
            if key in skip:
                continue
            click.echo(f"{key}\t{value}")
        items = envelope.get("items") or []
        if items:
            click.echo(json.dumps(items, ensure_ascii=False, indent=2))
        return
    click.echo(json.dumps(envelope, ensure_ascii=False))
