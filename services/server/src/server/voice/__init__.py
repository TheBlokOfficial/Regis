"""Pipeline głosowy satelit — WS gateway + wake-word/VAD-signaling + STT/TTS.

Rozłączny z `server.world` — zna wyłącznie opaque `sender_id`, nigdy nie czyta
configu World (pokój/przypisanie nadawcy). Jedyny punkt styku z kernelem to
publiczny kontrakt `AgentEngine` (`start_interaction()` + `EventBus`), dokładnie
tak jak korzysta z niego `network/routes/chat.py`. Patrz `docs/manifest.md`,
sekcja "server/voice/" dla pełnego opisu architektury i protokołu ramek WS.
"""
