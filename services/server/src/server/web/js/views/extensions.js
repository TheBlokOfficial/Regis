import { HomeAssistantExtensionView } from './extensions/home_assistant_view.js';
import { WorldPromptsView } from './world_prompts_view.js';

/**
 * Widok konfiguracji świata — jedna, ciągła przewijana strona: najpierw
 * Konfiguracja (Home Assistant + satelity), potem, po lekko widocznej
 * kresce, Prompty (profile tożsamości Świata — World jest jedynym autorem
 * promptu tury, gdy podłączony, patrz `world_prompts_view.js`). Bez
 * przełącznika/pod-zakładek — obie sekcje widoczne naraz.
 */
export class ExtensionsView {
  constructor() {
    /** @type {import('../network/api_client.js').ApiClient|null} */
    this.apiClient = null;
    this.configView = new HomeAssistantExtensionView();
    this.promptsView = new WorldPromptsView();
  }

  render() {
    return `
      <div class="view-shell">
        <div id="extensions-config-mount">
          <div class="card card-loading">Ładowanie konfiguracji Świata...</div>
        </div>
        <h3 class="section-heading section-heading--spaced-sm">Prompty</h3>
        <div class="world-prompts-panel" id="world-prompts-panel"></div>
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
  }

  hasUnsavedChanges() {
    return Boolean(this.promptsView.hasUnsavedChanges?.());
  }

  // --------------------------------------------------------------------------
  // Toast — identyczny wzorzec co `WorldPromptsView`
  // --------------------------------------------------------------------------

  _showToast(message, type = 'success') {
    let toastContainer = document.getElementById('toast-container');
    if (!toastContainer) {
      toastContainer = document.createElement('div');
      toastContainer.id = 'toast-container';
      toastContainer.className = 'toast-container';
      document.body.appendChild(toastContainer);
    }

    const toast = document.createElement('div');
    toast.className = `toast-notification toast-${type}`;
    toast.innerHTML = `<span>${escapeHtml(message)}</span>`;
    toastContainer.appendChild(toast);

    setTimeout(() => {
      toast.classList.add('toast-leaving');
      setTimeout(() => toast.remove(), 200);
    }, 3000);
  }
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str ?? '';
  return div.innerHTML;
}
