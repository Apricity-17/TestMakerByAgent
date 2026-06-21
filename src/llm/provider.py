"""LLM Provider abstract base class."""

from abc import ABC, abstractmethod

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.tools import BaseTool


class LLMProvider(ABC):
    """Abstract LLM provider. DeepSeek and Claude each implement this."""

    model_name: str
    temperature: float
    max_tokens: int

    @abstractmethod
    def get_model(self) -> BaseChatModel:
        """Return a LangChain-compatible chat model bound with tools."""
        ...

    @abstractmethod
    def bind_tools(self, tools: list[BaseTool]) -> BaseChatModel:
        """Bind tools to the model and return it."""
        ...

    @abstractmethod
    def invoke(self, messages: list[BaseMessage]) -> BaseMessage:
        """Invoke the LLM (without tools) and return the response message."""
        ...

    @abstractmethod
    def invoke_with_tools(
        self, messages: list[BaseMessage], tools: list[BaseTool]
    ) -> BaseMessage:
        """Invoke the LLM with tools bound, returning a message with possible tool_calls."""
        ...
