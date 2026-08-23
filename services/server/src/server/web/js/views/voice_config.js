import { Icons } from '../icons.js';
import { confirmModal } from '../modal_confirm.js';
import { getSenderId } from '../sender_id.js';
import { flashButtonResult, lockButtonForAction } from '../utils/button_flash.js';
import { escapeAttr, escapeHtml } from '../utils/dom.js';
import { senderLabel, shortSenderId } from '../utils/sender_label.js';
import { showToast } from '../utils/toast.js';

// Mapowanie SessionState.name (server/voice/session.py) -> etykieta PL widoczna na karcie.
const STATE_LABELS = {
  LISTENING_WAKEWORD: 'Nasłuchiwanie',
  RECORDING_UTTERANCE: 'Nagrywanie',
  PROCESSING: 'Przetwarzanie',
  SYNTHESIZING: 'Synteza mowy',
  SPEAKING: 'Odpowiada',
};

// Ile trwa "zaświecenie" ikony mikrofonu + wyświetlenie pewności po wykryciu wake-worda —
// czysto efemeryczne (nic nie jest trwale zapisywane, patrz server/voice/events.py).
const WAKE_WORD_FLASH_MS = 1500;

// Wartości `ClientCapability` (server/world/models.py) — jedyne źródło prawdy o tym,
// czym klient jest. UI NIE zgaduje typu (dawniej: porównanie z własnym localStorage,
// przez co każdy inny klient tekstowy wyglądał jak satelita).
const CAP_SPEAKER = 'speaker';
const CAP_MIC = 'mic';

// Capabilities deklarowane przez tę przeglądarkę przy rejestracji — nie ma mikrofonu
// ani głośnika w rozumieniu pipeline'u głosowego (nie łączy się przez /ws/voice/),
// jest czystym klientem tekstowym.
const BROWSER_CAPABILITIES = ['text'];

function isVoiceClient(capabilities) {
  const caps = capabilities || [];
  return caps.includes(CAP_SPEAKER) || caps.includes(CAP_MIC);
}

// Klient zarejestrowany, zanim capabilities w ogóle istniały (`senders.json` sprzed tej
// zmiany). Pokazujemy to WPROST, zamiast renderować go jak klienta tekstowego: World
// zbuduje mu tekstowe ramowanie odpowiedzi i odrzuci `speak_in_room` na niego, więc
// cicha, wyglądająca poprawnie karta ukrywałaby realnie złe zachowanie. Naprawa to
// wyrejestrowanie i ponowna rejestracja (jedno kliknięcie w zakładce Świat + tutaj).
function hasUnknownCapabilities(capabilities) {
  return (capabilities || []).length === 0;
}

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
 * jednosslotowy formularz żył nad shimem `GET/PUT /api/v1/voice/providers/config`;
 * shim został usunięty razem z tym formularzem, gdy okazało się, że po
 * przenosinach nikt go już nie woła.
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
 *
 * Ta przeglądarka (`getSenderId()`) jest traktowana jak każdy inny klient — płynie
 * tymi samymi listami `pending`/`registered`, tylko oznaczona (badge "ta przeglądarka"
 * / wariant karty `kind: 'browser'`), zamiast mieć osobny, jednoliniowy wpis poza
 * listą. Nigdy nie łączy się przez `/ws/voice/`, więc w karcie zarejestrowanej nie ma
 * sensu pokazywać online/offline ani stanu sesji głosowej — te pola są tam statyczne.
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

  async init(apiClient) {
    this.apiClient = apiClient;

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
    const [config, status] = await Promise.all([
      this.apiClient.getClientConfig(),
      this.apiClient.getVoiceStatus(),
    ]);
    this._voiceStatus = status;
    this._renderClientConfigSection(config);
  }

  /** Co realnie działa w runtime — nie co skonfigurowano.
   *
   * Serwer po cichu degraduje się do atrap, gdy czegoś brakuje: pusty klucz API →
   * `Mock*`, brak/nieistniejący plik modelu → `ThresholdEnergyWakeWordDetector`
   * (placeholder reagujący na samą głośność, nie na słowo "Regis"). W logu jest o
   * tym linijka przy starcie, ale bez tego wiersza w UI strojenie progu pewności
   * przy niezaładowanym modelu byłoby szukaniem problemu w złym miejscu.
   */
  _renderPipelineStatus() {
    const status = this._voiceStatus;
    if (!status) return '';

    const isPlaceholderWake = status.wakeword_detector === 'ThresholdEnergyWakeWordDetector';
    const item = (label, value, isFallback) =>
      `<span class="voice-pipeline-item${isFallback ? ' is-fallback' : ''}">
        <span class="voice-pipeline-label">${escapeHtml(label)}</span>
        <code>${escapeHtml(value)}</code>
      </span>`;

    return `
      <div class="voice-pipeline-status${status.is_production_ready ? '' : ' is-degraded'}">
        <div class="voice-pipeline-row">
          ${item('Wake-word', status.wakeword_detector, isPlaceholderWake)}
          ${item('STT', status.stt_provider, status.stt_provider.startsWith('Mock'))}
          ${item('TTS', status.tts_provider, status.tts_provider.startsWith('Mock'))}
        </div>
        ${
          status.is_production_ready
            ? ''
            : `<p class="voice-pipeline-warning">${Icons.AlertCircle()} ${
                isPlaceholderWake
                  ? 'Model wake-worda nie został załadowany — działa placeholder reagujący na głośność, nie na słowo. Strojenie progu pewności nic tu nie da; sprawdź <code>wakeword_model_path</code> w konfiguracji serwera.'
                  : 'Któryś dostawca to atrapa — skonfiguruj klucz API w zakładce Dostawcy.'
              }</p>`
        }
      </div>
    `;
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
        ${this._renderPipelineStatus()}
        <div class="form-actions">
          <button class="btn" id="voice-btn-save-client-config">Zapisz</button>
        </div>
      </div>
    `;

    document.getElementById('voice-btn-save-client-config')?.addEventListener('click', () => this._saveClientConfig());
  }

  // Wynik zapisu jest pokazywany BEZPOŚREDNIO na przycisku (checkmark/X, mirror
  // `config_panel.js::handleTestConnection` via `utils/button_flash.js`) — jeden
  // kanał informacji zamiast koloru na przycisku + osobnego toastu. Walidacja NaN
  // to jedyny wyjątek: to pre-flight przed wywołaniem API, przycisk jeszcze nic nie
  // "wie" o wyniku, więc zostaje jako toast.
  async _saveClientConfig() {
    const thresholdInput = document.getElementById('voice-input-threshold');
    const silenceInput = document.getElementById('voice-input-vad-silence');
    const amplitudeInput = document.getElementById('voice-input-vad-amplitude');
    const btn = document.getElementById('voice-btn-save-client-config');
    if (!thresholdInput || !silenceInput || !amplitudeInput || !btn) return;

    const thresholdPct = Number(thresholdInput.value);
    const silenceMs = Number(silenceInput.value);
    const amplitude = Number(amplitudeInput.value);
    if (Number.isNaN(thresholdPct) || Number.isNaN(silenceMs) || Number.isNaN(amplitude)) {
      showToast('Wszystkie pola muszą być liczbami.', 'error');
      return;
    }

    lockButtonForAction(btn);
    let ok = false;
    try {
      await this.apiClient.updateClientConfig({
        wakeword_threshold: thresholdPct / 100,
        vad_silence_duration_ms: silenceMs,
        vad_amplitude_threshold: amplitude,
      });
      ok = true;
    } catch {
      ok = false;
    }
    flashButtonResult(btn, ok, { successHtml: Icons.Check(), errorHtml: Icons.X() });
  }

  // --------------------------------------------------------------------------
  // Dashboard klientów — "Oczekujący" (połączeni, niezarejestrowani) + "Zarejestrowani"
  // (status online/offline, stan sesji, ikona mikrofonu). Ta przeglądarka płynie tymi
  // samymi listami co satelity (patrz `isThisBrowser` w `_renderPendingRow`/
  // `_renderClientCard`), tylko z innym badge/ikoną zamiast online/offline+mikrofon.
  // --------------------------------------------------------------------------

  async _loadAndRenderClients() {
    const [connected, senders, statesSnapshot] = await Promise.all([
      this.apiClient.getConnectedSenders(),
      this.apiClient.getSenders(),
      this.apiClient.getClientsStatus(),
    ]);
    // Capabilities z handshake — potrzebne wyłącznie przy rejestracji oczekującego
    // klienta; po rejestracji źródłem prawdy jest już `SenderProfile.capabilities`.
    this._pendingCapabilities = new Map((connected || []).map((c) => [c.sender_id, c.capabilities || []]));
    this._connectedSenderIds = new Set(this._pendingCapabilities.keys());
    this._registeredSenders = senders || [];
    this._senderStates = { ...statesSnapshot };
    this._renderClientsSection();
  }

  _renderClientsSection() {
    const container = document.getElementById('voice-clients-section');
    if (!container) return;

    const thisBrowserId = getSenderId();
    const registeredIds = new Set(this._registeredSenders.map((s) => s.sender_id));
    // Przeglądarka nigdy nie ma połączenia WS voice, więc nigdy nie trafia do
    // `_connectedSenderIds` — dopisujemy ją do "Oczekujący" jawnie, żeby miała
    // tam wpis zamiast znikać z obu list dopóki ktoś jej nie zarejestruje.
    const pendingIds = new Set([...this._connectedSenderIds].filter((id) => !registeredIds.has(id)));
    if (!registeredIds.has(thisBrowserId)) pendingIds.add(thisBrowserId);
    const pending = [...pendingIds];

    const pendingHtml =
      pending.length === 0
        ? '<p class="voice-empty-hint">Brak oczekujących połączeń.</p>'
        : `
      <div class="voice-list">
        ${pending
          .map((senderId) => this._renderPendingRow(senderId, senderId === thisBrowserId))
          .join('')}
      </div>
    `;

    const registeredHtml =
      this._registeredSenders.length === 0
        ? '<p class="voice-empty-hint">Brak zarejestrowanych klientów.</p>'
        : `
      <div class="voice-client-card-list">
        ${this._registeredSenders.map((s) => this._renderClientCard(s)).join('')}
      </div>
    `;

    container.innerHTML = `
      <h4 class="section-subheading">Oczekujący</h4>
      ${pendingHtml}

      <h4 class="section-subheading">Zarejestrowani</h4>
      ${registeredHtml}
    `;

    container.querySelectorAll('[data-register-sender]')?.forEach((btn) => {
      btn.addEventListener('click', () => this._registerSender(btn.getAttribute('data-register-sender')));
    });
    // "Zarejestruj ponownie" to ten sam upsert co pierwsza rejestracja — różni się
    // tylko tym, że wpis już istnieje i ma puste capabilities.
    container.querySelectorAll('[data-repair-sender]')?.forEach((btn) => {
      btn.addEventListener('click', () => this._registerSender(btn.getAttribute('data-repair-sender')));
    });
    container.querySelectorAll('[data-delete-sender]')?.forEach((btn) => {
      btn.addEventListener('click', () => this._deleteSender(btn.getAttribute('data-delete-sender')));
    });
    // Nazwa klienta — jedyne miejsce w całym UI, gdzie się ją nadaje (zakładka Świat
    // pokazuje ją read-only, patrz `extensions/ha/satellites_panel.js`). Zapis na Enter
    // albo utracie focusu; Escape przywraca poprzednią wartość bez żądania.
    container.querySelectorAll('[data-rename-sender]')?.forEach((input) => {
      const senderId = input.getAttribute('data-rename-sender');
      input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          // Zapis wprost, nie przez `blur()` — Enter ma zadziałać nawet wtedy, gdy
          // przeniesienie focusu z jakiegoś powodu nie wygeneruje zdarzenia blur.
          // Podwójnego żądania nie ma: `_renameSender` przestawia `defaultValue` od razu,
          // więc następujący po nim blur widzi wartość niezmienioną i kończy się od razu.
          this._renameSender(senderId, input);
          input.blur();
        } else if (e.key === 'Escape') {
          e.preventDefault();
          input.value = input.defaultValue;
          input.blur();
        }
      });
      input.addEventListener('blur', () => this._renameSender(senderId, input));
    });
  }

  /** Zmiana nazwy to ten sam upsert co rejestracja — `POST /senders` jest jedynym
   * wejściem do rejestru klientów. Pokój i możliwości przepisujemy z bieżącego wpisu,
   * żeby nie zależeć od kolejności pól w żądaniu. */
  async _renameSender(senderId, input) {
    const previousName = input.defaultValue;
    const nextName = input.value.trim();
    if (nextName === previousName) return;

    // Przestawiamy PRZED żądaniem — to jest jednocześnie strażnik przed drugim zapisem
    // (Enter woła zapis wprost, a zaraz po nim leci jeszcze blur tego samego pola).
    input.defaultValue = nextName;
    const existing = this._registeredSenders?.find((s) => s.sender_id === senderId);
    try {
      await this.apiClient.registerSender({
        sender_id: senderId,
        display_name: nextName,
        room_id: existing?.room_id ?? null,
        capabilities: existing?.capabilities || [],
      });
      if (existing) existing.display_name = nextName || null;
      showToast(nextName ? 'Zapisano nazwę klienta.' : 'Wyczyszczono nazwę klienta.', 'success');
    } catch (error) {
      input.defaultValue = previousName;
      input.value = previousName;
      showToast(error.message || 'Błąd zapisu nazwy klienta.', 'error');
    }
  }

  _renderPendingRow(senderId, isThisBrowser) {
    return `
      <div class="voice-list-row">
        <span class="voice-satellite-id" title="${escapeAttr(senderId)}">
          ${escapeHtml(shortSenderId(senderId))}
          ${isThisBrowser ? '<span class="badge-chip voice-browser-chip">ta przeglądarka</span>' : ''}
        </span>
        <button type="button" class="btn btn-sm btn-subtle" data-register-sender="${escapeAttr(senderId)}">Zarejestruj</button>
      </div>
    `;
  }

  // Karta zarejestrowanego klienta — kontener dyktuje rozmiar, dynamiczna treść
  // (badge online/offline, tekst stanu, pewność detekcji) NIGDY go nie zmienia:
  // stały 32×32 kwadrat na ikonę statusu (mirror `.agent-provider-card-check`,
  // `providers.css` — tylko `background-color`/`color` się przełącza) i zawsze
  // obecny w DOM span na pewność (toggle `opacity`, nie insert/remove).
  //
  // Wariant karty wynika WYŁĄCZNIE z `capabilities` zapisanych w World — klient bez
  // mikrofonu/głośnika nigdy nie łączy się przez `/ws/voice/`, więc online/offline i
  // stan sesji głosowej nie mają dla niego sensu; badge i tekst stanu są wtedy
  // statyczne, ale WYMIARY karty pozostają identyczne (kontener dyktuje rozmiar).
  _renderClientCard(sender) {
    const senderId = sender.sender_id;
    const isUnknown = hasUnknownCapabilities(sender.capabilities);
    const isVoice = isVoiceClient(sender.capabilities);
    const isOnline = this._connectedSenderIds.has(senderId);
    const state = this._senderStates[senderId];
    const stateLabel = state ? STATE_LABELS[state] || state : '—';

    let badgeHtml;
    let statusIconHtml;
    let metaText;
    if (isUnknown) {
      badgeHtml = '<span class="badge-chip voice-client-online-badge is-unknown" data-role="online-badge">nieznany</span>';
      statusIconHtml = `<div class="voice-client-mic-status" data-role="mic-icon" title="Brak zapisanych możliwości">${Icons.AlertCircle()}</div>`;
      // Naprawa wymaga PRAWDZIWYCH możliwości klienta, a te znamy wyłącznie z
      // handshake żywego połączenia. Offline nie da się tego odgadnąć — mówimy
      // wprost, zamiast dawać przycisk, który zapisałby pustą listę i niczego nie
      // naprawił.
      metaText = this._pendingCapabilities?.has(senderId)
        ? 'Można naprawić jednym kliknięciem'
        : 'Podłącz klienta, by odczytać możliwości';
    } else if (isVoice) {
      badgeHtml = `<span class="badge-chip voice-client-online-badge ${isOnline ? 'is-online' : 'is-offline'}" data-role="online-badge">${isOnline ? 'online' : 'offline'}</span>`;
      statusIconHtml = `<div class="voice-client-mic-status" data-role="mic-icon" title="Wake-word">${Icons.Mic()}</div>`;
      metaText = stateLabel;
    } else {
      badgeHtml = '<span class="badge-chip voice-client-online-badge" data-role="online-badge">tekstowy</span>';
      statusIconHtml = `<div class="voice-client-mic-status" data-role="mic-icon" title="Klient tekstowy">${Icons.MessageSquare()}</div>`;
      metaText = 'Klient tekstowy';
    }

    const canRepair = isUnknown && this._pendingCapabilities?.has(senderId);
    const repairBtn = isUnknown
      ? `<button type="button" class="btn btn-sm btn-subtle" data-repair-sender="${escapeAttr(senderId)}"
           ${canRepair ? '' : 'disabled title="Klient musi być podłączony, żeby odczytać jego możliwości"'}>
           Zarejestruj ponownie
         </button>`
      : '';

    return `
      <div class="voice-client-card" data-sender-id="${escapeAttr(senderId)}">
        <div class="voice-client-card-main">
          <div class="voice-client-card-title-row">
            <input type="text" class="voice-client-card-name-input" data-rename-sender="${escapeAttr(senderId)}"
              value="${escapeAttr(sender.display_name || '')}"
              placeholder="${escapeAttr(shortSenderId(senderId))}"
              title="${escapeAttr(senderId)}" aria-label="Nazwa klienta" />
            ${badgeHtml}
          </div>
          <div class="voice-client-card-meta">
            <span class="voice-client-state-text" data-role="state-text">${escapeHtml(metaText)}</span>
          </div>
        </div>
        <div class="voice-client-card-status">
          ${repairBtn}
          <span class="voice-client-confidence" data-role="confidence"></span>
          ${statusIconHtml}
          <button type="button" class="btn btn-ghost-danger btn-icon-square" data-delete-sender="${escapeAttr(senderId)}"
            title="Usuń rejestrację" aria-label="Usuń rejestrację">${Icons.Trash2()}</button>
        </div>
      </div>
    `;
  }

  // Capabilities biorą się z handshake WS (satelita) albo są stałe dla tej przeglądarki
  // — nigdy nie są zgadywane. Bez nich World nie umiałby zbudować poprawnego ramowania
  // odpowiedzi ani odrzucić `speak_in_room` celującego w klienta bez głośnika.
  async _registerSender(senderId) {
    const capabilities =
      senderId === getSenderId() ? BROWSER_CAPABILITIES : this._pendingCapabilities?.get(senderId) || [];
    // Przypisanie do pokoju zachowujemy — ta sama metoda obsługuje pierwszą
    // rejestrację (pokoju jeszcze nie ma) i naprawę istniejącego wpisu, gdzie
    // wyzerowanie pokoju byłoby cichą utratą konfiguracji użytkownika.
    const existing = this._registeredSenders?.find((s) => s.sender_id === senderId);
    try {
      await this.apiClient.registerSender({
        sender_id: senderId,
        room_id: existing?.room_id ?? null,
        capabilities,
      });
      showToast('Zarejestrowano klienta.', 'success');
      await this._loadAndRenderClients();
    } catch (error) {
      showToast(error.message || 'Błąd rejestracji klienta.', 'error');
    }
  }

  /** Wyrejestrowanie — odwrotność rejestracji, więc mieszka tu, a nie w zakładce
   * Świat (ta zna wyłącznie encje już zatwierdzone i ich pokoje). */
  async _deleteSender(senderId) {
    const confirmed = await confirmModal({
      title: 'Usunąć rejestrację klienta?',
      message: 'Klient przestanie móc rozmawiać z agentem, dopóki nie zostanie zarejestrowany ponownie.',
      confirmLabel: 'Usuń',
      cancelLabel: 'Anuluj',
    });
    if (!confirmed) return;
    try {
      await this.apiClient.deleteSender(senderId);
      showToast('Usunięto rejestrację klienta.', 'success');
      await this._loadAndRenderClients();
    } catch (error) {
      showToast(error.message || 'Błąd usuwania rejestracji.', 'error');
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
