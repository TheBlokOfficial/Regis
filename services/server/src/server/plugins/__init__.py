"""Pluginy — domeny możliwości, którymi agent może się posłużyć (Warstwa 1).

Nic z tego pakietu nie jest importowane przez `server.agent` (kernel) —
pluginy rejestrują się w Gateway przez kontrakt
`server.agent.plugin_contract.PluginProvider`, kernel/Gateway nigdy nie zna
ich konkretnej implementacji.
"""
