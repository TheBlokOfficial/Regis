# Regis

Projekt Regis to centralny serwer prywatnego asystenta głosowego (LLM-based) służący do sterowania infrastrukturą Home Assistant. Projekt jest zamknięty, przeznaczony na użytek prywatny i zaprojektowany pod kątem działania w odizolowanym środowisku LAN. Nie jest to oprogramowanie typu Open Source.

## Topologia sprzętowa

1. Środowisko deweloperskie (Dev): Windows / Linux (Testowano na RTX 5070).
2. Środowisko produkcyjne (Prod): Raspberry Pi 5 (8GB RAM, Dysk 1TB NVMe 970 EVO).
3. Urządzenia peryferyjne (Satelity): Moduły ESP32 z oprogramowaniem WakeWord.
4. Serwer Home Assistant: Zewnętrzne Raspberry Pi (4GB RAM) z zainstalowanym Dockerem.

## Architektura i działanie

System korzysta z założeń architektury Monorepo. Główny rdzeń logiki (komunikacja z Ollamą, promptowanie, narzędzia) znajduje się w katalogu `core/`, a zewnetrzne integracje w `integrations/`. 
Rzeczywiste programy uruchamiane przez użytkownika (punkty wejściowe) zostały rozdzielone na odrębne aplikacje w katalogu `apps/`:
- `server`: demon REST API dla Maliny
- `terminal`: okienkowy interfejs CLI
- `satellite`: usługa audio
- `boss_node`: węzeł odciążający na GPU

## Uruchamianie

System składa się z wielu aplikacji, dlatego zawsze uruchamiamy je z poziomu głównego katalogu (root), podając ścieżkę do modułu:
```bash
python -m apps.terminal.main  # Uruchamia klienta terminalowego
python -m apps.server.main    # Uruchamia serwer API (FastAPI)
```
Dla wygody na Windowsie przygotowano gotowe pliki `.bat` (np. `run_terminal.bat`).

## Testowanie (Środowisko Deweloperskie)

Aby zweryfikować poprawność kodu po wprowadzonych zmianach, uruchom:
```bash
pytest
```

## Dostępne komendy CLI

Podczas działania aplikacji (w oknie czatu) możesz użyć następujących komend:
- `/help` - wyświetla listę dostępnych komend
- `/exit` - wyjście z trybu produkcyjnego
- `/clear` - czyszczenie pamięci podręcznej rozmowy z asystentem
- `/tier` - przełącza między wbudowanymi warstwami: Recepcjonista (Lokalny) oraz Szef (Główny Gospodarz)
