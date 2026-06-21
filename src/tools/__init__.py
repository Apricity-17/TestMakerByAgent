"""Tool registry.

All tools are registered here and exported via get_all_tools().
"""

from langchain_core.tools import BaseTool

from src.tools.executor import exec_code
from src.tools.files import list_directory, read_file, write_file
from src.tools.parser import parse_code
from src.tools.runner import get_coverage, run_tests

_ALL_TOOLS: list[BaseTool] = [
    parse_code,
    read_file,
    write_file,
    list_directory,
    run_tests,
    get_coverage,
    exec_code,
]


def get_all_tools() -> list[BaseTool]:
    return _ALL_TOOLS


def get_explore_tools() -> list[BaseTool]:
    """Tools for the analyze phase: read-only exploration."""
    return [parse_code, read_file, list_directory]


def get_write_tools() -> list[BaseTool]:
    """Tools for writing test files."""
    return [write_file]


def get_exec_tools() -> list[BaseTool]:
    """Tools for executing tests and collecting coverage."""
    return [run_tests, get_coverage, exec_code]
