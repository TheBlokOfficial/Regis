from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator

class LLMBackend(ABC):
    @abstractmethod
    async def generate_stream(
        self,
        messages: list[dict],
        tools_registry: Any
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Asynchroniczny generator zwracający eventy ze strumienia LLM.
        
        Zwracane eventy mają format: {"type": "<typ>", "content": "<zawartość>"}
        Dozwolone typy: "thought", "content", "tool_call_raw", "tool_dict", "profiler", "error".
        """
        pass
        # Musi zawierać yield, by mypy wiedział, że to generator
        yield {"type": "dummy", "content": ""}

    @abstractmethod
    def is_available(self) -> bool:
        """Checks if the provider is currently available."""
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """Returns the name of the provider."""
        pass
