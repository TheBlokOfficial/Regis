import { HomeAssistantExtensionView } from './extensions/home_assistant_view.js';
import { WorldPromptSectionsView } from './world_prompt_sections_view.js';
import { WorldPromptsView } from './world_prompts_view.js';
import { showToast } from '../utils/toast.js';

/**
 * Widok konfiguracji świata — jedna, ciągła przewijana strona: Konfiguracja
 * (Home Assistant + satelity), Prompty (profile tożsamości — treść STABILNA,
 * trafia na pozycję zerową kontekstu) i Kontekst tury (fakty ZMIENNE,
 * wstrzykiwane tuż przed każdym pytaniem).
 *
 * Kolejność sekcji odzwierciedla kolejność w prompcie: najpierw kim agent jest,
 * potem co widzi teraz. Bez przełącznika/pod-zakładek — wszystko widoczne naraz.
 */
export class ExtensionsView {
  constructor() {
    /** @type {import('../network/api_client.js').ApiClient|null} */
    this.apiClient = null;
    this.configView = new HomeAssistantExtensionView();
    this.promptsView = new WorldPromptsView();
    this.sectionsView = new WorldPromptSectionsView();
  }

  render() {
    return `
      <div class="view-shell">
        <div id="extensions-config-mount">
          <div class="card card-loading">Ładowanie konfiguracji Świata...</div>
        </div>
        <h3 class="section-heading section-heading--spaced-sm">Prompty</h3>
        <div class="world-prompts-panel" id="world-prompts-panel"></div>

        <h3 class="section-heading section-heading--spaced-sm">Kontekst tury</h3>
        <div id="world-prompt-sections-panel"></div>
      </div>
    `;
  }

  async init(apiClient) {
    this.apiClient = apiClient;

    const configMount = document.getElementById('extensions-config-mount');
    await this.configView.mount(configMount, apiClient, this._showToast.bind(this));

    const promptsPanel = document.getElementById('world-prompts-panel');
    promptsPanel.innerHTML = this.promptsView.render();
    await this.promptsView.init(apiClient);

    const sectionsPanel = document.getElementById('world-prompt-sections-panel');
    sectionsPanel.innerHTML = this.sectionsView.render();
    await this.sectionsView.init(apiClient);
  }

  hasUnsavedChanges() {
    // Sekcje kontekstu tury też liczą się jako niezapisane zmiany — lista żyje w
    // pamięci widoku do czasu jawnego "Zapisz", więc przełączenie zakładki bez
    // ostrzeżenia po cichu wyrzuciłoby całą pracę użytkownika.
    return Boolean(this.promptsView.hasUnsavedChanges?.() || this.sectionsView.hasUnsavedChanges?.());
  }

  _showToast(message, type = 'success') {
    showToast(message, type);
  }
}
