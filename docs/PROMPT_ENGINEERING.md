# Podręcznik Prompt Engineeringu: Qwen 2.5 Instruct (v2)

Ten dokument jest stałą bazą wiedzy dla wszystkich agentów i programistów rozwijających projekt Regis. Zbiór wytycznych opracowano w celu uzyskania stabilnego, przewidywalnego zachowania modeli z rodziny Qwen 2.5 (warianty 7B i 14B), w tym niezawodnego Tool Callingu i stabilnej pętli ReAct.

**Zmiana względem v1:** dokument nie traktuje już samego promptu systemowego jako jedynego źródła niezawodności. Prompt odpowiada za *intencję* modelu, a nie za twarde gwarancje formatu czy powtarzalności — te zapewnia warstwa infrastruktury (sampling, constrained decoding, parser). Rozdzielenie tych dwóch warstw jest kluczowe i przewija się przez cały dokument.

Kolejni agenci edytujący prompty systemowe projektu mają obowiązek kierować się tymi zasadami.

## 1. Wybór Formatu: Język Markdown

- **Markdown jako język ojczysty:** Qwen 2.5 był trenowany na dużej ilości danych ustrukturyzowanych (dokumentacje techniczne, GitHub). Reaguje słabiej na jednolity blok prozy niż na jasno wydzielone sekcje.
- **Semantyka wizualna:** Zawsze używamy pełnego formatowania Markdown (nagłówki `##`, pogrubienia `**`, wypunktowania `- `, bloki kodu), by oddzielić tożsamość, polecenia, reguły i definicje narzędzi. Każdy nagłówek działa jak odseparowana "komora kontekstowa".

## 2. Architektura Poleceń i Psychologia Małych Modeli

- **Ramowanie pozytywne — z zastrzeżeniem.** Dla reguł *miękkich* (styl, ton, sposób formułowania odpowiedzi) afirmatywne instrukcje ("ZAWSZE RÓB Y") rzeczywiście działają lepiej niż zakazy — łatwiej je operacyjnie zrealizować w jednym przejściu generacji. Ale dla reguł *twardych* (bezpieczeństwo, nieodwracalne akcje, np. „nie usuwaj plików bez potwierdzenia”, „nie ujawniaj kluczy API") sam pozytywny zamiennik często nie wystarcza. Rekomendacja: reguły miękkie — czysto afirmatywne; reguły twarde — jawny zakaz **plus** afirmatywna alternatywa, np.:
  > "Nie wykonuj `DELETE` bez wcześniejszego potwierdzenia od użytkownika. Zawsze najpierw zapytaj: 'Czy na pewno chcesz usunąć [X]?' i czekaj na jednoznaczne 'tak'."
- **Empowerment:** Dajemy modelowi świadomość posiadanych narzędzi zamiast samych zakazów. Zamiast: "Nie zmyślaj daty", piszemy: "Zawsze używaj narzędzia `get_current_time`, zanim odniesiesz się do bieżącej daty".
- **Krótko i zwięźle:** Unikamy zdań wielokrotnie złożonych. Jedna reguła = jedno proste, kategoryczne zdanie na liście.
- **Sandwiching zamiast czystego recency bias.** W jednorazowym promptcie umieszczenie kluczowych reguł na końcu rzeczywiście zwiększa ich wagę operacyjną. **Ale w pętli ReAct to za mało** — system prompt jest stały, a poniżej niego rośnie historia tool_callsów i wyników narzędzi. Po kilku iteracjach koniec system promptu przestaje być "blisko" aktualnego punktu generacji (efekt *lost in the middle*). Dlatego:
  - Najkrytyczniejsze reguły formatu (tagi myślowe, cisza przed `tool_call`) umieszczamy **zarówno na początku, jak i na końcu** system promptu.
  - Przy długich pętlach (>5-6 tur) rozważamy wstrzykiwanie krótkiego przypomnienia o formacie co N iteracji, a nie poleganie na jednorazowym umieszczeniu w systemowym.
- **Rozbijanie złożoności (checklisty):** Modele 7B-14B gubią się przy dużym, wielowątkowym zadaniu podanym zero-shot. Prompt musi narzucać strukturę "krok po kroku" — model skupia całą uwagę na jednym małym tasku naraz, co eliminuje pogubienie się w kolejności działań.

## 3. Struktura Wypunktowana (Bullet Points)

- **Krytyczne dla Instruction Following:** zbite akapity tekstu obniżają zdolność modeli Instruct do podążania za instrukcjami. Reguły działania i procedury (Kroki 1, 2, 3...) muszą przyjąć formę wypunktowanych list.

## 4. ReAct i Wymuszanie Monologu

- **Tagi `<thought>`:** wymuszają "myślenie na głos" i zapobiegają powierzchownym odpowiedziom. Prompt musi jasno, z przykładem, nakazywać rozpoczęcie każdej iteracji od tego tagu.
- **Zgodność z natywnym formatem Qwena.** Qwen 2.5 ma własny wytrenowany format tool-callingu w stylu Hermes/ChatML (`<tool_call>{...}</tool_call>`). Tag `<thought>` jest dodatkiem spoza treningu bazowego — sensownym, ale wymagającym testów pod kątem konfliktu z automatycznym parserem tool-call w backendzie (np. wbudowany function-calling parser w vLLM czy Ollama). Przed wdrożeniem sprawdzić, czy parser nie odcina/nie gubi treści poza `<tool_call>`.
- **Cisza między `</thought>` a `<tool_call>` — cel, nie gwarancja.** Twardy wymóg "zero tekstu" między tagami to punkt kruchości: im sztywniejszy format, tym łatwiej 7B-14B go złamie (dopisze spację, "Okay,", nowy wiersz). Sam prompt tego nie zagwarantuje deterministycznie. Realną niezawodność zapewnia warstwa niżej — patrz punkt 5.
- Odpowiedź do człowieka pada dopiero, gdy model zrezygnuje z użycia narzędzi w danej turze.

## 5. Warstwa Deterministyczna Poza Promptem (nowość)

To sekcja, której brakowało w v1 — bez niej cel "niezniszczalny, deterministyczny tool calling" pozostaje deklaracją, nie gwarancją.

- **Constrained / grammar-guided decoding.** Prompt ustawia intencję modelu, ale twardą gwarancję poprawnej składni JSON daje sampler, nie tekst instrukcji. Używać `guided_json` / JSON Schema w vLLM, Outlines, lm-format-enforcer lub odpowiednika w danym backendzie, żeby model fizycznie nie mógł wygenerować niepoprawnego wywołania narzędzia.
- **Parametry samplingu:** niska temperatura (0–0.2) i ustalony `seed` tam, gdzie backend to wspiera, dla zadań wymagających powtarzalności (tool calling, ekstrakcja danych). Wyższa temperatura tylko tam, gdzie pożądana jest kreatywność odpowiedzi.
- **Tolerancyjny parser po stronie harnessu.** Nawet przy dobrym prompcie i constrained decoding warto, by parser odpowiedzi robił `strip()` białych znaków i miał fallback (np. regex wyłuskujący blok JSON), zamiast zakładać perfekcyjne, zero-tokenowe przejście z `</thought>` do `<tool_call>`.
- **Chat Templates:** najlepszy system prompt zawiedzie, jeśli backend nie wstrzykuje poprawnych tokenów kontrolnych zgodnych z treningiem modelu (np. `<|im_start|>system`). Zgodność formatu na poziomie infrastruktury to warunek konieczny, nie opcjonalny.

## 6. Obsługa Błędów i Self-Correction (nowość)

- Prompt musi definiować, co model robi, gdy wywołanie narzędzia zwróci błąd (zły parametr, halucynowane pole, timeout) — np. krótka instrukcja: "Jeśli wynik narzędzia zawiera pole `error`, przeanalizuj przyczynę w `<thought>` i popraw wywołanie zamiast powtarzać je bez zmian."
- Ograniczyć liczbę prób naprawczych w pętli (np. max 2 retry na to samo narzędzie), żeby uniknąć nieskończonej pętli przy uporczywym błędzie — po przekroczeniu limitu model ma zgłosić problem użytkownikowi zamiast ponawiać w nieskończoność.

## 7. Szablon "Pancernego" Promptu Systemowego (zaktualizowany)

1. **Definicja tożsamości i roli** — kim jest agent, krótki opis.
2. **Środowisko i narzędzia** — opis formatów, do czego służą narzędzia.
3. **Procedura działania (kroki)** — jasna lista: 1. Pomyśl, 2. Wywołaj narzędzie, 3. Czekaj na wynik, 4. W razie błędu — popraw i spróbuj ponownie (max N razy), 5. Odpowiedz.
4. **Twarde reguły behawioralne** — krótka, afirmatywna lista (język, ton, zwięzłość); reguły bezpieczeństwa jako zakaz + alternatywa (patrz punkt 2).
5. **Przypomnienie na końcu** — kluczowa dyrektywa zamykająca (format tagów myślowych), zduplikowana z sekcji 2/3 dla efektu sandwichingu.

## 8. Różnice 7B vs 14B (nowość)

Dokument v1 traktował oba warianty jednolicie — to uproszczenie warte skorygowania:

- **7B:** potrzebuje krótszych, bardziej rozdrobnionych checklist; mniej odporny na złożone, wielowarunkowe reguły w jednym zdaniu; few-shot praktycznie obowiązkowy, nie tylko zalecany.
- **14B:** lepiej radzi sobie z niejednoznacznością i dłuższym kontekstem instrukcji, ale nadal korzysta z sandwichingu w długich pętlach ReAct.
- Rekomendacja: utrzymywać dwie warianty promptu (lub przynajmniej dwie wersje sekcji checklisty) i testować je osobno w ewaluacji (punkt 10) — reguła dobra dla 14B nie zawsze przenosi się bezpośrednio na 7B.

## 9. Uzupełniające Najlepsze Praktyki

- **Few-shot prompting:** modele 7B-14B uczą się szybciej i precyzyjniej z przykładów niż z suchych regulaminów. Zawsze dołączać do promptu systemowego przynajmniej jeden kompletny przykład idealnej iteracji: otwarcie `<thought>`, myślenie, poprawne wywołanie narzędzia z ciszą przed `tool_call`.
- **Role/Persona Anchoring — realistyczne oczekiwania.** Nadanie roli (np. "Jesteś wybitnym asystentem AI...") wpływa realnie na *ton i styl* odpowiedzi — to potwierdzone zjawisko. Nie należy jednak zakładać, że samo to podnosi jakość rozumowania na zadaniach wymagających realnej zdolności (matematyka, logika, precyzyjny tool use) — dowody na taki efekt są słabe, część obserwacji wskazuje na efekt zerowy lub ujemny przy zadaniach stricte capability-based. Stosować personę dla spójności komunikacji, nie jako substytut lepszego promptu proceduralnego.
- **Chat Templates:** dbać o zgodność tokenów kontrolnych między promptem a backendem (patrz punkt 5).

## 10. Ewaluacja i Regresja Promptów (nowość)

Bez tej sekcji "pancerność" promptu jest deklaratywna, nie zmierzona.

- Utrzymywać mały, ale reprezentatywny zestaw przypadków testowych (eval suite) obejmujący: poprawne wywołania narzędzi, przypadki błędów/retry, wieloturowe konwersacje ReAct, przypadki brzegowe (dwuznaczne polecenia, brakujące parametry).
- Każda zmiana promptu systemowego lub wersji modelu (np. aktualizacja Qwen 2.5 → kolejna wersja) uruchamia eval suite przed wdrożeniem — nie polegamy wyłącznie na "wygląda dobrze przy ręcznym teście".
- Mierzyć osobno: trafność formatu (czy `<tool_call>` parsuje się bez błędu), trafność semantyczną (czy wywołane narzędzie i parametry są poprawne), oraz stabilność w czasie (czy zachowanie nie dryfuje między iteracjami tej samej sesji).
