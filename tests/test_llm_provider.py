"""Tests for LLM provider layer."""

import os
from unittest.mock import patch

import pytest

from src.llm.deepseek import DeepSeekProvider
from src.llm.claude import ClaudeProvider
from src.llm.factory import create_provider


class TestDeepSeekProvider:
    def test_init_with_explicit_api_key(self):
        provider = DeepSeekProvider(api_key="sk-test")
        assert provider._api_key == "sk-test"
        assert provider.model_name == "deepseek-v4-pro"

    def test_init_from_env(self):
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-env"}):
            provider = DeepSeekProvider()
            assert provider._api_key == "sk-env"

    def test_custom_base_url(self):
        provider = DeepSeekProvider(base_url="https://custom.api/v1")
        assert provider._base_url == "https://custom.api/v1"

    def test_get_model_returns_chat_model(self):
        provider = DeepSeekProvider(api_key="sk-test")
        model = provider.get_model()
        assert model is not None
        assert model.model_name == "deepseek-v4-pro"


class TestClaudeProvider:
    def test_init(self):
        provider = ClaudeProvider(api_key="sk-ant-test")
        assert provider._api_key == "sk-ant-test"
        assert provider.model_name == "claude-sonnet-4-6"


class TestFactory:
    def test_create_deepseek_default(self):
        config = {"model": {"provider": "deepseek", "name": "deepseek-v4-pro"}}
        provider = create_provider(config)
        assert isinstance(provider, DeepSeekProvider)
        assert provider.model_name == "deepseek-v4-pro"

    def test_create_claude(self):
        config = {
            "model": {"provider": "claude", "name": "claude-sonnet-4-6"},
            "claude": {"api_key": "sk-ant-test"},
        }
        provider = create_provider(config)
        assert isinstance(provider, ClaudeProvider)
        assert provider.model_name == "claude-sonnet-4-6"
