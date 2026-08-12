import { Icons } from '../icons.js';

/**
 * Moduł widoku głównego Dashboard z aktywnym dostawcą LLM i podglądem operacyjnym.
 */
export class DashboardView {
  render() {
    return `
      <div class="dashboard-grid">
        <!-- Minimalistyczny Nagłówek Strony -->
        <div class="page-header" style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
          <div>
            <h2 style="font-size: 1.35rem; font-weight: 600; color: var(--text-primary); letter-spacing: -0.01em;">System Przeglądu</h2>
            <p style="font-size: 0.88rem; color: var(--text-secondary); margin-top: 4px;">Monitorowanie i konfiguracja aktywnej instancji dostawcy LLM.</p>
          </div>
          <span class="badge-muted">v0.1.0</span>
        </div>

        <!-- Karta Bento Wyrównana do Lewej (col-8 / 66% Szerokości) -->
        <div class="bento-grid">
          <div id="active-provider-container" class="col-8">
            <div class="bento-card" style="padding: 36px 40px; min-height: 280px;">
              <div>
                <div class="bento-card-header">
                  <span class="bento-card-title" style="font-size: 1.15rem;">Aktywny Dostawca LLM</span>
                  <span class="badge badge-chip">ŁADOWANIE</span>
                </div>
                <div style="color: var(--text-secondary); font-size: 0.88rem;">Pobieranie danych o dostawcach...</div>
              </div>
            </div>
          </div>
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
        <div class="bento-card" style="padding: 36px 40px; min-height: 280px;">
          <div class="bento-card-header">
            <span class="bento-card-title" style="font-size: 1.15rem;">Aktywny Dostawca LLM</span>
          </div>
          <p style="color: var(--text-secondary); margin-bottom: 16px;">Brak skonfigurowanych dostawców LLM.</p>
          <button class="btn btn-primary" id="btn-open-manage-modal" style="width: auto; padding: 10px 20px;">
            + Dodaj Dostawcę
          </button>
        </div>
      `;
      this.attachMainViewEvents(container, apiClient, refreshCallback);
      return;
    }

    const activeProvider = data.providers.find((p) => p.is_active) || data.providers[0];
    const modelName = activeProvider.options?.model || 'domyślny';
    const baseUrl = activeProvider.options?.base_url || 'N/A';

    container.innerHTML = `
      <div class="bento-card" style="padding: 36px 40px; min-height: 280px; justify-content: space-between;">
        <div>
          <!-- Górny Wiersz: Etykieta sekcji + Para Plakietek po prawej -->
          <div style="display: flex; align-items: flex-start; justify-content: space-between; gap: 24px; margin-bottom: 24px;">
            <div>
              <div class="provider-section-label">Aktywny Dostawca LLM</div>
              <div style="font-size: 1.85rem; font-weight: 700; color: var(--text-primary); letter-spacing: -0.02em; line-height: 1.2; white-space: nowrap;">
                ${escapeHtml(activeProvider.name)}
              </div>
              <div style="font-size: 0.85rem; font-weight: 400; color: var(--text-muted); font-family: var(--font-mono); margin-top: 8px;">
                ${escapeHtml(modelName)}
              </div>
            </div>

            <!-- Prawa Grupa Plakietek -->
            <div style="display: flex; align-items: center; gap: 10px; flex-shrink: 0; margin-top: 4px;">
              <span class="badge badge-status" style="height: 30px; font-size: 0.84rem; padding: 0 14px;">
                ${escapeHtml((activeProvider.type || 'LLM').toUpperCase())}
              </span>
              <span class="badge badge-status" style="height: 30px; font-size: 0.84rem; padding: 0 14px;">
                <span class="status-dot-pulse"></span>Aktywny
              </span>
            </div>
          </div>

          <!-- Środkowy Wiersz: Base URL -->
          <div style="margin-top: 20px; padding-top: 18px; border-top: 1px solid var(--border-subtle);">
            <div style="font-size: 0.72rem; font-weight: 600; text-transform: uppercase; color: var(--text-muted); letter-spacing: 0.06em; margin-bottom: 8px;">Punkt Końcowy (Base URL)</div>
            <div style="font-size: 0.88rem; font-family: var(--font-mono); color: var(--text-secondary); background: var(--bg-base); padding: 8px 14px; border-radius: var(--radius-sm); border: 1px solid var(--border-subtle); display: inline-block;">
              ${escapeHtml(baseUrl)}
            </div>
          </div>
        </div>

        <!-- Stopka: Przycisk Akcji -->
        <div style="margin-top: 24px; padding-top: 18px; border-top: 1px solid var(--border-subtle); display: flex; justify-content: flex-end;">
          <button class="btn btn-primary" id="btn-open-manage-modal" style="padding: 10px 22px; font-weight: 500; gap: 10px;">
            <span>Zarządzaj Dostawcami</span>
            <span style="opacity: 0.55;">→</span>
          </button>
        </div>
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

      <div class="section-header-bar" style="margin-bottom: 16px;">
        <span style="font-size: 0.95rem; color: var(--text-secondary);">Skonfigurowane dostawce</span>
        <button class="btn btn-primary btn-sm" id="modal-btn-toggle-add-form">
          + Dodaj Dostawcę
        </button>
      </div>

      <!-- Formularz Dodawania (Ukryty domyślnie) -->
      <div class="card form-card hidden" id="modal-card-add-provider-form" style="margin-bottom: 20px; border: 1px solid var(--border-medium);">
        <button class="btn-close-corner" id="modal-btn-close-form" title="Zamknij formularz">✕</button>
        
        <div style="margin-bottom: 16px;">
          <span style="font-size: 1rem; font-weight: 600;">Nowa Instancja Dostawcy LLM</span>
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

          <div class="form-row" id="modal-dynamic-options-container" style="flex-wrap: wrap;"></div>

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
      listContainer.innerHTML = `<div class="card" style="padding: 20px;">Brak skonfigurowanych dostawców LLM.</div>`;
    } else {
      listContainer.innerHTML = `
        <div class="modal-provider-list">
          ${data.providers.map((p) => {
            const isActive = p.is_active;
            const modelName = p.options?.model || 'domyślny';
            const baseUrl = p.options?.base_url || 'N/A';

            return `
              <div class="modal-provider-item ${isActive ? 'active' : ''}">
                <div class="modal-provider-main-row">
                  <div style="display: flex; align-items: center; gap: 12px;">
                    <span style="font-size: 1.05rem; font-weight: 600; color: var(--text-primary);">${escapeHtml(p.name)}</span>
                    <span class="badge badge-chip">${escapeHtml((p.type || 'LLM').toUpperCase())}</span>
                    ${
                      isActive
                        ? `<span class="badge badge-status" style="height: 26px; font-size: 0.78rem; padding: 0 10px;">
                             <span class="status-dot-pulse"></span>Aktywny
                           </span>`
                        : ''
                    }
                  </div>

                  <div style="display: flex; align-items: center; gap: 8px;">
                    ${
                      !isActive
                        ? `<button class="btn btn-subtle btn-sm modal-btn-activate" data-id="${p.id}">
                             Aktywuj
                           </button>
                           <button class="btn btn-ghost-danger btn-sm modal-btn-delete" data-id="${p.id}" title="Usuń z dysku">
                             Usuń
                           </button>`
                        : `<span style="font-size: 0.84rem; font-weight: 600; color: var(--text-primary); display: flex; align-items: center; gap: 6px;">
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
            btn.style.opacity = '0.5';
            btn.style.pointerEvents = 'none';
            await apiClient.setActiveLLMProvider(id);
            if (refreshCallback) refreshCallback();
            await this.refreshModalContent(apiClient, refreshCallback);
          } catch (err) {
            this.showToast(`Błąd aktywacji: ${err.message}`, 'error');
            btn.disabled = false;
            btn.style.opacity = '1';
            btn.style.pointerEvents = 'auto';
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
              <span style="font-size: 0.82rem; color: #fca5a5; font-weight: 500;">Usunąć instancję?</span>
              <button class="btn-confirm-yes" style="background: #ef4444; color: #fff; border: none; padding: 4px 10px; font-size: 0.78rem; border-radius: var(--radius-sm); cursor: pointer; font-weight: 600;">Tak</button>
              <button class="btn-confirm-no" style="background: transparent; color: var(--text-secondary); border: 1px solid var(--border-subtle); padding: 4px 8px; font-size: 0.78rem; border-radius: var(--radius-sm); cursor: pointer;">Nie</button>
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
      toast.style.opacity = '0';
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
        <div class="form-group" style="min-width: 240px;">
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
