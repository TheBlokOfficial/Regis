# Lista Zadań Projektu Regis (TASKS)

## Rejestr Zrealizowanych Zadań (Sesja 2026-08-04 / 2026-08-05)

- [x] **Dekompozycja Monolitu Workera na Usługi `audio` i `llm`**:
  - Wydzielono 3 kanoniczne usługi: `satellite`, `audio` (STT Whisper + TTS Piper), `llm` (Qwen ReAct).
- [x] **Modułowy Podział SRP Usług**:
  - Podzielono `llm` i `audio` na czytelny układ plików (`service.py`, `registration.py`, `streaming.py`, `routes.py`, `app.py`, `__main__.py`).
  - Usunięto przestarzałe parsowanie CLI `get_args` / `argparse`.
- [x] **Bezportowa Architektura Sidecar Worker Pattern**:
  - Usunięto stawianie serwerów Uvicorn na portach 8001/8002/8003.
  - Usługi podrzędne subskrybują komendy z bramki Aplikacji Klienckiej (`internal_proxy.py` - port `47831`).
- [x] **Orkiestracja w Kontrolerze**:
  - Zaktualizowano `registry.py` (`get_audio_nodes()`, `get_llm_nodes()`, `get_satellite_nodes()`) oraz kaskadowy potok przetwarzania głosu w `chat_service.py`.

---

## Zadania Przyszłe / Propozycje

- [ ] **Dalsze Testy Integracyjne End-to-End**:
  - Przetestowanie pełnego potoku mowy w fizycznym środowisku z działającym Kontrolerem i Home Assistant.
