# Semantic Room Mapping & Hierarchical Memory (RFC)

## Problem
Modele LLM w architekturze dwuwarstwowej (Szef 14B / Lokaj 1.5B) nie posiadają natywnej zdolności do kojarzenia potocznych określeń domowników (np. "u Maćka", "u taty") z suchymi identyfikatorami encji w Home Assistant (np. `light.pokoj_1`), chyba że wprowadzimy "śmietnik" informacyjny w prompcie systemowym (tzw. Prompt Bloat), pożerający tokeny. 

Dodatkowo, nazywanie urządzeń w HA na sztywno "moj pokój" wprowadza pułapki tożsamościowe dla modeli generatywnych (LLM uznaje pokój za własną przestrzeń na serwerze).

## Propozycje Rozwiązań

### 1. Skondensowane Aliasy w Menu (Dla modelu 1.5B i 14B)
Minimalistyczny kompromis. Zamiast wprowadzać do kontekstu potężne pliki z historią każdego pomieszczenia, obok sztywnych, profesjonalnych i geograficznych nazw (np. *Pracownia, Sypialnia Północna*) dodajemy skrócone, 2-3 słowowe tagi (metadane) w nawiasach:
```markdown
## Pokój: Pracownia Główna
*Metadane: pokój TheBloka, brat, XBOX*
- light.pracownia_glowna
```
**Zalety:** Utrzymuje model w stanie "zero-latency". Błyskawicznie radzi sobie z in-context semantic matchingiem dla potocznych komend bez spowalniania logiki wykonawczej w małym modelu.

### 2. Architektura MemGPT (Hierarchiczna Pamięć dla modelu 14B)
Usunięcie wszystkich metadanych z "Core Memory" (Promptu wejściowego) i utworzenie bazy danych. Agent otrzymuje do dyspozycji narzędzie `search_memory(query)`.
Jeśli użytkownik zapyta "gdzie są słoiki", model musi wykonać pętlę ReAct, by pobrać z bazy szczegółowy log o zawartości "Spiżarni", zanim wejdzie w interakcję.
**Wady:** Wydłużenie czasu odpowiedzi (Latency) oraz zbyt wysoka trudność dedukcyjna dla małego modelu (1.5B).

### 3. Pre-processing NLP na Kontrolerze (Rozwiązanie Ostateczne)
Wprowadzenie warstwy *Entity Resolvera* po stronie serwera RPi, zanim polecenie trafi do LLMa. 
Backend łapie z mikrofonu komendę: "Zgaś u Maćka". Tłumaczy ją w locie ze słownika mapującego: "Zgaś w Pracowni Głównej" i podaje tę "sterylną" komendę LLM-owi. Model 1.5B zostaje całkowicie zwolniony z abstrakcyjnego kojarzenia.

## Konkluzja i Najbliższe Kroki
- Rozważamy zaimplementowanie opcji 1 (Skondensowane Aliasy) jako fundament dla menu urządzeń (Menu Payload w Routerze).
- Użytkownik przenazwie pokoje w Home Assistant, unikając zaimków "mój/twój" na rzecz chłodnego, obiektywnego nazewnictwa w systemie (np. *Pracownia, Studio, Sypialnia Główna*), wspierając się ukrytymi metadanymi na potrzeby asystenta.
