"""Language-agnostic code parser tool.

Detects language and extracts structural info using regex + AST for Python.
For non-Python files, uses heuristic regex to find functions/classes/branches.
"""

import ast
import re
from typing import Any

from langchain_core.tools import tool

LANG_MAP = {
    ".py": "python",
    ".java": "java",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".jsx": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".swift": "swift",
    ".kt": "kotlin",
    ".scala": "scala",
    ".php": "php",
}

FUNC_PATTERNS = {
    "python": re.compile(r"^\s*(def|class)\s+(\w+)", re.MULTILINE),
    "java": re.compile(
        r"^\s*(public|private|protected|static|\s)*\s+[\w<>[\],\s]+\s+(\w+)\s*\([^)]*\)\s*\{",
        re.MULTILINE,
    ),
    "javascript": re.compile(
        r"(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:\([^)]*\)|[^=]\S*)\s*=>|class\s+(\w+))",
        re.MULTILINE,
    ),
    "typescript": re.compile(
        r"(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*:\s*\([^)]*\)\s*=>|class\s+(\w+)|(?:public|private|protected)?\s*(?:async\s+)?(\w+)\s*\([^)]*\)\s*:)",
        re.MULTILINE,
    ),
    "go": re.compile(r"func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)\s*\(", re.MULTILINE),
    "rust": re.compile(r"fn\s+(\w+)\s*\(", re.MULTILINE),
    "ruby": re.compile(r"def\s+(\w+)", re.MULTILINE),
    "c": re.compile(
        r"^\s*[\w\s*]+\s+(\w+)\s*\([^)]*\)\s*\{", re.MULTILINE
    ),
    "cpp": re.compile(
        r"^\s*(?:[\w:]+(?:<[^>]*>)?[\s*&]+)+(\w+)\s*\([^)]*\)\s*(?:const\s*)?\{",
        re.MULTILINE,
    ),
}

BRANCH_PATTERNS = re.compile(
    r"^\s*(if|else\s+if|for|while|switch|catch|except|when|unless|match)\b",
    re.MULTILINE,
)


@tool
def parse_code(file_path: str) -> dict[str, Any]:
    """Parse a source file and return language, functions, classes, branches.

    Supports Python, Java, JavaScript, TypeScript, Go, Rust, Ruby, C, C++, C#,
    Swift, Kotlin, Scala, PHP.

    For Python, uses AST for precise results. For other languages, uses
    heuristic regex matching. LLM semantic analysis supplements this.
    """
    with open(file_path) as f:
        source = f.read()

    ext = _get_ext(file_path)
    language = LANG_MAP.get(ext, "unknown")
    lines = source.split("\n")

    functions: list[dict[str, Any]] = []
    classes: list[dict[str, Any]] = []
    branches: list[dict[str, Any]] = []
    imports: list[dict[str, Any]] = []

    # Python: use AST for accurate results
    if language == "python":
        functions, classes, imports, branches, external_deps = _parse_python(source)
    else:
        functions, classes = _parse_with_regex(source, language)
        imports = _detect_imports(source, language)
        branches = _detect_branches(lines)
        external_deps = _detect_external_deps(source, language)

    return {
        "file_path": file_path,
        "language": language,
        "line_count": len(lines),
        "functions": functions,
        "classes": classes,
        "imports": imports,
        "branches": branches,
        "external_deps": list(set(external_deps)),
    }


def _get_ext(file_path: str) -> str:
    import os
    base = os.path.basename(file_path)
    if base.endswith(".test.ts") or base.endswith(".spec.ts"):
        return ".ts"
    if base.endswith(".test.tsx") or base.endswith(".spec.tsx"):
        return ".tsx"
    if base.endswith(".test.js") or base.endswith(".spec.js"):
        return ".js"
    _, ext = os.path.splitext(file_path)
    return ext.lower()


# ─── Python AST ──────────────────────────────────────────────────────────────


def _parse_python(source: str) -> tuple[list, list, list, list, list]:
    functions: list[dict] = []
    classes: list[dict] = []
    imports: list[dict] = []
    branches: list[dict] = []
    external_deps: list[str] = []

    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            # Only top-level functions
            for child in ast.iter_child_nodes(tree):
                if child is node:
                    num_defaults = len(node.args.defaults)
                    num_no_default = len(node.args.args) - num_defaults
                    args_info = []
                    for i, a in enumerate(node.args.args):
                        default_val = None
                        if i >= num_no_default:
                            di = i - num_no_default
                            try:
                                default_val = ast.unparse(node.args.defaults[di])
                            except Exception:
                                default_val = None
                        args_info.append({
                            "name": a.arg,
                            "type_annotation": ast.unparse(a.annotation) if a.annotation else None,
                            "default": default_val,
                        })
                    functions.append({
                        "name": node.name,
                        "lineno": node.lineno,
                        "args": args_info,
                        "returns": ast.unparse(node.returns) if node.returns else None,
                        "decorators": [ast.unparse(d) for d in node.decorator_list],
                        "docstring": ast.get_docstring(node),
                        "complexity": _py_complexity(node),
                    })
                    break

        if isinstance(node, ast.ClassDef):
            for child in ast.iter_child_nodes(tree):
                if child is node:
                    methods = []
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef):
                            methods.append({
                                "name": item.name,
                                "lineno": item.lineno,
                                "args": [{"name": a.arg, "type_annotation": None} for a in item.args.args],
                                "complexity": _py_complexity(item),
                            })
                    classes.append({"name": node.name, "lineno": node.lineno, "methods": methods})
                    break

        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append({
                        "module": alias.name,
                        "names": [alias.asname or alias.name.split(".")[0]],
                        "lineno": node.lineno,
                    })
                    _detect_py_dep(alias.name, external_deps)
            else:
                module = node.module or ""
                imports.append({
                    "module": module,
                    "names": [a.asname or a.name for a in node.names],
                    "lineno": node.lineno,
                })
                _detect_py_dep(module, external_deps)

        if isinstance(node, (ast.If, ast.For, ast.While, ast.Try, ast.With)):
            branches.append({"type": node.__class__.__name__.lower(), "lineno": node.lineno})
        if isinstance(node, ast.ExceptHandler):
            branches.append({"type": "except", "lineno": node.lineno})

    # Deduplicate branches
    seen = set()
    unique = []
    for b in branches:
        key = (b["type"], b["lineno"])
        if key not in seen:
            seen.add(key)
            type_map = {"if": "if", "for": "for", "while": "while", "try": "try", "with": "with", "excepthandler": "except"}
            b["type"] = type_map.get(b["type"], b["type"])
            unique.append(b)

    return functions, classes, imports, unique, list(set(external_deps))


def _py_complexity(func_node: ast.FunctionDef) -> int:
    c = 1
    for node in ast.walk(func_node):
        if isinstance(node, (ast.If, ast.For, ast.While, ast.ExceptHandler)):
            c += 1
        if isinstance(node, ast.BoolOp):
            c += len(node.values) - 1
    return c


def _detect_py_dep(module_name: str, deps: list) -> None:
    known = {
        "requests": "http", "httpx": "http", "urllib": "http", "aiohttp": "http",
        "sqlite3": "database", "sqlalchemy": "database", "psycopg2": "database",
        "pymongo": "database", "redis": "database",
        "open": "file_io", "pathlib": "file_io", "os": "file_io",
        "subprocess": "system", "smtplib": "email", "socket": "network", "ssl": "network",
    }
    base = module_name.split(".")[0]
    if base in known:
        deps.append(known[base])


# ─── Regex-based (non-Python) ────────────────────────────────────────────────


def _parse_with_regex(source: str, language: str) -> tuple[list, list]:
    funcs: list[dict] = []
    classes: list[dict] = []

    pattern = FUNC_PATTERNS.get(language)
    if not pattern:
        return funcs, classes

    for m in pattern.finditer(source):
        name = next((g for g in m.groups() if g), None)
        if not name:
            continue
        lineno = source[: m.start()].count("\n") + 1
        funcs.append({"name": name, "lineno": lineno, "args": [], "complexity": 1})

    # Detect class-like constructs
    class_patterns = {
        "java": re.compile(r"class\s+(\w+)", re.MULTILINE),
        "javascript": re.compile(r"class\s+(\w+)", re.MULTILINE),
        "typescript": re.compile(r"class\s+(\w+)", re.MULTILINE),
        "go": re.compile(r"type\s+(\w+)\s+struct", re.MULTILINE),
        "rust": re.compile(r"struct\s+(\w+)", re.MULTILINE),
        "ruby": re.compile(r"class\s+(\w+)", re.MULTILINE),
        "cpp": re.compile(r"class\s+(\w+)", re.MULTILINE),
    }
    cp = class_patterns.get(language)
    if cp:
        for m in cp.finditer(source):
            lineno = source[: m.start()].count("\n") + 1
            classes.append({"name": m.group(1), "lineno": lineno, "methods": []})

    return funcs, classes


def _detect_branches(lines: list[str]) -> list[dict]:
    result: list[dict] = []
    for i, line in enumerate(lines):
        if BRANCH_PATTERNS.match(line):
            result.append({"type": line.strip().split()[0].lower(), "lineno": i + 1})
    return result


def _detect_imports(source: str, language: str) -> list[dict]:
    patterns = {
        "java": re.compile(r"import\s+([\w.]+)", re.MULTILINE),
        "javascript": re.compile(r"(?:import\s+.*?from\s+['\"]([^'\"]+)['\"]|require\(['\"]([^'\"]+)['\"]\))", re.MULTILINE),
        "typescript": re.compile(r"(?:import\s+.*?from\s+['\"]([^'\"]+)['\"]|require\(['\"]([^'\"]+)['\"]\))", re.MULTILINE),
        "go": re.compile(r"\"([^\"]+)\"", re.MULTILINE),
        "rust": re.compile(r"use\s+([\w:]+)", re.MULTILINE),
    }
    pat = patterns.get(language)
    if not pat:
        return []
    result: list[dict] = []
    for m in pat.finditer(source):
        pkg = next((g for g in m.groups() if g), None)
        if pkg:
            result.append({"module": pkg, "names": [pkg.split(".")[-1]]})
    return result


def _detect_external_deps(source: str, language: str) -> list[str]:
    deps: list[str] = []
    patterns = {
        "java": [(re.compile(r"import\s+java\.(sql|net|http|io|nio)"), "system")],
        "javascript": [
            (re.compile(r"require\(['\"]fs['\"]\)|from\s+['\"]fs['\"]"), "file_io"),
            (re.compile(r"require\(['\"]http['\"]\)|from\s+['\"]http['\"]"), "http"),
            (re.compile(r"fetch\(|axios|got"), "http"),
        ],
        "typescript": [
            (re.compile(r"from\s+['\"]fs['\"]"), "file_io"),
            (re.compile(r"from\s+['\"]http['\"]"), "http"),
            (re.compile(r"fetch\(|axios|got"), "http"),
        ],
    }
    for pat, dep_type in patterns.get(language, []):
        if pat.search(source):
            deps.append(dep_type)
    return deps
