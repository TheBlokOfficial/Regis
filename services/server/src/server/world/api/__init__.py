"""Warstwa REST silnika świata — ścieżki WZGLĘDNE, montowane pod `/api/v1/world`.

Wcześniej wszystkie 28 endpointów mieszkało w jednym `world/routes.py` (394 linie),
obsługującym osiem niezależnych rodzin zasobów naraz. Podział idzie po tym, czym
zasób JEST — po jednym pliku na rodzinę, każdy czytelny w całości bez przewijania:

```text
    home_assistant.py  konfiguracja połączenia + surowy katalog encji
    rooms.py           pokoje (byt World, niezależny od HA Areas)
    devices.py         zadeklarowane urządzenia (opt-in — to widzi agent)
    groups.py          nazwane zestawy urządzeń
    senders.py         rejestr klientów
    prompt_sections.py sekcje kontekstu tury (fakty ZMIENNE)
    prompts.py         profile tożsamości (treść STABILNA)
    mappers.py         byty domenowe -> DTO, wspólne dla powyższych
```

Ta warstwa jest **cienka z założenia**: przyjmuje żądanie, woła silnik, tłumaczy
wyjątek domenowy na kod odpowiedzi. Reguły w rodzaju „pominięte pole zachowuje
obecną wartość" należą do `WorldEngine`, nie tutaj — obowiązują każdego
wywołującego, nie tylko HTTP.
"""

from fastapi import APIRouter

from server.world.api import devices, groups, home_assistant, prompt_sections, prompts, rooms, senders
from server.world.engine import WorldEngine

# Kolejność montowania nie ma znaczenia dla routingu (ścieżki się nie nakładają),
# ale odzwierciedla drogę użytkownika: najpierw połączenie, potem to, co w nim żyje.
_MODULES = (home_assistant, rooms, devices, groups, senders, prompt_sections, prompts)


def create_world_router(engine: WorldEngine) -> APIRouter:
    """Składa komplet routerów Świata w jeden, montowany przez `network/gateway.py`."""
    router = APIRouter()
    for module in _MODULES:
        router.include_router(module.create_router(engine))
    return router
