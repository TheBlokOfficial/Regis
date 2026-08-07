# RFC: Inwalidacja Kontekstu LLM w Trakcie Przetwarzania

**Status:** Pomysł / Backlog  
**Data:** 2026-08-07  
**Autor:** Sesja projektowa

---

## Problem

Rozważmy następujący scenariusz:

1. Użytkownik mówi: *"Hej Regis, co mam dziś w kalendarzu?"*
2. Kontroler odbiera audio, wysyła do LLM-a, który zaczyna przetwarzać.
3. W trakcie przetwarzania (np. przez 2-4 sekundy) zachodzi **nowe zdarzenie zewnętrzne** — np. ktoś dzwoni do drzwi, czujnik ruchu wykrywa ruch, zmienia się status urządzenia HA.
4. LLM kończy generowanie odpowiedzi: *"Masz spotkanie o 15:00."*
5. System wysyła odpowiedź do Satelity, która ją odtwarza głosowo.

**Wynik:** odpowiedź jest **niekompletna lub przestarzała**. Informacja o dzwonku do drzwi została całkowicie pominięta, choć zaszła dosłownie sekundy temu i była istotna kontekstowo.

---

## Propozycja Rozwiązania

Przed wysłaniem wygenerowanej odpowiedzi do Satelity, Kontroler sprawdza:  
**"Czy od momentu odebrania zapytania użytkownika zaszły nowe, istotne zdarzenia?"**

Jeżeli tak:
1. **Wstrzymaj** gotową odpowiedź (odrzuć ją).
2. Dołącz nowe fakty do kontekstu konwersacji.
3. **Wyślij do LLM ponownie** z rozszerzonym kontekstem zawierającym nowe fakty.
4. LLM generuje odpowiedź uwzględniającą całą aktualną wiedzę.

### Przykład

```
Użytkownik: "Co mam dziś w kalendarzu?"
  LLM: [przetwarza...]
    → ZDARZENIE: dzwonek do drzwi (doorbell_rang)
  LLM: [gotowe] → "Masz spotkanie o 15:00."
  Kontroler: STOP. Nowe zdarzenie zaszło podczas przetwarzania.
  → porzuć odpowiedź
  → nowy kontekst: zapytanie + fakt "przed chwilą zadzwonił dzwonek"
  LLM: "Masz spotkanie o 15:00. Przy okazji, ktoś jest przy drzwiach."
```

---

## Kluczowe Pytania Projektowe

1. **Które zdarzenia są "wystarczająco istotne"** żeby inwalidować trwające przetwarzanie?
   - Dzwonek do drzwi, czujnik ruchu w pokoju użytkownika — prawdopodobnie TAK.
   - Zmiana pogody, aktualizacja oprogramowania — prawdopodobnie NIE.
   - Potrzebna lista priorytetów zdarzeń lub mechanizm tagowania (`interrupt: true/false`).

2. **Ile razy można przetwarzać ponownie?**
   - W dynamicznym środowisku nowe zdarzenia mogą napływać ciągle.
   - Potrzebny limit iteracji (np. max 2 re-przetworzone) lub timeout.

3. **Co z fragmentami już wygenerowanego tekstu?**
   - W trybie streamingu LLM zaczyna wysyłać tokeny na bieżąco.
   - Inwalidacja w połowie generowania wymaga mechanizmu przerwania strumienia (`abort`).

4. **Granularność zdarzeń:**
   - Zdarzenia zewnętrzne muszą być timestampowane i dostępne dla warstwy orkiestratora.
   - Orkiestrator potrzebuje dostępu do "bufora zdarzeń" z okna czasowego od momentu odebrania zapytania.

---

## Powiązane Komponenty

- `controller/` — warstwa decyzyjna, która musi implementować logikę sprawdzania bufora zdarzeń przed wysłaniem TTS.
- `controller/event_bus.py` — źródło zdarzeń zewnętrznych; potrzebuje timestampowania i możliwości odpytania "co zaszło od czasu T".
- LLM / Agent — musi obsługiwać ponowne wywołanie z rozszerzonym kontekstem.
- Satelita — pasywna, nieświadoma tej logiki. Czeka na sygnał końcowy od Kontrolera.

---

## Notatki

- Satelita jest w tym modelu **całkowicie pasywna** — jest w stanie `BUSY` i czeka. Cała logika inwalidacji i ponownego przetwarzania dzieje się wyłącznie po stronie Kontrolera/Agenta.
- Odpowiedź na zapytanie użytkownika powinna zawsze odzwierciedlać **aktualny stan świata**, nie stan z momentu złożenia zapytania.
