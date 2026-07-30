# Regis: Architektura i Filozofia Projektu

Ten dokument zawiera nadrzędne zasady projektowe, wybrane środowiska docelowe oraz filozofię budowania aplikacji Regis. Został oddzielony od technicznych protokołów agentów, aby zachować czytelność.

## Filozofia Architektury (Zasada "Apple")
Regis nie jest uniwersalnym oprogramowaniem open-source, które ma obsłużyć każdy dostępny model na rynku. 
Głównym priorytetem jest **wąska specjalizacja**. Optymalizujemy kod aplikacji i logikę promptów pod kątem najwyższej wydajności, "bystrości" i prędkości (zero-latency) w ściśle określonych warunkach i dla dwóch wybranych modeli z rodziny Qwen 2.5.

**Odrzucenie Agnostycyzmu:** 
Nie wolno pisać skomplikowanego, zwalniającego kodu (np. pętli auto-retry, ciężkich fallback parserów) w celu ratowania słabszych modeli, które nie radzą sobie z natywnym wsparciem narzędzi. Kod ma być szczupły, ascetyczny i szybki.

## Architektura Dwuwarstwowa (Tiered System / Swarm)
Aplikacja jest oparta o współpracę dwóch jednostek. Cała codzienna interakcja i obsługa prostych komend odbywa się na warstwie pierwszej. Warstwa druga włączana jest tylko w przypadku zaawansowanych problemów.

### 1. Warstwa Pierwsza: "Recepcjonista" (24/7)
- **Rola:** Podstawowa interakcja z domownikiem, proste narzędzia, sterowanie domem, szybki czas reakcji. Podproces Głównego Modelu.
- **Sprzęt:** Raspberry Pi 5 (8GB RAM), oddelegowane w 100% wyłącznie do wnioskowania LLM.
- **Zależności:** Home Assistant działa całkowicie odseparowany na własnym sprzęcie (Raspberry Pi 4), zwalniając pełne zasoby RPi 5.
- **Wybór Modelu:** `qwen2.5:1.5b-instruct`. Pierwotnie zakładano wersję 7B i 3B, jednak ze względu na brak akceleracji GPU na Raspberry Pi 5 i potrzebę obsługi systemów głosowych (TTS/STT) z zerowym opóźnieniem, obniżono półkę do 1.5B (zajmuje ok. 1GB RAM), co zapewnia błyskawiczną generację tekstu na samym procesorze. Dodatkowo model 1.5B korzysta z wymuszania schematu JSON (Structured Outputs) co całkowicie eliminuje halucynacje narzędzi.

### 2. Warstwa Druga: "Szef" (On-Demand)
- **Rola:** Zaawansowana analityka, obsługa ciężkich zadań, posiadanie dostępu do szerszej puli skomplikowanych narzędzi.
- **Sprzęt:** Stacje robocze Desktop PC z potężnymi układami graficznymi (przykładowo: RTX 5070 z 12GB VRAM).
- **Wybór Modelu:** `qwen2.5:14b-instruct`. Waży na tyle mało, aby zmieścić się w całości w 12GB VRAM wraz z kontekstem. Zapewnia to absolutny brak offloadingu do RAM-u systemowego, a co za tym idzie - błyskawiczną prędkość wnioskowania.

### Mechanizm "Handoff"
Gdy "Recepcjonista" na Raspberry Pi 5 napotka zbyt trudne zadanie, używa narzędzia (np. `call_boss()`). Regis samodzielnie sprawdza w tle (usługa telemetryczna), które komputery PC są włączone i mają wolne zasoby VRAM. Następnie wysyła prośbę wraz z pełnym kontekstem konwersacji do instancji Ollamy na Desktopie, ładuje model "Szefa", odbiera wynik i zwalnia zasoby PC, aby nie przeszkadzać w graniu czy pracy na komputerze głównym.

## Paradygmat Agentowy (Zasada CoT)
Regis i zawarte w nim byty (Lokaj, Regis) nie są standardowymi LLM służącymi "do plucia tekstem". Są pełnoprawnymi Agentami operującymi w pętli myślowej **ReAct (Reasoning and Acting)**.
Zabrania się ucinania narzędzi lub odłączania logiki podczas faz konwersacyjnych. Agent w każdym momencie swojego działania ma prawo do "pomylenia się", uświadomienia sobie błędu (otrzymania logu o błędzie od narzędzia) i wykonania auto-korekcji za pomocą kolejnych wywołań w tle (Chain of Thought), ZANIM przedstawi ostateczną, gotową odpowiedź człowiekowi.
W tym celu, komunikaty błędów po stronie narzędzi nie mogą "uświadamiać" użytkownika. Zawsze mają być kierowane wyłącznie do Agenta w formie wewnętrznej reprymendy (`BŁĄD WEWNĘTRZNY, wykonaj akcję naprawczą`), nakazującej Agentowi rozwiązać problem zanim wyjdzie z pętli.

**Zasada Wspierania Myślenia (Empowerment over Restriction):** Kładziemy główny nacisk na pomaganie modelowi w myśleniu i analizowaniu przestrzeni problemu (zapewniając Chain of Thought i dostęp do narzędzi), a nie na zakuwanie go w kajdany poprzez restrykcyjne nakazy czy zakazy w specyficznych sytuacjach. Nadmiar twardych, negatywnych zakazów (tzw. "Bans") degraduje ogólne zdolności kognitywne LLM-ów. Zamiast zakazywać halucynacji, pomagamy im ich uniknąć zmuszając do logicznej kaskady dedukcji przed przystąpieniem do akcji.
