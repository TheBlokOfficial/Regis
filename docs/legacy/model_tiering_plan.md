# Plan Wdrożenia: Architektura "Model Tiering" (Podział Klas Modeli)

Zbudowanie w Regis wbudowanego **Frameworka Kategoryzacji Modeli**. Oszczędzi to mniejszym modelom tzw. *cognitive overload* (kiedy widzą zbyt dużo narzędzi i z tego powodu "głupieją"), a jednocześnie odblokuje pełny potencjał gigantów.

## Zarys Architektury

### 1. Detekcja Klasy Modelu (Tiering)
Dodamy nową koncepcję "Klasy Modelu" (`butler` vs `regis`).
System będzie klasyfikował model podczas uruchamiania pętli (np. w `llm_engine.py` lub `config.py`):
- Automatycznie na podstawie nazwy (jeśli zawiera `7b`, `8b` -> `butler`; jeśli `70b`, `gpt`, `claude` -> `regis`).
- (Opcjonalnie) nadpisywane w `settings.json`, jeśli użytkownik chce wymusić klasę.

### 2. Rozwidlenie Narzędzi (Tool Scoping) w `tools_registry.py`
Narzędzia zostaną opatrzone atrybutem wymaganego poziomu, np. `required_tier: "regis"`.
Gdy pętla ładuje `tools_registry`, filtruje dostępne schematy narzędzi:
- **Mały model (Basic)**: Otrzymuje tylko podstawowe operacje (np. odczyt urządzeń, proste przełączanie).
- **Duży model (Advanced)**: Otrzymuje dostęp do wszystkich powyższych + narzędzi zaawansowanych (gdy takowe dodamy w przyszłości, np. "Uruchom Skrypt HA", "Analiza Logów HA", "Sprawdź pogodę i ustal harmonogram").

### 3. Rozwidlenie Persony i Zasad (Dynamic Prompts) w `llm_engine.py`
Przygotujemy dwa stałe prompty:
- **`SYSTEM_PROMPT_BASIC`**: Zawiera sztywniejsze wytyczne (zapobiegające halucynacjom) oraz jawną informację: *"Działasz w trybie ograniczonym (Basic). Jeśli użytkownik prosi o zaawansowaną analizę, poinformuj go, że Twoja wersja modelu jest na to za słaba."*
- **`SYSTEM_PROMPT_ADVANCED`**: Czysty, wyrafinowany prompt z ogromną swobodą decyzyjną, zachęcający do proaktywnego zarządzania domem.

## Wymagane Zmiany w Kodzie

#### [MODIFY] `core/llm_engine.py`
- Rozdzielenie `SYSTEM_PROMPT` na słownik promptów uzależnionych od parametru `tier`.
- Prosta logika detekcji klasy po nazwie (np. `self.tier = self._detect_tier(model_name)`).
- Przekazanie `self.tier` do inicjalizacji `tools_registry`.

#### [MODIFY] `core/tools_registry.py`
- Dodanie do schematów narzędzi pola "required_tier" (zignorowanego przez Ollamę, ucinanego podczas wysyłania do modelu, używanego tylko do wewnętrznego filtrowania w Pythonie).
- Metoda włączająca odrzucanie narzędzi, do których model nie ma dostępu.
