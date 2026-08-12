import { Icons } from '../icons.js';

/**
 * Moduł widoku Ustawienia.
 * Main view: Czysty kafelek z aktywnym dostawcą LLM + przycisk otwierający modal.
 * Modal: Pełne zarządzanie (dodawanie ze specyfikacji backendowej, aktywacja, usuwanie).
 */
export class SettingsView {
  render() {
    return `
      <div class="dashboard-grid">
        <!-- Baner Nagłówkowy Ustawień -->
        <div class="card card-hero">
          <div class="card-hero-header">
            <div>
              <span class="badge">Konfiguracja Systemowa</span>
              <h2 class="hero-title">Ustawienia Systemowe</h2>
              <p class="hero-description">
                Główne parametry pracy Regis OS, w tym konfiguracja aktywnego silnika AI i połączeń.
              </p>
            </div>
            <div class="hero-icon-box">
              ${Icons.Sliders()}
            </div>
          </div>
        </div>

        <!-- Sekcja: Aktywny Dostawca LLM -->
        <div class="section-header-bar">
          <h3 class="section-title">Dostawca Modelu LLM</h3>
        </div>

        <div id="active-provider-container">
          <div class="card card-loading">Ładowanie aktywnego dostawcy...</div>
        </div>
      </div>
    `;
  }

  /**
   * Renderuje pojedynczą kartę aktywnego dostawcy w głównym widoku Ustawień.
   */
  renderProvidersList(data, apiClient, refreshCallback) {
    const container = document.getElementById('active-provider-container');
    if (!container) return;

    if (!data || !data.providers || data.providers.length === 0) {
      container.innerHTML = `
        <div class="card">
          <p style="color: var(--text-secondary); margin-bottom: 14px;">Brak skonfigurowanych dostawców LLM.</p>
          <button class="btn btn-primary" id="btn-open-manage-modal">+ Dodaj Dostawcę</button>
        </div>
      `;
      this.attachMainViewEvents(container, apiClient, refreshCallback);
      return;
    }

    const activeProvider = data.providers.find((p) => p.is_active) || data.providers[0];
    const modelName = activeProvider.options?.model || 'domyślny';
    const baseUrl = activeProvider.options?.base_url || 'N/A';

    container.innerHTML = `
      <div class="card active-provider-card">
        <div class="provider-card-main">
          <div class="provider-info-box">
            <div class="provider-title-row">
              <span class="provider-name">${escapeHtml(activeProvider.name)}</span>
              <span class="badge">${activeProvider.type}</span>
              <span class="badge badge-active-tag">Aktywny</span>
            </div>
            <div class="provider-meta" style="margin-top: 10px;">
              <span>Model: <strong>${escapeHtml(modelName)}</strong></span>
              <span>URL: <code>${escapeHtml(baseUrl)}</code></span>
              <span>ID: <code>${activeProvider.id}</code></span>
            </div>
          </div>

          <div class="provider-actions">
            <button class="btn btn-primary" id="btn-open-manage-modal">
              Zarządzaj Dostawcami
            </button>
          </div>
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
   * Brak bezpośredniego formularza na głównej stronie (formularz znajduje się w modalu).
   */
  initForm(apiClient, refreshCallback) {
    // Brak akcji - obsługa formularza jest przeniesiona do modala
  }

  /**
   * Otwiera modal z pełnym zarządem dostawców LLM (lista + dodawanie ze specyfikacji API).
   */
  async openManageModal(apiClient, refreshCallback) {
    const overlay = document.getElementById('modal-overlay');
    const content = document.getElementById('modal-content');
    if (!overlay || !content) return;

    // Utworzenie struktury modala
    content.innerHTML = `
      <div class="modal-header">
        <h3 class="modal-title">Zarządzanie Dostawcami LLM</h3>
        <button class="btn-close-corner" id="btn-close-modal" title="Zamknij (Esc)">✕</button>
      </div>

      <div class="section-header-bar" style="margin-bottom: 16px;">
        <span style="font-size: 0.95rem; color: var(--text-secondary);">Instancje na dysku</span>
        <button class="btn btn-primary btn-sm" id="modal-btn-toggle-add-form">
          + Dodaj Dostawcę
        </button>
      </div>

      <!-- Generyczny Formularz Dodawania (Ukryty domyślnie) -->
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

    // Pokaż overlay
    overlay.classList.remove('hidden');

    // Obsługa zamykania modala
    const closeModal = () => {
      overlay.classList.add('hidden');
      content.innerHTML = '';
      window.removeEventListener('keydown', handleEsc);
    };

    const handleEsc = (e) => {
      if (e.key === 'Escape') closeModal();
    };

    window.addEventListener('keydown', handleEsc);
    document.getElementById('btn-close-modal').addEventListener('click', closeModal);
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) closeModal();
    });

    // Wczytaj dane i zainicjalizuj logikę modala
    await this.refreshModalContent(apiClient, refreshCallback);
  }

  /**
   * Ładuje i odświeża listę oraz formularz wewnątrz modala.
   */
  async refreshModalContent(apiClient, refreshCallback) {
    const listContainer = document.getElementById('modal-providers-list');
    if (!listContainer) return;

    // 1. Pobranie danych o dostawcach
    const data = await apiClient.getLLMProviders();
    if (!data || !data.providers || data.providers.length === 0) {
      listContainer.innerHTML = `<div class="card">Brak skonfigurowanych dostawców.</div>`;
    } else {
      listContainer.innerHTML = data.providers.map((p) => {
        const isActive = p.is_active;
        const modelName = p.options?.model || 'domyślny';
        const baseUrl = p.options?.base_url || 'N/A';

        return `
          <div class="card provider-card ${isActive ? 'active-provider-card' : ''}">
            <div class="provider-card-main">
              <div class="provider-info-box">
                <div class="provider-title-row">
                  <span class="provider-name">${escapeHtml(p.name)}</span>
                  <span class="badge">${p.type}</span>
                  ${isActive ? '<span class="badge badge-active-tag">Aktywny</span>' : ''}
                </div>
                <div class="provider-meta">
                  <span>Model: <strong>${escapeHtml(modelName)}</strong></span>
                  <span>URL: <code>${escapeHtml(baseUrl)}</code></span>
                  <span>ID: <code>${p.id}</code></span>
                </div>
              </div>

              <div class="provider-actions">
                ${
                  !isActive
                    ? `<button class="btn btn-sm btn-subtle modal-btn-activate" data-id="${p.id}">Aktywuj</button>
                       <button class="btn btn-sm btn-ghost-danger modal-btn-delete" data-id="${p.id}" title="Usuń z dysku">Usuń</button>`
                    : `<span class="text-active-indicator">${Icons.CheckCircle2()} Wybrany</span>`
                }
              </div>
            </div>
          </div>
        `;
      }).join('');

      // Podpięcie zdarzeń w modalu
      listContainer.querySelectorAll('.modal-btn-activate').forEach((btn) => {
        btn.addEventListener('click', async (e) => {
          const id = e.currentTarget.getAttribute('data-id');
          try {
            btn.disabled = true;
            btn.textContent = 'Aktywowanie...';
            await apiClient.setActiveLLMProvider(id);
            if (refreshCallback) refreshCallback();
            await this.refreshModalContent(apiClient, refreshCallback);
          } catch (err) {
            alert(`Błąd aktywacji: ${err.message}`);
            btn.disabled = false;
            btn.textContent = 'Aktywuj';
          }
        });
      });

      listContainer.querySelectorAll('.modal-btn-delete').forEach((btn) => {
        btn.addEventListener('click', async (e) => {
          const id = e.currentTarget.getAttribute('data-id');
          if (!confirm(`Czy na pewno chcesz usunąć instancję [${id}] z dysku?`)) return;

          try {
            btn.disabled = true;
            await apiClient.deleteLLMProvider(id);
            if (refreshCallback) refreshCallback();
            await this.refreshModalContent(apiClient, refreshCallback);
          } catch (err) {
            alert(`Błąd usuwania: ${err.message}`);
            btn.disabled = false;
          }
        });
      });
    }

    // 2. Inicjalizacja formularza w modalu (100% Backend-driven Generic Form Renderer)
    this.initModalForm(apiClient, refreshCallback);
  }

  /**
   * Dynamiczny renderer formularza w modalu z wykorzystaniem specyfikacji z API.
   */
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
    if (typeSelect.dataset.initialized === 'true') return; // Zabezpieczenie przed podwójnym przypisaniem

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
        alert(`Błąd tworzenia dostawcy: ${err.message}`);
      }
    });
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
