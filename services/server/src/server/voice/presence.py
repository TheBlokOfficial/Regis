"""Kto jest teraz podłączony i co robi — mechaniczny fakt o żywych połączeniach WS.

Dotąd były to **trzy gołe kolekcje tworzone w `main.py`** (`connected_sender_ids`,
`sender_states`, `pending_capabilities`), przekazywane przez sygnatury dwóch fabryk
routerów i konstruktor połączenia. Nic nie wiązało ich ze sobą poza dyscypliną autora:
przy rozłączeniu trzeba było pamiętać o sprzątnięciu wszystkich trzech, w trzech
osobnych linijkach, w bloku `finally`. To wzorzec, w którym pierwszy zapomniany wpis
zostaje w pamięci na zawsze i objawia się jako klient „podłączony", którego nie ma.

**Zero wiedzy o rejestracji, pokoju czy tożsamości** — to należy do `World`
(`docs/manifest.md`, sekcja 5). Tutaj mieszka wyłącznie to, co gateway widzi na oczy.

Zwykłe słowniki bez locka: jeden wątek asyncio, mutacje są atomowe.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ClientPresenceRegistry:
    """Rejestr żywych połączeń satelit — współdzielony przez gateway WS i routery REST.

    Trzy pytania, jedna odpowiedź na każde:

    * **kto jest podłączony** — panel „Nadawcy" pokazuje dzięki temu satelity
      podłączone, ale jeszcze niezatwierdzone;
    * **w jakim jest stanie** (`SessionState.name`) — snapshot do hydratacji dashboardu
      „Klienci" przy pierwszym załadowaniu strony; dalsze zmiany idą już SSE;
    * **co zadeklarowała w handshake** — Web UI czyta to przy rejestracji, żeby zapisać
      w World prawdziwe możliwości klienta zamiast zgadywać jego typ.
    """

    states: dict[str, str] = field(default_factory=dict)
    capabilities: dict[str, list[str]] = field(default_factory=dict)
    _connected: set[str] = field(default_factory=set)

    def connect(self, sender_id: str) -> None:
        self._connected.add(sender_id)

    def disconnect(self, sender_id: str) -> None:
        """Jedno wywołanie sprząta **cały** ślad po kliencie — powód istnienia tej klasy."""
        self._connected.discard(sender_id)
        self.states.pop(sender_id, None)
        self.capabilities.pop(sender_id, None)

    def is_connected(self, sender_id: str) -> bool:
        return sender_id in self._connected

    def connected_ids(self) -> set[str]:
        """Kopia — wywołujący nie ma jak przypadkiem zmutować rejestru."""
        return set(self._connected)

    def set_state(self, sender_id: str, state: str) -> None:
        self.states[sender_id] = state

    def declare_capabilities(self, sender_id: str, capabilities: list[str]) -> None:
        self.capabilities[sender_id] = capabilities

    def capabilities_of(self, sender_id: str) -> list[str]:
        return self.capabilities.get(sender_id, [])
