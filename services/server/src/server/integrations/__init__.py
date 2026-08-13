"""Konkretne integracje (Warstwa 2) implementujące kontrakty zdefiniowane przez addony.

Zależność płynie w jedną stronę: integracja importuje kontrakt z addonu, którego
dotyczy (np. `server.addons.smart_home.base.DeviceIntegration`) — addon nigdy
nie importuje niczego z tego pakietu, ani nie zna nazw konkretnych integracji
na sztywno. Każda integracja rejestruje się jawnie w addonie przy starcie
aplikacji (`main.py`), przez `addon.register_integration_type(...)`.
"""

__all__: list[str] = []
