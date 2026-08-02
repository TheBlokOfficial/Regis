# Regis Project Handoff

## Ostatnia Sesja (Zrealizowano)
- **Layout UI & Ergonomia Szerokości (Pulpit vs Czat/Logi):** Zaimplementowano dynamiczny układ interfejsu. Widoki tekstowe (*Czat & Konwersacje* oraz *Dziennik Zdarzeń*) zachowują ergonomiczne centrowanie do 1000px (`calc((100% - 1000px) / 2)`), zapobiegając bieganiu wzrokiem od krawędzi do krawędzi na panoramicznych monitorach 16:9. *Pulpit Systemu* korzysta z 10% bocznego marginesu i siatki 3 bezwzględnie równych kolumn (`repeat(3, minmax(0, 1fr))`), w których rozmieszczono odpowiednio: **Węzły Lokalne**, **Dostawców Zewnętrznych (LLM)** oraz **Integracje**.
- **Kompaktowe Kafelki i Stałe Wysokości:** Górne kafelki statusowe zostały zwężone i wycentrowane pośrodku ekranu (`justify-content: center`). Dolne panele zasobów otrzymały ujednoliconą wysokość (380px) z wewnętrznym scrollowaniem pionowym (`overflow-y: auto`). Wprowadzono klasę `.list-info` zapobiegającą łamaniu wierszy i obcinającą zbyt długie nazwy modeli/dostawców przy użyciu wielokropka (`ellipsis`).
- **Czysty Dziennik Zdarzeń (Filtrowanie & Ustandaryzowany Format):** Usunięto szum informacyjny z mikro-zdarzeń pod-usług (worker/satelita) oraz wyeliminowano powtórne odtwarzanie historii przy odświeżaniu SSE (`is_history`). Wdrożono nowy, profesjonalny format wpisów przypominający logi systemowe: `[CZAS]  [INFO / OFFLINE / ERROR]  Treść komunikatu`.
- **Oczyszczenie Kart Węzłów:** Usunięto rozbijający wiersze wskaźnik VAD z kafelków na rzecz czystych, minimalistycznych badge'y (np. `SAT (pracownia_glowna)`). Wyczyszczono przestarzały fallback portu `:8099` (Zjednoczony Węzeł łączy się wychodząco po WebSocket, prezentowany jest czysty adres IP).
- **Naprawa Testów Jednostkowych:** Zaktualizowano sygnatury w `tests/test_llm_backends.py` dopasowane do nowej architektury `OpenRouterBackend` (100% przechodzących testów pytest).

## Aktualny stan kodu
Frontend (`src/controller/web/`) jest w pełni reaktywny, zoptymalizowany pod kątem proporcji na monitorach 16:9 i wolny od szumów informacyjnych. Backend (`src/controller/`) sprawnie obsługuje separację Zjednoczonych Węzłów od Dostawców Chmurowych oraz strumieniowanie SSE i Tool Calling.

## Kroki Startowe dla Nowego Agenta
1. Zapoznaj się z dokumentami `docs/MANIFEST.md` i `docs/AGENT_GUIDE.md` (priorytety: czystość kodu, determinizm, brak niepotrzebnego szumu wizualnego).
2. Otwórz `d:\Projekty\Regis\src\controller\web\index.html` oraz `style.css` i przejrzyj wyczyszczoną siatkę `dashboard-grid` oraz 3-zakładkowy układ Sidebara.
3. Uruchom testy jednostkowe `pytest` w głównym katalogu, aby upewnić się, że całe środowisko jest stabilne.
4. Przejdź do pliku `.agents/TASKS.md` w celu podjęcia kolejnego zadania z listy (np. dociągnięcie abstrakcji STT/TTS lub przygotowanie instalatora Windows).
