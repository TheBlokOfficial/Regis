import { Icons } from '../icons.js';
import { confirmModal } from '../modal_confirm.js';
import { renderSelectMarkup, initSelect } from '../components/select.js';
import { escapeHtml, escapeAttr } from '../utils/dom.js';
import { showToast } from '../utils/toast.js';

/**
 * Sekcja Agent (Ustawienia) — dostawcy LLM (dawny Kernel) + system prompt
 * (fallback bez CRUD, używany tylko gdy żaden silnik świata nie jest
 * podłączony — patrz `world_prompts_view.js` dla właściwej tożsamości agenta).
 *
 * Przebudowa wzorem Chat: pływające karty, duże zaokrąglenia, odstęp zamiast
 * kresek. Composer dodawania dostawcy jest zawsze widoczny (bez przełącznika
 * pokaż/ukryj) — karty dostawców są w pełni klikalne (aktywacja), bez
 * osobnego przycisku "Aktywuj".
 */
export class AgentConfigView {
  render() {
    return `
      <div class="view-shell">
        <h3 class="section-heading">Dostawcy</h3>

        <form id="agent-form-create-provider" class="agent-composer">
          <div class="agent-composer-row">
            ${renderSelectMarkup('agent-provider-type', { placeholder: 'Ładowanie...' })}
            <div class="agent-composer-fields" id="agent-dynamic-options-container"></div>
            <button type="submit" class="agent-composer-submit" title="Dodaj dostawcę" aria-label="Dodaj dostawcę">${Icons.Plus()}</button>
          </div>
        </form>

        <div class="agent-provider-list" id="agent-providers-list">
          <div class="card card-loading">Ładowanie dostawców...</div>
        </div>

        <h3 class="section-heading section-heading--spaced">System Prompt</h3>
        <p class="section-hint">Używany tylko bez podłączonego świata.</p>
        <div class="chat-floating-box agent-prompt-box">
          <textarea id="agent-default-prompt-textarea" class="chat-textarea agent-prompt-textarea" placeholder="Ładowanie..."></textarea>
        </div>
      </div>
    `;
  }

  async init(apiClient) {
    this.apiClient = apiClient;
    await this.refresh();
    await this._initDefaultPrompt();
    await this._initForm();
  }

  async refresh() {
    const listContainer = document.getElementById('agent-providers-list');
    if (!listContainer) return;

    const data = await this.apiClient.getLLMProviders();
    if (!data || !data.providers || data.providers.length === 0) {
      listContainer.innerHTML = `<div class="card card-sm">Brak skonfigurowanych dostawców LLM.</div>`;
      return;
    }

    listContainer.innerHTML = data.providers
      .map((p) => {
        const isActive = p.is_active;
        const modelName = p.options?.model || p.name || 'domyślny';
        const baseUrl = p.options?.base_url || (p.type === 'OPENROUTER' ? 'https://openrouter.ai/api/v1' : 'N/A');
        const tokensLabel = p.options?.max_tokens ? `${p.options.max_tokens} tokenów` : 'bez limitu tokenów';

        return `
          <div class="agent-provider-card ${isActive ? 'is-active' : ''}" data-id="${escapeAttr(p.id)}" role="button" tabindex="0" ${isActive ? 'aria-current="true"' : ''}>
            <div class="agent-provider-card-main">
              <div class="agent-provider-card-title-row">
                <span class="agent-provider-card-name" title="${escapeAttr(modelName)}">${escapeHtml(modelName)}</span>
                <span class="badge badge-chip">${escapeHtml((p.type || 'LLM').toUpperCase())}</span>
              </div>
              <div class="agent-provider-card-meta">
                <span>${escapeHtml(tokensLabel)}</span>
                <span class="agent-provider-card-meta-sep">·</span>
                <span>${escapeHtml(baseUrl)}</span>
              </div>
            </div>
            ${
              isActive
                ? `<span class="agent-provider-card-check" title="Aktywny dostawca">${Icons.CheckCircle2()}</span>`
                : `<button class="btn btn-ghost-danger btn-icon-square agent-provider-card-delete" data-id="${escapeAttr(p.id)}" title="Usuń dostawcę" aria-label="Usuń dostawcę">${Icons.Trash2()}</button>`
            }
          </div>
        `;
      })
      .join('');

    listContainer.querySelectorAll('.agent-provider-card:not(.is-active)').forEach((card) => {
      const activate = async () => {
        const id = card.getAttribute('data-id');
        try {
          card.style.pointerEvents = 'none';
          await this.apiClient.setActiveLLMProvider(id);
          await this.refresh();
        } catch (err) {
          this.showToast(`Błąd aktywacji: ${err.message}`, 'error');
          card.style.pointerEvents = '';
        }
      };
      card.addEventListener('click', activate);
      card.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          activate();
        }
      });
    });

    listContainer.querySelectorAll('.agent-provider-card-delete').forEach((btn) => {
      btn.addEventListener('click', async (e) => {
        e.stopPropagation();
        const id = btn.getAttribute('data-id');
        const confirmed = await confirmModal({
          title: 'Usunąć dostawcę?',
          message: 'Ta instancja zostanie trwale usunięta z dysku. Tej operacji nie można cofnąć.',
          confirmLabel: 'Usuń',
          cancelLabel: 'Anuluj',
        });
        if (!confirmed) return;
        try {
          await this.apiClient.deleteLLMProvider(id);
          this.showToast('Instancja została usunięta z dysku.', 'success');
          await this.refresh();
        } catch (err) {
          this.showToast(`Błąd usuwania: ${err.message}`, 'error');
        }
      });
    });
  }

  async _initForm() {
    const optionsContainer = document.getElementById('agent-dynamic-options-container');
    const form = document.getElementById('agent-form-create-provider');
    if (!optionsContainer || !form) return;

    this._optionsContainer = optionsContainer;

    const schemasResponse = await this.apiClient.getProviderSchemas();
    if (!schemasResponse || !schemasResponse.provider_types) {
      optionsContainer.innerHTML = '<span class="section-hint">Błąd ładowania schematów API</span>';
      return;
    }

    this._providerTypes = schemasResponse.provider_types;
    this._typeSelect = initSelect({
      idPrefix: 'agent-provider-type',
      options: this._providerTypes.map((pt) => ({ value: pt.type, label: pt.label })),
      value: this._providerTypes[0]?.type ?? '',
      onChange: () => this._renderOptions(),
    });
    this._renderOptions();

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const type = this._typeSelect?.getValue() ?? '';
      const options = {};
      optionsContainer.querySelectorAll('.modal-dynamic-opt-input').forEach((input) => {
        const optName = input.getAttribute('data-opt-name');
        if (optName) options[optName] = input.value;
      });
      const name = options.model || type;

      try {
        await this.apiClient.createLLMProvider({ type, name, options });
        this.showToast('Dodano dostawcę.', 'success');
        form.reset();
        this._typeSelect?.setValue(this._providerTypes[0]?.type ?? type);
        await this.refresh();
      } catch (err) {
        this.showToast(`Błąd tworzenia dostawcy: ${err.message}`, 'error');
      }
    });
  }

  _renderOptions() {
    if (!this._typeSelect || !this._providerTypes) return;
    const selectedSpec = this._providerTypes.find((pt) => pt.type === this._typeSelect.getValue());

    if (!selectedSpec || !selectedSpec.options_schema) {
      this._optionsContainer.innerHTML = '';
      return;
    }

    this._optionsContainer.innerHTML = selectedSpec.options_schema
      .map(
        (opt) => `
      <input
        type="${opt.type === 'password' ? 'password' : opt.type === 'number' ? 'number' : 'text'}"
        id="agent-opt-${opt.name}"
        data-opt-name="${opt.name}"
        class="form-control modal-dynamic-opt-input"
        placeholder="${escapeHtml(opt.placeholder || opt.label || '')}"
        value="${escapeHtml(opt.default_value || '')}"
        ${opt.required ? 'required' : ''}
      />
    `
      )
      .join('');
  }

  // --------------------------------------------------------------------------
  // System Prompt (fallback, bez CRUD) — autosave na blur/debounce
  // --------------------------------------------------------------------------

  async _initDefaultPrompt() {
    const textarea = document.getElementById('agent-default-prompt-textarea');
    if (!textarea) return;

    const data = await this.apiClient.getAgentDefaultPrompt();
    textarea.value = data?.content ?? '';
    this._defaultPromptSaved = textarea.value;

    let debounceTimer = null;
    const scheduleSave = () => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => this._saveDefaultPrompt(textarea), 1500);
    };

    textarea.addEventListener('input', scheduleSave);
    textarea.addEventListener('blur', () => {
      clearTimeout(debounceTimer);
      this._saveDefaultPrompt(textarea);
    });
  }

  async _saveDefaultPrompt(textarea) {
    if (textarea.value === this._defaultPromptSaved) return;
    try {
      await this.apiClient.setAgentDefaultPrompt(textarea.value);
      this._defaultPromptSaved = textarea.value;
      this.showToast('Zapisano.', 'success');
    } catch (err) {
      this.showToast(`Błąd zapisu: ${err.message}`, 'error');
    }
  }

  showToast(message, type = 'info') {
    showToast(message, type);
  }
}
