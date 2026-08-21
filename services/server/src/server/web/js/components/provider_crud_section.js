import { Icons } from '../icons.js';
import { confirmModal } from '../modal_confirm.js';
import { renderSelectMarkup, initSelect } from './select.js';
import { escapeHtml, escapeAttr } from '../utils/dom.js';
import { showToast } from '../utils/toast.js';

/**
 * Sekcja CRUD dostawcy (composer zawsze widoczny + lista klikalnych kart) —
 * wyekstrahowana z dawnego `AgentConfigView` (LLM), reużywana teraz trzy razy
 * (LLM/STT/TTS) w `views/providers_config.js`. `idPrefix` rozróżnia DOM-owe id
 * trzech współistniejących na stronie instancji (ten sam wzorzec co
 * `idPrefix` w `components/select.js`).
 *
 * Wiersz meta karty jest budowany GENERYCZNIE z `options_schema` (pomijając
 * pola `type: "password"`) — LLM/STT/TTS mają różne nazwy pól opcji
 * (`model`/`base_url`/`max_tokens` vs `api_key`/`model` vs
 * `api_key`/`voice_id`/`model_id`), więc nie da się zahardkodować jak w
 * dawnym `AgentConfigView.refresh()`.
 */
export class ProviderCrudSection {
  /**
   * @param {object} opts
   * @param {string} opts.idPrefix - np. 'llm', 'stt', 'tts'
   * @param {string} opts.emptyLabel - komunikat gdy lista jest pusta
   * @param {object} opts.api - nazwy metod na `apiClient`: getSchemas, getList, setActive, create, delete_
   */
  constructor({ idPrefix, emptyLabel, api }) {
    this.idPrefix = idPrefix;
    this.emptyLabel = emptyLabel;
    this.api = api;
  }

  render() {
    const p = this.idPrefix;
    return `
      <form id="${p}-form-create-provider" class="agent-composer">
        <div class="agent-composer-row">
          ${renderSelectMarkup(`${p}-provider-type`, { placeholder: 'Ładowanie...' })}
          <div class="agent-composer-fields" id="${p}-dynamic-options-container"></div>
          <button type="submit" class="agent-composer-submit" title="Dodaj dostawcę" aria-label="Dodaj dostawcę">${Icons.Plus()}</button>
        </div>
      </form>

      <div class="agent-provider-list" id="${p}-providers-list">
        <div class="card card-loading">Ładowanie dostawców...</div>
      </div>
    `;
  }

  async init(apiClient) {
    this.apiClient = apiClient;
    await this.refresh();
    await this._initForm();
  }

  async refresh() {
    const p = this.idPrefix;
    const listContainer = document.getElementById(`${p}-providers-list`);
    if (!listContainer) return;

    const data = await this.apiClient[this.api.getList]();
    if (!data || !data.providers || data.providers.length === 0) {
      listContainer.innerHTML = `<div class="card card-sm">${escapeHtml(this.emptyLabel)}</div>`;
      return;
    }

    const schemasResponse = this._schemasCache || (await this.apiClient[this.api.getSchemas]());
    this._schemasCache = schemasResponse;

    listContainer.innerHTML = data.providers.map((provider) => this._renderCard(provider, schemasResponse)).join('');

    listContainer.querySelectorAll('.agent-provider-card:not(.is-active)').forEach((card) => {
      const activate = async () => {
        const id = card.getAttribute('data-id');
        try {
          card.style.pointerEvents = 'none';
          await this.apiClient[this.api.setActive](id);
          await this.refresh();
        } catch (err) {
          showToast(`Błąd aktywacji: ${err.message}`, 'error');
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
          await this.apiClient[this.api.delete_](id);
          showToast('Instancja została usunięta z dysku.', 'success');
          await this.refresh();
        } catch (err) {
          showToast(`Błąd usuwania: ${err.message}`, 'error');
        }
      });
    });
  }

  _renderCard(p, schemasResponse) {
    const isActive = p.is_active;
    const typeSpec = schemasResponse?.provider_types?.find((t) => t.type === p.type);
    const metaFields = (typeSpec?.options_schema || [])
      .filter((opt) => opt.type !== 'password')
      .map((opt) => p.options?.[opt.name])
      .filter((value) => value !== undefined && value !== null && value !== '');

    return `
      <div class="agent-provider-card ${isActive ? 'is-active' : ''}" data-id="${escapeAttr(p.id)}" role="button" tabindex="0" ${isActive ? 'aria-current="true"' : ''}>
        <div class="agent-provider-card-main">
          <div class="agent-provider-card-title-row">
            <span class="agent-provider-card-name" title="${escapeAttr(p.name)}">${escapeHtml(p.name)}</span>
            <span class="badge badge-chip">${escapeHtml((p.type || '').toUpperCase())}</span>
          </div>
          <div class="agent-provider-card-meta">
            ${metaFields
              .map((value, idx) => `${idx > 0 ? '<span class="agent-provider-card-meta-sep">·</span>' : ''}<span>${escapeHtml(String(value))}</span>`)
              .join('')}
          </div>
        </div>
        ${
          isActive
            ? `<span class="agent-provider-card-check" title="Aktywny dostawca">${Icons.CheckCircle2()}</span>`
            : `<button class="btn btn-ghost-danger btn-icon-square agent-provider-card-delete" data-id="${escapeAttr(p.id)}" title="Usuń dostawcę" aria-label="Usuń dostawcę">${Icons.Trash2()}</button>`
        }
      </div>
    `;
  }

  async _initForm() {
    const p = this.idPrefix;
    const optionsContainer = document.getElementById(`${p}-dynamic-options-container`);
    const form = document.getElementById(`${p}-form-create-provider`);
    if (!optionsContainer || !form) return;

    this._optionsContainer = optionsContainer;

    const schemasResponse = this._schemasCache || (await this.apiClient[this.api.getSchemas]());
    this._schemasCache = schemasResponse;
    if (!schemasResponse || !schemasResponse.provider_types) {
      optionsContainer.innerHTML = '<span class="section-hint">Błąd ładowania schematów API</span>';
      return;
    }

    this._providerTypes = schemasResponse.provider_types;
    this._typeSelect = initSelect({
      idPrefix: `${p}-provider-type`,
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
      const selectedSpec = this._providerTypes.find((pt) => pt.type === type);
      const nonSecretValues = (selectedSpec?.options_schema || [])
        .filter((o) => o.type !== 'password')
        .map((o) => options[o.name])
        .filter(Boolean);
      const name = nonSecretValues[0] || selectedSpec?.label || type;

      try {
        await this.apiClient[this.api.create]({ type, name, options });
        showToast('Dodano dostawcę.', 'success');
        form.reset();
        this._typeSelect?.setValue(this._providerTypes[0]?.type ?? type);
        await this.refresh();
      } catch (err) {
        showToast(`Błąd tworzenia dostawcy: ${err.message}`, 'error');
      }
    });
  }

  _renderOptions() {
    const p = this.idPrefix;
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
        id="${p}-opt-${opt.name}"
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
}
