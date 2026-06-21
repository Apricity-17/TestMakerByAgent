"""DeepSeek provider — OpenAI-compatible API with JSON fallback."""

import json
import os
import re
from typing import Any, Optional

from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI

from src.llm.provider import LLMProvider


def extract_json_from_content(content: str) -> dict[str, Any]:
    """Fallback: extract JSON from LLM text response."""
    # Try ```json block
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass
    # Try first { ... } pair
    m = re.search(r"\{[\s\S]*\}", content)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return {}


class DeepSeekProvider(LLMProvider):
    DEFAULT_BASE_URL = "https://api.deepseek.com/v1"

    def __init__(
        self,
        model_name: str = "deepseek-v4-pro",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ):
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._api_key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        self._base_url = base_url or os.environ.get(
            "DEEPSEEK_BASE_URL", self.DEFAULT_BASE_URL
        )
        self._client: Optional[ChatOpenAI] = None

    def _get_client(self) -> ChatOpenAI:
        if self._client is None:
            self._client = ChatOpenAI(
                model=self.model_name,
                api_key=self._api_key,
                base_url=self._base_url,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
        return self._client

    def get_model(self) -> ChatOpenAI:
        return self._get_client()

    def bind_tools(self, tools: list[BaseTool]) -> ChatOpenAI:
        return self._get_client().bind_tools(tools)

    def invoke(self, messages: list[BaseMessage]) -> BaseMessage:
        return self._get_client().invoke(messages)

    def invoke_with_tools(
        self, messages: list[BaseMessage], tools: list[BaseTool]
    ) -> BaseMessage:
        llm = self.bind_tools(tools)
        return llm.invoke(messages)
