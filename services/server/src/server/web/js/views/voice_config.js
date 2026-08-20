/**
 * Zakładka Głos — dziś w całości zakładka-widmo: `server/voice` ma tylko
 * jeden, zahardkodowany dev-provider każdego rodzaju (`main.py`), zero
 * realnego endpointu konfiguracji STT/TTS do wystawienia w UI. Zamiast
 * pokazywać status jednego dev-providera (mylące — sugerowało realną
 * konfigurowalność, której nie ma), trzy jawne placeholdery na przyszłe
 * sekcje: STT, TTS, Satelity — każda w tym samym szkielecie co pozostałe
 * zakładki Ustawień (`.section-heading` + karta `.stat-panel`).
 */
export class VoiceConfigView {
  render() {
    return `
      <div class="view-shell">
        <h3 class="section-heading">STT</h3>
        <div class="stat-panel">
          <p class="voice-placeholder-text">
            Zakładka jeszcze nieaktywna. Konfiguracja dostawcy rozpoznawania mowy
            (klucz API, wybór modelu) pojawi się tutaj po podłączeniu realnego
            dostawcy chmurowego.
          </p>
        </div>

        <h3 class="section-heading section-heading--spaced-sm">TTS</h3>
        <div class="stat-panel">
          <p class="voice-placeholder-text">
            Zakładka jeszcze nieaktywna. Konfiguracja dostawcy syntezy mowy
            (klucz API, wybór głosu/modelu) pojawi się tutaj po podłączeniu
            realnego dostawcy chmurowego.
          </p>
        </div>

        <h3 class="section-heading section-heading--spaced-sm">Satelity</h3>
        <div class="stat-panel">
          <p class="voice-placeholder-text">
            Rejestracja pokoju dla nadawców (w tym satelit głosowych) znajduje się w sekcji
            <a href="#" id="voice-link-to-world" class="text-link">Świat</a>.
          </p>
        </div>
      </div>
    `;
  }

  async init(apiClient, onNavigateToWorld) {
    document.getElementById('voice-link-to-world')?.addEventListener('click', (e) => {
      e.preventDefault();
      onNavigateToWorld?.('world');
    });
  }
}
