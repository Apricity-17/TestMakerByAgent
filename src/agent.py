"""Agent core — LangGraph StateGraph with ReAct + Reflection nodes."""

import json
import re
import sys
from typing import Any, Literal, Mapping, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from src.llm.provider import LLMProvider
from src.llm.factory import create_provider
from src.logger import get_logger
from src.prompt.templates import (
    REFLECT_PROMPT,
    get_analyze_prompt,
    get_generate_prompt,
    get_interactive_prompt,
    get_plan_prompt,
    get_report_prompt,
    get_system_prompt,
)
from src.state import AgentState
from src.tools import get_all_tools, get_explore_tools, get_exec_tools, get_write_tools

from src.skills.loader import (
    get_default_skills_dir,
    inject_skills_into_prompt,
    load_all_skills,
    match_skills,
)

logger = get_logger(__name__)

# Load skills once at module level
_SKILLS = load_all_skills(get_default_skills_dir())

# Module-level LTM (set by run/run_interactive before graph execution)
_LTM: Any = None

# ─── Helper ───────────────────────────────────────────────────────────────────


def _make_output_dir(target_path: str, test_dir: str) -> tuple[str, str, str]:
    """Compute output directory next to the source file.

    Returns (output_dir, test_file_path, language_extension).

    /path/to/gitlet/Main.java → (/path/to/gitlet/test_Main/, .../test_Main/MainTest.java, .java)
    sample_simple.py         → (test_sample_simple/, test_sample_simple/test_sample_simple.py, .py)
    module.go                → (test_module/, test_module/module_test.go, .go)
    """
    import os

    base = os.path.basename(target_path)
    stem, ext = os.path.splitext(base)  # Main, .java
    source_dir = os.path.dirname(os.path.abspath(target_path))
    folder = os.path.join(source_dir, f"test_{stem}") if source_dir else f"test_{stem}"

    # Determine test file extension and naming convention per language
    lang_map = {
        ".py": ("test_" + stem + ".py", ".py"),
        ".java": (stem + "Test.java", ".java"),
        ".js": (stem + ".test.js", ".js"),
        ".ts": (stem + ".test.ts", ".ts"),
        ".go": (stem + "_test.go", ".go"),
        ".rs": ("test_" + stem + ".rs", ".rs"),
        ".rb": ("test_" + stem + ".rb", ".rb"),
    }
    test_name, lang_ext = lang_map.get(ext, ("test_" + stem + ".py", ".py"))

    # For Java: place test file next to source (same package), not in subfolder
    if ext == ".java":
        test_path = os.path.join(source_dir, test_name)
        return source_dir, test_path, lang_ext

    test_path = os.path.join(folder, test_name)
    return folder, test_path, lang_ext


def _extract_json(content: str) -> dict[str, Any]:
    """Extract JSON object from LLM response, trying multiple strategies."""
    # Strategy 1: direct parse
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    # Strategy 2: extract from ```json blocks
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass
    # Strategy 3: find first { ... } pair
    m = re.search(r"\{[\s\S]*\}", content)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return {}


def _safe_json_dumps(obj: Any, default_str: str = "[]") -> str:
    try:
        return json.dumps(obj, indent=2, ensure_ascii=False)
    except (TypeError, ValueError):
        return default_str


# ─── Node Functions ──────────────────────────────────────────────────────────


def node_analyze(state: AgentState, provider: LLMProvider) -> dict[str, Any]:
    """Explore target file: read, parse, list directory. Returns analysis data."""
    logger.info("node_analyze: %s", state.get("target_path", "?"))
    lang = state.get("language", "zh")
    explore_tools = get_explore_tools()

    messages = [
        SystemMessage(content=get_system_prompt(lang)),
        HumanMessage(
            content=get_analyze_prompt(lang).format(target_path=state["target_path"])
        ),
    ]

    llm_with_tools = provider.get_model().bind_tools(explore_tools)
    response = llm_with_tools.invoke(messages)
    messages.append(response)

    # Execute tool calls greedily (max 5 rounds)
    for _ in range(5):
        if not hasattr(response, "tool_calls") or not response.tool_calls:
            break
        for tc in response.tool_calls:
            tool_map = {t.name: t for t in explore_tools}
            tool_fn = tool_map.get(tc["name"])
            if tool_fn:
                try:
                    result = tool_fn.invoke(tc["args"])
                except Exception as e:
                    result = {"error": str(e)}
            else:
                result = {"error": f"Unknown tool: {tc['name']}"}
            messages.append(
                ToolMessage(content=_safe_json_dumps(result), tool_call_id=tc["id"])
            )
        response = llm_with_tools.invoke(messages)
        messages.append(response)

    # Parse analysis from LLM's last text response
    final_content = response.content if hasattr(response, "content") else str(response)
    return {
        "messages": messages,
        "source_code": final_content,
        "ast_summary": {"raw_analysis": final_content},
    }


def node_plan(state: AgentState, provider: LLMProvider) -> dict[str, Any]:
    """Generate a structured test plan based on code analysis."""
    logger.info("node_plan: iteration=%d", state.get("iteration", 0))
    lang = state.get("language", "zh")

    analysis_summary = _safe_json_dumps(state.get("ast_summary", {}))
    source_code = state.get("source_code", "")[:1500]  # truncated to save tokens

    # Load user preferences from long-term memory
    prefs_context = ""
    if _LTM:
        try:
            prefs = _LTM.get_all_preferences()
            if prefs:
                prefs_context = f"\nUser preferences from past sessions: {_safe_json_dumps(prefs)}"
        except Exception:
            pass

    # Match relevant skills
    ctx = analysis_summary + " " + (state.get("source_code", "")[:1000])
    matched = match_skills(_SKILLS, ctx)
    plan_prompt = inject_skills_into_prompt(
        matched,
        get_plan_prompt(lang).format(analysis_summary=analysis_summary, source_code_snippet=source_code)
        + prefs_context,
    )

    messages = [
        SystemMessage(content=get_system_prompt(lang)),
        HumanMessage(content=plan_prompt),
    ]

    model = provider.get_model()
    response = model.invoke(messages)
    content = response.content if hasattr(response, "content") else str(response)

    plan_data = _extract_json(content)
    targets = plan_data.get("targets", [])

    return {
        "messages": state.get("messages", []) + messages + [response],
        "test_plan": targets,
    }


def node_generate(state: AgentState, provider: LLMProvider) -> dict[str, Any]:
    """Generate test code for each planned target, or retry-fix failing tests."""
    logger.info(
        "node_generate: reason=%s, targets=%d",
        state.get("termination_reason", "continue"),
        len(state.get("test_plan", [])),
    )
    lang = state.get("language", "zh")

    termination_reason = state.get("termination_reason", "")
    test_results = state.get("test_results") or {}
    source_code = state.get("source_code", "")
    test_files: list[str] = list(state.get("test_files", []))
    generated_count = state.get("generated_count", 0)
    test_dir = state.get("test_dir", "tests")
    target_path = state.get("target_path", "")
    output_dir, test_file_path, _lang_ext = _make_output_dir(target_path, test_dir)

    all_tools = get_all_tools()
    llm_with_tools = provider.get_model().bind_tools(all_tools)

    # ── Retry mode: fix failing tests ──
    if termination_reason == "retry":
        failures = test_results.get("failures_detail", [])
        failures_text = _safe_json_dumps(failures[:5])
        messages = [
            SystemMessage(content=get_system_prompt(lang)),
            HumanMessage(
                content=(
                    "Several tests failed. Fix the test code — NOT the source.\n\n"
                    f"Test file: {test_file_path}\n"
                    f"Failures:\n{failures_text}\n\n"
                    "Read the test file, identify the bugs in the test code, "
                    "and fix them with write_file (mode='w' to rewrite)."
                )
            ),
        ]
        response = llm_with_tools.invoke(messages)
        if hasattr(response, "tool_calls") and response.tool_calls:
            tool_map = {t.name: t for t in all_tools}
            for tc in response.tool_calls:
                tool_fn = tool_map.get(tc["name"])
                if tool_fn:
                    try:
                        tool_fn.invoke(tc["args"])
                    except Exception as e:
                        logger.error("Retry tool %s failed: %s", tc["name"], e)
        return {"test_files": test_files, "generated_count": generated_count, "messages": state.get("messages", [])}

    # ── Continue mode: generate new tests from plan ──
    test_plan = state.get("test_plan", [])
    if not test_plan:
        return {"test_files": test_files, "generated_count": generated_count, "messages": state.get("messages", [])}

    # Load existing test file content for append mode
    existing = ""
    mode = "a" if test_file_path in test_files else "w"
    if test_file_path in test_files:
        try:
            with open(test_file_path) as f:
                existing = f.read()[-2000:]
        except OSError:
            pass

    for plan_item in test_plan:
        target_name = plan_item.get("target", "unknown")
        cases = plan_item.get("cases", [])
        mock_strategy = plan_item.get("mock_strategy", "none")
        priority = plan_item.get("priority", "medium")

        cases_list = "\n".join(
            f"  - [{c.get('type', 'normal')}] {c.get('desc', '')}"
            for c in cases
        )

        # Match skills relevant to this target
        ctx = target_name + " " + mock_strategy + " " + cases_list
        matched = match_skills(_SKILLS, ctx)
        gen_prompt = inject_skills_into_prompt(
            matched,
            get_generate_prompt(lang).format(
                target_name=target_name,
                mock_strategy=mock_strategy,
                priority=priority,
                cases_list=cases_list,
                source_code=source_code[:2000],
                existing_test_code=existing,
                specific_instruction="Generate complete test code for these cases.",
            ),
        )
        gen_prompt += f"\n\nUse write_file to write the test code. mode={mode}, file_path={test_file_path}"

        msg_list = [
            SystemMessage(content=get_system_prompt(lang)),
            HumanMessage(content=gen_prompt),
        ]

        # Multi-round: allow LLM to explore first, then write
        for _round in range(4):
            response = llm_with_tools.invoke(msg_list)
            content = response.content if hasattr(response, "content") else ""
            has_tc = hasattr(response, "tool_calls") and response.tool_calls

            if not has_tc:
                # No more tool calls — if content has code, write it as fallback
                if len(content) > 50:
                    code = content
                    m = re.search(r"```(?:python)?\s*([\s\S]*?)```", content)
                    if m:
                        code = m.group(1).strip()
                    all_tools_map = {t.name: t for t in all_tools}
                    wf = all_tools_map.get("write_file")
                    if wf:
                        try:
                            wf.invoke({"file_path": test_file_path, "content": code, "mode": mode})
                            if test_file_path not in test_files:
                                test_files.append(test_file_path)
                            logger.info("generate: wrote %d bytes via fallback", len(code))
                        except Exception as e:
                            logger.error("Fallback write_file failed: %s", e)
                break

            # Execute tool calls — append assistant response first, then tool results
            msg_list.append(response)
            tool_map = {t.name: t for t in all_tools}
            for tc in response.tool_calls:
                tool_fn = tool_map.get(tc["name"])
                if tool_fn:
                    try:
                        result = tool_fn.invoke(tc["args"])
                        if tc["name"] == "write_file":
                            if test_file_path not in test_files:
                                test_files.append(test_file_path)
                            logger.info("generate: wrote test file via write_file tool")
                    except Exception as e:
                        result = {"error": str(e)}
                        logger.error("Tool %s failed: %s", tc["name"], e)
                else:
                    result = {"error": f"Unknown tool: {tc['name']}"}
                msg_list.append(
                    ToolMessage(content=_safe_json_dumps(result), tool_call_id=tc["id"])
                )

        generated_count += len(cases)

    return {
        "test_files": test_files,
        "generated_count": generated_count,
        "messages": state.get("messages", []),
    }


def node_execute(state: AgentState, provider: LLMProvider) -> dict[str, Any]:
    """Run tests and collect coverage. No LLM — deterministic tool execution."""
    logger.info("node_execute: tests=%s", state.get("test_files", []))

    test_files = state.get("test_files", [])
    target_path = state.get("target_path", "")
    iteration = state.get("iteration", 0) + 1

    exec_tools = get_exec_tools()
    test_runner = {t.name: t for t in exec_tools}.get("run_tests")
    cov_runner = {t.name: t for t in exec_tools}.get("get_coverage")

    test_results = None
    coverage_data = None

    if test_files and test_runner:
        try:
            test_results = test_runner.invoke(
                {"test_path": test_files[0], "target_path": target_path}
            )
        except Exception as e:
            test_results = {"exit_code": -1, "total": 0, "passed": 0, "failed": 0, "errors": 1, "failures_detail": [{"test": "EXECUTION_ERROR", "message": str(e)}], "stdout": "", "stderr": str(e)}

    if test_files and cov_runner and target_path:
        try:
            coverage_data = cov_runner.invoke(
                {"source_path": target_path, "test_path": test_files[0]}
            )
            # Remove internal field
            coverage_data.pop("_test_stdout", None)
        except Exception as e:
            coverage_data = {"line_rate": 0.0, "branch_rate": 0.0, "total_lines": 0, "covered_lines": 0, "uncovered": [], "per_function": [], "error": str(e)}

    coverage_history = list(state.get("coverage_history", []))
    if coverage_data:
        coverage_history.append(
            {
                "iteration": iteration,
                "line_rate": coverage_data.get("line_rate", 0.0),
                "branch_rate": coverage_data.get("branch_rate", 0.0),
            }
        )

    return {
        "test_results": test_results,
        "coverage_data": coverage_data,
        "iteration": iteration,
        "coverage_history": coverage_history,
    }


def node_reflect(state: AgentState, provider: LLMProvider) -> dict[str, Any]:
    """Evaluate results and decide: continue, retry, or stop."""
    lang = state.get("language", "zh")
    test_results = state.get("test_results") or {}
    coverage_data = state.get("coverage_data") or {}

    # If tests can't execute at all (no build tool), stop immediately
    if test_results.get("can_execute") is False:
        return {"termination_reason": "not_worth"}

    logger.info(
        "node_reflect: iteration=%d, line_rate=%.2f",
        state.get("iteration", 0),
        coverage_data.get("line_rate", 0.0),
    )
    iteration = state.get("iteration", 0)
    max_iterations = state.get("max_iterations", 5)
    target_coverage = state.get("target_coverage", 0.90)
    coverage_history = state.get("coverage_history", [])

    # Hard limits
    if iteration >= max_iterations:
        return {"termination_reason": "max_iter"}
    if coverage_data.get("line_rate", 0.0) >= target_coverage:
        return {"termination_reason": "coverage_met"}

    # Diminishing returns check
    if len(coverage_history) >= 2:
        last_two = coverage_history[-2:]
        if last_two[1]["line_rate"] - last_two[0]["line_rate"] < 0.02:
            return {"termination_reason": "diminishing"}

    # LLM evaluation
    uncovered = coverage_data.get("uncovered", [])
    uncovered_summary = _safe_json_dumps(uncovered[:10])
    trend_lines = [
        f"  Iter {h['iteration']}: line={h['line_rate']:.1%}, branch={h['branch_rate']:.1%}"
        for h in coverage_history
    ]

    reflect_body = REFLECT_PROMPT.format(
        iteration=iteration,
        max_iterations=max_iterations,
        total_tests=test_results.get("total", 0),
        passed=test_results.get("passed", 0),
        failed=test_results.get("failed", 0),
        errors=test_results.get("errors", 0),
        failures_detail=_safe_json_dumps(test_results.get("failures_detail", [])),
        line_rate=coverage_data.get("line_rate", 0.0),
        branch_rate=coverage_data.get("branch_rate", 0.0),
        uncovered_summary=uncovered_summary,
        coverage_trend="\n".join(trend_lines) if trend_lines else "No history yet",
    )
    matched = match_skills(_SKILLS, uncovered_summary + " coverage")
    reflect_body = inject_skills_into_prompt(matched, reflect_body)

    messages = [
        SystemMessage(content=get_system_prompt(lang)),
        HumanMessage(content=reflect_body),
    ]

    model = provider.get_model()
    response = model.invoke(messages)
    content = response.content if hasattr(response, "content") else str(response)

    decision_data = _extract_json(content)
    decision = decision_data.get("decision", "stop")

    # Map LLM decision to termination_reason
    reason_map = {"continue": "continue", "retry": "retry", "stop": "not_worth"}
    reason = reason_map.get(decision, "not_worth")

    return {
        "termination_reason": reason,
        "messages": state.get("messages", []) + messages + [response],
    }


def node_report(state: AgentState, provider: LLMProvider) -> dict[str, Any]:
    """Generate final Markdown report."""
    logger.info("node_report: generating final report")
    lang = state.get("language", "zh")

    coverage_data = state.get("coverage_data") or {}
    test_dir = state.get("test_dir", "tests")
    target_path = state.get("target_path", "")
    output_dir, _test_path, _lang_ext = _make_output_dir(target_path, test_dir)
    import os as _os
    _stem = _os.path.splitext(_os.path.basename(target_path))[0]
    report_path = f"{output_dir}/{_stem}_report.md"

    all_tools = get_all_tools()
    llm_with_tools = provider.get_model().bind_tools(all_tools)

    # Build test result detail for report
    test_results = state.get("test_results") or {}
    failures = test_results.get("failures_detail", [])
    test_result_detail = (
        f"总测试: {test_results.get('total', 0)}, "
        f"通过: {test_results.get('passed', 0)}, "
        f"失败: {test_results.get('failed', 0)}, "
        f"错误: {test_results.get('errors', 0)}"
    )
    if test_results.get("total", 0) > 0:
        success_rate = test_results.get("passed", 0) / max(test_results.get("total", 0), 1)
        test_result_detail += f", 成功率: {success_rate:.1%}"
    if failures:
        test_result_detail += f"\n失败详情: {_safe_json_dumps(failures[:10])}"

    # Multi-round: allow exploration before writing report
    msg_list = [
        SystemMessage(content=get_system_prompt(lang)),
        HumanMessage(
            content=get_report_prompt(lang).format(
                target_path=target_path,
                iteration=state.get("iteration", 0),
                test_files=_safe_json_dumps(state.get("test_files", [])),
                generated_count=state.get("generated_count", 0),
                line_rate=coverage_data.get("line_rate", 0.0),
                branch_rate=coverage_data.get("branch_rate", 0.0),
                termination_reason=state.get("termination_reason", "unknown"),
                report_path=report_path,
                test_result_detail=test_result_detail,
            )
        ),
    ]

    final_report = ""
    for _round in range(3):
        response = llm_with_tools.invoke(msg_list)
        content = response.content if hasattr(response, "content") else ""
        has_tc = hasattr(response, "tool_calls") and response.tool_calls

        if not has_tc:
            final_report = content
            break

        msg_list.append(response)
        tool_map = {t.name: t for t in all_tools}
        for tc in response.tool_calls:
            tool_fn = tool_map.get(tc["name"])
            if tool_fn:
                try:
                    result = tool_fn.invoke(tc["args"])
                except Exception as e:
                    result = {"error": str(e)}
                    logger.error("Tool %s failed in report: %s", tc["name"], e)
            else:
                result = {"error": f"Unknown tool: {tc['name']}"}
            msg_list.append(
                ToolMessage(content=_safe_json_dumps(result), tool_call_id=tc["id"])
            )

    if not final_report and msg_list:
        tr = state.get("test_results") or {}
        total = tr.get("total", 0)
        passed = tr.get("passed", 0)
        failed = tr.get("failed", 0)
        rate = f"{passed}/{total} ({passed/max(total,1):.0%})" if total > 0 else "N/A"
        final_report = (
            f"## 测试报告\n\n"
            f"**目标**: {target_path}\n\n"
            f"**测试文件**: {', '.join(state.get('test_files', [])) or '无'}\n\n"
            f"**测试结果**: {rate} 通过\n"
            f"- ✅ 通过: {passed}\n"
            f"- ❌ 失败: {failed}\n"
            f"- 总计: {total}\n\n"
            f"**覆盖率**: 行 {coverage_data.get('line_rate', 0):.1%} | 分支 {coverage_data.get('branch_rate', 0):.1%}\n\n"
            f"**迭代轮次**: {state.get('iteration', 0)}\n"
            f"**终止原因**: {state.get('termination_reason', 'unknown')}\n\n"
            f"详细报告: {report_path or '未生成'}"
        )

    # Write to long-term memory
    if _LTM:
        try:
            _LTM.record_session(
                target_path=state.get("target_path", ""),
                total_tests=state.get("generated_count", 0),
                final_line_rate=coverage_data.get("line_rate", 0.0),
                final_branch_rate=coverage_data.get("branch_rate", 0.0),
                iterations=state.get("iteration", 0),
                termination_reason=state.get("termination_reason", ""),
            )
            _LTM.set_preference("test_dir", state.get("test_dir", "tests"))
        except Exception as e:
            logger.error("Failed to write long-term memory: %s", e)

    return {
        "final_report": final_report,
        "messages": state.get("messages", []) + msg_list + [response],
    }


# ─── LangGraph Construction ──────────────────────────────────────────────────


def build_graph(
    provider: LLMProvider,
) -> StateGraph:
    """Build the full ReAct + Reflection LangGraph."""
    workflow = StateGraph(AgentState)

    # Bind provider into node closures
    workflow.add_node("analyze", lambda s: node_analyze(s, provider))
    workflow.add_node("plan", lambda s: node_plan(s, provider))
    workflow.add_node("generate", lambda s: node_generate(s, provider))
    workflow.add_node("execute", lambda s: node_execute(s, provider))
    workflow.add_node("reflect", lambda s: node_reflect(s, provider))
    workflow.add_node("report", lambda s: node_report(s, provider))

    workflow.set_entry_point("analyze")
    workflow.add_edge("analyze", "plan")
    workflow.add_edge("plan", "generate")
    workflow.add_edge("generate", "execute")
    workflow.add_edge("execute", "reflect")

    workflow.add_conditional_edges(
        "reflect",
        _route_after_reflect,
        {"generate": "generate", "report": "report"},
    )

    workflow.add_edge("report", END)

    return workflow


def build_interactive_graph(provider: LLMProvider) -> StateGraph:
    """Build the interactive mode graph: analyze → interactive_loop → report."""
    workflow = StateGraph(AgentState)

    workflow.add_node("analyze", lambda s: node_analyze(s, provider))
    workflow.add_node("interactive", lambda s: _node_interactive_loop(s, provider))
    workflow.add_node("report", lambda s: node_report(s, provider))

    workflow.set_entry_point("analyze")
    workflow.add_edge("analyze", "interactive")
    workflow.add_conditional_edges(
        "interactive",
        _route_after_interactive,
        {"loop": "interactive", "report": "report"},
    )
    workflow.add_edge("report", END)

    return workflow


# ─── Routing ──────────────────────────────────────────────────────────────────


def _route_after_reflect(state: AgentState) -> Literal["generate", "report"]:
    reason = state.get("termination_reason", "")
    if reason in ("continue", "retry", ""):
        return "generate"
    return "report"


def _route_after_interactive(state: AgentState) -> Literal["loop", "report"]:
    if state.get("termination_reason") == "user_stop":
        return "report"
    return "loop"


# ─── Interactive Loop Node ───────────────────────────────────────────────────


def _node_interactive_loop(state: AgentState, provider: LLMProvider) -> dict[str, Any]:
    """Single iteration of interactive mode — prompt user, execute, loop."""
    from rich.console import Console

    console = Console()
    lang = state.get("language", "zh")

    # Display status summary on first entry
    if state.get("iteration", 0) == 0:
        funcs = []
        for t in state.get("test_plan", []):
            funcs.append(t.get("target", "?"))
        test_files = state.get("test_files", [])
        cov = state.get("coverage_data") or {}

        if lang == "zh":
            console.print("\n[bold blue]TestMaker 交互模式[/]")
            console.print(f"  目标: {state.get('target_path', '?')}")
            console.print(f"  函数: {', '.join(funcs) if funcs else '分析中...'}")
            if test_files:
                console.print(f"  测试文件: {', '.join(test_files)}")
            if cov.get("line_rate"):
                console.print(f"  覆盖率: 行 {cov['line_rate']:.1%} | 分支 {cov.get('branch_rate', 0):.1%}")
            console.print("\n[dim]输入指令或 [bold]done[/bold] 退出生成报告[/dim]\n")
        else:
            console.print("\n[bold blue]TestMaker Interactive[/]")
            console.print(f"  Target: {state.get('target_path', '?')}")
            console.print(f"  Functions: {', '.join(funcs) if funcs else 'analyzing...'}")
            if test_files:
                console.print(f"  Test files: {', '.join(test_files)}")
            if cov.get("line_rate"):
                console.print(f"  Coverage: line {cov['line_rate']:.1%} | branch {cov.get('branch_rate', 0):.1%}")
            console.print("\n[dim]Enter instruction or [bold]done[/bold] to finish[/dim]\n")

    user_input = console.input("[bold green]> [/bold green]")

    if user_input.strip().lower() in ("done", "exit", "quit", "q"):
        console.print("\n[bold]正在生成报告...[/]\n" if lang == "zh" else "\n[bold]Generating report...[/]\n")
        return {
            "termination_reason": "user_stop",
            "iteration": state.get("iteration", 0),
        }

    if not user_input.strip():
        return {"iteration": state.get("iteration", 0)}

    # Process user instruction — use full message history
    messages = list(state.get("messages", []))
    messages.append(HumanMessage(content=user_input))

    all_tools = get_all_tools()
    llm_with_tools = provider.get_model().bind_tools(all_tools)

    tool_results: list[str] = []  # Track what happened for summary

    # Multi-round tool execution: keep calling LLM until no more tool_calls
    for _round in range(5):
        with console.status("[bold yellow]处理中...[/bold yellow]" if lang == "zh" else "[bold yellow]Processing...[/bold yellow]", spinner="dots"):
            response = llm_with_tools.invoke(messages)
        has_tc = bool(getattr(response, "tool_calls", None))
        if not has_tc:
            messages.append(response)
            break

        # Append assistant message with tool_calls FIRST
        messages.append(response)

        # Execute each tool call and append corresponding ToolMessage
        tool_map = {t.name: t for t in all_tools}
        for tc in response.tool_calls:
            tc_name = tc.get("name", "") if isinstance(tc, dict) else getattr(tc, "name", "")
            tc_id = tc.get("id", "") if isinstance(tc, dict) else getattr(tc, "id", "")
            tool_fn = tool_map.get(tc_name)
            if tool_fn:
                try:
                    args = tc.get("args", {}) if isinstance(tc, dict) else getattr(tc, "args", {})
                    result = tool_fn.invoke(args)
                    # Track for summary
                    if tc_name == "read_file":
                        tool_results.append(f"读取 {args.get('file_path', '?')}")
                    elif tc_name == "write_file":
                        fp = args.get("file_path", "?")
                        size = result.get("bytes_written", 0) if isinstance(result, dict) else 0
                        tool_results.append(f"写入 {fp} ({size} bytes)")
                    elif tc_name == "run_tests":
                        p = result.get("passed", 0) if isinstance(result, dict) else 0
                        f = result.get("failed", 0) if isinstance(result, dict) else 0
                        tool_results.append(f"运行测试: {p} passed, {f} failed")
                    elif tc_name == "get_coverage":
                        lr = result.get("line_rate", 0) if isinstance(result, dict) else 0
                        tool_results.append(f"覆盖率: {lr:.0%}")
                    elif tc_name == "parse_code":
                        lang = result.get("language", "?") if isinstance(result, dict) else "?"
                        tool_results.append(f"解析代码 ({lang})")
                    elif tc_name == "exec_code":
                        tool_results.append("执行代码片段")
                    elif tc_name == "list_directory":
                        tool_results.append(f"列出目录 {args.get('path', '?')}")
                    else:
                        tool_results.append(tc_name)
                except Exception as e:
                    result = {"error": str(e)}
                    tool_results.append(f"✗ {tc_name}: {e}")
            else:
                result = {"error": f"Unknown tool: {tc_name}"}
                tool_results.append(f"✗ 未知工具: {tc_name}")
            messages.append(
                ToolMessage(content=_safe_json_dumps(result), tool_call_id=tc_id)
            )

    # ── Show results summary ──
    # LLM's text response
    final_content = getattr(response, "content", "") if response else ""
    if final_content:
        from rich.markdown import Markdown
        console.print()
        console.print(Markdown(final_content))

    # Tool execution log
    if tool_results:
        console.print()
        for r in tool_results:
            if r.startswith("✗"):
                console.print(f"  [red]{r}[/red]")
            else:
                console.print(f"  [dim]• {r}[/dim]")

    # Update test_files and test_results from tool calls
    test_files = list(state.get("test_files", []))
    test_results = dict(state.get("test_results") or {})
    for msg in messages:
        tcs = getattr(msg, "tool_calls", None) or []
        for tc in tcs:
            tc_name = tc.get("name", "") if isinstance(tc, dict) else getattr(tc, "name", "")
            if tc_name == "write_file":
                args = tc.get("args", {}) if isinstance(tc, dict) else getattr(tc, "args", {})
                fp = args.get("file_path", "") if isinstance(args, dict) else getattr(args, "file_path", "")
                if fp and fp not in test_files:
                    test_files.append(fp)
        # Capture run_tests results from ToolMessages
        for i, m in enumerate(messages):
            if isinstance(m, ToolMessage) and hasattr(m, "content"):
                try:
                    data = json.loads(m.content)
                    if data.get("total", 0) > 0 and "passed" in data:
                        test_results = data
                except (json.JSONDecodeError, TypeError):
                    pass

    # ── Prompt for next action ──
    console.print()
    if lang == "zh":
        console.print(
            "[bold blue]接下来做什么？[/bold blue] "
            "[dim](输入指令, 或 [bold]done[/bold] 退出)[/dim]"
        )
    else:
        console.print(
            "[bold blue]What next?[/bold blue] "
            "[dim](enter instruction, or [bold]done[/bold] to finish)[/dim]"
        )

    return {
        "messages": messages,
        "test_files": test_files,
        "test_results": test_results,
        "iteration": state.get("iteration", 0) + 1,
    }


# ─── Top-Level Entry Points ──────────────────────────────────────────────────


def create_initial_state(
    target_path: str,
    target_functions: Optional[list[str]] = None,
    target_coverage: float = 0.90,
    max_iterations: int = 5,
    test_dir: str = "tests",
    language: str = "zh",
) -> dict[str, Any]:
    return {
        "target_path": target_path,
        "target_functions": target_functions or [],
        "target_coverage": target_coverage,
        "max_iterations": max_iterations,
        "test_dir": test_dir,
        "language": language,
        "messages": [],
        "source_code": "",
        "ast_summary": None,
        "test_plan": [],
        "test_files": [],
        "generated_count": 0,
        "test_results": None,
        "coverage_data": None,
        "iteration": 0,
        "coverage_history": [],
        "termination_reason": "",
        "final_report": "",
        "error_message": "",
    }


def run(
    target_path: str,
    target_functions: Optional[list[str]] = None,
    target_coverage: float = 0.90,
    max_iterations: int = 5,
    test_dir: str = "tests",
    model_override: Optional[str] = None,
    language: str = "zh",
) -> dict[str, Any]:
    """Execute the full test generation workflow (auto mode).

    Returns the final AgentState dict.
    """
    from config import load_config

    config = load_config()
    if model_override:
        config["model"]["provider"] = model_override

    from src.memory.long_term import LongTermMemory

    global _LTM
    _LTM = LongTermMemory()

    provider = create_provider(config)
    graph = build_graph(provider)
    checkpointer = MemorySaver()
    compiled = graph.compile(checkpointer=checkpointer)

    initial_state = create_initial_state(
        target_path=target_path,
        target_functions=target_functions or [],
        target_coverage=target_coverage,
        max_iterations=max_iterations,
        test_dir=test_dir,
        language=language,
    )

    logger.info("Starting agent run for %s", target_path)

    try:
        result = compiled.invoke(
            initial_state,
            config={
                "recursion_limit": 50,
                "configurable": {"thread_id": "testmaker-auto"},
            },
        )
    except Exception as e:
        logger.exception("Agent run failed")
        result = {**initial_state, "error_message": str(e), "final_report": f"Error: {e}"}

    return result


def run_interactive(
    target_path: str,
    target_functions: Optional[list[str]] = None,
    test_dir: str = "tests",
    model_override: Optional[str] = None,
    language: str = "zh",
) -> dict[str, Any]:
    """Execute the interactive test generation workflow.

    Returns the final AgentState dict after user exits.
    """
    from config import load_config

    config = load_config()
    if model_override:
        config["model"]["provider"] = model_override

    from src.memory.long_term import LongTermMemory

    global _LTM
    _LTM = LongTermMemory()

    provider = create_provider(config)
    graph = build_interactive_graph(provider)
    compiled = graph.compile()

    initial_state = create_initial_state(
        target_path=target_path,
        target_functions=target_functions or [],
        target_coverage=0.90,
        max_iterations=50,
        test_dir=test_dir,
        language=language,
    )

    logger.info("Starting interactive run for %s", target_path)

    try:
        result = compiled.invoke(
            initial_state,
            config={
                "recursion_limit": 200,
                "configurable": {"thread_id": "testmaker-interactive"},
            },
        )
    except Exception as e:
        logger.exception("Interactive run failed")
        result = {**initial_state, "error_message": str(e), "final_report": f"Error: {e}"}

    return result
