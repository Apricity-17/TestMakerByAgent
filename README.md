# TestMaker — AI-Powered Test Case Generator

r分析源码逻辑，自动规划、生成、运行并迭代优化测试用例，覆盖率驱动闭环迭代。

支持 Python、Java、JavaScript、TypeScript、Go、Rust 等 14 种语言。

## 环境要求

- Python 3.9+
- [DeepSeek API Key](https://platform.deepseek.com/)（或 Anthropic Claude API Key）
- Java 17+（可选，仅 Java 测试需要）
- Node.js（可选，仅 JS/TS 测试需要）

## 安装

```bash
pip install -r requirements.txt
```

## 配置 API Key

**方式一：`.env` 文件（推荐）**

在项目根目录创建 `.env` 文件，启动时自动加载：

```
DEEPSEEK_API_KEY=sk-xxxxxxxx
```

**方式二：环境变量**

```bash
export DEEPSEEK_API_KEY="sk-xxxxxxxx"
```

Claude 用户设置 `ANTHROPIC_API_KEY` 并在命令中加 `--model claude`。

可选：编辑 `config.yaml` 调整默认参数（覆盖率目标、最大迭代次数等）。

## 使用方式

### 模式一：全自动

```bash
# Python
python3 cli.py sample_simple.py

# Java
python3 cli.py Calc.java

# 指定覆盖率目标 95%
python3 cli.py sample_simple.py --coverage 0.95

# 中文输出（默认）/ 英文输出
python3 cli.py sample_simple.py --lang zh
python3 cli.py sample_simple.py --lang en
```

Agent 自动完成：分析代码 → 规划用例 → 生成测试 → 编译运行 → 评估覆盖率 → 补测 → 生成报告。

### 模式二：交互式

```bash
python3 cli.py Calc.java --interactive
```

Agent 分析完成后进入对话循环，生成完自动运行测试：

```
> 只测试 add 和 divide 方法
  写入 CalcTest.java
  自动运行测试... 12/12 passed

> done
```

### 输出

```
<源文件同级目录>/test_<文件名>/
├── test_<模块>.py          # Python 测试
├── <类名>Test.java         # Java 测试
└── *_report.md             # 测试报告
```

## 示例

### 示例 1：Python — 简单函数

```bash
$ python3 cli.py sample_simple.py
```

Agent 分析 `add()` 和 `divide()`，生成 18 个用例，100% 覆盖率，1 轮迭代达标。

### 示例 2：Python — 多分支函数

```bash
$ python3 cli.py sample_branches.py
```

`get_discount()` 含多个条件分支，Agent 自动补充 VIP、GOLD、SILVER + 节日叠加 + 折扣上限等边界用例。

### 示例 3：Java — CLI 计算器

```bash
$ python3 cli.py Calc.java
```

`Calc.java` 有 add、divide、multiply 和 main 入口。Agent 生成 JUnit 5 测试，自动编译运行，59/59 通过。

### 示例 4：Python — 外部依赖 Mock

```bash
$ python3 cli.py sample_external.py
```

`fetch_user_name()` 依赖 `requests.get`，Agent 自动识别 HTTP 依赖并生成 Mock。

## CLI 参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `target_path` | 目标源文件路径 | 必填 |
| `--func` | 指定测试的函数（可重复） | 全部函数 |
| `--coverage` | 目标覆盖率 (0.0–1.0) | 0.90 |
| `--max-iter` | 最大迭代次数 | 5 |
| `--model` | LLM 模型 (deepseek\|claude) | deepseek |
| `--lang` | 输出语言 (zh\|en) | zh |
| `--output-dir` | 测试输出目录 | tests |
| `--verbose` | 详细输出 | false |
| `--dry-run` | 仅分析不生成 | false |
| `--interactive` | 交互式模式 | false |

## Java 测试环境（可选）

Java 测试需要 JUnit 5 运行时 JAR。Agent 会自动从 `test_*/` 目录搜索。手动下载：

```bash
# JUnit Console Launcher（必选）
curl -LO https://repo1.maven.org/maven2/org/junit/platform/junit-platform-console-standalone/1.11.4/junit-platform-console-standalone-1.11.4.jar

# Mockito（含反射测试时需要）
curl -LO https://repo1.maven.org/maven2/org/mockito/mockito-core/5.14.2/mockito-core-5.14.2.jar
```

将 JAR 放在被测文件同级目录或 `test_*/` 子目录下即可。
