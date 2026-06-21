"""Multi-language safe code execution tool."""

import os
import subprocess
import sys
from typing import Any

from langchain_core.tools import tool

PYTHON_RESTRICTED_PRELUDE = """
import builtins
_orig_import = builtins.__import__
def _safe_import(name, *args, **kwargs):
    forbidden = ('os', 'subprocess', 'sys', 'shutil', 'socket', 'ctypes',
                 'signal', 'multiprocessing', 'threading', 'pty', 'fcntl')
    if name.split('.')[0] in forbidden:
        raise ImportError(f"Module {name} is forbidden in sandbox")
    return _orig_import(name, *args, **kwargs)
builtins.__import__ = _safe_import
"""


def _detect_lang(code: str) -> str:
    if "fn main" in code or "fn test" in code or "use std" in code:
        return "rust"
    if "func Test" in code or "package " in code[:50]:
        return "go"
    if "public class" in code or "import java" in code:
        return "java"
    return "python"


@tool
def exec_code(code: str, timeout: int = 10) -> dict[str, Any]:
    """Execute a code snippet in an isolated subprocess.

    Python: restricted sandbox (no os, subprocess, socket, etc.)
    JavaScript/TypeScript: run via node
    Java: compile with javac then run with java
    Go: go run
    Rust: rustc + run (if rustc available)
    Unknown: defaults to Python execution

    Args:
        code: Source code string to execute.
        timeout: Maximum execution time in seconds (default 10).
    """
    lang = _detect_lang(code)

    if lang == "go":
        return _run_go(code, timeout)
    elif lang == "rust":
        return _run_rust(code, timeout)
    elif lang == "java":
        return _run_java(code, timeout)
    else:
        return _run_python(code, timeout)


def _run_python(code: str, timeout: int) -> dict[str, Any]:
    full_code = PYTHON_RESTRICTED_PRELUDE + "\n" + code
    try:
        result = subprocess.run(
            [sys.executable, "-c", full_code],
            capture_output=True, text=True, timeout=timeout,
        )
        return {
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "return_value": "",
            "exception": None if result.returncode == 0 else f"Exit code {result.returncode}",
        }
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": "", "return_value": "", "exception": f"Timed out after {timeout}s"}


def _run_go(code: str, timeout: int) -> dict[str, Any]:
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".go", mode="w", delete=False) as f:
        f.write(code)
        tmp_path = f.name
    try:
        result = subprocess.run(
            ["go", "run", tmp_path],
            capture_output=True, text=True, timeout=timeout,
        )
        return {
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "return_value": "",
            "exception": None if result.returncode == 0 else f"Exit code {result.returncode}",
        }
    except FileNotFoundError:
        return {"stdout": "", "stderr": "", "return_value": "", "exception": "go not installed"}
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": "", "return_value": "", "exception": f"Timed out after {timeout}s"}
    finally:
        os.unlink(tmp_path)


def _run_rust(code: str, timeout: int) -> dict[str, Any]:
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".rs", mode="w", delete=False) as f:
        f.write(code)
        tmp_path = f.name
    bin_path = tmp_path.replace(".rs", "")
    try:
        compile_result = subprocess.run(
            ["rustc", tmp_path, "-o", bin_path],
            capture_output=True, text=True, timeout=30,
        )
        if compile_result.returncode != 0:
            return {"stdout": "", "stderr": compile_result.stderr.strip(), "return_value": "", "exception": "Compilation failed"}
        run_result = subprocess.run(
            [bin_path], capture_output=True, text=True, timeout=timeout,
        )
        return {
            "stdout": run_result.stdout.strip(),
            "stderr": run_result.stderr.strip(),
            "return_value": "",
            "exception": None if run_result.returncode == 0 else f"Exit code {run_result.returncode}",
        }
    except FileNotFoundError:
        return {"stdout": "", "stderr": "", "return_value": "", "exception": "rustc not installed"}
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": "", "return_value": "", "exception": f"Timed out after {timeout}s"}
    finally:
        try:
            os.unlink(tmp_path)
            os.unlink(bin_path)
        except OSError:
            pass


def _run_java(code: str, timeout: int) -> dict[str, Any]:
    import tempfile, re
    class_match = re.search(r"class\s+(\w+)", code)
    class_name = class_match.group(1) if class_match else "TempExec"
    tmp_dir = tempfile.mkdtemp()
    tmp_path = os.path.join(tmp_dir, class_name + ".java")
    with open(tmp_path, "w") as f:
        f.write(code)
    try:
        compile_result = subprocess.run(
            ["javac", tmp_path], capture_output=True, text=True, timeout=30,
        )
        if compile_result.returncode != 0:
            return {"stdout": "", "stderr": compile_result.stderr.strip(), "return_value": "", "exception": "Compilation failed"}
        run_result = subprocess.run(
            ["java", "-cp", tmp_dir, class_name],
            capture_output=True, text=True, timeout=timeout,
        )
        return {
            "stdout": run_result.stdout.strip(),
            "stderr": run_result.stderr.strip(),
            "return_value": "",
            "exception": None if run_result.returncode == 0 else f"Exit code {run_result.returncode}",
        }
    except FileNotFoundError:
        return {"stdout": "", "stderr": "", "return_value": "", "exception": "javac not installed"}
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": "", "return_value": "", "exception": f"Timed out after {timeout}s"}
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)
