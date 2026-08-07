# HANDOFF — Stan Projektu Regis po Sesji 2026-08-07 (Filozofia)

## Co zostało zrobione w tej sesji

Sesja była w całości filozoficzna i dokumentacyjna — zero zmian w kodzie. Przeprowadzono fundamentalne przeformułowanie filozofii projektu i zaktualizowano dokumenty `docs/MANIFEST.md` i `docs/AGENT_GUIDE.md`.

### 1. Trójwarstwowy model architektury (nowy rdzeń MANIFEST §3)

Ustalono i udokumentowano trójwarstwowy podział systemu:

- **Warstwa 1 — Core (Układ Nerwowy):** pętla ReAct, session manager, tool registry (mechanizm), abstrakcyjne interfejsy (`ILLMProvider`, `ISTTProvider`, `ITTSProvider`, `ISatellite`). Core nie zawiera referencji do konkretnych providerów ani narzędzi.
- **Warstwa 2 — Providers & Channels (Zmysły i Ręce):** wymienna cybernetyka. OpenRouter/Ollama, Whisper/Cloud STT, Piper/Cloud TTS, ESP32/Desktop/Terminal. **Regis Desktop** jest szczególnym przypadkiem — bundluje wiele implementacji warstwy 2 jako menedżer usług (satelita + lokalny LLM + STT + TTS).
- **Warstwa 3 — Integrations (Narzędzia):** Home Assistant, web, pliki, kamery, własne skrypty. W pełni opcjonalne, rejestrują się w Tool Registry przy starcie.

### 2. Redefinicja tożsamości projektu (MANIFEST §1)

Stara definicja ("lekka warstwa abstrakcji między domownikami a urządzeniami") zastąpiona przez:
- Regis jako **autonomiczne oprogramowanie agenta** z panelem webowym — produkt, nie framework
- **Istota projektu:** Regis interaktuje z oprogramowaniami tak jak człowiek — widzi "włączona/wyłączona", nie MQTT/Zigbee. HA z setkami integracji jest dla Regisa jedną pozycją w `integrations/`.
- Regis jest projektem **osobistym** — nie enterprise, nie scraping, nie korporacja.
- Explicite odróżnienie od LangChaina: LangChain = biblioteka dla programistów, Regis = produkt który instalujesz i konfigurujesz.

### 3. Persona agenta przepisana (MANIFEST §6)

Stary opis ("Regis jest charakterny, rzeczowy i bezpośredni") był prywatną preferencją wpisaną jako standard produktu. Zastąpiony przez:
- **Persona jest user-defined** — system dostarcza mechanizm, nie treść
- **Zasada spójności:** cokolwiek użytkownik skonfiguruje, musi być spójne we wszystkich trybach
- **Cele projektowe systemu** (nie persony): szybkość, bezpośredniość, niezawodność — jako *intencje*, nie twierdzenia

### 4. Nazewnictwo ujednolicone

- Dawny "Kontroler" → **"Regis"** lub "system Regis" (to jest cały system, nie jeden komponent)
- Dawny "Windows Node" → **"Regis Desktop"** (menedżer usług warstwy 2)
- Dawna "Satelita" → pojęcie zachowane wewnętrznie; użytkownikowi: "Regis Desktop" lub "Regis ESP32"
- Instalator: `RegisDesktopSetup.exe` (nie `RegisNodeSetup.exe`)

### 5. AGENT_GUIDE.md zaktualizowany

- Tabela "Decyzje Już Podjęte" — dodano trójwarstwowy model jako rozstrzygniętą decyzję
- Lista "Typowe Błędy" — dodano punkt #8 o mieszaniu warstw (np. konkretny provider w Core)

---

## Aktualny stan kodu

**Kod nie był ruszany w tej sesji.** Wszystkie zmiany dotyczą wyłącznie dokumentacji:
- `docs/MANIFEST.md` — całkowicie przepisany (sekcje 1 i 3 nowe, sekcja 6 przepisana)
- `docs/AGENT_GUIDE.md` — dwa dodatki (tabela decyzji + lista błędów)

Ostatni smoke test kodu był z poprzedniej sesji:
```
python -c "import controller.app; print('OK')"
→ OK (exit code 0)
```

---

## Otwarte kwestie do przyszłych sesji

1. **Pamięć długoterminowa** — wskazana jako kluczowy brakujący feature odróżniający Regisa od HA AI. Stary system Notatnika wycięty, nowe rozwiązanie niezaprojektowane. To jest realny priorytet architektoniczny.
2. **Scheduler zadań agenta** — "zgaś światło za godzinę jeżeli..." wymaga mechanizmu odroczonych "szturchnięć" agenta. Niezaprojektowane.
3. **Docker deployment** — cel dystrybucyjny ustalony w dyskusji. Regis jako obraz Docker na mini PC (analogia do HA). Nie jest jeszcze udokumentowany ani zaimplementowany.
4. **Formalne interfejsy warstwy 2** — `ILLMProvider`, `ISTTProvider` etc. istnieją jako koncepcja, nie jako klasy bazowe w kodzie.

---

## Precyzyjne kroki startowe dla następnego agenta

1. Wczytaj `docs/MANIFEST.md` — jest teraz znacząco inny od wersji z poprzednich sesji. Sekcja 1 i 3 są nowe, §6 przepisana.
2. Wczytaj `docs/AGENT_GUIDE.md` — zaktualizowana tabela decyzji i lista błędów.
3. Uruchom smoke test: `cd src ; python -c "import controller.app; print('OK')"`.
4. Jeśli użytkownik chce kontynuować refaktoryzację kodu, patrz poprzedni HANDOFF — kolejne obszary to `llm/backends/` i FastAPI DI.
5. Jeśli użytkownik chce projektować pamięć długoterminową lub scheduler — to są nowe, niezaprojektowane obszary wymagające sesji architektonicznej.
