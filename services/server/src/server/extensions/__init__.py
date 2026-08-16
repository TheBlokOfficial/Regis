"""Rozszerzenia — Warstwa 1: domeny możliwości agenta.

Każde rozszerzenie samo dostarcza i obsługuje swój wkład dla Gateway
(`PluginProvider`) i opcjonalnie własną obecność sieciową (`NetworkExtension`,
`server.network.extension_contract`). Kernel nigdy nie importuje niczego z
tego pakietu — rozszerzenia rejestrują się jawnie w kompozycji aplikacji
(`main.py`).
"""
