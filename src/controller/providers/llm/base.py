from abc import ABC, abstractmethod
from typing import Any, Generator


class LLMBackend(ABC):
    @abstractmethod
    def chat_stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None
    ) -> Generator[dict, None, None]:
        """
        Wykonuje pojedyncze zapytanie strumieniowe do dostawcy LLM.

        Generuje zdarzenia w postaci słowników, np.:
        - {"type": "content", "content": token}
        - {"type": "tool_calls", "tool_calls": [...]}
        - {"type": "profiler", "metric": "llm_ttft", "value": ms}
        """
        pass

    def generate_response(
        self,
        messages: list[dict],
        tools_registry: Any = None,
        **kwargs
    ) -> str:
        """
        Fasada zachowująca wsteczną kompatybilność sygnatury `generate_response()`.
        Deleguje wykonanie do uniwersalnego Silnika Agenta (agent/engine.py).
        """
        import asyncio
        from controller.agent.engine import run_agent_loop

        q = kwargs.get("q") or asyncio.Queue()
        try:
            loop = kwargs.get("loop") or asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.get_event_loop()

        user_message = ""
        if messages and isinstance(messages[-1], dict) and messages[-1].get("role") == "user":
            user_message = messages[-1].get("content", "")

        return asyncio.run(run_agent_loop(
            stream_provider=self,
            session_history=messages,
            user_message=user_message,
            satellite_id=kwargs.get("satellite_id", "default"),
            room=kwargs.get("room"),
            worker_id=self.get_provider_name(),
            model_name=getattr(self, "model_name", "unknown"),
            q=q,
            loop=loop,
            tools_registry=tools_registry,
        ))

    @abstractmethod
    def is_available(self) -> bool:
        """Checks if the provider is currently available."""
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """Returns the name of the provider."""
        pass
