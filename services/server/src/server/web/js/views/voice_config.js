/**
 * Zakładka Głos — status pipeline'u głosowego (server/voice), wyłącznie do odczytu.
 *
 * Dziś nie ma żadnego backendowego rejestru instancji STT/TTS (jeden,
 * zahardkodowany dev-provider każdego rodzaju w main.py) — zamiast budować
 * pełny CRUD bez drugiego, realnego providera w ręku (YAGNI), ta zakładka
 * pokazuje wyłącznie aktualną konfigurację i jawnie sygnalizuje brak
 * prawdziwego dostawcy chmurowego.
 */
export class VoiceConfigView {
  render() {
    return `
      <div class="dashboard-grid">
        <div class="page-header">
          <div>
            <h2 class="page-header-title">Głos</h2>
            <p class="page-header-desc">Status pipeline'u głosowego satelit (wake-word → VAD → STT → agent → TTS).</p>
          </div>
        </div>

        <div id="voice-status-container">
          <div class="card card-loading">Ładowanie statusu...</div>
        </div>

        <div class="section-header-bar">
          <h3 class="section-title">Satelity</h3>
        </div>
        <p class="dashboard-empty-desc">
          Rejestracja pokoju dla nadawców (w tym satelit głosowych) znajduje się w zakładce
          <a href="#" id="voice-link-to-world">Świat</a>.
        </p>
      </div>
    `;
  }

  async init(apiClient) {
    this.apiClient = apiClient;

    document.getElementById('voice-link-to-world')?.addEventListener('click', (e) => {
      e.preventDefault();
      document.getElementById('nav-extensions')?.click();
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
      <div class="dashboard-hero-top">
        <div>
          <div class="provider-section-label">Konfiguracja aktywna</div>
          <div class="dashboard-hero-name">Wake-word: ${escapeHtml(status.wakeword_detector)}</div>
        </div>
        <div class="dashboard-hero-badges">
          <span class="badge badge-status">
            <span class="status-dot-pulse"></span>${status.is_production_ready ? 'Gotowe' : 'Tylko dev'}
          </span>
        </div>
      </div>

      <div class="provider-meta-grid">
        <div class="provider-meta-item">
          <span class="provider-meta-label">Dostawca STT</span>
          <span class="provider-meta-value">${escapeHtml(status.stt_provider)}</span>
        </div>
        <div class="provider-meta-item">
          <span class="provider-meta-label">Dostawca TTS</span>
          <span class="provider-meta-value">${escapeHtml(status.tts_provider)}</span>
        </div>
      </div>

      ${
        status.is_production_ready
          ? ''
          : `<p class="dashboard-empty-desc">
               Brak realnego dostawcy STT/TTS w chmurze — dziś działają wyłącznie dev-providerzy
               (bez połączenia z żadną usługą zewnętrzną). Podłączenie realnego dostawcy i modelu
               wake-word to kolejny krok wdrożenia.
             </p>`
      }
    `;
  }
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
