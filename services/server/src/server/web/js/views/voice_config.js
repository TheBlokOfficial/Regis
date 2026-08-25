import { initClientConfigForm } from './voice/voice_client_config_form.js';
import { initClientsDashboard } from './voice/voice_clients_dashboard.js';
import { renderVoiceConfigLayoutMarkup } from './voice/voice_client_template.js';

/**
 * Zakładka Klienci (dawniej Głos) — cienki "klej" spinający dwie niezależne
 * odpowiedzialności, wydzielone tym samym wzorcem `renderXMarkup`/`initX` co
 * `ChatView`/`chat/*`: (1) `voice/voice_client_config_form.js` — formularz progu
 * wake-worda + VAD; (2) `voice/voice_clients_dashboard.js` — dashboard klientów na
 * żywo (SSE przez `voice/voice_clients_watch_channel.js`, mirror `chat_watch_channel.js`,
 * ale strumień globalny, nie per-sesja). Podział 1:1 odzwierciedla dwie role, jakie ta
 * zakładka od dawna pełniła (patrz niżej).
 *
 * Config dostawców STT/TTS przeniesiony do zakładki Dostawcy
 * (`views/providers_config.js`, pełny CRUD mirror LLM) — dawny płaski,
 * jednosslotowy formularz żył nad shimem `GET/PUT /api/v1/voice/providers/config`;
 * shim został usunięty razem z tym formularzem, gdy okazało się, że po
 * przenosinach nikt go już nie woła.
 */
export class VoiceConfigView {
  constructor() {
    this.apiClient = null;
    // Formularz configu i dashboard klientów są tworzone raz (patrz `_ensureModules`) i
    // przetrwają wielokrotne wizyty na zakładce Klienci — `VoiceConfigView` jest instancją
    // długożyjącą (`SettingsView` tworzy ją raz), ale `render()`/`init()` uruchamiają się
    // przy każdym przełączeniu na tę sekcję (patrz `settings.js#activateSection`). Dashboard
    // MUSI przetrwać ponowne `init()` — inaczej świeży `initClientsDashboard()` przy każdej
    // wizycie tworzyłby nowy kanał SSE, osierocając (bez abortu) poprzedni.
    this._configForm = null;
    this._clientsDashboard = null;
  }

  render() {
    return renderVoiceConfigLayoutMarkup();
  }

  async init(apiClient) {
    this.apiClient = apiClient;
    this._ensureModules();

    await this._configForm.load();
    await this._clientsDashboard.load();
    this._clientsDashboard.openWatch();
  }

  _ensureModules() {
    if (!this._configForm) {
      this._configForm = initClientConfigForm({ apiClient: this.apiClient });
    }
    if (!this._clientsDashboard) {
      this._clientsDashboard = initClientsDashboard({ apiClient: this.apiClient });
    }
  }
}
