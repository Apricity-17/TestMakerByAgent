"""Claude provider — Anthropic API (reserved for future use)."""

import os
from typing import Optional, TYPE_CHECKING

from langchain_core.messages import BaseMessage
from langchain_core.tools import BaseTool

from src.llm.provider import LLMProvider

if TYPE_CHECKING:
    from langchain_anthropic import ChatAnthropic


class ClaudeProvider(LLMProvider):
    def __init__(
        self,
        model_name: str = "claude-sonnet-4-6",
        api_key: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ):
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._client = None

    def _get_client(self) -> "ChatAnthropic":
        if self._client is None:
            from langchain_anthropic import ChatAnthropic

            self._client = ChatAnthropic(
                model=self.model_name,
                api_key=self._api_key,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
        return self._client

    def get_model(self) -> "ChatAnthropic":
        return self._get_client()

    def bind_tools(self, tools: list[BaseTool]) -> "ChatAnthropic":
        return self._get_client().bind_tools(tools)

    def invoke(self, messages: list[BaseMessage]) -> BaseMessage:
        return self._get_client().invoke(messages)

    def invoke_with_tools(
        self, messages: list[BaseMessage], tools: list[BaseTool]
    ) -> BaseMessage:
        llm = self.bind_tools(tools)
        return llm.invoke(messages)
