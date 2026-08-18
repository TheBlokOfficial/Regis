import { Icons } from '../icons.js';

/**
 * Zakładka Kernel — zarządzanie dostawcami LLM (dawniej wtopione w Dashboard).
 * Czysty refaktor UI: ta sama logika/API co wcześniej w `dashboard.js`
 * (`apiClient.getLLMProviders/getProviderSchemas/createLLMProvider/
 * setActiveLLMProvider/deleteLLMProvider`), bez zmian backendu — pełna
 * zakładka renderuje listę bezpośrednio na stronie zamiast w modalu.
 */
export class KernelConfigView {
  render() {
    return `
      <div class="dashboard-grid">
        <div class="page-header">
          <div>
            <h2 class="page-header-title">Kernel</h2>
            <p class="page-header-desc">Dostawcy LLM zasilający rdzeń agenta (pętla ReAct, generowanie odpowiedzi).</p>
          </div>
          <button class="btn btn-primary btn-sm" id="kernel-btn-toggle-add-form">+ Dodaj Dostawcę</button>
        </div>

        <div class="card form-card hidden" id="kernel-card-add-provider-form">
          <button class="btn-close-corner" id="kernel-btn-close-form" title="Zamknij formularz">✕</button>
          <div class="form-card-title-row">
            <span class="form-card-title">Nowa Instancja Dostawcy LLM</span>
          </div>
          <form id="kernel-form-create-provider">
            <div class="form-row">
              <div class="form-group">
                <label for="kernel-provider-type">Typ Dostawcy</label>
                <select id="kernel-provider-type" class="form-control" required>
                  <option value="">Ładowanie dostępnych typów...</option>
                </select>
              </div>
              <div class="form-group">
                <label for="kernel-provider-name">Nazwa Wyświetlana</label>
                <input type="text" id="kernel-provider-name" class="form-control" placeholder="np. Nowy Dostawca" required />
              </div>
            </div>
            <div class="form-row form-row-wrap" id="kernel-dynamic-options-container"></div>
            <div class="form-actions">
              <button type="submit" class="btn btn-primary">Zapisz Instancję</button>
              <button type="button" class="btn btn-subtle" id="kernel-btn-cancel-form">Anuluj</button>
            </div>
          </form>
        </div>

        <div class="providers-list" id="kernel-providers-list">
          <div class="card card-loading">Ładowanie dostawców...</div>
        </div>
      </div>
    `;
  }

  async init(apiClient) {
    this.apiClient = apiClient;
    await this.refresh();

    document.getElementById('kernel-btn-toggle-add-form')?.addEventListener('click', () => this._showForm());
    document.getElementById('kernel-btn-close-form')?.addEventListener('click', () => this._hideForm());
    document.getElementById('kernel-btn-cancel-form')?.addEventListener('click', () => this._hideForm());

    await this._initForm();
  }

  async refresh() {
    const listContainer = document.getElementById('kernel-providers-list');
    if (!listContainer) return;

    const data = await this.apiClient.getLLMProviders();
    if (!data || !data.providers || data.providers.length === 0) {
      listContainer.innerHTML = `<div class="card card-sm">Brak skonfigurowanych dostawców LLM.</div>`;
      return;
    }

    listContainer.innerHTML = `
      <div class="modal-provider-list">
        ${data.providers.map((p) => {
          const isActive = p.is_active;
          const modelName = p.options?.model || 'domyślny';
          const baseUrl = p.options?.base_url || (p.type === 'OPENROUTER' ? 'https://openrouter.ai/api/v1' : 'N/A');

          return `
            <div class="modal-provider-item ${isActive ? 'active' : ''}">
              <div class="modal-provider-main-row">
                <div class="modal-provider-title-group">
                  <span class="modal-provider-name">${escapeHtml(p.name)}</span>
                  <span class="badge badge-chip">${escapeHtml((p.type || 'LLM').toUpperCase())}</span>
                  ${
                    isActive
                      ? `<span class="badge badge-status badge-status-sm"><span class="status-dot-pulse"></span>Aktywny</span>`
                      : ''
                  }
                </div>
                <div class="modal-provider-actions">
                  ${
                    !isActive
                      ? `<button class="btn btn-subtle btn-sm kernel-btn-activate" data-id="${p.id}">Aktywuj</button>
                         <button class="btn btn-ghost-danger btn-sm kernel-btn-delete" data-id="${p.id}" title="Usuń z dysku">Usuń</button>`
                      : `<span class="text-active-indicator">${Icons.CheckCircle2()} Wybrany</span>`
                  }
                </div>
              </div>
              <div class="modal-meta-row">
                <span class="meta-tag">Model: <code>${escapeHtml(modelName)}</code></span>
                <span class="meta-tag">Base URL: <code>${escapeHtml(baseUrl)}</code></span>
              </div>
            </div>
          `;
        }).join('')}
      </div>
    `;

    listContainer.querySelectorAll('.kernel-btn-activate').forEach((btn) => {
      btn.addEventListener('click', async (e) => {
        const id = e.currentTarget.getAttribute('data-id');
        try {
          btn.disabled = true;
          await this.apiClient.setActiveLLMProvider(id);
          await this.refresh();
        } catch (err) {
          this.showToast(`Błąd aktywacji: ${err.message}`, 'error');
          btn.disabled = false;
        }
      });
    });

    listContainer.querySelectorAll('.kernel-btn-delete').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        const id = e.currentTarget.getAttribute('data-id');
        const actionsBox = e.currentTarget.parentElement;
        if (!actionsBox) return;

        actionsBox.innerHTML = `
          <div class="delete-confirm-inline">
            <span class="delete-confirm-text">Usunąć instancję?</span>
            <button class="btn-confirm-yes">Tak</button>
            <button class="btn-confirm-no">Nie</button>
          </div>
        `;

        actionsBox.querySelector('.btn-confirm-no')?.addEventListener('click', () => this.refresh());
        actionsBox.querySelector('.btn-confirm-yes')?.addEventListener('click', async () => {
          const yesBtn = actionsBox.querySelector('.btn-confirm-yes');
          try {
            yesBtn.disabled = true;
            yesBtn.textContent = '...';
            await this.apiClient.deleteLLMProvider(id);
            this.showToast('Instancja została usunięta z dysku.', 'success');
            await this.refresh();
          } catch (err) {
            this.showToast(`Błąd usuwania: ${err.message}`, 'error');
            await this.refresh();
          }
        });
      });
    });
  }

  _showForm() {
    document.getElementById('kernel-card-add-provider-form')?.classList.remove('hidden');
    this._renderOptions();
  }

  _hideForm() {
    const formCard = document.getElementById('kernel-card-add-provider-form');
    formCard?.classList.add('hidden');
    document.getElementById('kernel-form-create-provider')?.reset();
  }

  async _initForm() {
    const typeSelect = document.getElementById('kernel-provider-type');
    const nameInput = document.getElementById('kernel-provider-name');
    const optionsContainer = document.getElementById('kernel-dynamic-options-container');
    const form = document.getElementById('kernel-form-create-provider');
    if (!typeSelect || !nameInput || !optionsContainer || !form) return;

    this._nameInput = nameInput;
    this._optionsContainer = optionsContainer;

    const schemasResponse = await this.apiClient.getProviderSchemas();
    if (!schemasResponse || !schemasResponse.provider_types) {
      typeSelect.innerHTML = '<option value="">Błąd ładowania schematów API</option>';
      return;
    }

    this._providerTypes = schemasResponse.provider_types;
    typeSelect.innerHTML = this._providerTypes.map((pt) => `<option value="${pt.type}">${escapeHtml(pt.label)}</option>`).join('');

    typeSelect.addEventListener('change', () => this._renderOptions());
    this._renderOptions();

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const type = typeSelect.value;
      const name = nameInput.value;
      const options = {};
      optionsContainer.querySelectorAll('.modal-dynamic-opt-input').forEach((input) => {
        const optName = input.getAttribute('data-opt-name');
        if (optName) options[optName] = input.value;
      });

      try {
        await this.apiClient.createLLMProvider({ type, name, options });
        this._hideForm();
        await this.refresh();
      } catch (err) {
        this.showToast(`Błąd tworzenia dostawcy: ${err.message}`, 'error');
      }
    });
  }

  _renderOptions() {
    const typeSelect = document.getElementById('kernel-provider-type');
    if (!typeSelect || !this._providerTypes) return;
    const selectedSpec = this._providerTypes.find((pt) => pt.type === typeSelect.value);

    if (!selectedSpec || !selectedSpec.options_schema) {
      this._optionsContainer.innerHTML = '';
      return;
    }

    this._optionsContainer.innerHTML = selectedSpec.options_schema.map((opt) => `
      <div class="form-group form-group-min240">
        <label for="kernel-opt-${opt.name}">${escapeHtml(opt.label)}</label>
        <input
          type="${opt.type === 'password' ? 'password' : 'text'}"
          id="kernel-opt-${opt.name}"
          data-opt-name="${opt.name}"
          class="form-control modal-dynamic-opt-input"
          placeholder="${escapeHtml(opt.placeholder || '')}"
          value="${escapeHtml(opt.default_value || '')}"
          ${opt.required ? 'required' : ''}
        />
      </div>
    `).join('');

    if (selectedSpec.label) this._nameInput.value = `${selectedSpec.label}`;
  }

  showToast(message, type = 'info') {
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
    }, 3200);
  }
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
