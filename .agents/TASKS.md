# Lista Zadań Projektu Regis (TASKS)

## Rejestr Zrealizowanych Zadań (Sesja 2026-08-05)

- [x] **Spłaszczenie i Uporządkowanie Architektury Satelity (`satellite/`)**:
  - Usunięto katalog `core/` i scalono logikę orkiestratora w `satellite/__main__.py`.
  - Wyeliminowano pętlę pollingu `while True` na rzecz modelu reaktywnego sterowanego zadaniami.
- [x] **Dedykowana i Zunifikowana Maszyna Stanów (`SatelliteState`)**:
  - Wprowadzono stany: `INITIALIZING`, `WAITING`, `WAKEWORD`, `LISTENING`, `PROCESSING`, `SPEAKING`.
  - Zapewniono symetryczną weryfikację flagi `self._paused` na granicach faz bez kodowania wyjątków.
- [x] **Uniwersalny Pakiet Sterowania Usługami (`service_control`)**:
  - Wdrożono komendę `SERVICE_CONTROL` w `ServiceCommand` z akcjami `RESUME` oraz `PAUSE`.
  - Wyeliminowano niskopoziomowe komendy OS (`START`, `STOP`, `RESTART`) z sieciowego interfejsu Kontrolera w celu zachowania autonomii Klienta.
- [x] **Silnie Typowane Schematy Konfiguracji Usług (`NodeServicesConfig`)**:
  - Utworzono modele Pydantic `SatelliteConfig`, `AudioConfig`, `LLMConfig` oraz `NodeServicesConfig` w `schemas.py`.
- [x] **Stabilizacja Auto-Discovery i Naprawa Modułów**:
  - Wdrożono czyszczenie bufora URL Auto-Discovery (`reset_discovered_controller_url`).
  - Naprawiono usterki składniowe i brakujące importy w `controller_api.py`, `satellite/__main__.py`, `llm/__main__.py`, `audio/__main__.py`.

---

## Zadania Przyszłe / Propozycje

- [ ] **Unifikacja Usług `audio` i `llm`**:
  - Spłaszczenie struktur i unifikacja orkiestratorów w `audio` oraz `llm` na wzór zrealizowanego modułu `satellite`.
- [ ] **Dalsze Testy Integracyjne End-to-End**:
  - Przetestowanie pełnego potoku mowy w środowisku z działającym Kontrolerem i Home Assistant.
