import { HomeAssistantExtensionView } from './extensions/home_assistant_view.js';

/**
 * Widok konfiguracji świata — dziś jeden, konkretny silnik (Home Assistant +
 * satelity), nie generyczna lista wymiennych rozszerzeń. Montuje bezpośrednio
 * widok domenowy, bez pośredniej warstwy listy/przełącznika enabled.
 */
export class ExtensionsView {
  constructor() {
    /** @type {import('../network/api_client.js').ApiClient|null} */
    this.apiClient = null;
    this.detailView = null;
  }

  render() {
    return `<div class="extensions-panel-detail" id="extensions-panel-detail"></div>`;
  }

  async init(apiClient) {
    this.apiClient = apiClient;
    const panel = document.getElementById('extensions-panel-detail');
    if (!panel) return;
    panel.innerHTML = `<div class="extensions-detail-loading">Ładowanie...</div>`;
    this.detailView = new HomeAssistantExtensionView();
    await this.detailView.mount(panel, this.apiClient, this._showToast.bind(this));
  }

  // --------------------------------------------------------------------------
  // Toast — identyczny wzorzec co `AgentsView`
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
