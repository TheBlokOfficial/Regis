import { Icons } from '../icons.js';
import { initSelect, renderSelectMarkup } from '../components/select.js';
import { getSenderId } from '../sender_id.js';
import { escapeHtml } from '../utils/dom.js';
import { showToast } from '../utils/toast.js';

/**
 * Zakładka Głos — STT (Groq)/TTS (ElevenLabs) mają od tej sesji realne
 * formularze configu (wcześniej: świadomy placeholder, YAGNI, patrz historia
 * gita). Wzorzec pola klucza API/przycisku "Zapisz" skopiowany 1:1 z
 * `extensions/ha/config_panel.js` (jawny "Zapisz" odblokowywany dopiero po
 * zmianie, puste pole klucza nie nadpisuje zapisanego, pole hasła z
 * przełącznikiem pokaż/ukryj) — dwa niezależne panele/przyciski "Zapisz"
 * (STT/TTS), bo to dwa niezależne dostawcy z osobnym cyklem życia klucza.
 *
 * Model Groq wybierany przez wspólny custom dropdown (`components/select.js`)
 * zamiast natywnego `<select>` — ten sam komponent co typ dostawcy LLM w
 * `agent_config.js`.
 *
 * Zmiana klucza/modelu zapisuje się na dysk natychmiast, ale zaczyna
 * obowiązywać dopiero po restarcie serwera — providery STT/TTS są budowane
 * raz przy starcie (`main.py`), nie ma dziś hot-reloadu (patrz `routes.py`).
 *
 * Sekcja "Satelity" pokazuje `sender_id` z żywym połączeniem WS
 * (`GET /api/v1/voice/connected` — mechaniczny fakt z `server/voice`), które
 * nie mają jeszcze rejestracji w `World`. To świadomie **tutaj**, nie w
 * zakładce Świat: monitorowanie żywych połączeń jest konceptualnie i pod
 * maską domeną `voice`, nie `world` — World zna wyłącznie zatwierdzone
 * encje (rejestracja/pokój), nigdy stan gniazda WS. Przycisk "Zarejestruj"
 * tylko przenosi do zakładki Świat (bez prefill formularza — świadomie
 * najprostszy wariant, żaden most/stan przejściowy między zakładkami).
 */

const GROQ_MODEL_OPTIONS = [
  { value: 'whisper-large-v3-turbo', label: 'whisper-large-v3-turbo (szybszy, tańszy)' },
  { value: 'whisper-large-v3', label: 'whisper-large-v3 (dokładniejszy)' },
];

export class VoiceConfigView {
  constructor() {
    this.apiClient = null;
    this.config = null;
    this._modelSelect = null;
  }

  render() {
    return `
      <div class="view-shell">
        <h3 class="section-heading">STT — Groq</h3>
        <div class="form-card">
          <div class="form-row">
            <div class="form-group">
              <label for="voice-input-groq-key">Klucz API</label>
              <div class="voice-token-field-wrap">
                <input type="password" id="voice-input-groq-key" class="form-control" placeholder="Wklej klucz API..." />
                <button type="button" class="voice-token-toggle-eye" id="voice-btn-toggle-groq-key" title="Pokaż klucz" aria-label="Pokaż klucz">${Icons.Eye()}</button>
              </div>
            </div>
            <div class="form-group">
              <label id="voice-select-groq-model-label">Model</label>
              ${renderSelectMarkup('voice-select-groq-model', { placeholder: 'Wybierz model...' })}
            </div>
          </div>
          <p class="section-hint voice-token-hint">
            Klucz API wygenerujesz w konsoli <a href="https://console.groq.com/keys" target="_blank" rel="noopener" class="text-link">Groq</a>.
          </p>
          <div class="form-actions">
            <button class="btn" id="voice-btn-save-stt" disabled>Zapisz</button>
          </div>
        </div>

        <h3 class="section-heading section-heading--spaced-sm">TTS — ElevenLabs</h3>
        <div class="form-card">
          <div class="form-row">
            <div class="form-group">
              <label for="voice-input-elevenlabs-key">Klucz API</label>
              <div class="voice-token-field-wrap">
                <input type="password" id="voice-input-elevenlabs-key" class="form-control" placeholder="Wklej klucz API..." />
                <button type="button" class="voice-token-toggle-eye" id="voice-btn-toggle-elevenlabs-key" title="Pokaż klucz" aria-label="Pokaż klucz">${Icons.Eye()}</button>
              </div>
            </div>
            <div class="form-group">
              <label for="voice-input-elevenlabs-voice-id">ID głosu</label>
              <input type="text" id="voice-input-elevenlabs-voice-id" class="form-control" placeholder="np. pNInz6obpgDQGcFmaJgB (Adam)" />
            </div>
          </div>
          <p class="section-hint voice-token-hint">
            Klucz API i listę głosów znajdziesz w panelu <a href="https://elevenlabs.io/app/settings/api-keys" target="_blank" rel="noopener" class="text-link">ElevenLabs</a>.
            Domyślnie głos "Adam".
          </p>
          <div class="form-actions">
            <button class="btn" id="voice-btn-save-tts" disabled>Zapisz</button>
          </div>
        </div>

        <p class="section-hint voice-restart-hint">Zmiana klucza/modelu zaczyna obowiązywać po restarcie serwera.</p>

        <h3 class="section-heading section-heading--spaced-sm">Satelity</h3>
        <div id="voice-satellites-section"></div>
      </div>
    `;
  }

  async init(apiClient, onNavigateToWorld) {
    this.apiClient = apiClient;
    this._onNavigateToWorld = onNavigateToWorld;

    await this._loadAndRenderSatellites();

    this.config = await this.apiClient.getVoiceProvidersConfig();
    if (!this.config) return;

    this._modelSelect = initSelect({
      idPrefix: 'voice-select-groq-model',
      options: GROQ_MODEL_OPTIONS,
      value: this.config.groq_stt_model,
      onChange: () => this._markDirty('stt'),
    });

    this._setKeyPlaceholder('groq', this.config.groq_api_key);
    this._setKeyPlaceholder('elevenlabs', this.config.elevenlabs_api_key);

    const voiceIdInput = document.getElementById('voice-input-elevenlabs-voice-id');
    if (voiceIdInput) voiceIdInput.value = this.config.elevenlabs_voice_id;

    document.getElementById('voice-btn-toggle-groq-key')?.addEventListener('click', () => this._toggleKeyVisibility('groq'));
    document.getElementById('voice-btn-toggle-elevenlabs-key')?.addEventListener('click', () => this._toggleKeyVisibility('elevenlabs'));

    document.getElementById('voice-input-groq-key')?.addEventListener('input', () => this._markDirty('stt'));
    document.getElementById('voice-input-elevenlabs-key')?.addEventListener('input', () => this._markDirty('tts'));
    document.getElementById('voice-input-elevenlabs-voice-id')?.addEventListener('input', () => this._markDirty('tts'));

    document.getElementById('voice-btn-save-stt')?.addEventListener('click', () => this._saveStt());
    document.getElementById('voice-btn-save-tts')?.addEventListener('click', () => this._saveTts());
  }

  async _loadAndRenderSatellites() {
    const [connectedSenderIds, senders] = await Promise.all([this.apiClient.getConnectedSenders(), this.apiClient.getSenders()]);
    const thisBrowserId = getSenderId();
    const registeredIds = new Set((senders || []).map((s) => s.sender_id));
    const pending = (connectedSenderIds || []).filter((id) => id !== thisBrowserId && !registeredIds.has(id));
    this._renderSatellitesSection(pending);
  }

  _renderSatellitesSection(pending) {
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
              <button type="button" class="btn btn-sm btn-subtle" data-goto-world-registration>Zarejestruj</button>
            </div>
          `
            )
            .join('')}
        </div>
      </div>
    `;

    container.innerHTML = `
      ${pendingHtml}
      <div class="stat-panel">
        <p class="voice-placeholder-text">
          Rejestracja pokoju dla nadawców (w tym satelit głosowych) znajduje się w sekcji
          <a href="#" id="voice-link-to-world" class="text-link">Świat</a>.
        </p>
      </div>
    `;

    const goToWorld = (e) => {
      e.preventDefault();
      this._onNavigateToWorld?.('world');
    };
    document.getElementById('voice-link-to-world')?.addEventListener('click', goToWorld);
    container.querySelectorAll('[data-goto-world-registration]')?.forEach((btn) => {
      btn.addEventListener('click', goToWorld);
    });
  }

  hasUnsavedChanges() {
    const sttDirty = document.getElementById('voice-btn-save-stt')?.disabled === false;
    const ttsDirty = document.getElementById('voice-btn-save-tts')?.disabled === false;
    return Boolean(sttDirty || ttsDirty);
  }

  _keyInputId(provider) {
    return provider === 'groq' ? 'voice-input-groq-key' : 'voice-input-elevenlabs-key';
  }

  _toggleBtnId(provider) {
    return provider === 'groq' ? 'voice-btn-toggle-groq-key' : 'voice-btn-toggle-elevenlabs-key';
  }

  _saveBtnId(panel) {
    return panel === 'stt' ? 'voice-btn-save-stt' : 'voice-btn-save-tts';
  }

  _setKeyPlaceholder(provider, maskedKey) {
    const input = document.getElementById(this._keyInputId(provider));
    if (input) input.placeholder = maskedKey || 'Wklej klucz API...';
  }

  _markDirty(panel) {
    const btn = document.getElementById(this._saveBtnId(panel));
    if (btn) btn.disabled = false;
  }

  _toggleKeyVisibility(provider) {
    const input = document.getElementById(this._keyInputId(provider));
    const btn = document.getElementById(this._toggleBtnId(provider));
    if (!input || !btn) return;
    const showing = input.type === 'text';
    input.type = showing ? 'password' : 'text';
    btn.innerHTML = showing ? Icons.Eye() : Icons.EyeOff();
    btn.title = showing ? 'Pokaż klucz' : 'Ukryj klucz';
    btn.setAttribute('aria-label', btn.title);
  }

  async _saveStt() {
    const key = document.getElementById('voice-input-groq-key')?.value || '';
    const model = this._modelSelect?.getValue() || this.config.groq_stt_model;
    try {
      this.config = await this.apiClient.updateVoiceProvidersConfig({
        groq_api_key: key || null,
        groq_stt_model: model,
        elevenlabs_api_key: null,
        elevenlabs_voice_id: this.config.elevenlabs_voice_id,
        elevenlabs_model_id: this.config.elevenlabs_model_id,
      });
      showToast('Zapisano konfigurację STT.', 'success');
      this._afterSave('groq', 'stt');
    } catch (error) {
      showToast(error.message || 'Błąd zapisu konfiguracji STT.', 'error');
    }
  }

  async _saveTts() {
    const key = document.getElementById('voice-input-elevenlabs-key')?.value || '';
    const voiceId = document.getElementById('voice-input-elevenlabs-voice-id')?.value.trim() || this.config.elevenlabs_voice_id;
    try {
      this.config = await this.apiClient.updateVoiceProvidersConfig({
        groq_api_key: null,
        groq_stt_model: this.config.groq_stt_model,
        elevenlabs_api_key: key || null,
        elevenlabs_voice_id: voiceId,
        elevenlabs_model_id: this.config.elevenlabs_model_id,
      });
      showToast('Zapisano konfigurację TTS.', 'success');
      this._afterSave('elevenlabs', 'tts');
    } catch (error) {
      showToast(error.message || 'Błąd zapisu konfiguracji TTS.', 'error');
    }
  }

  _afterSave(provider, panel) {
    const keyInput = document.getElementById(this._keyInputId(provider));
    if (keyInput) {
      keyInput.value = '';
      keyInput.type = 'password';
    }
    this._setKeyPlaceholder(provider, provider === 'groq' ? this.config.groq_api_key : this.config.elevenlabs_api_key);

    const eyeBtn = document.getElementById(this._toggleBtnId(provider));
    if (eyeBtn) {
      eyeBtn.innerHTML = Icons.Eye();
      eyeBtn.title = 'Pokaż klucz';
      eyeBtn.setAttribute('aria-label', eyeBtn.title);
    }

    const saveBtn = document.getElementById(this._saveBtnId(panel));
    if (saveBtn) saveBtn.disabled = true;
  }
}
