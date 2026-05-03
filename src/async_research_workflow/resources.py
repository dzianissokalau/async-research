"""Package resource helpers for async_research_workflow."""

from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Union

TraversablePath = Union[str, Path]


def package_root():
    return resources.files("async_research_workflow")


def schema_path(name: str):
    return package_root().joinpath("schemas", name)


def template_path(*parts: str):
    return package_root().joinpath("templates", *parts)


def docs_path(*parts: str):
    return package_root().joinpath("docs", *parts)


def examples_path(*parts: str):
    return package_root().joinpath("examples", *parts)
