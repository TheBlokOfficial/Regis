import { Icons } from '../icons.js';
import { getSenderId } from '../sender_id.js';
import { escapeAttr, escapeHtml } from '../utils/dom.js';
import { showToast } from '../utils/toast.js';

// Mapowanie SessionState.name (server/voice/session.py) -> etykieta PL widoczna na karcie.
const STATE_LABELS = {
  LISTENING_WAKEWORD: 'Nasłuchiwanie',
  RECORDING_UTTERANCE: 'Nagrywanie',
  PROCESSING: 'Przetwarzanie',
  SPEAKING: 'Odpowiada',
};

// Ile trwa "zaświecenie" ikony mikrofonu + wyświetlenie pewności po wykryciu wake-worda —
// czysto efemeryczne (nic nie jest trwale zapisywane, patrz server/voice/events.py).
const WAKE_WORD_FLASH_MS = 1500;

/**
 * Zakładka Klienci (dawniej Głos) — dwie role: (1) "Konfiguracja klienta", jeden
 * globalny formularz (próg wake-worda + parametry VAD, patrz
 * `_renderClientConfigSection`); (2) dashboard klientów na żywo — lista podzielona
 * na "Oczekujący" (połączeni, niezarejestrowani) i "Zarejestrowani" (status
 * online/offline, stan sesji, ikona mikrofonu reagująca na wake-word), zasilana
 * przez `GET .../clients/status` (hydratacja) + `GET .../clients/watch` (SSE, mirror
 * `ChatView.openWatch` — jeden długożyjący strumień, zdarzenia aktualizują DOM po
 * `sender_id`, zero trwałego zapisu po stronie klienta).
 *
 * Config dostawców STT/TTS przeniesiony do zakładki Dostawcy
 * (`views/providers_config.js`, pełny CRUD mirror LLM) — dawny płaski,
 * jednosslotowy formularz (shim `GET/PUT /api/v1/voice/providers/config`)
 * usunięty stąd; backendowy endpoint zostaje (nieużywany przez to UI, ale
 * tani do utrzymania jako headless kompatybilność).
 *
 * Rejestracja nadawców żyje świadomie **tutaj**, nie w zakładce Świat: pierwszy
 * kontakt z nieznanym nadawcą jest konceptualnie i pod maską domeną `voice`, nie
 * `world` — World zna wyłącznie zatwierdzone encje (nadawca + pokój), nigdy stan
 * gniazda WS. Przycisk "Zarejestruj" woła `POST /api/v1/world/senders` **od razu,
 * bez pokoju** (World i tak przyjmuje `room_id: null` — pokój przypisuje się później,
 * przez picker w zakładce Świat, `satellites_panel.js`, `POST` jest tam upsertem).
 * Cross-domenowe wywołanie zapisu z poziomu UI innej domeny jest tu świadomie
 * dopuszczone — narusza własność danych dopiero *renderowanie* cudzej domeny, nie
 * samo wywołanie jej REST API.
 */
export class VoiceConfigView {
  constructor() {
    this.apiClient = null;
    this._watchController = null;
    // sender_id -> stan karty żyjący wyłącznie w DOM (nigdy nie zapisywany) —
    // trzymamy referencje/timery tu, żeby móc je posprzątać przy re-renderze listy.
    this._flashTimers = new Map();
  }

  render() {
    return `
      <div class="view-shell">
        <h3 class="section-heading">Konfiguracja klienta</h3>
        <div id="voice-client-config-section"></div>

        <h3 class="section-heading">Klienci</h3>
        <div id="voice-clients-section"></div>
      </div>
    `;
  }

  async init(apiClient, onNavigateToWorld) {
    this.apiClient = apiClient;
    this._onNavigateToWorld = onNavigateToWorld;

    await this._loadAndRenderClientConfig();
    await this._loadAndRenderClients();
    this._openWatch();
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

    // Zwykłe pola tekstowe (nie type="number") — natywne strzałki góra/dół przeglądarki
    // wyglądają brzydko/niespójnie z resztą UI. Parsowanie/walidacja w JS przy zapisie.
    container.innerHTML = `
      <div class="form-card">
        <div class="form-row">
          <div class="form-group">
            <label for="voice-input-threshold">Próg pewności wake-worda (%)</label>
            <input type="text" inputmode="numeric" id="voice-input-threshold" class="form-control" value="${thresholdPct}" />
          </div>
          <div class="form-group">
            <label for="voice-input-vad-silence">Cisza po wypowiedzi (ms)</label>
            <input type="text" inputmode="numeric" id="voice-input-vad-silence" class="form-control" value="${config.vad_silence_duration_ms}" />
          </div>
          <div class="form-group">
            <label for="voice-input-vad-amplitude">Próg amplitudy VAD</label>
            <input type="text" inputmode="numeric" id="voice-input-vad-amplitude" class="form-control" value="${config.vad_amplitude_threshold}" />
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

    const thresholdPct = Number(thresholdInput.value);
    const silenceMs = Number(silenceInput.value);
    const amplitude = Number(amplitudeInput.value);
    if (Number.isNaN(thresholdPct) || Number.isNaN(silenceMs) || Number.isNaN(amplitude)) {
      showToast('Wszystkie pola muszą być liczbami.', 'error');
      return;
    }

    try {
      await this.apiClient.updateClientConfig({
        wakeword_threshold: thresholdPct / 100,
        vad_silence_duration_ms: silenceMs,
        vad_amplitude_threshold: amplitude,
      });
      showToast('Zapisano konfigurację klienta.', 'success');
    } catch (error) {
      showToast(error.message || 'Błąd zapisu konfiguracji klienta.', 'error');
    }
  }

  // --------------------------------------------------------------------------
  // Dashboard klientów — "Oczekujący" (połączeni, niezarejestrowani) + "Zarejestrowani"
  // (status online/offline, stan sesji, ikona mikrofonu). ID tej przeglądarki (nadawca
  // tekstowy, nigdy nie ma połączenia WS) zostaje osobnym, prostym wierszem — nie jest
  // satelitą, karta statusu (mic/stan) nie miałaby dla niej sensu.
  // --------------------------------------------------------------------------

  async _loadAndRenderClients() {
    const [connectedSenderIds, senders, statesSnapshot] = await Promise.all([
      this.apiClient.getConnectedSenders(),
      this.apiClient.getSenders(),
      this.apiClient.getClientsStatus(),
    ]);
    this._connectedSenderIds = new Set(connectedSenderIds || []);
    this._registeredSenders = senders || [];
    this._senderStates = { ...statesSnapshot };
    this._renderClientsSection();
  }

  _renderClientsSection() {
    const container = document.getElementById('voice-clients-section');
    if (!container) return;

    const thisBrowserId = getSenderId();
    const registeredIds = new Set(this._registeredSenders.map((s) => s.sender_id));
    const pending = [...this._connectedSenderIds].filter((id) => id !== thisBrowserId && !registeredIds.has(id));
    const registered = this._registeredSenders.filter((s) => s.sender_id !== thisBrowserId);
    const thisBrowserRegistered = registeredIds.has(thisBrowserId);

    const pendingHtml =
      pending.length === 0
        ? '<p class="voice-empty-hint">Brak oczekujących połączeń.</p>'
        : `
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
    `;

    const registeredHtml =
      registered.length === 0
        ? '<p class="voice-empty-hint">Brak zarejestrowanych klientów.</p>'
        : `
      <div class="voice-client-card-list">
        ${registered.map((s) => this._renderClientCard(s.sender_id)).join('')}
      </div>
    `;

    container.innerHTML = `
      <h4 class="section-subheading">Oczekujący</h4>
      ${pendingHtml}

      <h4 class="section-subheading">Zarejestrowani</h4>
      ${registeredHtml}

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

  // Karta zarejestrowanego klienta — kontener dyktuje rozmiar, dynamiczna treść
  // (badge online/offline, tekst stanu, pewność detekcji) NIGDY go nie zmienia:
  // stały 32×32 kwadrat na ikonę mikrofonu (mirror `.agent-provider-card-check`,
  // `providers.css` — tylko `background-color`/`color` się przełącza) i zawsze
  // obecny w DOM span na pewność (toggle `opacity`, nie insert/remove).
  _renderClientCard(senderId) {
    const isOnline = this._connectedSenderIds.has(senderId);
    const state = this._senderStates[senderId];
    const stateLabel = state ? STATE_LABELS[state] || state : '—';

    return `
      <div class="voice-client-card" data-sender-id="${escapeAttr(senderId)}">
        <div class="voice-client-card-main">
          <div class="voice-client-card-title-row">
            <span class="voice-client-card-name">${escapeHtml(senderId)}</span>
            <span class="badge-chip voice-client-online-badge ${isOnline ? 'is-online' : 'is-offline'}" data-role="online-badge">${isOnline ? 'online' : 'offline'}</span>
          </div>
          <div class="voice-client-card-meta">
            <span class="voice-client-state-text" data-role="state-text">${escapeHtml(stateLabel)}</span>
          </div>
        </div>
        <div class="voice-client-card-status">
          <span class="voice-client-confidence" data-role="confidence"></span>
          <div class="voice-client-mic-status" data-role="mic-icon" title="Wake-word">${Icons.Mic()}</div>
        </div>
      </div>
    `;
  }

  async _registerSender(senderId) {
    try {
      await this.apiClient.registerSender({ sender_id: senderId, room_id: null });
      showToast('Zarejestrowano nadawcę.', 'success');
      await this._loadAndRenderClients();
    } catch (error) {
      showToast(error.message || 'Błąd rejestracji nadawcy.', 'error');
    }
  }

  // --------------------------------------------------------------------------
  // Kanał obserwujący (GET .../clients/watch, SSE) — jeden, długożyjący strumień
  // dla WSZYSTKICH klientów naraz (mirror `ChatView.openWatch`, ale globalny, nie
  // per-sesja). Aktualizuje DOM po `sender_id` bez przeładowania całej listy —
  // pełny re-render (`_loadAndRenderClients`) następuje tylko przy connect/
  // disconnect (zmiana zbioru online) albo rejestracji nowego klienta.
  // --------------------------------------------------------------------------

  _openWatch() {
    this._closeWatch();
    const controller = new AbortController();
    this._watchController = controller;
    this._runWatchLoop(controller);
  }

  _closeWatch() {
    if (this._watchController) {
      this._watchController.abort();
      this._watchController = null;
    }
    for (const timer of this._flashTimers.values()) clearTimeout(timer);
    this._flashTimers.clear();
  }

  async _runWatchLoop(controller) {
    while (!controller.signal.aborted) {
      try {
        await this.apiClient.watchClients(
          {
            onConnected: (senderId) => this._onClientConnected(senderId),
            onDisconnected: (senderId) => this._onClientDisconnected(senderId),
            onStateChanged: (senderId, state) => this._onClientStateChanged(senderId, state),
            onWakeWordDetected: (senderId, score) => this._onClientWakeWordDetected(senderId, score),
          },
          controller.signal
        );
      } catch (err) {
        if (controller.signal.aborted) return;
        console.error('[VoiceConfigView] Kanał klientów przerwany, ponawiam za chwilę:', err);
      }
      if (controller.signal.aborted) return;
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
  }

  _onClientConnected(senderId) {
    this._connectedSenderIds.add(senderId);
    this._setOnlineBadge(senderId, true);
    // Nowy sender_id mógł nie istnieć wcześniej na liście (np. nowa satelita) —
    // pełny re-render żeby dołożyć/przenieść go do właściwej sekcji.
    if (!document.querySelector(`[data-sender-id="${CSS.escape(senderId)}"]`)) {
      this._renderClientsSection();
    }
  }

  _onClientDisconnected(senderId) {
    this._connectedSenderIds.delete(senderId);
    delete this._senderStates[senderId];
    this._setOnlineBadge(senderId, false);
  }

  _onClientStateChanged(senderId, state) {
    this._senderStates[senderId] = state;
    const card = document.querySelector(`[data-sender-id="${CSS.escape(senderId)}"]`);
    const stateEl = card?.querySelector('[data-role="state-text"]');
    if (stateEl) stateEl.textContent = STATE_LABELS[state] || state;
  }

  _onClientWakeWordDetected(senderId, score) {
    const card = document.querySelector(`[data-sender-id="${CSS.escape(senderId)}"]`);
    if (!card) return;
    const micEl = card.querySelector('[data-role="mic-icon"]');
    const confidenceEl = card.querySelector('[data-role="confidence"]');
    if (!micEl || !confidenceEl) return;

    micEl.classList.add('is-detected');
    if (typeof score === 'number') {
      confidenceEl.textContent = `${Math.round(score * 100)}%`;
      confidenceEl.classList.add('is-visible');
    }

    const existingTimer = this._flashTimers.get(senderId);
    if (existingTimer) clearTimeout(existingTimer);
    this._flashTimers.set(
      senderId,
      setTimeout(() => {
        micEl.classList.remove('is-detected');
        confidenceEl.classList.remove('is-visible');
        this._flashTimers.delete(senderId);
      }, WAKE_WORD_FLASH_MS)
    );
  }

  _setOnlineBadge(senderId, isOnline) {
    const card = document.querySelector(`[data-sender-id="${CSS.escape(senderId)}"]`);
    const badge = card?.querySelector('[data-role="online-badge"]');
    if (!badge) return;
    badge.textContent = isOnline ? 'online' : 'offline';
    badge.classList.toggle('is-online', isOnline);
    badge.classList.toggle('is-offline', !isOnline);
  }
}
