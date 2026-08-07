# RFC: Dwuwarstwowa Architektura Sub-Agentów i Ekspertów Domenowych

**Status:** Koncepcja Architektoniczna / RFC  
**Data:** 2026-08-07  
**Autor:** Sesja Projektowa Regis  

---

## 1. Problem i Motywacja

Lokalne modele językowe o mniejszej liczbie parametrów (np. `qwen2.5:1.5b` lub `qwen3.5:3b` uruchamiane na Raspberry Pi lub zasobach lokalnych) posiadają ograniczone okno uwagi oraz spadającą sprawność dedukcyjną przy zbyt dużych promptach wejściowych (*Prompt Bloat*).

Próba stworzenia jednego "monolitycznego" Agenta, który jednocześnie pamięta i obsługuje:
- Wszystkie urządzenia domowe (światła, rolety, ogrzewanie),
- Pielęgnację ogrodu, harmonogramy nawadniania i odczyty gleby,
- Analitykę finansową, monitoring bezpieczeństwa i logi systemowe,

prowadzi do:
1. Wydłużenia czasu reakcji (*Latency*).
2. Wyższego ryzyka halucynacji wywołań narzędzi (*Tool Calling Errors*).
3. Pożerania cennego kontekstu na informacje nieistotne dla danej interakcji.

---

## 2. Propozycja Rozwiązania: Dwuwarstwowy Model Sub-Agentów (MoA)

Zamiast przeciążać jednego Agenta, system Regis przyjmuje architekturę **Mixture of Specialist Sub-Agents (MoA)**.

System dzieli odpowiedzialność na:
- **Nadrzędnego Agenta Konwersacyjnego ("Recepcjonistę / Lokaja")** – nastawionego na natychmiastową interakcję z domownikiem (światła, proste pytania, audio STT/TTS).
- **Wyspecjalizowanych Sub-Agentów Tła ("Ekspertów")** – np. *Agent Ogrodnik*, *Agent Ochroniarz*, *Agent Analityk*.

---

## 3. Dwuwarstwowa Budowa Promptu (Two-Tier Prompt Pattern)

Każdy Sub-Agent operuje na **dwuwarstwowym prompcie systemowym**, składanym dynamicznie przez fabrykę promptów (`PromptBuilder`):

1. **Warstwa Nadrzędna (`Core Identity Manifest`):**  
   Niezmienna podstawa tożsamości. Daje Sub-Agentowi świadomość, że jest częścią nadrzędnego systemu Regis:  
   > *"Jesteś częścią nadrzędnego systemu Regis. Działasz jako wysoce wyspecjalizowana podinstancja autonomiczna."*

2. **Warstwa Specjalistyczna (`Specialist Domain Mask`):**  
   Dedykowane zasady i rola (np. `prompts/roles/garden_expert.md`):  
   > *"Twoim wyłącznym zadaniem jest opieka nad ogrodem, analizowanie poziomu nawodnienia gleby oraz optymalizacja zużycia wody."*

3. **Wywężona Przestrzeń Akcji (`Scoped Tool Space`):**  
   Sub-Agent widzi **wyłącznie** narzędzia i urządzenia przypisane do swojej domeny. Agent Ogrodnik nie widzi świateł w sypialni ani zamków w drzwiach – posiada w swoim schemacie tylko komendy dotyczące ogrodu i pogody.

---

## 4. Tryby Pracy Sub-Agentów

Sub-Agenci mogą działać w dwóch trybach:

1. **Tryb Autonomiczny / Harmonogramowy (Background Cron / Event Worker):**  
   Sub-Agent wywoływany jest cyklicznie przez system (np. co godzinę) lub po wystąpieniu zdarzenia na `EventBus` (np. wykrycie deszczu).  
   *Przepływ:* Budzenie $\rightarrow$ Pobranie czujników $\rightarrow$ Pętla ReAct $\rightarrow$ Zapisnotatki/Raportu $\rightarrow$ Uśpienie.
2. **Tryb Oddelegowania (Handoff / Task Delegation):**  
   Główny Agent Konwersacyjny podczas rozmowy z człowiekiem wykrywa skomplikowany problem domenowy i przekazuje zadanie do odpowiedniego Sub-Agenta, odbierając od niego wygenerowany wynik.

---

## 5. Korzyści Architektoniczne

- **Zero-Latency Response:** Mały model (1.5B) dostaje skondensowany prompt (<400 tokenów) i 2-3 dedykowane narzędzia, co gwarantuje natychmiastową generację odpowiedzi na lokalnym procesorze.
- **Bezpieczeństwo i Izolacja:** Błąd lub niepoprawna dedukcja Sub-Agenta Ogrodnika nie wpływa na działanie zamków ani oświetlenia domowego.
- **Modułowość:** Nowe specjalizacje (np. integrację fotowoltaiki) dodaje się poprzez stworzenie nowego szablonu roli i podpięcie wywężonych narzędzi, bez modyfikacji głównego promptu systemu.

---

## 6. Powiązane Komponenty w Kodzie

- `src/controller/llm/prompt/builder.py` – Fabryka składająca prompty dwuwarstwowe.
- `src/controller/llm/orchestrator.py` – Orkiestrator zarządzący pętlami ReAct poszczególnych Sub-Agentów.
- `src/controller/core/event_bus.py` / `schedule` – Wyzwalanie Sub-Agentów w tle.
