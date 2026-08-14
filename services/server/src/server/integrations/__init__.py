"""Konkretne integracje (Warstwa 2) implementujące kontrakty zdefiniowane przez pluginy.

Zależność płynie w jedną stronę: integracja importuje kontrakt z pluginu, którego
dotyczy (np. `server.plugins.smart_home.contract.DeviceIntegration`) — plugin nigdy
nie importuje niczego z tego pakietu, ani nie zna nazw konkretnych integracji
na sztywno. Każda integracja rejestruje się jawnie w pluginie przy starcie
aplikacji (`main.py`), przez `plugin.register_integration_type(...)`.
"""

__all__: list[str] = []
