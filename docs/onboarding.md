# Onboarding Dewelopera

Instrukcja szybkiego uruchomienia środowiska programistycznego.

## 1. Wymagania wstępne
- Python >= 3.11
- Menedżer `uv` (`pip install uv`)

## 2. Inicjalizacja środowiska
```bash
# Instalacja wszystkich zależności i powiązanie workspace
python -m uv sync
```

## 3. Uruchomienie serwera dev
```bash
python -m uv run uvicorn server.main:app --reload
```

## 4. Test połączenia
- **HTTP**: `http://127.0.0.1:8000/`
- **WebSocket**: `ws://127.0.0.1:8000/ws`
