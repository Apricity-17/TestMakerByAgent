"""Configuration loader: YAML + .env + environment variable overrides."""

import os
from pathlib import Path
from typing import Optional, Union

import yaml


def _try_load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).parent / ".env")
    except ImportError:
        # python-dotenv not installed — use manual .env parsing
        env_path = Path(__file__).parent / ".env"
        if env_path.exists():
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, _, val = line.partition("=")
                        if key.strip() not in os.environ:
                            os.environ[key.strip()] = val.strip().strip("\"'")


DEFAULT_CONFIG_PATH = Path(__file__).parent / "config.yaml"


def load_config(config_path: Union[str, Path, None] = None) -> dict:
    _try_load_dotenv()

    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH

    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path) as f:
        config = yaml.safe_load(f) or {}

    # --- Environment variable overrides ---
    _override_model(config)
    _override_api_keys(config)
    _override_agent(config)

    return config


def _override_model(config: dict) -> None:
    model = config.setdefault("model", {})
    if os.environ.get("TESTMAKER_MODEL"):
        model["name"] = os.environ["TESTMAKER_MODEL"]
    if os.environ.get("TESTMAKER_PROVIDER"):
        model["provider"] = os.environ["TESTMAKER_PROVIDER"]
    # Expand ~ in long_term_path and log file
    for section in ("memory", "logging"):
        if section in config:
            for key in ("long_term_path", "file"):
                if key in config[section] and config[section][key].startswith("~"):
                    config[section][key] = os.path.expanduser(config[section][key])


def _override_api_keys(config: dict) -> None:
    if os.environ.get("DEEPSEEK_API_KEY"):
        config.setdefault("deepseek", {})["api_key"] = os.environ["DEEPSEEK_API_KEY"]
    if os.environ.get("ANTHROPIC_API_KEY"):
        config.setdefault("claude", {})["api_key"] = os.environ["ANTHROPIC_API_KEY"]


def _override_agent(config: dict) -> None:
    agent = config.setdefault("agent", {})
    if os.environ.get("TESTMAKER_MAX_ITER"):
        agent["max_iterations"] = int(os.environ["TESTMAKER_MAX_ITER"])
    if os.environ.get("TESTMAKER_COVERAGE_TARGET"):
        agent["target_coverage"] = float(os.environ["TESTMAKER_COVERAGE_TARGET"])
