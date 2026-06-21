"""Tests for parse_code tool."""

import tempfile
from pathlib import Path

from src.tools.parser import parse_code


SAMPLE_MODULE = '''
"""Sample module for testing."""

import os
import requests
from typing import Optional

def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b

def divide(a: float, b: float) -> float:
    """Divide a by b. Raises on zero."""
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b

class Calculator:
    """Simple calculator."""

    def __init__(self, initial: float = 0):
        self.value = initial

    def add(self, x: float) -> float:
        self.value += x
        return self.value

    @staticmethod
    def version() -> str:
        return "1.0"
'''


class TestParseCode:
    def test_extracts_functions(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as f:
            f.write(SAMPLE_MODULE)
            tmp_path = f.name

        try:
            result = parse_code.invoke({"file_path": tmp_path})
            func_names = [fn["name"] for fn in result["functions"]]
            assert "add" in func_names
            assert "divide" in func_names
            assert len(result["functions"]) >= 2
        finally:
            Path(tmp_path).unlink()

    def test_extracts_classes(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as f:
            f.write(SAMPLE_MODULE)
            tmp_path = f.name

        try:
            result = parse_code.invoke({"file_path": tmp_path})
            class_names = [c["name"] for c in result["classes"]]
            assert "Calculator" in class_names
        finally:
            Path(tmp_path).unlink()

    def test_extracts_imports(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as f:
            f.write(SAMPLE_MODULE)
            tmp_path = f.name

        try:
            result = parse_code.invoke({"file_path": tmp_path})
            imported = {imp["module"] for imp in result["imports"]}
            assert "os" in imported
            assert "requests" in imported
        finally:
            Path(tmp_path).unlink()

    def test_extracts_branches(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as f:
            f.write(SAMPLE_MODULE)
            tmp_path = f.name

        try:
            result = parse_code.invoke({"file_path": tmp_path})
            branch_types = [b["type"] for b in result["branches"]]
            assert "if" in branch_types
        finally:
            Path(tmp_path).unlink()

    def test_detects_external_deps(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as f:
            f.write(SAMPLE_MODULE)
            tmp_path = f.name

        try:
            result = parse_code.invoke({"file_path": tmp_path})
            assert "http" in result["external_deps"]
            assert "file_io" in result["external_deps"]
        finally:
            Path(tmp_path).unlink()

    def test_complexity_calculation(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as f:
            f.write(SAMPLE_MODULE)
            tmp_path = f.name

        try:
            result = parse_code.invoke({"file_path": tmp_path})
            add_fn = next(fn for fn in result["functions"] if fn["name"] == "add")
            divide_fn = next(fn for fn in result["functions"] if fn["name"] == "divide")
            assert add_fn["complexity"] == 1
            assert divide_fn["complexity"] >= 2  # has an if
        finally:
            Path(tmp_path).unlink()
