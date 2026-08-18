"""Silnik świata Regis — jedyne ramię agenta dotykające świata zewnętrznego.

Implementuje `server.agent.context_provider.WorldInterface` strukturalnie.
Wewnątrz: klient Home Assistant, rejestr satelit, narzędzia — zwykłe, wprost
wołane obiekty Pythona, bez protokołu między nimi (jeden, konkretny silnik,
nie generyczna kolekcja wymiennych rozszerzeń).
"""

from server.world.engine import WorldEngine

__all__ = ["WorldEngine"]
