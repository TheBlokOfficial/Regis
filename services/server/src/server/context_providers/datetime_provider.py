"""Dostawca kontekstu bieżącej daty i godziny.

Jedyny, trywialny dowód działania mechanizmu Dostawców kontekstu (wizja,
sekcja 2 i 3) — żadnej innej logiki, żadnego stanu.
"""

from datetime import datetime

from server.agent.context_provider_contract import Fact


class DateTimeContextProvider:
    """Zwraca fakt z aktualną datą i godziną serwera."""

    async def get_facts(self) -> list[Fact]:
        now = datetime.now()
        return [Fact(key="aktualna_data_i_godzina", value=now.strftime("%Y-%m-%d %H:%M:%S"))]
