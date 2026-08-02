# Regis Project Handoff

## Ostatnia Sesja (Zrealizowano)
- **Refaktoryzacja LLM (Native Tools):** Całkowicie usunięto starsze, ręczne pętle ReAct oparte na ciągach znaków. Zmigrowano system (`OllamaBackend` i routing) do użycia natywnego Tool Callingu. Funkcje są teraz mapowane w warstwie backendowej i model otrzymuje precyzyjne schematy `tools`.
- **System Providerów Chmurowych (Cloud Providers):** Stworzono system dynamicznego zarządzania zewnętrznymi dostawcami LLM (np. OpenRouter) ze wsparciem dla dwóch trybów: `extended` (pełny tryb dedukcji) oraz `basic` (szybki NLU parser, ograniczony do narzędzi wykonawczych i czyszczenia sesji). Logika backendowa obsługiwana jest przez REST API, a rejestracja w pamięci działa w czasie rzeczywistym.
- **Ascetyczne UI (Architektura Sidebar):** Zlikwidowano dotychczasowy interfejs z kafelkami/dashboardem. Przepisano kod frontendowy na dwukolumnowy układ z lewym panelem nawigacyjnym (Sidebar) oraz dedykowanymi sekcjami. Znacząco spłaszczono design (`border-radius: 4px`, ciemne szarości, kolorowanie wyłącznie semantyczne), zastępując emotikony profesjonalnymi tagami konsolowymi (np. `[WORKER]`, `[EXT]`, `[CORE]`).

## Aktualny stan kodu
Frontend składa się z wysoce czytelnego kodu Grid w `index.html` z własnym mini-routingiem w `app.js`. Back-end dynamicznie zarządza stanami chmury i tool-callingiem.

## Kroki Startowe dla Nowego Agenta
1. Sprawdź pliki `docs/MANIFEST.md` oraz `docs/AGENT_GUIDE.md` aby zrozumieć filozofię projektu (surowość, determinizm, minimalizm UI/UX).
2. Wyświetl plik `d:\Projekty\Regis\src\controller\web\index.html`, by zapoznać się z nową konstrukcją zakładek (sekcje `.view-section`).
3. Spójrz do pliku `.agents/TASKS.md` w celu zidentyfikowania następnego modułu do implementacji (np. In-Process Fallback na nowej architekturze).
