from __future__ import annotations

import json


def load_envelope(output: str) -> dict:
    for line in reversed(output.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        data = json.loads(line)
        if "data_source" in data and "items" in data:
            return data
    raise AssertionError(output)
