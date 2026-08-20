/**
 * Zakładka Głos — status pipeline'u głosowego (server/voice), wyłącznie do odczytu.
 *
 * Dziś nie ma żadnego backendowego rejestru instancji STT/TTS (jeden,
 * zahardkodowany dev-provider każdego rodzaju w main.py) — zamiast budować
 * pełny CRUD bez drugiego, realnego providera w ręku (YAGNI), ta zakładka
 * pokazuje wyłącznie aktualną konfigurację i jawnie sygnalizuje brak
 * prawdziwego dostawcy chmurowego.
 *
 * Wizualnie ten sam system co Agent/Świat — bez zbędnego nagłówka strony
 * (pigułka nawigacji już mówi "Głos"), status na pływającej karcie.
 */
import { escapeHtml } from '../utils/dom.js';

export class VoiceConfigView {
  render() {
    return `
      <div class="view-shell">
        <h3 class="section-heading">Status</h3>
        <div id="voice-status-container">
          <div class="card card-loading">Ładowanie statusu...</div>
        </div>

        <h3 class="section-heading section-heading--spaced-sm">Satelity</h3>
        <p class="section-hint">
          Rejestracja pokoju dla nadawców (w tym satelit głosowych) znajduje się w sekcji
          <a href="#" id="voice-link-to-world" class="text-link">Świat</a>.
        </p>
      </div>
    `;
  }

  async init(apiClient, onNavigateToWorld) {
    this.apiClient = apiClient;

    document.getElementById('voice-link-to-world')?.addEventListener('click', (e) => {
      e.preventDefault();
      onNavigateToWorld?.('world');
    });

    await this.refresh();
  }

  async refresh() {
    const container = document.getElementById('voice-status-container');
    if (!container) return;

    const status = await this.apiClient.getVoiceStatus();
    if (!status) {
      container.innerHTML = `<div class="card card-sm">Błąd pobierania statusu pipeline'u głosowego.</div>`;
      return;
    }

    container.innerHTML = `
      <div class="stat-panel">
        <div class="stat-panel-header">
          <div>
            <div class="stat-panel-label">Konfiguracja aktywna</div>
            <div class="stat-panel-title">Wake-word: ${escapeHtml(status.wakeword_detector)}</div>
          </div>
          <div class="stat-panel-badges">
            <span class="badge badge-status">
              <span class="status-dot-pulse"></span>${status.is_production_ready ? 'Gotowe' : 'Tylko dev'}
            </span>
          </div>
        </div>

        <div class="stat-panel-meta-grid">
          <div class="stat-panel-meta-item">
            <span class="stat-panel-meta-label">Dostawca STT</span>
            <span class="stat-panel-meta-value">${escapeHtml(status.stt_provider)}</span>
          </div>
          <div class="stat-panel-meta-item">
            <span class="stat-panel-meta-label">Dostawca TTS</span>
            <span class="stat-panel-meta-value">${escapeHtml(status.tts_provider)}</span>
          </div>
        </div>

        ${
          status.is_production_ready
            ? ''
            : `<p class="section-hint voice-status-notice">
                 Brak realnego dostawcy STT/TTS w chmurze — dziś działają wyłącznie dev-providerzy
                 (bez połączenia z żadną usługą zewnętrzną). Podłączenie realnego dostawcy i modelu
                 wake-word to kolejny krok wdrożenia.
               </p>`
        }
      </div>
    `;
  }
}
