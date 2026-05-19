#!/usr/bin/env python3
"""Guarded apply command for reviewed data foundation proposals."""

from __future__ import annotations

import sys
from typing import Iterable

from async_research_workflow.scripts.foundation_proposal_apply import main_for_target


def main(argv: Iterable[str] | None = None) -> int:
    return main_for_target("data", argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
