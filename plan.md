# Implementation Plan：测试用例生成 Agent (C04)

> 基于 research.md | 日期：2026-06-20 | 状态：待确认

---

## 1. 实现思路

### 1.1 核心策略

**从最小可用到完整迭代**。先实现单轮 `analyze → generate → execute → report` 的 MVP（能对一个简单函数生成测试并运行），再逐步加入 `reflect → 迭代`、记忆系统、Skill 系统。每一阶段产出可运行的中间版本。

### 1.2 技术路线

```
LangGraph StateGraph（控制流）
    + DeepSeek API（LLM 推理，openai 兼容接口）
    + LangChain @tool（工具定义与绑定）
    + pytest + coverage.py（测试执行与覆盖率采集）
    + SQLite（长期记忆）
    + Rich（CLI 美化）
```

### 1.3 架构分层

```
cli.py          ── 入口，解析用户输入，调用 agent.run()
agent.py        ── LangGraph 图定义，节点连接
state.py        ── AgentState 类型
tools/          ── 7 个工具实现，每个是独立函数 + @tool 装饰器
llm/            ── LLM Provider 抽象 + DeepSeek/Claude 实现
prompt/         ── System prompt 和节点级 prompt 模板
memory/         ── Checkpointer 封装 + SQLite 操作
skills/         ── Skill 加载器 + data/ 目录下的 Markdown 知识文件
config.py       ── 配置加载（YAML + 环境变量）
```

### 1.4 关键设计约束

1. **DeepSeek 优先，Claude 可切换**：`llm/provider.py` 定义 `LLMProvider` 抽象基类，`DeepSeekProvider` 和 `ClaudeProvider` 各自实现。配置文件 `provider: deepseek` 或 `provider: claude`。默认模型为 `deepseek-v4-pro`。
2. **工具不依赖 LangGraph**：每个工具函数是纯 Python 函数，可独立测试。`@tool` 装饰器仅用于注册到 LangChain。
3. **状态不可变风格**：每个 LangGraph 节点返回 `dict[str, Any]`（部分状态更新），而非原地修改。
4. **Prompt 与代码分离**：所有 prompt 模板集中在 `prompt/templates.py`，便于调优。

---

## 2. 文件清单

### 2.1 新增文件（全部，共 25 个）

```
testmaker/
├── cli.py                          # CLI 入口
├── config.py                       # 配置加载
├── config.yaml                     # 默认配置文件
├── requirements.txt                # 依赖声明
├── src/
│   ├── __init__.py
│   ├── agent.py                    # LangGraph 图定义 + 节点函数
│   ├── state.py                    # AgentState TypedDict
│   ├── logger.py                   # 日志配置
│   ├── tools/
│   │   ├── __init__.py             # 工具注册、get_all_tools()
│   │   ├── parser.py               # parse_code: AST 解析
│   │   ├── files.py                # read_file, write_file, list_directory
│   │   ├── runner.py               # run_tests, get_coverage
│   │   └── executor.py             # exec_code: 安全执行 Python 代码片段
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── provider.py             # LLMProvider 抽象基类
│   │   ├── deepseek.py             # DeepSeekProvider
│   │   └── claude.py               # ClaudeProvider（预留）
│   ├── prompt/
│   │   ├── __init__.py
│   │   └── templates.py            # 所有 prompt 模板
│   ├── memory/
│   │   ├── __init__.py
│   │   ├── checkpointer.py         # MemorySaver 封装
│   │   └── long_term.py            # SQLite 操作
│   └── skills/
│       ├── __init__.py
│       ├── loader.py               # Skill 加载与匹配
│       └── data/
│           ├── pytest-patterns.md
│           ├── mock-strategy.md
│           ├── boundary-analysis.md
│           └── coverage-strategy.md
└── tests/                          # Agent 自身的测试（agent 测自己不符合课程要求，这里测工具函数）
    ├── __init__.py
    ├── test_parser.py
    ├── test_runner.py
    ├── test_files.py
    └── test_llm_provider.py
```

### 2.2 文件职责速查

| 文件 | 职责 | 行数估算 |
|------|------|----------|
| `cli.py` | argparse 解析、调用 agent.run()、Rich 美化输出 | ~80 |
| `config.py` | 读取 YAML + env、生成配置字典 | ~50 |
| `src/agent.py` | 核心：build_graph()、6 个节点函数、条件边路由 | ~250 |
| `src/state.py` | AgentState TypedDict + 辅助类型 | ~50 |
| `src/tools/parser.py` | AST 解析，输出结构化摘要 | ~100 |
| `src/tools/files.py` | read_file / write_file / list_directory | ~60 |
| `src/tools/runner.py` | subprocess 调用 pytest + coverage | ~100 |
| `src/tools/executor.py` | 受限 exec() / eval() ，超时控制 | ~60 |
| `src/llm/provider.py` | 抽象基类：chat(messages, tools) → response | ~40 |
| `src/llm/deepseek.py` | openai SDK → DeepSeek endpoint | ~60 |
| `src/llm/claude.py` | anthropic SDK → Claude API | ~60 |
| `src/prompt/templates.py` | 5 个节点的 prompt 模板 + system prompt | ~150 |
| `src/memory/checkpointer.py` | LangGraph MemorySaver 初始化 | ~20 |
| `src/memory/long_term.py` | SQLite CRUD：preferences、patterns、sessions | ~100 |
| `src/skills/loader.py` | 读取 data/*.md、按关键词匹配、拼接到 prompt | ~60 |
| `src/skills/data/*.md` | 4 个 Skill 知识文件 | ~200 行合计 |

---

## 3. 数据结构设计

### 3.1 AgentState（核心状态）

```python
# src/state.py
from typing import TypedDict, Annotated, Optional
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage

class FunctionInfo(TypedDict):
    name: str
    lineno: int
    args: list[dict]         # [{"name": str, "type_annotation": str|None, "default": str|None}]
    returns: str | None
    decorators: list[str]
    docstring: str | None
    complexity: int           # 圈复杂度

class BranchInfo(TypedDict):
    type: str                 # "if" | "for" | "while" | "try" | "except" | "with"
    lineno: int
    condition: str | None

class ASTSummary(TypedDict):
    file_path: str
    functions: list[FunctionInfo]
    classes: list[dict]        # 类名 + 方法列表（递归 FunctionInfo）
    imports: list[dict]        # [{"module": str, "names": list[str]}]
    branches: list[BranchInfo]
    external_deps: list[str]   # 推断的外部依赖（HTTP、DB、文件IO等）

class TestCasePlan(TypedDict):
    target: str                # 函数名或 类名.方法名
    priority: str              # "high" | "medium" | "low"
    cases: list[dict]          # [{"type": "normal|boundary|exception", "desc": str, "input_example": str}]
    mock_strategy: str         # "none" | "mock_external" | "mock_db" | "mock_all"

class CoverageData(TypedDict):
    line_rate: float
    branch_rate: float
    total_lines: int
    covered_lines: int
    uncovered: list[dict]      # [{"file": str, "lines": list[int]}]
    per_function: list[dict]   # [{"name": str, "line_rate": float, "uncovered_lines": list[int]}]

class TestResult(TypedDict):
    exit_code: int
    total: int
    passed: int
    failed: int
    errors: int
    failures_detail: list[dict]  # [{"test": str, "message": str}]
    stdout: str

class AgentState(TypedDict):
    # === 输入 ===
    target_path: str
    target_functions: list[str]    # 可选，指定具体函数

    # === 对话消息（短期记忆） ===
    messages: Annotated[list[BaseMessage], add_messages]

    # === 代码分析 ===
    source_code: str
    ast_summary: ASTSummary | None

    # === 测试计划 ===
    test_plan: list[TestCasePlan]

    # === 生成产物 ===
    test_files: list[str]          # 已写测试文件路径
    generated_count: int           # 累计生成用例数

    # === 执行结果 ===
    test_results: TestResult | None
    coverage_data: CoverageData | None

    # === 迭代控制 ===
    iteration: int
    coverage_history: list[dict]   # [{"iteration": int, "line_rate": float, "branch_rate": float}]
    termination_reason: str        # "" | "coverage_met" | "diminishing" | "not_worth" | "max_iter" | "user_stop"

    # === 输出 ===
    final_report: str
    error_message: str             # 异常时填充
```

### 3.2 Tool Schema（输入输出结构）

```python
# 工具 1: parse_code
# Input:  file_path: str
# Output: ASTSummary (见上)

# 工具 2: read_file
# Input:  file_path: str, encoding: str = "utf-8"
# Output: {"content": str, "line_count": int, "file_path": str}

# 工具 3: write_file
# Input:  file_path: str, content: str, mode: str = "w"  # "w": overwrite, "a": append
# Output: {"success": bool, "file_path": str, "bytes_written": int}

# 工具 4: run_tests
# Input:  test_path: str, target_path: str = "", pytest_args: list[str] = []
# Output: TestResult (见上)

# 工具 5: get_coverage
# Input:  source_path: str, test_path: str
# Output: CoverageData (见上)

# 工具 6: list_directory
# Input:  path: str, pattern: str = "*.py", recursive: bool = False
# Output: {"files": list[str], "dirs": list[str], "total": int}

# 工具 7: exec_code
# Input:  code: str, timeout: int = 10
# Output: {"stdout": str, "stderr": str, "return_value": str, "exception": str|None}
```

### 3.3 长期记忆 SQLite Schema

```sql
-- preferences: 用户偏好
CREATE TABLE IF NOT EXISTS preferences (
    key        TEXT PRIMARY KEY,     -- e.g. "test_framework", "assertion_style"
    value      TEXT NOT NULL,
    updated_at TEXT DEFAULT (datetime('now'))
);

-- project_patterns: 项目级测试模式
CREATE TABLE IF NOT EXISTS project_patterns (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_path    TEXT NOT NULL,
    module_name     TEXT NOT NULL,
    test_dir        TEXT,            -- 测试文件存放目录，如 "tests/"
    mock_library    TEXT,            -- 使用的 mock 库
    coverage_target REAL,            -- 用户设定的覆盖率目标
    created_at      TEXT DEFAULT (datetime('now')),
    UNIQUE(project_path, module_name)
);

-- session_history: 每次运行的记录
CREATE TABLE IF NOT EXISTS session_history (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    target_path         TEXT NOT NULL,
    total_tests         INTEGER,
    final_line_rate     REAL,
    final_branch_rate   REAL,
    iterations          INTEGER,
    termination_reason  TEXT,
    created_at          TEXT DEFAULT (datetime('now'))
);
```

---

## 4. 接口设计

### 4.1 LLM Provider 接口

```python
# src/llm/provider.py
from abc import ABC, abstractmethod
from langchain_core.messages import BaseMessage
from langchain_core.tools import BaseTool

class LLMProvider(ABC):
    """LLM Provider 抽象基类。DeepSeek 和 Claude 各自实现。"""

    @abstractmethod
    def get_model_name(self) -> str:
        """返回模型名称，如 'deepseek-v4-pro' 或 'claude-sonnet-4-6'"""
        ...

    @abstractmethod
    def bind_tools(self, tools: list[BaseTool]) -> "LLMProvider":
        """绑定工具列表，返回自身（支持链式调用）。"""
        ...

    @abstractmethod
    def invoke(self, messages: list[BaseMessage]) -> BaseMessage:
        """同步调用 LLM，返回包含 tool_calls 或 content 的消息。"""
        ...

    @abstractmethod
    async def ainvoke(self, messages: list[BaseMessage]) -> BaseMessage:
        """异步调用 LLM。"""
        ...
```

### 4.2 全局接口（agent.run）

```python
# cli.py 调用的顶层入口
# src/agent.py

from src.state import AgentState

def build_graph(
    provider: "LLMProvider",
    tools: list[BaseTool],
    checkpointer: "BaseCheckpointSaver",
) -> "CompiledStateGraph":
    """构建并编译 LangGraph 图。返回 compiled graph。"""
    ...

def create_initial_state(
    target_path: str,
    target_functions: list[str] | None = None,
) -> AgentState:
    """创建初始状态对象。"""
    ...

def run(
    target_path: str,
    target_functions: list[str] | None = None,
    target_coverage: float = 0.90,
    max_iterations: int = 5,
) -> AgentState:
    """
    顶层入口：执行完整的测试生成流程。

    Args:
        target_path: 被测文件或目录路径
        target_functions: 可选，指定函数名列表
        target_coverage: 目标覆盖率（默认 0.90）
        max_iterations: 最大迭代次数（默认 5）

    Returns:
        AgentState: 最终状态，包含 final_report、coverage_data 等
    """
    ...
```

### 4.3 Skill 接口

```python
# src/skills/loader.py

class Skill:
    name: str
    description: str
    triggers: list[str]     # 触发关键词
    content: str            # Skill 知识文本（Markdown）

def load_all_skills(skills_dir: str) -> list[Skill]:
    """从 data/ 目录加载所有 Skill。解析 Markdown front matter 获取元信息。"""
    ...

def match_skills(skills: list[Skill], context: str) -> list[Skill]:
    """
    根据当前上下文匹配 Skill。
    匹配方式：context 中包含 triggers 中的关键词 → 匹配成功。
    """
    ...

def inject_skills_into_prompt(skills: list[Skill], base_prompt: str) -> str:
    """将匹配的 Skill 内容注入 prompt 的知识段。"""
    ...
```

### 4.4 长期记忆接口

```python
# src/memory/long_term.py

class LongTermMemory:
    def __init__(self, db_path: str = "~/.testmaker/memory.db"): ...

    # 偏好
    def get_preference(self, key: str) -> str | None: ...
    def set_preference(self, key: str, value: str) -> None: ...
    def get_all_preferences(self) -> dict[str, str]: ...

    # 项目模式
    def get_project_pattern(self, project_path: str, module_name: str) -> dict | None: ...
    def upsert_project_pattern(self, project_path: str, module_name: str, **kwargs) -> None: ...

    # 会话记录
    def record_session(self, **kwargs) -> None: ...
    def get_recent_sessions(self, limit: int = 5) -> list[dict]: ...
```

---

## 5. LangGraph 图设计

### 5.1 节点定义

```python
# src/agent.py 中的节点函数签名

def node_analyze(state: AgentState) -> dict[str, Any]:
    """
    职责：
      1. 调用 read_file 读取目标文件
      2. 调用 list_directory 了解模块结构
      3. 调用 parse_code 获取 AST 摘要
      4. 更新 state.source_code, state.ast_summary
    工具调用方式：此节点中的 LLM 调用绑定了探索类工具（read_file, list_directory, parse_code）
    """

def node_plan(state: AgentState) -> dict[str, Any]:
    """
    职责：
      1. LLM 基于 ast_summary + source_code 生成测试计划
      2. 加载匹配的 Skill（boundary-analysis, mock-strategy）
      3. 输出 test_plan JSON
      4. 更新 state.test_plan
    工具调用：无（纯 LLM 推理，结构化输出）
    """

def node_generate(state: AgentState) -> dict[str, Any]:
    """
    职责：
      1. 基于 test_plan 逐个生成测试代码
      2. 调用 write_file 写入测试文件
      3. 更新 state.test_files, state.generated_count
    工具调用：write_file（可能多次调用）
    Skill：pytest-patterns
    """

def node_execute(state: AgentState) -> dict[str, Any]:
    """
    职责：
      1. 调用 run_tests 执行测试
      2. 调用 get_coverage 收集覆盖率
      3. 更新 state.test_results, state.coverage_data, state.coverage_history
    工具调用：run_tests, get_coverage（无 LLM 参与，纯工具调用）
    """

def node_reflect(state: AgentState) -> dict[str, Any]:
    """
    职责：
      1. LLM 分析 test_results 和 coverage_data
      2. 判断是否有失败测试需要修正
      3. 判断覆盖率缺口是否值得补充
      4. 输出决策：continue | retry | stop
      5. 更新 state.termination_reason
    工具调用：无（纯 LLM 推理）
    """

def node_report(state: AgentState) -> dict[str, Any]:
    """
    职责：
      1. LLM 汇总全流程数据
      2. 生成结构化最终报告（Markdown）
      3. 写入长期记忆（用户偏好、项目模式）
      4. 更新 state.final_report
    工具调用：write_file（保存报告文件）
    """
```

### 5.2 节点间的边与路由

```python
# 条件路由函数
def route_after_reflect(state: AgentState) -> str:
    """
    根据 state.termination_reason 路由：
      "" → "generate"        # 首次 reflect，默认继续
      "retry" → "generate"   # 测试失败，修正后重跑
      "continue" → "generate" # 覆盖率不足，补测
      "coverage_met" → "report"
      "diminishing" → "report"
      "not_worth" → "report"
      "max_iter" → "report"
    """
    reason = state.get("termination_reason", "")
    if reason in ("continue", "retry", ""):
        return "generate"
    else:
        return "report"

def route_after_generate(state: AgentState) -> str:
    """generate 完成后始终进入 execute。"""
    return "execute"

# 图构建
def build_graph(provider, tools, checkpointer):
    workflow = StateGraph(AgentState)

    workflow.add_node("analyze", node_analyze)
    workflow.add_node("plan", node_plan)
    workflow.add_node("generate", node_generate)
    workflow.add_node("execute", node_execute)
    workflow.add_node("reflect", node_reflect)
    workflow.add_node("report", node_report)

    workflow.set_entry_point("analyze")
    workflow.add_edge("analyze", "plan")
    workflow.add_edge("plan", "generate")
    workflow.add_edge("generate", "execute")
    workflow.add_edge("execute", "reflect")

    workflow.add_conditional_edges(
        "reflect",
        route_after_reflect,
        {"generate": "generate", "report": "report"}
    )

    workflow.add_edge("report", END)

    return workflow.compile(checkpointer=checkpointer)
```

### 5.3 LLM 调用的节点分配

| 节点 | 是否调用 LLM | 绑定的工具 | 说明 |
|------|-------------|-----------|------|
| analyze | 是 | read_file, list_directory, parse_code | LLM 决定"我需要看哪些文件" |
| plan | 是 | 无（结构化 JSON 输出） | 纯推理生成测试计划 |
| generate | 是 | write_file | LLM 决定"这个用例怎么写" |
| execute | 否 | run_tests, get_coverage | 确定性执行，无需 LLM |
| reflect | 是 | 无（结构化 JSON 输出） | LLM 评估结果并决策 |
| report | 是 | write_file | LLM 汇总生成报告 |

### 5.4 交互式模式的控制流

交互式模式下不使用固定的六节点 DAG，改为 analyze 后进入**用户驱动的 ReAct 循环**：

```python
# 交互式图：analyze（自动） → interactive_loop（用户驱动）
def build_interactive_graph(provider, tools, checkpointer):
    workflow = StateGraph(AgentState)

    workflow.add_node("analyze", node_analyze)                     # 自动分析
    workflow.add_node("interactive", node_interactive_loop)        # ReAct 循环
    workflow.add_node("report", node_report)                       # 结束时生成报告

    workflow.set_entry_point("analyze")
    workflow.add_edge("analyze", "interactive")
    workflow.add_conditional_edges(
        "interactive",
        route_after_interactive,
        {"loop": "interactive", "report": "report"}
    )
    workflow.add_edge("report", END)

    return workflow.compile(checkpointer=checkpointer)
```

`node_interactive_loop` 内部逻辑：

```
展示状态摘要 → 等待用户输入 → input("> ")
  ├─ 输入 done/exit/quit → 返回 {"termination_reason": "user_stop"}，路由到 report
  └─ 其他输入 → 作为 HumanMessage 追加到 messages
                → LLM 调用（绑定全部 7 个工具）
                → 执行 tool_calls
                → 展示结果
                → 回到展示状态摘要
```

与全自动模式的关键区别：

| 维度 | 全自动 DAG | 交互式 ReAct |
|------|-----------|-------------|
| 控制流 | 固定顺序 6 节点 | analyze 后进入自由循环 |
| 工具绑定 | 每个节点部分工具 | 7 个工具全部绑定 |
| 终止条件 | terminal_reason 自动判断 | 用户输入 `done`/`exit` |
| LLM 职责 | 每个节点有明确任务 | 自行判断用户意图并选择行动 |

---

## 6. 与 research.md 的差异及调整

research.md 是概念设计，plan.md 在以下点上做了工程化调整：

| 差异点 | research 描述 | plan 调整 |
|--------|-------------|----------|
| 工具数量 | search_code, get_diff 共 9 个 | 暂不加 search_code/get_diff（Phase 2 用 LLM grep 替代），MVP 7 个工具 |
| 迭代上限 | 5 轮 | 5 轮，且连续 2 轮提升 < 2% 自动终止 |
| AST 解析语言 | 未指定 | MVP 仅支持 Python（`ast` 标准库）。多语言是远期目标 |
| Skill 匹配 | "LLM 主动检索" | 简化：关键词匹配 + 显式触发，避免过度设计 |
| 断言的生成策略 | 推断预期值 | 三级：docstring 示例 > LLM 语义推断 > 类型断言兜底 |
| exec_code 安全 | 未讨论 | 必须：subprocess 隔离 + 超时 + 禁止网络/文件写入 |
| 测试风格记忆 | LLM 提取 | Phase 5 实现。Phase 1-4 每次独立，不做跨会话记忆 |
| write_file 行为 | 覆盖 | 追加模式：test 文件已存在时 append 而非覆盖 |

---

## 7. 分阶段实施步骤

### Phase 1：项目骨架与配置（0.5 天）

**目标**：代码目录创建、依赖安装、配置加载、CLI 可启动。

| 步骤 | 内容 | 产出 |
|------|------|------|
| 1.1 | 创建 `testmaker/` 目录结构 | 空目录树 |
| 1.2 | 编写 `requirements.txt` | `langgraph`, `langchain-core`, `openai`, `pyyaml`, `pytest`, `pytest-cov`, `coverage`, `rich` |
| 1.3 | 编写 `config.py` + `config.yaml` | 可加载配置：model、api_key(env)、max_iterations、coverage_target |
| 1.4 | 编写 `src/logger.py` | 统一日志格式 |
| 1.5 | 编写 `cli.py` | `argparse` + `agent.run()` 桩调用 |
| 1.6 | 配置 `.env` 方式管理 API key | `.env.example` 文件 |

**验收**：`python cli.py --help` 输出帮助信息；`python cli.py path/to/file.py` 输出 "Not implemented"。

---

### Phase 2：LLM Provider 层（0.5 天）

**目标**：LLM 调用链路通。

| 步骤 | 内容 | 产出 |
|------|------|------|
| 2.1 | 编写 `src/llm/provider.py` 抽象基类 | `LLMProvider` ABC |
| 2.2 | 编写 `src/llm/deepseek.py` | `DeepSeekProvider`，openai SDK 兼容调用 |
| 2.3 | 编写 `src/llm/claude.py` | `ClaudeProvider`（桩或完整实现均可，预留即可） |
| 2.4 | 编写 `tests/test_llm_provider.py` | 验证 provider 可初始化、可发送消息、可接收回复 |

**验收**：`DeepSeekProvider().invoke([HumanMessage("hi")])` 返回有效回复。

---

### Phase 3：工具层实现（1 天）

**目标**：7 个工具全部可用，可独立测试。

| 步骤 | 内容 | 产出 |
|------|------|------|
| 3.1 | `src/tools/parser.py` — `parse_code` | AST 解析 → ASTSummary |
| 3.2 | `src/tools/files.py` — `read_file`, `write_file`, `list_directory` | 基本文件操作 |
| 3.3 | `src/tools/runner.py` — `run_tests`, `get_coverage` | subprocess 调用 pytest + coverage |
| 3.4 | `src/tools/executor.py` — `exec_code` | subprocess 隔离执行（超时、无网络、无文件写入） |
| 3.5 | `src/tools/__init__.py` — `get_all_tools()` | 注册为 LangChain Tool 列表 |
| 3.6 | `tests/test_parser.py`, `tests/test_runner.py`, `tests/test_files.py` | 工具层的单元测试 |

**验收**：每个工具可独立调用并返回预期格式的结果。

---

### Phase 4：单轮 Agent 核心（1.5 天）

**目标**：实现 `analyze → plan → generate → execute → report` 单轮链路。

| 步骤 | 内容 | 产出 |
|------|------|------|
| 4.1 | 编写 `src/state.py` — AgentState | TypedDict 完整定义 |
| 4.2 | 编写 `src/prompt/templates.py` | SYSTEM_PROMPT + 5 个节点 prompt 模板 |
| 4.3 | 编写 `src/agent.py` — `analyze` 节点 | LLM + 探索工具 → AST 摘要 |
| 4.4 | 编写 `src/agent.py` — `plan` 节点 | LLM 推理 → test_plan JSON |
| 4.5 | 编写 `src/agent.py` — `generate` 节点 | LLM + write_file → 测试文件 |
| 4.6 | 编写 `src/agent.py` — `execute` 节点 | 纯工具调用 → 测试结果 + 覆盖率 |
| 4.7 | 编写 `src/agent.py` — `report` 节点 | LLM 汇总 → Markdown 报告 |
| 4.8 | 编写 `src/agent.py` — `build_graph()` + `run()` + `run_interactive()` | 图拼接 + 全自动入口 + 交互式入口 |

**验收**：对一个简单 Python 函数（如 `def add(a, b): return a + b`）完整走通 analyze → report，生成可运行的测试文件。`--interactive` 可进入对话循环。

---

### Phase 5：迭代闭环（0.5 天）

**目标**：实现 `reflect → 条件路由 → iterate` 循环。

| 步骤 | 内容 | 产出 |
|------|------|------|
| 5.1 | 编写 `reflect` 节点 | LLM 评估覆盖率/失败 → 输出决策 |
| 5.2 | 编写 `route_after_reflect` 条件路由 | 根据 termination_reason 路由 |
| 5.3 | 迭代终止条件实现 | 覆盖率达标 / 边际递减 / 不可测 / 最大轮次 |
| 5.4 | 测试失败修正逻辑 | retry 类型：测试错误 → 修正 regenerate |

**验收**：对一个有多个分支的函数，Agent 能自动运行 2-3 轮迭代直到覆盖率达标或判定不值得继续。

---

### Phase 6：Skill 系统（0.5 天）

**目标**：Skill 加载、匹配、注入到 prompt。

| 步骤 | 内容 | 产出 |
|------|------|------|
| 6.1 | 编写 `src/skills/data/*.md` 4 个 Skill 文件 | pytest-patterns, mock-strategy, boundary-analysis, coverage-strategy |
| 6.2 | 编写 `src/skills/loader.py` | 加载 + 关键词匹配 + 注入 |
| 6.3 | 在 `plan`、`generate`、`reflect` 节点集成 Skill | 节点调用前加载匹配的 Skill 注入 prompt |

**验收**：Agent 生成测试时自动应用 pytest fixture 模式（而非硬编码）；mock 策略选择有 Skill 知识支撑。

---

### Phase 7：记忆系统（0.5 天）

**目标**：跨会话状态持久化。

| 步骤 | 内容 | 产出 |
|------|------|------|
| 7.1 | 编写 `src/memory/checkpointer.py` | MemorySaver 封装 |
| 7.2 | 编写 `src/memory/long_term.py` | SQLite CRUD |
| 7.3 | 在 `report` 节点写入长期记忆 | 偏好 + 项目模式 + 会话记录 |
| 7.4 | 在 `plan` 节点读取长期记忆 | 加载用户偏好和项目模式 |

**验收**：第二次对同目录运行 Agent 时，能复用上次的测试目录和 mock 策略偏好。

---

### Phase 8：打磨与文档（1 天）

**目标**：错误处理、CLI 美化、演示准备。

| 步骤 | 内容 | 产出 |
|------|------|------|
| 8.1 | 全链路错误处理 | LLM 输出格式校验、工具异常降级、超时处理 |
| 8.2 | CLI 美化（Rich） | 进度条、颜色、面板。全自动和交互式两种模式均有视觉区分 |
| 8.3 | 交互式模式打磨 | 对话历史回滚、指令补全提示、help 命令 |
| 8.4 | `README.md` | 环境配置、运行方法、≥3 个使用示例（含交互式示例） |
| 8.5 | 演示准备 | 准备 3 个不同复杂度的 Python 文件作为演示用例 |

**验收**：README 中的 3 个示例均可复现。

---

## 7. 关键节点 Prompt 设计要点

### 7.1 System Prompt

```
你是 TestMaker，一个专业的测试用例生成 Agent。
你的能力：
1. 分析 Python 代码的结构和语义
2. 规划测试策略（正常路径、边界条件、异常路径）
3. 生成符合 pytest 规范的测试代码
4. 运行测试并根据覆盖率反馈迭代改进

你的约束：
- 只生成可执行的 Python 测试代码
- 不生成被测代码的修改建议（除非用户要求）
- 断言必须具体（不能只 assert result 不为 None）
- 对外部依赖（网络、数据库、文件系统）使用 Mock
- 未知行为时标注 # FIXME: verify expected behavior，而不是猜测

你的工作流：
analyze → plan → generate → execute → reflect → (iterate) → report
```

### 7.2 plan 节点 prompt 要点

```
输入：AST 摘要 + 源码片段
输出：JSON 格式的测试计划

要求：
- 为每个函数列出用例，按 priority 排序
- normal 用例必须包含具体的输入和预期输出
- boundary 用例覆盖：空值、零值、极值、边界 ±1
- exception 用例覆盖：类型错误、值错误、依赖故障
- 判断是否需要 mock，以及 mock 什么

JSON Schema: { "targets": [{ "target": str, "priority": "high|medium|low", "cases": [...] }] }
```

### 7.3 reflect 节点 prompt 要点

```
输入：当前覆盖率、历史覆盖率趋势、测试失败详情
输出：JSON 格式的评估决策

要求：
- 分析失败是"测试错误"还是"被测代码 bug"
- 分析未覆盖分支的价值
- 输出决策：continue | retry | stop
- 附带理由

JSON Schema: { "decision": str, "reason": str, "next_actions": [...] }
```

---

## 8. 风险分析与缓解

| # | 风险 | 概率 | 影响 | 缓解措施 | 对应 Phase |
|---|------|------|------|----------|-----------|
| R1 | DeepSeek function calling 不稳定，tool_call 格式异常 | 中 | 高 | Phase 2 验证 FC 稳定性；加 JSON 格式 fallback（手动解析 content） | 2, 4 |
| R2 | LLM 生成测试代码有语法错误 | 高 | 中 | write_file 后用 `ast.parse` 预检；失败让 LLM 修正（retry 最多 3 次） | 5 |
| R3 | `exec_code` 安全漏洞 | 中 | 高 | subprocess 隔离 + 无网络 + 超时 10s + 禁用 `__import__`/`open`/`os` | 3 |
| R4 | pytest 环境差异（缺依赖）导致测试跑不起来 | 中 | 中 | 检测 ImportError 时提示用户安装；generate 时优先 mock 不可用依赖 | 4 |
| R5 | 迭代死循环 | 低 | 高 | 硬限制 max 5 轮 + 边际递减检测（2 轮提升 < 2%） | 5 |
| R6 | 长源码导致 token 超限 | 中 | 中 | parse_code 用 AST 摘要代替源码进 prompt；超过 500 行分函数处理 | 4 |
| R7 | prompt 太弱导致 LLM 输出格式不固定 | 中 | 中 | 用 JSON Schema + `response_format` 约束；加解析层做 schema 校验，失败重试 | 2, 4 |

---

## 9. CLI 接口设计

```bash
# 基本用法
python cli.py path/to/module.py

# 指定函数
python cli.py path/to/module.py --func login --func register

# 指定覆盖率目标
python cli.py path/to/module.py --coverage 95

# 控制最大迭代次数
python cli.py path/to/module.py --max-iter 3

# 更换模型
python cli.py path/to/module.py --model claude

# 输出测试文件目录（默认 tests/）
python cli.py path/to/module.py --output-dir custom_tests/

# 详细输出
python cli.py path/to/module.py --verbose

# 仅分析不生成（dry run）
python cli.py path/to/module.py --dry-run

# 交互式对话模式
python cli.py path/to/module.py --interactive
# → 进入对话循环，Agent 等待用户指令
```

### 9.1 两种运行模式

#### 模式一：全自动（默认）

```
python cli.py path/to/module.py
```

Agent 自动完成 analyze → plan → generate → execute → reflect → (iterate) → report 全流程，终端仅展示进度。用户不参与中间决策。

#### 模式二：交互式（`--interactive`）

```
python cli.py path/to/module.py --interactive
```

Agent 完成初始分析后暂停，交还控制权给用户。用户通过自然语言在对话窗口中下达指令，Agent 响应后再次等待。

**交互式模式流程**：

```
Agent 启动
  │
  ├─ [analyze] 自动执行，分析目标文件
  │
  └─ 进入对话循环 ──────────────────────────────┐
       │                                          │
       │  ╭─ TestMaker (interactive) ─╮           │
       │  │ 已分析 path/to/module.py   │           │
       │  │ 发现 3 个函数, 8 个分支     │           │
       │  │                            │           │
       │  │ > 请输入指令                │           │
       │  ╰────────────────────────────╯           │
       │                                          │
       ▼                                          │
   用户输入: "我希望对数组越界进行测试"              │
       │                                          │
       ▼                                          │
   LLM 解析意图 → 决定行动                          │
   可能的行为:                                     │
   ├─ 生成特定测试 → write_file → run_tests        │
   ├─ 回答覆盖率问题 → get_coverage → 解释          │
   ├─ 修改已有测试 → 定位文件 → 修改 → 重跑         │
   └─ 用户输入 "done" → 退出循环 → 生成报告          │
       │                                          │
       ▼                                          │
   输出结果给用户                                   │
       │                                          │
       └──── 返回对话循环，等待下一次输入 ─────────┘
```

**与全自动模式的关键区别**：

| 维度 | 全自动 | 交互式 |
|------|--------|--------|
| 控制流 | 固定 DAG (analyze→plan→...→report) | 自由 ReAct 循环（用户指令驱动） |
| 工具绑定 | 每个节点绑部分工具 | 绑全部 7 个工具，LLM 自主选择 |
| 终止条件 | 覆盖率达标 / 边际递减 | 用户输入 `done` / `exit` / `quit` |
| 用户参与 | 无 | 每轮等待用户输入 |
| 适用场景 | 快速批量生成 | 探索式测试、逐步细化 |

**交互式 CLI 实现要点**：

```python
# cli.py 中的交互循环（概念）
def run_interactive(target_path: str) -> None:
    state = create_initial_state(target_path)
    state = node_analyze(state)  # 自动完成初始分析
    display_analysis_summary(state)

    while True:
        user_input = console.input("[bold green]> [/bold green]")
        if user_input.lower() in ("done", "exit", "quit", "q"):
            break

        # 将用户输入追加到 messages，调用 LLM
        state["messages"].append(HumanMessage(content=user_input))
        # LLM 绑定了全部工具，自主决定调用哪些
        response = provider.invoke(state["messages"])
        # 执行 tool_calls，展示结果
        ...

    # 退出时生成报告
    state = node_report(state)
    display_final_report(state)
```

**典型交互示例**：

```
> 分析 path/to/user_service.py

📂 已分析 user_service.py:
   4 个函数: create_user, delete_user, update_email, get_by_id
   12 个分支, 3 个外部依赖 (SQLAlchemy, bcrypt, redis)
   已有测试: tests/test_user_service.py (8 用例, 覆盖率 67%)

> 补充 delete_user 的异常测试，重点测数据库超时

✍️  正在生成...
   ✓ tests/test_user_service.py (追加 3 个用例)
🧪 3 passed, 0 failed
📊 delete_user 覆盖率: 67% → 94%

> 看一下当前总体覆盖率

📊 整体覆盖率: 行 78.4% | 分支 71.2%
   未覆盖: create_user#L45 (email 格式校验)
           update_email#L89 (redis 写入失败)

> done

📄 正在生成最终报告...
   报告已保存至: tests/user_service_report.md
```

---

## 10. 配置文件设计（config.yaml）

```yaml
# config.yaml
model:
  provider: deepseek              # deepseek | claude
  name: deepseek-v4-pro              # deepseek-v4-pro 为默认模型
  temperature: 0.3
  max_tokens: 4096

agent:
  max_iterations: 5
  target_coverage: 0.90           # 默认目标覆盖率
  test_dir: tests                 # 默认测试输出目录
  retry_on_failure: 3             # 测试失败时的最大重试次数
  code_timeout: 60                # 测试执行超时（秒）

memory:
  long_term_path: ~/.testmaker/memory.db

skills:
  dir: src/skills/data
  auto_load: true                 # 启动时自动加载全部 Skill

logging:
  level: INFO
  file: ~/.testmaker/agent.log

# claude 配置（provider 为 claude 时使用）
claude:
  model: claude-sonnet-4-6
  max_tokens: 4096
```

---

## 11. 关键实现约束

### 11.1 错误处理层级

```
Layer 1 (工具层): 每个工具捕获自己的异常，返回结构化错误（不抛）
Layer 2 (节点层): 节点函数 try/except，写入 state.error_message，路由到 report
Layer 3 (Agent 层): run() 顶层 try/except，保证不崩溃
Layer 4 (CLI 层): 显示友好错误信息
```

### 11.2 代码规范

- Python 3.10+，使用 `str | None` 语法（非 `Optional[str]`）
- 类型标注覆盖率 100%
- 无 `*args, **kwargs`，显式参数
- 工具函数返回值统一用 dict（TypedDict 约束）
- prompt 模板用 f-string + 占位符，不拼接
- 每个 .py 文件不超过 200 行

### 11.3 测试策略（Agent 自身的测试）

- 工具层：100% 单元测试（纯函数，易测）
- LLM Provider 层：集成测试（mock API 响应）
- Agent 图：端到端测试（用固定 Python 文件作被测目标）
- 不测：LLM 输出的"语义正确性"（只能人工判断）

---

## 12. 各阶段依赖关系

```
Phase 1 (骨架)
  └→ Phase 2 (LLM Provider)
       └→ Phase 3 (工具层) ←──────────┐
            └→ Phase 4 (单轮 Agent) ──→ Phase 5 (迭代闭环)
                                        │
            Phase 6 (Skill) ────────────┤
            Phase 7 (记忆) ─────────────┘
                                        └→ Phase 8 (打磨)
```

Phase 6 和 Phase 7 可并行开发，它们是对 Phase 4-5 的增强。

---

## 附录：验证用被测代码示例

Phase 4 验收时用以下三个简单的 Python 文件验证：

### A. 简单函数（验证单轮链路）

```python
# sample_simple.py
def divide(a: float, b: float) -> float:
    """Divide a by b."""
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b
```

### B. 多分支函数（验证迭代）

```python
# sample_branches.py
from typing import Optional

def get_discount(price: float, user_level: str, is_holiday: bool = False) -> float:
    """Calculate discount based on user level and holiday."""
    if price <= 0:
        raise ValueError("Price must be positive")

    discount = 0.0
    if user_level == "VIP":
        discount = 0.3
    elif user_level == "GOLD":
        discount = 0.2
    elif user_level == "SILVER":
        discount = 0.1

    if is_holiday:
        discount += 0.05

    # Cap discount at 0.5
    if discount > 0.5:
        discount = 0.5

    return discount
```

### C. 有外部依赖的函数（验证 Mock）

```python
# sample_external.py
import requests

def fetch_user_name(user_id: int, api_base_url: str) -> Optional[str]:
    """Fetch user name from API."""
    try:
        resp = requests.get(f"{api_base_url}/users/{user_id}", timeout=5)
        resp.raise_for_status()
        return resp.json().get("name")
    except requests.RequestException:
        return None
```

---

