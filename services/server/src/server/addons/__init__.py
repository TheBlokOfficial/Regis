"""Addony — możliwości/domeny, którymi agent może się posłużyć (Warstwa 1).

Nic z tego pakietu nie jest importowane przez `server.agent` (kernel) —
addony rejestrują się w kernelu przez kontrakt `server.agent.addon_contract.AddonProvider`,
kernel nigdy nie zna ich konkretnej implementacji.
"""

from server.addons.base import BaseTool

__all__ = ["BaseTool"]
