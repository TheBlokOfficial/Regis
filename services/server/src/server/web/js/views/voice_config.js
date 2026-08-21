import { getSenderId } from '../sender_id.js';
import { escapeAttr, escapeHtml } from '../utils/dom.js';
import { showToast } from '../utils/toast.js';

/**
 * Zakładka Głos — wyłącznie Satelity (status podłączonych/niezarejestrowanych
 * nadawców). Config dostawców STT/TTS przeniesiony do zakładki Dostawcy
 * (`views/providers_config.js`, pełny CRUD mirror LLM) — dawny płaski,
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
        <h3 class="section-heading">Satelity</h3>
        <div id="voice-satellites-section"></div>
      </div>
    `;
  }

  async init(apiClient, onNavigateToWorld) {
    this.apiClient = apiClient;
    this._onNavigateToWorld = onNavigateToWorld;

    await this._loadAndRenderSatellites();
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
