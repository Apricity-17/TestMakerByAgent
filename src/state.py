"""Agent state type definitions.

All TypedDict definitions for the AgentState that flows through the LangGraph.
"""

from typing import Annotated, Any, Optional, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class FunctionInfo(TypedDict):
    name: str
    lineno: int
    args: list[dict[str, Any]]
    returns: Optional[str]
    decorators: list[str]
    docstring: Optional[str]
    complexity: int


class BranchInfo(TypedDict):
    type: str
    lineno: int


class ASTSummary(TypedDict):
    file_path: str
    functions: list[dict[str, Any]]
    classes: list[dict[str, Any]]
    imports: list[dict[str, Any]]
    branches: list[dict[str, Any]]
    external_deps: list[str]


class TestCasePlan(TypedDict, total=False):
    target: str
    priority: str
    cases: list[dict[str, str]]
    mock_strategy: str


class CoverageData(TypedDict, total=False):
    line_rate: float
    branch_rate: float
    total_lines: int
    covered_lines: int
    uncovered: list[dict[str, Any]]
    per_function: list[dict[str, Any]]
    error: Optional[str]


class TestResult(TypedDict, total=False):
    exit_code: int
    total: int
    passed: int
    failed: int
    errors: int
    failures_detail: list[dict[str, str]]
    stdout: str
    stderr: str


class AgentState(TypedDict, total=False):
    # Input
    target_path: str
    target_functions: list[str]
    target_coverage: float
    max_iterations: int
    test_dir: str

    # Messages (short-term memory)
    messages: Annotated[list[BaseMessage], add_messages]

    # Code analysis
    source_code: str
    ast_summary: Optional[dict[str, Any]]

    # Test plan
    test_plan: list[dict[str, Any]]

    # Generated artifacts
    test_files: list[str]
    generated_count: int

    # Execution results
    test_results: Optional[dict[str, Any]]
    coverage_data: Optional[dict[str, Any]]

    # Iteration control
    iteration: int
    coverage_history: list[dict[str, Any]]
    termination_reason: str

    # Output
    final_report: str
    error_message: str
