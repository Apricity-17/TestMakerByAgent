"""LLM provider factory."""

from src.llm.claude import ClaudeProvider
from src.llm.deepseek import DeepSeekProvider
from src.llm.provider import LLMProvider


def create_provider(config: dict) -> LLMProvider:
    """Create an LLMProvider from configuration dict."""
    model_cfg = config.get("model", {})
    provider_name = model_cfg.get("provider", "deepseek")

    if provider_name == "claude":
        claude_cfg = config.get("claude", {})
        return ClaudeProvider(
            model_name=model_cfg.get("name", claude_cfg.get("model", "claude-sonnet-4-6")),
            api_key=claude_cfg.get("api_key"),
            temperature=model_cfg.get("temperature", 0.3),
            max_tokens=model_cfg.get("max_tokens", 4096),
        )

    # Default: deepseek
    deepseek_cfg = config.get("deepseek", {})
    return DeepSeekProvider(
        model_name=model_cfg.get("name", "deepseek-v4-pro"),
        api_key=deepseek_cfg.get("api_key"),
        temperature=model_cfg.get("temperature", 0.3),
        max_tokens=model_cfg.get("max_tokens", 4096),
    )


__all__ = ["create_provider"]
