#!/usr/bin/env python3
"""TestMaker CLI — 测试用例生成 Agent 入口."""

import argparse
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="testmaker",
        description="AI-powered test case generation agent",
    )
    parser.add_argument(
        "target_path",
        type=str,
        help="Source file or directory to analyze and generate tests for",
    )
    parser.add_argument(
        "--func",
        dest="target_functions",
        action="append",
        default=None,
        help="Specific function(s) to test (repeatable)",
    )
    parser.add_argument(
        "--coverage",
        dest="target_coverage",
        type=float,
        default=None,
        help="Target coverage ratio (0.0–1.0, default 0.90)",
    )
    parser.add_argument(
        "--max-iter",
        dest="max_iterations",
        type=int,
        default=None,
        help="Maximum iteration rounds (default 5)",
    )
    parser.add_argument(
        "--model",
        dest="model",
        type=str,
        default=None,
        choices=["deepseek", "claude"],
        help="LLM provider to use (overrides config)",
    )
    parser.add_argument(
        "--output-dir",
        dest="test_dir",
        type=str,
        default=None,
        help="Directory to write test files (default: tests/)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=False,
        help="Enable verbose logging output",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Analyze and plan only, do not generate tests",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        default=False,
        help="Enter interactive conversation mode after analysis",
    )
    parser.add_argument(
        "--lang",
        dest="language",
        type=str,
        default="zh",
        choices=["zh", "en"],
        help="Output language: zh (Chinese, default) or en (English)",
    )
    return parser


def validate_args(args: argparse.Namespace) -> None:
    target = Path(args.target_path)
    if not target.exists():
        print(f"Error: '{args.target_path}' does not exist.", file=sys.stderr)
        sys.exit(1)

    if args.target_coverage is not None and not (0.0 <= args.target_coverage <= 1.0):
        print("Error: --coverage must be between 0.0 and 1.0", file=sys.stderr)
        sys.exit(1)

    if args.max_iterations is not None and args.max_iterations < 1:
        print("Error: --max-iter must be >= 1", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    validate_args(args)

    console = Console()

    console.print(
        Panel.fit(
            f"[bold]TestMaker[/bold] — 测试用例生成 Agent\n"
            f"目标: {args.target_path}",
            border_style="blue",
        )
    )

    # Import and run the agent
    from src.agent import run, run_interactive

    if args.dry_run:
        console.print("[yellow]Dry-run mode: analyze only, no tests generated.[/]")
        console.print(f"[dim]Target: {args.target_path}")
        console.print(f"[dim]Mode: {'interactive' if args.interactive else 'auto'}[/]")
        return

    if args.interactive:
        console.print("[bold green]Entering interactive mode...[/]")
        result = run_interactive(
            target_path=args.target_path,
            target_functions=args.target_functions,
            test_dir=args.test_dir or "tests",
            model_override=args.model,
            language=args.language,
        )
    else:
        result = run(
            target_path=args.target_path,
            target_functions=args.target_functions,
            target_coverage=args.target_coverage or 0.90,
            max_iterations=args.max_iterations or 5,
            test_dir=args.test_dir or "tests",
            model_override=args.model,
            language=args.language,
        )

    if result.get("error_message"):
        console.print(f"\n[red]Error: {result['error_message']}[/]")
        sys.exit(1)

    final_report = result.get("final_report", "No report generated.")
    console.print(Panel.fit(final_report, title="Final Report", border_style="green"))


if __name__ == "__main__":
    main()
