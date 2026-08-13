"""Wewnętrzne modele danych dla systemu przechowywania promptów systemowych Agenta Regis OS."""

from pydantic import BaseModel, Field


class PromptFileContent(BaseModel):
    """Zawartość pojedynczego pliku JSON w data/prompts/<id>.json."""

    name: str = Field(..., description="Wyświetlana nazwa promptu")
    content: str = Field(..., description="Treść instrukcji systemowej (system prompt)")
    description: str | None = Field(default=None, description="Opcjonalny opis przeznaczenia promptu")


class PromptInstanceConfig(PromptFileContent):
    """Pełna konfiguracja instancji promptu z ID, używana wewnętrznie."""

    id: str = Field(..., description="Unikalny identyfikator promptu (np. prompt_default)")


class ActivePromptConfig(BaseModel):
    """Konfiguracja wskazująca aktywny prompt — przechowywana w data/active_prompt.json."""

    active_id: str = Field(..., description="ID aktualnie aktywnego promptu systemowego")
