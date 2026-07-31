from abc import ABC, abstractmethod
from typing import Any

class LLMBackend(ABC):
    @abstractmethod
    def generate_response(
        self,
        messages: list[dict],
        tools_registry: Any,
        tier: str,
        on_tool_call: Any = None,
        on_thought_token: Any = None,
        on_content_token: Any = None,
        on_raw_tool_call: Any = None,
        on_profiler: Any = None
    ) -> str:
        """Generates response from the LLM model."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Checks if the provider is currently available."""
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """Returns the name of the provider."""
        pass
