import { getSenderId } from '../sender_id.js';
import { escapeAttr, escapeHtml } from '../utils/dom.js';
import { showToast } from '../utils/toast.js';

/**
 * Zakładka Klienci (dawniej Głos) — konfiguracja klienta (próg wake-worda + VAD
 * satelity, patrz `_renderClientConfigSection`) i Satelity (status podłączonych/
 * niezarejestrowanych nadawców). Config dostawców STT/TTS przeniesiony do zakładki
 * Dostawcy (`views/providers_config.js`, pełny CRUD mirror LLM) — dawny płaski,
 * jednosslotowy formularz (shim `GET/PUT /api/v1/voice/providers/config`)
 * usunięty stąd; backendowy endpoint zostaje (nieużywany przez to UI, ale
 * tani do utrzymania jako headless kompatybilność).
 *
 * Sekcja "Satelity" pokazuje `sender_id` z żywym połączeniem WS
 * (`GET /api/v1/voice/connected` — mechaniczny fakt z `server/voice`), które
 * nie mają jeszcze rejestracji w `World`, oraz ID tej przeglądarki (nadawca
 * tekstowy, nigdy nie ma połączenia WS, więc nie pojawi się na tamtej liście
 * — osobny przypadek). To świadomie **tutaj**, nie w zakładce Świat:
 * pierwszy kontakt z nieznanym nadawcą jest konceptualnie i pod maską domeną
 * `voice`, nie `world` — World zna wyłącznie zatwierdzone encje (nadawca +
 * pokój), nigdy stan gniazda WS. Przycisk "Zarejestruj" woła
 * `POST /api/v1/world/senders` **od razu, bez pokoju** (World i tak
 * przyjmuje `room_id: null` — pokój przypisuje się później, przez picker w
 * zakładce Świat, `satellites_panel.js`, `POST` jest tam upsertem). Cross-
 * domenowe wywołanie zapisu z poziomu UI innej domeny jest tu świadomie
 * dopuszczone — narusza własność danych dopiero *renderowanie* cudzej
 * domeny, nie samo wywołanie jej REST API.
 */
export class VoiceConfigView {
  constructor() {
    this.apiClient = null;
  }

  render() {
    return `
      <div class="view-shell">
        <h3 class="section-heading">Konfiguracja klienta</h3>
        <div id="voice-client-config-section"></div>

        <h3 class="section-heading">Satelity</h3>
        <div id="voice-satellites-section"></div>
      </div>
    `;
  }

  async init(apiClient, onNavigateToWorld) {
    this.apiClient = apiClient;
    this._onNavigateToWorld = onNavigateToWorld;

    await this._loadAndRenderClientConfig();
    await this._loadAndRenderSatellites();
  }

  // --------------------------------------------------------------------------
  // Konfiguracja klienta: próg wake-worda (100% serwerowa detekcja, patrz
  // `voice/wakeword.py`) + parametry VAD satelity (algorytm lokalny, próg
  // centralnie skonfigurowany tutaj i wysyłany satelicie przy handshake —
  // `ServerMessageType.CLIENT_CONFIG`). Pojedynczy globalny config, nie
  // kolekcja instancji jak dostawcy LLM/STT/TTS — prosty formularz, jawny
  // "Zapisz" (mirror wzorca z `extensions/ha/config_panel.js`).
  // --------------------------------------------------------------------------

  async _loadAndRenderClientConfig() {
    const config = await this.apiClient.getClientConfig();
    this._renderClientConfigSection(config);
  }

  _renderClientConfigSection(config) {
    const container = document.getElementById('voice-client-config-section');
    if (!container) return;

    if (!config) {
      container.innerHTML = `<p class="voice-empty-hint">Nie udało się wczytać konfiguracji.</p>`;
      return;
    }

    const thresholdPct = Math.round(config.wakeword_threshold * 100);

    container.innerHTML = `
      <div class="form-card">
        <div class="form-row">
          <div class="form-group">
            <label for="voice-input-threshold">Próg pewności wake-worda (%)</label>
            <input type="number" id="voice-input-threshold" class="form-control" min="0" max="100" step="1" value="${thresholdPct}" />
          </div>
          <div class="form-group">
            <label for="voice-input-vad-silence">Cisza po wypowiedzi (ms)</label>
            <input type="number" id="voice-input-vad-silence" class="form-control" min="100" step="100" value="${config.vad_silence_duration_ms}" />
          </div>
          <div class="form-group">
            <label for="voice-input-vad-amplitude">Próg amplitudy VAD</label>
            <input type="number" id="voice-input-vad-amplitude" class="form-control" min="0" step="50" value="${config.vad_amplitude_threshold}" />
          </div>
        </div>
        <p class="section-hint">
          Detekcja wake-worda dzieje się w 100% na serwerze. VAD (koniec wypowiedzi) liczy
          się lokalnie na satelicie, ale jego próg jest stąd centralnie wysyłany przy
          każdym połączeniu — zmiana zadziała po następnym reconnect satelity, bez
          restartu serwera.
        </p>
        <div class="form-actions">
          <button class="btn" id="voice-btn-save-client-config">Zapisz</button>
        </div>
      </div>
    `;

    document.getElementById('voice-btn-save-client-config')?.addEventListener('click', () => this._saveClientConfig());
  }

  async _saveClientConfig() {
    const thresholdInput = document.getElementById('voice-input-threshold');
    const silenceInput = document.getElementById('voice-input-vad-silence');
    const amplitudeInput = document.getElementById('voice-input-vad-amplitude');
    if (!thresholdInput || !silenceInput || !amplitudeInput) return;

    const payload = {
      wakeword_threshold: Number(thresholdInput.value) / 100,
      vad_silence_duration_ms: Number(silenceInput.value),
      vad_amplitude_threshold: Number(amplitudeInput.value),
    };

    try {
      await this.apiClient.updateClientConfig(payload);
      showToast('Zapisano konfigurację klienta.', 'success');
    } catch (error) {
      showToast(error.message || 'Błąd zapisu konfiguracji klienta.', 'error');
    }
  }

  async _loadAndRenderSatellites() {
    const [connectedSenderIds, senders] = await Promise.all([this.apiClient.getConnectedSenders(), this.apiClient.getSenders()]);
    const thisBrowserId = getSenderId();
    const registeredIds = new Set((senders || []).map((s) => s.sender_id));
    const pending = (connectedSenderIds || []).filter((id) => id !== thisBrowserId && !registeredIds.has(id));
    const thisBrowserRegistered = registeredIds.has(thisBrowserId);
    this._renderSatellitesSection(pending, thisBrowserId, thisBrowserRegistered);
  }

  _renderSatellitesSection(pending, thisBrowserId, thisBrowserRegistered) {
    const container = document.getElementById('voice-satellites-section');
    if (!container) return;

    const pendingHtml =
      pending.length === 0
        ? ''
        : `
      <div class="voice-pending-satellites">
        <p class="voice-pending-satellites-label">Podłączone, oczekujące na rejestrację:</p>
        <div class="voice-list">
          ${pending
            .map(
              (senderId) => `
            <div class="voice-list-row">
              <span class="voice-satellite-id">${escapeHtml(senderId)}</span>
              <button type="button" class="btn btn-sm btn-subtle" data-register-sender="${escapeAttr(senderId)}">Zarejestruj</button>
            </div>
          `
            )
            .join('')}
        </div>
      </div>
    `;

    container.innerHTML = `
      ${pendingHtml}
      <p class="voice-empty-hint voice-browser-self-hint">
        ID tej przeglądarki: <span class="voice-satellite-id">${escapeHtml(thisBrowserId)}</span>
        ${thisBrowserRegistered ? '<span class="badge-chip">zarejestrowana</span>' : `<button type="button" class="btn btn-sm btn-ghost" data-register-sender="${escapeAttr(thisBrowserId)}">Zarejestruj tę przeglądarkę</button>`}
      </p>
      <div class="stat-panel">
        <p class="voice-placeholder-text">
          Przypisanie pokoju do zarejestrowanego nadawcy znajduje się w sekcji
          <a href="#" id="voice-link-to-world" class="text-link">Świat</a>.
        </p>
      </div>
    `;

    document.getElementById('voice-link-to-world')?.addEventListener('click', (e) => {
      e.preventDefault();
      this._onNavigateToWorld?.('world');
    });
    container.querySelectorAll('[data-register-sender]')?.forEach((btn) => {
      btn.addEventListener('click', () => this._registerSender(btn.getAttribute('data-register-sender')));
    });
  }

  async _registerSender(senderId) {
    try {
      await this.apiClient.registerSender({ sender_id: senderId, room_id: null });
      showToast('Zarejestrowano nadawcę.', 'success');
      await this._loadAndRenderSatellites();
    } catch (error) {
      showToast(error.message || 'Błąd rejestracji nadawcy.', 'error');
    }
  }
}
