import { Icons } from '../icons.js';
import { HomeAssistantExtensionView } from './extensions/home_assistant_view.js';

/**
 * Jawny rejestr widoków szczegółowych per rozszerzenie — klucz to `extension_id`
 * z REST (`GET /api/v1/extensions`), ten sam identyfikator co `plugin_id` w
 * kernelu. Brak wpisu dla danego ID jest zamierzonym, miękkim niepowodzeniem:
 * karta rozszerzenia nadal się renderuje i przełącza, tylko klik nie otwiera
 * panelu szczegółów (analogicznie do pominięcia kolidującego narzędzia w
 * `Gateway.build()` — widok nigdy się nie wywala z powodu nieznanego ID).
 */
const EXTENSION_DETAIL_VIEWS = {
  home_assistant: HomeAssistantExtensionView,
};

/**
 * Widok listy rozszerzeń — lista kart (lewa kolumna) z przełącznikiem enabled,
 * panel szczegółów (prawa kolumna) wzorowany na layoutcie `AgentsView`.
 */
export class ExtensionsView {
  constructor() {
    /** @type {import('../network/api_client.js').ApiClient|null} */
    this.apiClient = null;
    /** @type {Array<{id:string, label:string, enabled:boolean}>} */
    this.extensions = [];
    this.selectedId = null;
  }

  render() {
    return `
      <div class="extensions-layout" id="extensions-layout">
        <div class="extensions-panel-list">
          <div class="extensions-panel-header">
            <span class="extensions-panel-title">Rozszerzenia</span>
          </div>
          <div class="extensions-list" id="extensions-list">
            <div class="extensions-list-loading">Ładowanie...</div>
          </div>
          <div class="extensions-panel-footer" id="extensions-panel-footer"></div>
        </div>
        <div class="extensions-panel-detail" id="extensions-panel-detail">
          <div class="extensions-detail-empty">
            <div class="extensions-detail-empty-icon">${Icons.Puzzle()}</div>
            <p>Wybierz rozszerzenie z listy.</p>
          </div>
        </div>
      </div>
    `;
  }

  async init(apiClient) {
    this.apiClient = apiClient;
    await this._loadAndRender();
  }

  async _loadAndRender(selectId = null) {
    const data = await this.apiClient.getExtensions();
    if (!data) {
      this._renderListError();
      return;
    }
    this.extensions = data.extensions || [];

    if (selectId && this.extensions.some((e) => e.id === selectId)) {
      this.selectedId = selectId;
    }

    this._renderList();
    if (this.selectedId) {
      const selected = this.extensions.find((e) => e.id === this.selectedId);
      if (selected) this._renderDetail(selected);
    }
  }

  _renderListError() {
    const list = document.getElementById('extensions-list');
    if (list) list.innerHTML = `<div class="extensions-list-error">Błąd ładowania listy rozszerzeń.</div>`;
  }

  _renderList() {
    const list = document.getElementById('extensions-list');
    const footer = document.getElementById('extensions-panel-footer');
    if (!list) return;

    if (this.extensions.length === 0) {
      list.innerHTML = `<div class="extensions-list-empty"><p>Brak zarejestrowanych rozszerzeń.</p></div>`;
      if (footer) footer.innerHTML = '';
      return;
    }

    list.innerHTML = this.extensions
      .map((ext) => {
        const isSelected = ext.id === this.selectedId;
        const hasDetailView = Boolean(EXTENSION_DETAIL_VIEWS[ext.id]);
        return `
          <div class="extensions-card ${isSelected ? 'selected' : ''}" data-id="${escapeAttr(ext.id)}" role="button" tabindex="0" ${isSelected ? 'aria-current="true"' : ''}>
            <div class="extensions-card-row">
              <span class="extensions-card-name" title="${escapeAttr(ext.label)}">${escapeHtml(ext.label)}</span>
              <label class="extensions-toggle" title="${ext.enabled ? 'Wyłącz rozszerzenie' : 'Włącz rozszerzenie'}">
                <input type="checkbox" class="extensions-toggle-input" data-toggle-id="${escapeAttr(ext.id)}" ${ext.enabled ? 'checked' : ''} />
                <span class="extensions-toggle-track"></span>
              </label>
            </div>
            ${!hasDetailView ? '<span class="extensions-card-hint">Brak konfiguracji — tylko przełącznik</span>' : ''}
          </div>
        `;
      })
      .join('');

    list.querySelectorAll('.extensions-card').forEach((el) => {
      el.addEventListener('click', (e) => {
        if (e.target.closest('.extensions-toggle')) return;
        this._selectExtension(el.getAttribute('data-id'));
      });
      el.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          this._selectExtension(el.getAttribute('data-id'));
        }
      });
    });

    list.querySelectorAll('.extensions-toggle-input').forEach((input) => {
      input.addEventListener('click', (e) => e.stopPropagation());
      input.addEventListener('change', (e) => this._handleToggle(e.target.getAttribute('data-toggle-id'), e.target.checked));
    });

    if (footer) {
      const count = this.extensions.length;
      footer.textContent = count === 1 ? '1 rozszerzenie' : `${count} rozszerzeń`;
    }
  }

  async _handleToggle(extensionId, enabled) {
    try {
      await this.apiClient.setExtensionEnabled(extensionId, enabled);
      this._showToast(enabled ? 'Rozszerzenie włączone.' : 'Rozszerzenie wyłączone.', 'success');
      await this._loadAndRender(this.selectedId);
    } catch (error) {
      this._showToast(error.message || 'Błąd przełączania rozszerzenia.', 'error');
      await this._loadAndRender(this.selectedId);
    }
  }

  /**
   * Klik na kartę bez zarejestrowanego widoku szczegółowego jest zamierzonym,
   * miękkim niepowodzeniem — karta pozostaje wybrana wizualnie, panel po
   * prawej po prostu informuje o braku konfiguracji, zero wyjątku.
   */
  async _selectExtension(id) {
    this.selectedId = id;
    this._renderList();
    const ext = this.extensions.find((e) => e.id === id);
    if (ext) await this._renderDetail(ext);
  }

  async _renderDetail(ext) {
    const panel = document.getElementById('extensions-panel-detail');
    if (!panel) return;

    const ViewClass = EXTENSION_DETAIL_VIEWS[ext.id];
    if (!ViewClass) {
      panel.innerHTML = `
        <div class="extensions-detail-empty">
          <div class="extensions-detail-empty-icon">${Icons.Puzzle()}</div>
          <p><strong>${escapeHtml(ext.label)}</strong> nie ma dedykowanego widoku konfiguracji.</p>
          <p class="extensions-detail-empty-hint">Włącz lub wyłącz je przełącznikiem na liście.</p>
        </div>
      `;
      return;
    }

    panel.innerHTML = `<div class="extensions-detail-loading">Ładowanie...</div>`;
    const detailView = new ViewClass();
    await detailView.mount(panel, this.apiClient, this._showToast.bind(this));
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

function escapeAttr(str) {
  return escapeHtml(str).replace(/"/g, '&quot;');
}
