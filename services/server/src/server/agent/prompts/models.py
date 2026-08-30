"""Model danych dla fallbackowego promptu systemowego kernela agenta Regis."""

from pydantic import BaseModel, Field


class AgentDefaultPromptConfig(BaseModel):
    """Zawartość pliku data/agent_default_prompt.json — jedyny, edytowalny fallback
    kernela, używany wyłącznie gdy żaden silnik świata nie dostarcza własnego promptu
    (patrz `agent/context_provider.py`, `ContextBuild.system_prompt`)."""

    content: str = Field(..., description="Treść fallbackowej instrukcji systemowej agenta")
