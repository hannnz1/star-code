from collections.abc import AsyncIterator
from typing import Protocol

from muse.contracts import ModelEvent, ToolDefinition


class ModelProvider(Protocol):
    def stream(self, messages: list[dict], tools: list[ToolDefinition]) -> AsyncIterator[ModelEvent]: ...
