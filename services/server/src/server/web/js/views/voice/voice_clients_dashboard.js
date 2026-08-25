import { confirmModal } from '../../modal_confirm.js';
import { getSenderId } from '../../sender_id.js';
import { showToast } from '../../utils/toast.js';
import { STATE_LABELS, renderClientCardMarkup, renderPendingRowMarkup } from './voice_client_template.js';
import { createClientsWatchChannel } from './voice_clients_watch_channel.js';

// Ile trwa "zaświecenie" ikony mikrofonu + wyświetlenie pewności po wykryciu wake-worda —
// czysto efemeryczne (nic nie jest trwale zapisywane, patrz server/voice/events.py).
const WAKE_WORD_FLASH_MS = 1500;

// Capabilities deklarowane przez tę przeglądarkę przy rejestracji — nie ma mikrofonu
// ani głośnika w rozumieniu pipeline'u głosowego (nie łączy się przez /ws/voice/),
// jest czystym klientem tekstowym.
const BROWSER_CAPABILITIES = ['text'];

/**
 * Dashboard klientów na żywo — "Oczekujący" (połączeni, niezarejestrowani) + "Zarejestrowani"
 * (status online/offline, stan sesji, ikona mikrofonu reagująca na wake-word), zasilany
 * przez `GET .../clients/status` (hydratacja) + kanał SSE z `voice_clients_watch_channel.js`
 * (mirror `chat_watch_channel.js`, ale globalny strumień, nie per-sesja). Aktualizuje DOM
 * po `sender_id` bez przeładowania całej listy — pełny re-render (`load`) następuje tylko
 * przy connect/disconnect (zmiana zbioru online) albo rejestracji nowego klienta.
 *
 * Rejestracja nadawców żyje świadomie tutaj (dawniej: w `VoiceConfigView`), nie w zakładce
 * Świat: pierwszy kontakt z nieznanym nadawcą jest konceptualnie i pod maską domeną `voice`,
 * nie `world` — World zna wyłącznie zatwierdzone encje (nadawca + pokój), nigdy stan gniazda
 * WS. Przycisk "Zarejestruj" woła `POST /api/v1/world/senders` **od razu, bez pokoju** (World
 * i tak przyjmuje `room_id: null` — pokój przypisuje się później, przez picker w zakładce
 * Świat, `satellites_panel.js`, `POST` jest tam upsertem). Cross-domenowe wywołanie zapisu z
 * poziomu UI innej domeny jest tu świadomie dopuszczone — narusza własność danych dopiero
 * *renderowanie* cudzej domeny, nie samo wywołanie jej REST API.
 *
 * Ta przeglądarka (`getSenderId()`) jest traktowana jak każdy inny klient — płynie tymi
 * samymi listami `pending`/`registered`, tylko oznaczona (badge "ta przeglądarka"), zamiast
 * mieć osobny, jednoliniowy wpis poza listą. Nigdy nie łączy się przez `/ws/voice/`, więc w
 * karcie zarejestrowanej nie ma sensu pokazywać online/offline ani stanu sesji głosowej —
 * te pola są tam statyczne.
 */
export function initClientsDashboard({ apiClient }) {
  let registeredSenders = [];
  let connectedSenderIds = new Set();
  // Capabilities z handshake — potrzebne wyłącznie przy rejestracji oczekującego klienta;
  // po rejestracji źródłem prawdy jest już `SenderProfile.capabilities`.
  let pendingCapabilities = new Map();
  let senderStates = {};
  // sender_id -> stan karty żyjący wyłącznie w DOM (nigdy nie zapisywany) — trzymamy
  // referencje/timery tu, żeby móc je posprzątać przy re-renderze listy.
  const flashTimers = new Map();

  const watchChannel = createClientsWatchChannel(apiClient, {
    onConnected: (senderId) => onClientConnected(senderId),
    onDisconnected: (senderId) => onClientDisconnected(senderId),
    onStateChanged: (senderId, state) => onClientStateChanged(senderId, state),
    onWakeWordDetected: (senderId, score) => onClientWakeWordDetected(senderId, score),
  });

  async function load() {
    const [connected, senders, statesSnapshot] = await Promise.all([
      apiClient.getConnectedSenders(),
      apiClient.getSenders(),
      apiClient.getClientsStatus(),
    ]);
    pendingCapabilities = new Map((connected || []).map((c) => [c.sender_id, c.capabilities || []]));
    connectedSenderIds = new Set(pendingCapabilities.keys());
    registeredSenders = senders || [];
    senderStates = { ...statesSnapshot };
    render();
  }

  function render() {
    const container = document.getElementById('voice-clients-section');
    if (!container) return;

    const thisBrowserId = getSenderId();
    const registeredIds = new Set(registeredSenders.map((s) => s.sender_id));
    // Przeglądarka nigdy nie ma połączenia WS voice, więc nigdy nie trafia do
    // `connectedSenderIds` — dopisujemy ją do "Oczekujący" jawnie, żeby miała
    // tam wpis zamiast znikać z obu list dopóki ktoś jej nie zarejestruje.
    const pendingIds = new Set([...connectedSenderIds].filter((id) => !registeredIds.has(id)));
    if (!registeredIds.has(thisBrowserId)) pendingIds.add(thisBrowserId);
    const pending = [...pendingIds];

    const pendingHtml =
      pending.length === 0
        ? '<p class="voice-empty-hint">Brak oczekujących połączeń.</p>'
        : `
      <div class="voice-list">
        ${pending.map((senderId) => renderPendingRowMarkup(senderId, senderId === thisBrowserId)).join('')}
      </div>
    `;

    const registeredHtml =
      registeredSenders.length === 0
        ? '<p class="voice-empty-hint">Brak zarejestrowanych klientów.</p>'
        : `
      <div class="voice-client-card-list">
        ${registeredSenders
          .map((s) =>
            renderClientCardMarkup(s, {
              isOnline: connectedSenderIds.has(s.sender_id),
              state: senderStates[s.sender_id],
              hasPendingCapabilities: pendingCapabilities.has(s.sender_id),
            })
          )
          .join('')}
      </div>
    `;

    container.innerHTML = `
      <h4 class="section-subheading">Oczekujący</h4>
      ${pendingHtml}

      <h4 class="section-subheading">Zarejestrowani</h4>
      ${registeredHtml}
    `;

    container.querySelectorAll('[data-register-sender]')?.forEach((btn) => {
      btn.addEventListener('click', () => registerSender(btn.getAttribute('data-register-sender')));
    });
    // "Zarejestruj ponownie" to ten sam upsert co pierwsza rejestracja — różni się
    // tylko tym, że wpis już istnieje i ma puste capabilities.
    container.querySelectorAll('[data-repair-sender]')?.forEach((btn) => {
      btn.addEventListener('click', () => registerSender(btn.getAttribute('data-repair-sender')));
    });
    container.querySelectorAll('[data-delete-sender]')?.forEach((btn) => {
      btn.addEventListener('click', () => deleteSender(btn.getAttribute('data-delete-sender')));
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
          // Podwójnego żądania nie ma: `renameSender` przestawia `defaultValue` od razu,
          // więc następujący po nim blur widzi wartość niezmienioną i kończy się od razu.
          renameSender(senderId, input);
          input.blur();
        } else if (e.key === 'Escape') {
          e.preventDefault();
          input.value = input.defaultValue;
          input.blur();
        }
      });
      input.addEventListener('blur', () => renameSender(senderId, input));
    });
  }

  /** Zmiana nazwy to ten sam upsert co rejestracja — `POST /senders` jest jedynym
   * wejściem do rejestru klientów. Pokój i możliwości przepisujemy z bieżącego wpisu,
   * żeby nie zależeć od kolejności pól w żądaniu. */
  async function renameSender(senderId, input) {
    const previousName = input.defaultValue;
    const nextName = input.value.trim();
    if (nextName === previousName) return;

    // Przestawiamy PRZED żądaniem — to jest jednocześnie strażnik przed drugim zapisem
    // (Enter woła zapis wprost, a zaraz po nim leci jeszcze blur tego samego pola).
    input.defaultValue = nextName;
    const existing = registeredSenders?.find((s) => s.sender_id === senderId);
    try {
      await apiClient.registerSender({
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

  // Capabilities biorą się z handshake WS (satelita) albo są stałe dla tej przeglądarki
  // — nigdy nie są zgadywane. Bez nich World nie umiałby zbudować poprawnego ramowania
  // odpowiedzi ani odrzucić `speak_in_room` celującego w klienta bez głośnika.
  async function registerSender(senderId) {
    const capabilities = senderId === getSenderId() ? BROWSER_CAPABILITIES : pendingCapabilities?.get(senderId) || [];
    // Przypisanie do pokoju zachowujemy — ta sama metoda obsługuje pierwszą
    // rejestrację (pokoju jeszcze nie ma) i naprawę istniejącego wpisu, gdzie
    // wyzerowanie pokoju byłoby cichą utratą konfiguracji użytkownika.
    const existing = registeredSenders?.find((s) => s.sender_id === senderId);
    try {
      await apiClient.registerSender({
        sender_id: senderId,
        room_id: existing?.room_id ?? null,
        capabilities,
      });
      showToast('Zarejestrowano klienta.', 'success');
      await load();
    } catch (error) {
      showToast(error.message || 'Błąd rejestracji klienta.', 'error');
    }
  }

  /** Wyrejestrowanie — odwrotność rejestracji, więc mieszka tu, a nie w zakładce
   * Świat (ta zna wyłącznie encje już zatwierdzone i ich pokoje). */
  async function deleteSender(senderId) {
    const confirmed = await confirmModal({
      title: 'Usunąć rejestrację klienta?',
      message: 'Klient przestanie móc rozmawiać z agentem, dopóki nie zostanie zarejestrowany ponownie.',
      confirmLabel: 'Usuń',
      cancelLabel: 'Anuluj',
    });
    if (!confirmed) return;
    try {
      await apiClient.deleteSender(senderId);
      showToast('Usunięto rejestrację klienta.', 'success');
      await load();
    } catch (error) {
      showToast(error.message || 'Błąd usuwania rejestracji.', 'error');
    }
  }

  function onClientConnected(senderId) {
    connectedSenderIds.add(senderId);
    setOnlineBadge(senderId, true);
    // Nowy sender_id mógł nie istnieć wcześniej na liście (np. nowa satelita) —
    // pełny re-render żeby dołożyć/przenieść go do właściwej sekcji.
    if (!document.querySelector(`[data-sender-id="${CSS.escape(senderId)}"]`)) {
      render();
    }
  }

  function onClientDisconnected(senderId) {
    connectedSenderIds.delete(senderId);
    delete senderStates[senderId];
    setOnlineBadge(senderId, false);
  }

  function onClientStateChanged(senderId, state) {
    senderStates[senderId] = state;
    const card = document.querySelector(`[data-sender-id="${CSS.escape(senderId)}"]`);
    const stateEl = card?.querySelector('[data-role="state-text"]');
    if (stateEl) stateEl.textContent = STATE_LABELS[state] || state;
  }

  function onClientWakeWordDetected(senderId, score) {
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

    const existingTimer = flashTimers.get(senderId);
    if (existingTimer) clearTimeout(existingTimer);
    flashTimers.set(
      senderId,
      setTimeout(() => {
        micEl.classList.remove('is-detected');
        confidenceEl.classList.remove('is-visible');
        flashTimers.delete(senderId);
      }, WAKE_WORD_FLASH_MS)
    );
  }

  function setOnlineBadge(senderId, isOnline) {
    const card = document.querySelector(`[data-sender-id="${CSS.escape(senderId)}"]`);
    const badge = card?.querySelector('[data-role="online-badge"]');
    if (!badge) return;
    badge.textContent = isOnline ? 'online' : 'offline';
    badge.classList.toggle('is-online', isOnline);
    badge.classList.toggle('is-offline', !isOnline);
  }

  function openWatch() {
    for (const timer of flashTimers.values()) clearTimeout(timer);
    flashTimers.clear();
    watchChannel.open();
  }

  return { load, openWatch };
}
