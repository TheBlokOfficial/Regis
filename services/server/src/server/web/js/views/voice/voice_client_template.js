import { Icons } from '../../icons.js';
import { escapeAttr, escapeHtml } from '../../utils/dom.js';
import { shortSenderId } from '../../utils/sender_label.js';

/**
 * Czyste funkcje renderujące HTML zakładki Klienci — wydzielone z `VoiceConfigView`
 * (wzorzec `renderXMarkup` z `components/select.js`, ten sam co `chat/chat_template.js`).
 * Zero dostępu do `this`/DOM, tylko stringi. Stałe/helpery dotyczące KSZTAŁTU danych
 * (`STATE_LABELS`, `isVoiceClient`, `hasUnknownCapabilities`) mieszkają tu razem z
 * szablonem, bo obie strony (initial render i live SSE update w
 * `voice_clients_dashboard.js`) muszą się zgadzać co do tych samych etykiet/reguł.
 */

// Mapowanie SessionState.name (server/voice/session.py) -> etykieta PL widoczna na karcie.
export const STATE_LABELS = {
  LISTENING_WAKEWORD: 'Nasłuchiwanie',
  RECORDING_UTTERANCE: 'Nagrywanie',
  PROCESSING: 'Przetwarzanie',
  SYNTHESIZING: 'Synteza mowy',
  SPEAKING: 'Odpowiada',
};

// Wartości `ClientCapability` (server/world/models.py) — jedyne źródło prawdy o tym,
// czym klient jest. UI NIE zgaduje typu (dawniej: porównanie z własnym localStorage,
// przez co każdy inny klient tekstowy wyglądał jak satelita).
const CAP_SPEAKER = 'speaker';
const CAP_MIC = 'mic';

export function isVoiceClient(capabilities) {
  const caps = capabilities || [];
  return caps.includes(CAP_SPEAKER) || caps.includes(CAP_MIC);
}

// Klient zarejestrowany, zanim capabilities w ogóle istniały (`senders.json` sprzed tej
// zmiany). Pokazujemy to WPROST, zamiast renderować go jak klienta tekstowego: World
// zbuduje mu tekstowe ramowanie odpowiedzi i odrzuci `speak_in_room` na niego, więc
// cicha, wyglądająca poprawnie karta ukrywałaby realnie złe zachowanie. Naprawa to
// wyrejestrowanie i ponowna rejestracja (jedno kliknięcie w zakładce Świat + tutaj).
export function hasUnknownCapabilities(capabilities) {
  return (capabilities || []).length === 0;
}

export function renderVoiceConfigLayoutMarkup() {
  return `
    <div class="view-shell">
      <h3 class="section-heading">Konfiguracja klienta</h3>
      <div id="voice-client-config-section"></div>

      <h3 class="section-heading">Klienci</h3>
      <div id="voice-clients-section"></div>
    </div>
  `;
}

export function renderClientConfigErrorMarkup() {
  return `<p class="voice-empty-hint">Nie udało się wczytać konfiguracji.</p>`;
}

/** Co realnie działa w runtime — nie co skonfigurowano.
 *
 * Serwer po cichu degraduje się do atrap, gdy czegoś brakuje: pusty klucz API →
 * `Mock*`, brak/nieistniejący plik modelu → `ThresholdEnergyWakeWordDetector`
 * (placeholder reagujący na samą głośność, nie na słowo "Regis"). W logu jest o
 * tym linijka przy starcie, ale bez tego wiersza w UI strojenie progu pewności
 * przy niezaładowanym modelu byłoby szukaniem problemu w złym miejscu.
 */
export function renderPipelineStatusMarkup(status) {
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

export function renderClientConfigFormMarkup(config, status) {
  const thresholdPct = Math.round(config.wakeword_threshold * 100);

  // Zwykłe pola tekstowe (nie type="number") — natywne strzałki góra/dół przeglądarki
  // wyglądają brzydko/niespójnie z resztą UI. Parsowanie/walidacja w JS przy zapisie.
  return `
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
      ${renderPipelineStatusMarkup(status)}
      <div class="form-actions">
        <button class="btn" id="voice-btn-save-client-config">Zapisz</button>
      </div>
    </div>
  `;
}

export function renderPendingRowMarkup(senderId, isThisBrowser) {
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
//
// `isOnline`/`state`/`hasPendingCapabilities` przychodzą jako gotowe wartości z
// `voice_clients_dashboard.js` (pochodzą z jego stanu SSE) — funkcja zostaje czysta.
export function renderClientCardMarkup(sender, { isOnline, state, hasPendingCapabilities }) {
  const senderId = sender.sender_id;
  const isUnknown = hasUnknownCapabilities(sender.capabilities);
  const isVoice = isVoiceClient(sender.capabilities);
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
    metaText = hasPendingCapabilities ? 'Można naprawić jednym kliknięciem' : 'Podłącz klienta, by odczytać możliwości';
  } else if (isVoice) {
    badgeHtml = `<span class="badge-chip voice-client-online-badge ${isOnline ? 'is-online' : 'is-offline'}" data-role="online-badge">${isOnline ? 'online' : 'offline'}</span>`;
    statusIconHtml = `<div class="voice-client-mic-status" data-role="mic-icon" title="Wake-word">${Icons.Mic()}</div>`;
    metaText = stateLabel;
  } else {
    badgeHtml = '<span class="badge-chip voice-client-online-badge" data-role="online-badge">tekstowy</span>';
    statusIconHtml = `<div class="voice-client-mic-status" data-role="mic-icon" title="Klient tekstowy">${Icons.MessageSquare()}</div>`;
    metaText = 'Klient tekstowy';
  }

  const canRepair = isUnknown && hasPendingCapabilities;
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
