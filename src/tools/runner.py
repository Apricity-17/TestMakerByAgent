"""Multi-language test execution and coverage tools."""

import json
import os
import re
import subprocess
import sys
import tempfile
from typing import Any, Optional

from langchain_core.tools import tool


LANGUAGE_MAP = {
    ".py": "python",
    ".java": "java",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".jsx": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
}


def _detect_language(test_path: str, target_path: str) -> str:
    ext = os.path.splitext(test_path)[1].lower()
    if ext == ".py":
        return "python"
    if ext in (".js", ".jsx", ".ts", ".tsx"):
        return "javascript"
    if ext == ".java":
        return "java"
    if ext == ".go":
        return "go"
    if ext == ".rs":
        return "rust"
    if ext == ".rb":
        return "ruby"
    # Fallback: check target
    if target_path:
        ext2 = os.path.splitext(target_path)[1].lower()
        return LANGUAGE_MAP.get(ext2, "unknown")
    return "unknown"


def _build_test_cmd(test_path: str, target_path: str, language: str, pytest_args: Optional[list[str]] = None) -> list[str]:
    extra = pytest_args or []
    if language == "python":
        return [sys.executable, "-m", "pytest", test_path, "-v", "--tb=short", "--no-header"] + extra
    elif language == "javascript":
        npx = "npx.cmd" if sys.platform == "win32" else "npx"
        return [npx, "jest", test_path, "--verbose", "--no-coverage"] + extra
    elif language == "java":
        # Run via Maven or Gradle — for single file, use javac + java
        return _java_test_cmd(test_path, extra)
    elif language == "go":
        return ["go", "test", "-v", test_path] + extra
    elif language == "rust":
        return ["cargo", "test"] + extra
    elif language == "ruby":
        return ["ruby", "-Itest", test_path] + extra
    return ["echo", f"No test runner configured for {language}"]


def _detect_java_project_root(hint_path: str = "") -> Optional[str]:
    """Walk upward from hint_path (or cwd) to find Maven/Gradle project root."""
    start = os.path.dirname(os.path.abspath(hint_path)) if hint_path else os.getcwd()
    cwd = start
    for _ in range(5):
        if os.path.exists(os.path.join(cwd, "pom.xml")):
            return cwd
        if os.path.exists(os.path.join(cwd, "build.gradle")) or os.path.exists(os.path.join(cwd, "build.gradle.kts")):
            return cwd
        parent = os.path.dirname(cwd)
        if parent == cwd:
            break
        cwd = parent
    return None

def _find_junit_jars(near_path: str) -> Optional[str]:
    """Search for JUnit console standalone JAR near the test file or in test_* directories."""
    import glob as _glob
    search_dirs = [
        os.path.dirname(os.path.abspath(near_path)),
        os.path.join(os.path.dirname(os.path.abspath(near_path)), "test_*"),
    ]
    for d in search_dirs:
        for p in _glob.glob(os.path.join(d, "junit-platform-console-standalone*.jar")):
            return os.path.dirname(p)
        for p in _glob.glob(os.path.join(d, "**", "junit-platform-console-standalone*.jar"), recursive=True):
            return os.path.dirname(p)
    return None


def _java_test_cmd(test_path: str, extra: list[str]) -> list[str]:
    """Build Java test command using Maven or Gradle if available."""
    project_root = _detect_java_project_root(test_path)
    test_class = os.path.basename(test_path).replace(".java", "")

    if project_root:
        # Check Maven: only use if mvn binary exists
        if os.path.exists(os.path.join(project_root, "pom.xml")):
            mvn_check = subprocess.run(["which", "mvn"], capture_output=True, text=True)
            if mvn_check.returncode == 0 and mvn_check.stdout.strip():
                return ["mvn", "test", "-Dtest=" + test_class, "-f", os.path.join(project_root, "pom.xml")] + extra
        # Check Gradle
        if os.path.exists(os.path.join(project_root, "build.gradle")) or os.path.exists(os.path.join(project_root, "build.gradle.kts")):
            gradle = os.path.join(project_root, "gradlew")
            if not os.path.exists(gradle):
                gradle = "gradle"
            gradle_check = subprocess.run(["which", gradle], capture_output=True, text=True)
            if gradle_check.returncode == 0 and gradle_check.stdout.strip():
                return [gradle, "test", "--tests", test_class, "-p", project_root] + extra

    # No build tool — try JUnit ConsoleLauncher with local JARs
    import glob as _glob
    jar_dir = _find_junit_jars(test_path)
    if jar_dir:
        source_dir = os.path.dirname(os.path.abspath(test_path))
        # Use parent dir as classpath root (required by package declarations)
        classpath_root = os.path.dirname(source_dir)
        all_jars = _glob.glob(os.path.join(jar_dir, "*.jar"))
        cp = ":".join([classpath_root] + all_jars)
        # Compile all .java files from source directory
        test_dir_local = os.path.dirname(os.path.abspath(test_path))
        all_java_rel = " ".join(os.path.relpath(f, classpath_root) for f in _glob.glob(os.path.join(test_dir_local, "*.java")))
        compile_cmd = f"cd {classpath_root} && javac -cp '{cp}' {all_java_rel} 2>&1 && echo 'COMPILE_OK'"
        # Run from source dir so --scan-classpath finds the test classes
        run_cmd = f"cd {classpath_root} && java -cp '{cp}' org.junit.platform.console.ConsoleLauncher --scan-classpath --details=tree 2>&1"
        combined = f"{compile_cmd}; {run_cmd}"
        return ["sh", "-c", combined]

    msg = (
        f"echo 'Java test cannot run: no Maven/Gradle/JUnit JARs found.\\n"
        f"Options:\\n"
        f"  1. Download JUnit JARs to {os.path.dirname(test_path)}/\\n"
        f"  2. Test file is at: {test_path}'"
    )
    return ["sh", "-c", msg]


def _build_cov_cmd(source_path: str, test_path: str, language: str, json_path: str) -> Optional[list[str]]:
    if language == "python":
        cov_target = source_path
        if cov_target.endswith(".py"):
            cov_target = cov_target[:-3]
        return [
            sys.executable, "-m", "pytest", test_path,
            f"--cov={cov_target}",
            f"--cov-report=json:{json_path}",
            "--cov-report=term", "--no-header", "-q",
        ]
    elif language == "javascript":
        npx = "npx.cmd" if sys.platform == "win32" else "npx"
        return [npx, "jest", test_path, "--coverage", "--json", "--outputFile=" + json_path, "--no-coverage"]
    elif language == "java":
        project_root = _detect_java_project_root(test_path)
        if project_root and os.path.exists(os.path.join(project_root, "pom.xml")):
            test_class = os.path.basename(test_path).replace(".java", "")
            return [
                "mvn", "test", "-Dtest=" + test_class, "-f", os.path.join(project_root, "pom.xml"),
            ]
        return None  # Java without Maven — can't measure coverage
    # For other languages, coverage not yet supported
    return None


@tool
def run_tests(
    test_path: str,
    target_path: str = "",
    pytest_args: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Run tests on a test file and return results.

    Supports Python (pytest), JavaScript/TypeScript (Jest), Java (JUnit/Maven/Gradle),
    Go (go test), Rust (cargo test), Ruby (ruby -Itest).

    Args:
        test_path: Path to the test file or directory.
        target_path: Optional source path for context.
        pytest_args: Additional test runner arguments.
    """
    language = _detect_language(test_path, target_path)
    cmd = _build_test_cmd(test_path, target_path, language, pytest_args)

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120, cwd=os.getcwd()
        )
    except subprocess.TimeoutExpired:
        return {
            "exit_code": -1, "total": 0, "passed": 0, "failed": 0, "errors": 1,
            "failures_detail": [{"test": "TIMEOUT", "message": "Test execution timed out (120s)"}],
            "stdout": "", "stderr": "TIMEOUT",
        }
    except FileNotFoundError:
        return {
            "exit_code": -1, "total": 0, "passed": 0, "failed": 0, "errors": 1,
            "failures_detail": [{"test": "RUNNER_NOT_FOUND", "message": f"Test runner not found for {language}. Install it first."}],
            "stdout": "", "stderr": f"Command not found: {cmd[0]}",
        }

    return _parse_test_output(result.stdout, result.stderr, language)


@tool
def get_coverage(source_path: str, test_path: str) -> dict[str, Any]:
    """Run tests with coverage measurement and return coverage data.

    Full support: Python (pytest-cov).
    Basic support: JavaScript/TypeScript (Jest --coverage).
    Other languages: runs tests only, returns placeholder coverage.

    Args:
        source_path: Path to the source file or package to measure.
        test_path: Path to the test file or directory.
    """
    language = _detect_language(test_path, source_path)

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        json_path = tmp.name

    try:
        cmd = _build_cov_cmd(source_path, test_path, language, json_path)
        if cmd is None:
            # Language not supported for coverage — just run tests
            test_result = run_tests.invoke({"test_path": test_path, "target_path": source_path})
            return {
                "line_rate": 0.0, "branch_rate": 0.0,
                "total_lines": 0, "covered_lines": 0,
                "uncovered": [], "per_function": [],
                "_test_stdout": test_result.get("stdout", ""),
                "note": _coverage_note(language, test_path),
            }

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120, cwd=os.getcwd()
        )

        if language == "python":
            return _parse_python_coverage(json_path, source_path, result.stdout)
        elif language == "javascript":
            return _parse_jest_coverage(json_path, result.stdout)
        else:
            return {
                "line_rate": 0.0, "branch_rate": 0.0,
                "total_lines": 0, "covered_lines": 0,
                "uncovered": [], "per_function": [],
                "_test_stdout": result.stdout,
            }
    except subprocess.TimeoutExpired:
        return {
            "line_rate": 0.0, "branch_rate": 0.0,
            "total_lines": 0, "covered_lines": 0,
            "uncovered": [], "per_function": [],
            "error": "Coverage execution timed out",
        }
    finally:
        try:
            os.unlink(json_path)
        except OSError:
            pass


# ─── Parsers ─────────────────────────────────────────────────────────────────


def _coverage_note(language: str, test_path: str) -> str:
    if language == "java":
        return (
            f"Java coverage requires Maven/Gradle with JaCoCo plugin. "
            f"Test file at: {test_path}. "
            f"Run with: mvn test jacoco:report"
        )
    if language == "go":
        return "Run: go test -coverprofile=coverage.out"
    if language == "rust":
        return "Run: cargo tarpaulin"
    return f"Coverage measurement not yet supported for {language}"


def _parse_test_output(stdout: str, stderr: str, language: str = "python") -> dict[str, Any]:
    # Strip ANSI escape codes for parsing
    clean = re.sub(r"\x1b\[[0-9;]*m", "", stdout)
    total, passed, failed, errors = 0, 0, 0, 0
    failures_detail: list[dict[str, str]] = []

    # JUnit ConsoleLauncher format
    m_success = re.search(r"(\d+)\s+tests\s+successful", clean)
    m_failed = re.search(r"(\d+)\s+tests\s+failed", clean)
    m_found = re.search(r"(\d+)\s+tests\s+found", clean)
    if m_success or m_failed:
        passed = int(m_success.group(1)) if m_success else 0
        failed = int(m_failed.group(1)) if m_failed else 0
        total = passed + failed if (m_success or m_failed) else (int(m_found.group(1)) if m_found else 0)
        # Extract failure details from JUnit tree
        for line in clean.split("\n"):
            if "✘" in line:
                test_name = re.sub(r".*│.*└─\s*", "", line).replace("✘", "").strip()
                failures_detail.append({"test": test_name, "message": ""})
        return {
            "exit_code": 0 if failed == 0 else 1,
            "total": total, "passed": passed, "failed": failed, "errors": errors,
            "failures_detail": failures_detail,
            "stdout": stdout, "stderr": stderr,
            "can_execute": True,
        }

    for line in stdout.split("\n"):
        m_pass = re.search(r"(\d+)\s+passed", line)
        m_fail = re.search(r"(\d+)\s+failed", line)
        m_err = re.search(r"(\d+)\s+error", line)
        if m_pass or m_fail or m_err:
            passed = int(m_pass.group(1)) if m_pass else passed
            failed = int(m_fail.group(1)) if m_fail else failed
            errors = int(m_err.group(1)) if m_err else errors
            total = passed + failed + errors

        # Jest: "Tests: 5 passed, 5 total"
        m_jest = re.search(r"Tests:\s+(\d+)\s+passed.*?(\d+)\s+total", line)
        if m_jest:
            passed = int(m_jest.group(1))
            total = int(m_jest.group(2))
            failed = total - passed

        # Java JUnit
        m_junit = re.search(r"Tests run:\s*(\d+).*?Failures:\s*(\d+).*?Errors:\s*(\d+)", line)
        if m_junit:
            total = int(m_junit.group(1))
            failed = int(m_junit.group(2))
            errors = int(m_junit.group(3))
            passed = total - failed - errors

        if "FAILED" in line or "FAIL" in line:
            parts = line.split("FAILED") if "FAILED" in line else line.split("FAIL")
            if len(parts) >= 2:
                failures_detail.append({"test": parts[0].strip(), "message": parts[1].strip()})

        # Go test failures
        if language == "go" and "--- FAIL:" in line:
            failures_detail.append({"test": line.replace("--- FAIL:", "").strip(), "message": ""})

    # Detect "cannot execute at all" vs "tests ran but some failed"
    can_execute = not (
        "RUNNER_NOT_FOUND" in stderr
        or "Command not found" in stdout
        or "Java test cannot run" in stdout
    )
    # JUnit ran successfully if we got test counts
    if language == "java" and (total > 0 or "Test run finished" in stdout):
        can_execute = True

    return {
        "exit_code": 0 if failed + errors == 0 else 1,
        "total": total, "passed": passed, "failed": failed, "errors": errors,
        "failures_detail": failures_detail,
        "stdout": stdout, "stderr": stderr,
        "can_execute": can_execute,
        "execution_note": (
            ""
            if can_execute
            else f"Tests cannot be executed in this environment ({language}). "
            f"Test files have been generated and are ready for manual review. "
            f"To run: set up {language} build tools and execute the test file."
        ),
    }


def _parse_python_coverage(json_path: str, source_path: str, stdout: str) -> dict[str, Any]:
    try:
        with open(json_path) as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"line_rate": 0.0, "branch_rate": 0.0, "total_lines": 0, "covered_lines": 0, "uncovered": [], "per_function": []}

    totals = data.get("totals", {})
    uncovered: list[dict] = []
    per_function: list[dict] = []

    for file_path, file_data in data.get("files", {}).items():
        missing = file_data.get("missing_lines", [])
        if missing:
            uncovered.append({"file": file_path, "lines": missing})
        for func_name, func_data in file_data.get("functions", {}).items():
            per_function.append({
                "name": func_name,
                "line_rate": func_data.get("summary", {}).get("percent_covered", 0) / 100.0,
                "uncovered_lines": func_data.get("missing_lines", []),
            })

    return {
        "line_rate": totals.get("percent_covered", 0) / 100.0 if totals else 0.0,
        "branch_rate": totals.get("percent_covered", 0) / 100.0 if totals else 0.0,
        "total_lines": totals.get("num_statements", 0) if totals else 0,
        "covered_lines": totals.get("covered_lines", 0) if totals else 0,
        "uncovered": uncovered,
        "per_function": per_function,
        "_test_stdout": stdout,
    }


def _parse_jest_coverage(json_path: str, stdout: str) -> dict[str, Any]:
    """Parse Jest JSON coverage output if available."""
    try:
        with open(json_path) as f:
            data = json.load(f)
        totals = data.get("total", {})
        lines_pct = totals.get("lines", {}).get("pct", 0)
        branches_pct = totals.get("branches", {}).get("pct", 0)
        return {
            "line_rate": lines_pct / 100.0,
            "branch_rate": branches_pct / 100.0,
            "total_lines": totals.get("lines", {}).get("total", 0),
            "covered_lines": totals.get("lines", {}).get("covered", 0),
            "uncovered": [],
            "per_function": [],
            "_test_stdout": stdout,
        }
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return {
            "line_rate": 0.0, "branch_rate": 0.0,
            "total_lines": 0, "covered_lines": 0,
            "uncovered": [], "per_function": [],
            "_test_stdout": stdout,
        }
