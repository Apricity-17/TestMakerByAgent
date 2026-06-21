"""File I/O tools for the agent."""

import glob as glob_mod
import os
from typing import Any

from langchain_core.tools import tool


@tool
def read_file(file_path: str, encoding: str = "utf-8") -> dict[str, Any]:
    """Read content of a file. Use this to get source code text.

    Args:
        file_path: Absolute or relative path to the file.
        encoding: Text encoding, defaults to utf-8.
    """
    try:
        with open(file_path, encoding=encoding) as f:
            content = f.read()
        lines = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
        return {"content": content, "line_count": lines, "file_path": file_path}
    except FileNotFoundError:
        return {"error": f"File not found: {file_path}", "file_path": file_path}
    except UnicodeDecodeError as e:
        return {"error": f"Encoding error ({encoding}): {e}", "file_path": file_path}


@tool
def write_file(file_path: str, content: str, mode: str = "w") -> dict[str, Any]:
    """Write or append content to a file. Use this to create test files.

    Args:
        file_path: Path to the file to write.
        content: The text content to write.
        mode: 'w' to overwrite, 'a' to append (default 'w').
    """
    try:
        os.makedirs(os.path.dirname(file_path) or ".", exist_ok=True)
        with open(file_path, mode, encoding="utf-8") as f:
            f.write(content)
        size = os.path.getsize(file_path)
        return {"success": True, "file_path": file_path, "bytes_written": size}
    except OSError as e:
        return {"success": False, "file_path": file_path, "error": str(e)}


@tool
def list_directory(
    path: str = ".", pattern: str = "*.py", recursive: bool = False
) -> dict[str, Any]:
    """List files and directories. Use to explore module structure.

    Args:
        path: Directory path to list.
        pattern: Glob pattern filter, e.g. '*.py' (default).
        recursive: If True, search subdirectories.
    """
    try:
        search_pattern = os.path.join(path, "**" if recursive else "", pattern)
        files = sorted(glob_mod.glob(search_pattern, recursive=recursive))
        dirs = sorted(
            [
                d
                for d in os.listdir(path)
                if os.path.isdir(os.path.join(path, d)) and not d.startswith(".")
            ]
        )
        return {"files": files, "dirs": dirs, "total": len(files)}
    except OSError as e:
        return {"files": [], "dirs": [], "total": 0, "error": str(e)}
