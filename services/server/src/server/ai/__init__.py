"""Konkretne backendy AI (LLM/STT/TTS/wake-word) dla serwera Regis.

Trzyma wyłącznie konkretne implementacje i logikę wyboru dostawcy. Kontrakty,
które te klasy spełniają, mieszkają w `server.ports` — dzięki temu ani kernel
(`server.agent`), ani pipeline głosowy (`server.voice`) nie muszą importować
tej warstwy, a ona nie musi importować ich (patrz `ports/__init__.py`,
sekcja o zerwanych cyklach).

Wyjątkiem, celowo, jest `WorldInterface`: zostaje w `agent/context_provider.py`,
bo implementuje go `server.world`, a `world -> agent` jest jednokierunkowe —
żaden cykl tam nie powstał, więc nie ma czego naprawiać.
"""
