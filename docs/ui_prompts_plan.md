# Plan Implementacji UI: Zarządzanie Promptami Systemowymi

## Kontekst
Backend posiada już gotowy moduł `PromptStore` (CRUD + REST API pod `/api/v1/agent/prompts`).
Kolejnym krokiem jest odblokowanie zakładki "Agenty" we frontendzie i zbudowanie interfejsu użytkownika do zarządzania promptami.

### Zachowanie interfejsu (UX):
1. **Lista (Lewa kolumna):**
   - Zawiera listę promptów (`GET /api/v1/agent/prompts`).
   - Aktywny prompt (ten, którego używa Agent) oznaczony wyraźnie (np. zielona kropka, badge).
   - Zaznaczony do edycji prompt jest podświetlony na liście.
2. **Edytor (Prawa kolumna):**
   - Wyświetla dane z wybranego promptu.
   - Pola: Nazwa (input), Opis (input opcjonalny), Treść (textarea flex/rozwijane).
   - Akcje na dole:
     - **Aktywuj** (`PUT /{id}/activate`) - ustawia prompt jako główny w systemie.
     - **Zapisz** (`PUT /{id}`) - aktualizuje treść/nazwę.
     - **Usuń** (`DELETE /{id}`) - usuwa prompt z systemu (wymaga blokady usunięcia dla aktywnego promptu).
3. **Tworzenie nowego:**
   - Przycisk `+ Nowy` na górze widoku.
   - Czyści edytor po prawej stronie (lub tworzy tymczasowy slot na liście), pozwalając na wpisanie danych. Zapis wywołuje `POST /api/v1/agent/prompts`.

### Zakres Zmian (Dla przyszłego Agenta):
1. `web/js/network/api_client.js`: Dodanie 6 metod do komunikacji z API `/api/v1/agent/prompts`.
2. `web/js/views/agents.js`: Utworzenie klasy widoku realizującej powyższy układ HTML + eventy.
3. `web/css/views/agents.css`: Style CSS definiujące układ Grid/Flexbox dla lewej listy i prawego panelu.
4. `web/js/tab_manager.js` & `index.html`: Zarejestrowanie widoku `AgentsView` i usunięcie atrybutów `disabled` / `wkrótce` z nawigacji `data-tab="agents"`.
