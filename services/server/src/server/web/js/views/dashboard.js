import { Icons } from '../icons.js';

/**
 * Moduł widoku głównego Dashboard z aktywnym dostawcą LLM i podglądem operacyjnym.
 */
export class DashboardView {
  render() {
    return `
      <div class="dashboard-grid">
        <!-- Minimalistyczny Nagłówek Strony -->
        <div class="page-header">
          <div>
            <h2 class="page-header-title">System Przeglądu</h2>
            <p class="page-header-desc">Monitorowanie i konfiguracja aktywnej instancji dostawcy LLM.</p>
          </div>
          <span class="badge-muted">v0.1.0</span>
        </div>

        <div id="active-provider-container">
          <div class="section-header-bar">
            <h3 class="section-title">Aktywny Dostawca LLM</h3>
            <span class="badge badge-chip">ŁADOWANIE</span>
          </div>
          <p class="dashboard-loading-text">Pobieranie danych o dostawcach...</p>
        </div>
      </div>
    `;
  }

  /**
   * Renderuje pojedynczą kartę aktywnego dostawcy w głównym widoku Dashboardu.
   */
  renderProvidersList(data, apiClient, refreshCallback) {
    const container = document.getElementById('active-provider-container');
    if (!container) return;

    if (!data || !data.providers || data.providers.length === 0) {
      container.innerHTML = `
        <div class="section-header-bar">
          <h3 class="section-title">Aktywny Dostawca LLM</h3>
        </div>
        <p class="dashboard-empty-desc">Brak skonfigurowanych dostawców LLM.</p>
        <button class="btn btn-primary" id="btn-open-manage-modal">
          + Dodaj Dostawcę
        </button>
      `;
      this.attachMainViewEvents(container, apiClient, refreshCallback);
      return;
    }

    const activeProvider = data.providers.find((p) => p.is_active) || data.providers[0];
    const modelName = activeProvider.options?.model || 'domyślny';
    const baseUrl = activeProvider.options?.base_url || (activeProvider.type === 'OPENROUTER' ? 'https://openrouter.ai/api/v1' : 'N/A');

    container.innerHTML = `
      <div class="dashboard-hero-top">
        <div>
          <div class="provider-section-label">Aktywny Dostawca LLM</div>
          <div class="dashboard-hero-name">${escapeHtml(activeProvider.name)}</div>
          <div class="dashboard-hero-model">${escapeHtml(modelName)}</div>
        </div>

        <div class="dashboard-hero-badges">
          <span class="badge badge-status">
            ${escapeHtml((activeProvider.type || 'LLM').toUpperCase())}
          </span>
          <span class="badge badge-status">
            <span class="status-dot-pulse"></span>Aktywny
          </span>
        </div>
      </div>

      <div class="dashboard-hero-endpoint">
        <div class="dashboard-hero-endpoint-label">Punkt Końcowy (Base URL)</div>
        <div class="dashboard-hero-endpoint-value">${escapeHtml(baseUrl)}</div>
      </div>

      <div class="dashboard-hero-footer">
        <button class="btn btn-primary" id="btn-open-manage-modal">
          <span>Zarządzaj Dostawcami</span>
          <span class="dashboard-hero-arrow">→</span>
        </button>
      </div>
    `;

    this.attachMainViewEvents(container, apiClient, refreshCallback);
  }

  attachMainViewEvents(container, apiClient, refreshCallback) {
    const btn = container.querySelector('#btn-open-manage-modal');
    if (btn) {
      btn.addEventListener('click', () => {
        this.openManageModal(apiClient, refreshCallback);
      });
    }
  }

  /**
   * Otwiera modal z pełnym zarządzaniem dostawcami LLM.
   */
  async openManageModal(apiClient, refreshCallback) {
    const overlay = document.getElementById('modal-overlay');
    const content = document.getElementById('modal-content');
    if (!overlay || !content) return;

    content.innerHTML = `
      <div class="modal-header">
        <h3 class="modal-title">Zarządzanie Dostawcami LLM</h3>
        <button class="btn-close-corner" id="btn-close-modal" title="Zamknij (Esc)">✕</button>
      </div>

      <div class="modal-list-header">
        <span class="modal-list-header-label">Skonfigurowane dostawce</span>
        <button class="btn btn-primary btn-sm" id="modal-btn-toggle-add-form">
          + Dodaj Dostawcę
        </button>
      </div>

      <!-- Formularz Dodawania (Ukryty domyślnie) -->
      <div class="card form-card hidden" id="modal-card-add-provider-form">
        <button class="btn-close-corner" id="modal-btn-close-form" title="Zamknij formularz">✕</button>

        <div class="form-card-title-row">
          <span class="form-card-title">Nowa Instancja Dostawcy LLM</span>
        </div>

        <form id="modal-form-create-provider">
          <div class="form-row">
            <div class="form-group">
              <label for="modal-provider-type">Typ Dostawcy</label>
              <select id="modal-provider-type" class="form-control" required>
                <option value="">Ładowanie dostępnych typów...</option>
              </select>
            </div>

            <div class="form-group">
              <label for="modal-provider-name">Nazwa Wyświetlana</label>
              <input type="text" id="modal-provider-name" class="form-control" placeholder="np. Nowy Dostawca" required />
            </div>
          </div>

          <div class="form-row form-row-wrap" id="modal-dynamic-options-container"></div>

          <div class="form-actions">
            <button type="submit" class="btn btn-primary">Zapisz Instancję</button>
            <button type="button" class="btn btn-subtle" id="modal-btn-cancel-form">Anuluj</button>
          </div>
        </form>
      </div>

      <!-- Kontener Listy Dostawców w Modalu -->
      <div class="providers-list" id="modal-providers-list">
        <div class="card card-loading">Ładowanie dostawców...</div>
      </div>
    `;

    // Animacja wejścia: dodaj klasę before-show, usuń ją po jednej klatce
    overlay.classList.add('modal-entering');
    overlay.classList.remove('hidden');
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        overlay.classList.remove('modal-entering');
      });
    });

    const closeModal = () => {
      overlay.classList.add('modal-closing');
      window.removeEventListener('keydown', handleEsc);
      setTimeout(() => {
        overlay.classList.remove('modal-closing');
        overlay.classList.add('hidden');
        content.innerHTML = '';
      }, 180);
    };

    const handleEsc = (e) => {
      if (e.key === 'Escape') closeModal();
    };

    window.addEventListener('keydown', handleEsc);
    document.getElementById('btn-close-modal').addEventListener('click', closeModal);
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) closeModal();
    });

    await this.refreshModalContent(apiClient, refreshCallback);
  }

  async refreshModalContent(apiClient, refreshCallback) {
    const listContainer = document.getElementById('modal-providers-list');
    if (!listContainer) return;

    const data = await apiClient.getLLMProviders();
    if (!data || !data.providers || data.providers.length === 0) {
      listContainer.innerHTML = `<div class="card card-sm">Brak skonfigurowanych dostawców LLM.</div>`;
    } else {
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
                        ? `<span class="badge badge-status badge-status-sm">
                             <span class="status-dot-pulse"></span>Aktywny
                           </span>`
                        : ''
                    }
                  </div>

                  <div class="modal-provider-actions">
                    ${
                      !isActive
                        ? `<button class="btn btn-subtle btn-sm modal-btn-activate" data-id="${p.id}">
                             Aktywuj
                           </button>
                           <button class="btn btn-ghost-danger btn-sm modal-btn-delete" data-id="${p.id}" title="Usuń z dysku">
                             Usuń
                           </button>`
                        : `<span class="text-active-indicator">
                             ${Icons.CheckCircle2()} Wybrany
                           </span>`
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

      listContainer.querySelectorAll('.modal-btn-activate').forEach((btn) => {
        btn.addEventListener('click', async (e) => {
          const id = e.currentTarget.getAttribute('data-id');
          try {
            btn.disabled = true;
            await apiClient.setActiveLLMProvider(id);
            if (refreshCallback) refreshCallback();
            await this.refreshModalContent(apiClient, refreshCallback);
          } catch (err) {
            this.showToast(`Błąd aktywacji: ${err.message}`, 'error');
            btn.disabled = false;
          }
        });
      });

      listContainer.querySelectorAll('.modal-btn-delete').forEach((btn) => {
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

          const yesBtn = actionsBox.querySelector('.btn-confirm-yes');
          const noBtn = actionsBox.querySelector('.btn-confirm-no');

          if (noBtn) {
            noBtn.addEventListener('click', () => {
              this.refreshModalContent(apiClient, refreshCallback);
            });
          }

          if (yesBtn) {
            yesBtn.addEventListener('click', async () => {
              try {
                yesBtn.disabled = true;
                yesBtn.textContent = '...';
                await apiClient.deleteLLMProvider(id);
                this.showToast('Instancja została usunięta z dysku.', 'success');
                if (refreshCallback) refreshCallback();
                await this.refreshModalContent(apiClient, refreshCallback);
              } catch (err) {
                this.showToast(`Błąd usuwania: ${err.message}`, 'error');
                await this.refreshModalContent(apiClient, refreshCallback);
              }
            });
          }
        });
      });
    }

    this.initModalForm(apiClient, refreshCallback);
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

  async initModalForm(apiClient, refreshCallback) {
    const formCard = document.getElementById('modal-card-add-provider-form');
    const toggleBtn = document.getElementById('modal-btn-toggle-add-form');
    const closeBtn = document.getElementById('modal-btn-close-form');
    const cancelBtn = document.getElementById('modal-btn-cancel-form');
    const form = document.getElementById('modal-form-create-provider');

    const typeSelect = document.getElementById('modal-provider-type');
    const nameInput = document.getElementById('modal-provider-name');
    const optionsContainer = document.getElementById('modal-dynamic-options-container');

    if (!formCard || !toggleBtn || !form || !typeSelect || !optionsContainer) return;
    if (typeSelect.dataset.initialized === 'true') return;

    typeSelect.dataset.initialized = 'true';

    const schemasResponse = await apiClient.getProviderSchemas();
    if (!schemasResponse || !schemasResponse.provider_types) {
      typeSelect.innerHTML = '<option value="">Błąd ładowania schematów API</option>';
      return;
    }

    const providerTypes = schemasResponse.provider_types;

    typeSelect.innerHTML = providerTypes.map((pt) => `
      <option value="${pt.type}">${escapeHtml(pt.label)}</option>
    `).join('');

    const renderOptions = () => {
      const selectedType = typeSelect.value;
      const selectedSpec = providerTypes.find((pt) => pt.type === selectedType);

      if (!selectedSpec || !selectedSpec.options_schema) {
        optionsContainer.innerHTML = '';
        return;
      }

      optionsContainer.innerHTML = selectedSpec.options_schema.map((opt) => `
        <div class="form-group form-group-min240">
          <label for="modal-opt-${opt.name}">${escapeHtml(opt.label)}</label>
          <input
            type="${opt.type === 'password' ? 'password' : 'text'}"
            id="modal-opt-${opt.name}"
            data-opt-name="${opt.name}"
            class="form-control modal-dynamic-opt-input"
            placeholder="${escapeHtml(opt.placeholder || '')}"
            value="${escapeHtml(opt.default_value || '')}"
            ${opt.required ? 'required' : ''}
          />
        </div>
      `).join('');

      if (selectedSpec.label) {
        nameInput.value = `${selectedSpec.label}`;
      }
    };

    typeSelect.addEventListener('change', renderOptions);
    renderOptions();

    const showForm = () => {
      formCard.classList.remove('hidden');
      renderOptions();
    };

    const hideForm = () => {
      formCard.classList.add('hidden');
      form.reset();
    };

    toggleBtn.addEventListener('click', showForm);
    if (closeBtn) closeBtn.addEventListener('click', hideForm);
    if (cancelBtn) cancelBtn.addEventListener('click', hideForm);

    form.addEventListener('submit', async (e) => {
      e.preventDefault();

      const type = typeSelect.value;
      const name = nameInput.value;

      const options = {};
      optionsContainer.querySelectorAll('.modal-dynamic-opt-input').forEach((input) => {
        const optName = input.getAttribute('data-opt-name');
        if (optName) {
          options[optName] = input.value;
        }
      });

      const payload = {
        type: type,
        name: name,
        options: options,
      };

      try {
        await apiClient.createLLMProvider(payload);
        hideForm();
        if (refreshCallback) refreshCallback();
        await this.refreshModalContent(apiClient, refreshCallback);
      } catch (err) {
        this.showToast(`Błąd tworzenia dostawcy: ${err.message}`, 'error');
      }
    });
  }

  updateStatus(healthData) {
    // Stan połączenia obsługiwany globalnie w app.js
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
