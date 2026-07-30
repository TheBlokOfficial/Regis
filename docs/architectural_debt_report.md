# Raport Długu Architektonicznego: Monolit vs Rozproszone Komponenty (Mikro-narzędzia)

## 1. Analiza Problemu: Dystrybucja Węzłów i Konfiguracja

Bieżąca architektura Regis narusza zasady fizycznej separacji komponentów w środowisku rozproszonym, co bezpośrednio generuje ryzyko awarii konfiguracyjnych podczas wdrożeń. Zidentyfikowano dwa główne obszary długu:

### 1.1 Scentralizowany Stan Konfiguracji (Monolityczny `settings.json`)
Konfiguracja wszystkich ról w systemie (Kontroler, Worker, Satelita) jest utrzymywana w jednym pliku współdzielonym.
- **Ryzyko wdrożeniowe:** Deployment pełnej konfiguracji na węzły brzegowe (np. Raspberry Pi) powoduje nadpisanie tożsamości instancji docelowej. Przykładowo, węzeł typu Worker próbuje ładować zasoby, porty i modele LLM przypisane do głównego serwera.
- **Niestabilny deployment:** Obecny proces wymaga ręcznego wykluczania plików z paczki wdrożeniowej, co jest wysoce podatne na błędy (incydent z awarią usługi Butler).
- **Brak izolacji:** Architektura nie wspiera mechanizmu profili konfiguracyjnych dedykowanych poszczególnym klasom urządzeń.

### 1.2 Dystrybucja Kodu Źródłowego zamiast Skompilowanych Komponentów
Każdy węzeł brzegowy otrzymuje pełne repozytorium `Regis`, mimo iż jego rola w architekturze jest ściśle określona i ograniczona.
- **Nadmiarowy narzut (Overhead):** Uruchomienie Zdalnego Satelity lub Workera na maszynie brzegowej wiąże się z przesyłaniem zbędnych modułów (m.in. serwera Kontrolera, logiki administracyjnej, integracji z Home Assistant).
- **Zależność środowiskowa:** System wymusza proces instalacji zależności, utrzymywanie wirtualnego środowiska Pythona (`.venv`) oraz uruchamianie usług z monolitycznych skryptów startowych na każdym urządzeniu. Stanowi to naruszenie zasady rozdzielenia logiki określonej w dokumencie `MANIFEST.md`.

## 2. Rekomendacje Architektoniczne (Action Items)

W celu systematycznej redukcji długu zaleca się implementację następujących zmian w procesie wytwórczym:

### 2.1 Architektura Konfiguracji per Profil (Node-Specific Configuration)
- Wdrożyć mechanizm podziału konfiguracji na zrębne profile (np. według konwencji `settings.<PROFILE>.json`).
- Zaadaptować wzorzec z lokalnym plikiem środowiskowym `.env` na węzłach (określającym np. `ACTIVE_PROFILE=rpi5-worker`). Kod aplikacji, w fazie bootstrap, powinien wczytywać tylko podzbiór ustawień odpowiadający wskazanemu profilowi.

### 2.2 Wyizolowane Pakiety Dystrybucyjne (Standalone Binaries)
- Wyeliminować transfer surowego kodu źródłowego (`tar.gz` z repozytorium) ze skryptów odpowiedzialnych za deployment.
- Zaadaptować rozwiązania do budowania samodzielnych plików binarnych/pakietów wykonywalnych (np. `PyInstaller` lub `hatch`) dla odseparowanych komponentów brzegowych (np. generowanie `regis-satellite.exe`, `regis-worker`).
- Przekształcić usługi Satelity i Workera w bezstanowe oprogramowanie typu "plug-and-play", redukując w ten sposób wymóg utrzymywania `.venv` na systemach klienckich oraz chroniąc kod biznesowy (Kontroler) przed transferem do niepowołanych punktów.
