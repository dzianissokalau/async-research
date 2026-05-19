#!/usr/bin/env python3
"""Write a deterministic adapter marker for the runnable analysis fixture."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: write_fixture_marker.py <target-json>", file=sys.stderr)
        return 2
    target = Path(argv[0])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps({"ok": True, "source": "runnable_experiment_analysis_adapter"}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
