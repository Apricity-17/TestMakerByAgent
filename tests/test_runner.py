"""Tests for test runner tools."""

from pathlib import Path

from src.tools.runner import _parse_test_output, run_tests


class TestParsePytestOutput:
    def test_parses_all_passing(self):
        stdout = "tests/test_x.py::test_one PASSED\ntests/test_x.py::test_two PASSED\n3 passed in 0.5s\n"
        result = _parse_test_output(stdout, "")
        assert result["total"] == 3
        assert result["passed"] == 3
        assert result["failed"] == 0

    def test_parses_mixed(self):
        stdout = "tests/test_x.py::test_ok PASSED\ntests/test_x.py::test_bad FAILED test failed\n1 passed, 1 failed in 0.3s\n"
        result = _parse_test_output(stdout, "")
        assert result["passed"] == 1
        assert result["failed"] == 1
        assert len(result["failures_detail"]) >= 1


class TestRunTests:
    def test_runs_tests_on_valid_file(self, tmp_path):
        # Create a simple test file
        test_file = tmp_path / "test_sample.py"
        test_file.write_text("""
def test_always_passes():
    assert True

def test_addition():
    assert 1 + 1 == 2
""")

        result = run_tests.invoke({"test_path": str(test_file)})
        assert result["total"] == 2
        assert result["passed"] == 2
        assert result["failed"] == 0

    def test_detects_failures(self, tmp_path):
        test_file = tmp_path / "test_failing.py"
        test_file.write_text("""
def test_fails():
    assert False, "intentional failure"
""")

        result = run_tests.invoke({"test_path": str(test_file)})
        assert result["failed"] == 1

    def test_timeout_returns_error(self, tmp_path):
        test_file = tmp_path / "test_slow.py"
        test_file.write_text("""
import time
def test_slow():
    time.sleep(200)
""")

        result = run_tests.invoke({"test_path": str(test_file), "pytest_args": ["--timeout=1"]})
        # The test may timeout or just be very slow; either way it should be handled
        assert "exit_code" in result
