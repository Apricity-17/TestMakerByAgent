# TestMaker — AI-Powered Test Case Generator

基于 AI Agent 的 Python 测试用例自动生成工具。分析源码逻辑，自动规划、生成并迭代优化 pytest 测试用例，以覆盖率驱动闭环迭代。

## 环境要求

- Python 3.9+
- [DeepSeek API Key](https://platform.deepseek.com/)（或 Anthropic Claude API Key）

## 安装

```bash
pip install -r requirements.txt
```

## 配置

设置 API Key 环境变量：

```bash
# DeepSeek（默认）
export DEEPSEEK_API_KEY="sk-xxxxxxxx"

# 或者 Claude
export ANTHROPIC_API_KEY="sk-ant-xxxx"
```

可选：编辑 `config.yaml` 调整默认参数（覆盖率目标、最大迭代次数等）。

## 使用方式

### 模式一：全自动

```bash
# 基本用法：分析 sample_simple.py 并自动生成测试
python cli.py sample_simple.py

# 指定覆盖率目标 95%
python cli.py sample_simple.py --coverage 0.95

# 只测试指定函数
python cli.py sample_branches.py --func get_discount

# 使用 Claude 模型
python cli.py sample_simple.py --model claude
```

Agent 自动完成：分析代码 → 规划用例 → 生成测试 → 运行 → 评估覆盖率 → 补测 → 生成报告。

### 模式二：交互式

```bash
python cli.py sample_simple.py --interactive
```

Agent 完成初始分析后进入对话循环。你可以：

```
> 查看覆盖率
> 补充 get_discount 的边界测试
> 修正 test_calculate.py 中第 15 行的断言
> done
```

输入 `done` 退出并生成最终报告。

### 输出

- `tests/test_<module>.py` — 生成的测试代码
- `tests/test_<module>_report.md` — 测试报告

## 示例

### 示例 1：简单函数

```bash
$ python cli.py sample_simple.py
```

Agent 分析 `divide()` 和 `add()` 两个函数，生成正常/边界/异常测试用例，运行并通过。

### 示例 2：多分支函数（迭代）

```bash
$ python cli.py sample_branches.py
```

`get_discount()` 包含多个条件分支。Agent 首轮覆盖主要路径后，reflect 节点评估未覆盖分支，自动补充 VIP、GOLD、SILVER + 节日叠加 + 折扣上限等边界用例。

### 示例 3：外部依赖 + Mock

```bash
$ python cli.py sample_external.py
```

`fetch_user_name()` 依赖 `requests.get`。Agent 自动识别 HTTP 依赖，生成 `unittest.mock.patch` 来模拟 API 响应，并测试正常返回和 RequestException 两种路径。

## CLI 参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `target_path` | 目标 Python 文件路径 | 必填 |
| `--func` | 指定测试的函数（可重复） | 全部函数 |
| `--coverage` | 目标覆盖率 (0.0–1.0) | 0.90 |
| `--max-iter` | 最大迭代次数 | 5 |
| `--model` | LLM 模型 (deepseek\|claude) | deepseek |
| `--output-dir` | 测试输出目录 | tests |
| `--verbose` | 详细输出 | false |
| `--dry-run` | 仅分析不生成 | false |
| `--interactive` | 交互式模式 | false |
