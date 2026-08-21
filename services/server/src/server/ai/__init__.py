"""Konkretne backendy AI (LLM/STT/TTS) dla serwera Regis.

Sąsiad `agent/`/`voice/` — trzyma wyłącznie konkretne implementacje i logikę
wyboru dostawcy. Protokoły (`BaseLLMProvider`, `BaseSTTProvider`,
`BaseTTSProvider`) zostają we właściwych domenach (`agent.llm`, `voice.stt`,
`voice.tts`), dokładnie jak `WorldInterface` zostaje w `agent/` mimo że jedyna
konkretna implementacja (`WorldEngine`) mieszka w sąsiednim `world/`.
"""
