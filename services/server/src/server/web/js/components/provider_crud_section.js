import { Icons } from '../icons.js';
import { confirmModal } from '../modal_confirm.js';
import { renderSelectMarkup, initSelect } from './select.js';
import { escapeHtml, escapeAttr } from '../utils/dom.js';
import { showToast } from '../utils/toast.js';

/**
 * Sekcja presetów dostawcy (LLM/STT/TTS) — lista kart, z których każda **rozwija się
 * w pełny edytor w miejscu**. Reużywana trzy razy w `views/providers_config.js`;
 * `idPrefix` rozróżnia DOM-owe id trzech współistniejących instancji (ten sam wzorzec
 * co `idPrefix` w `components/select.js`).
 *
 * **Dlaczego karta rozwija się w edytor, a nie modal ani osobna kolumna.** Preset
 * dostał kilkanaście pól (model, klucz, temperatura, głębokość rozumowania…), więc
 * dawny composer — jeden poziomy rząd inputów — przestał je mieścić. Edycja w miejscu
 * daje jedną implementację formularza dla tworzenia i edycji, zostawia listę
 * skanowalną i nie zabiera ekranu jak modal. Kosztem jest to, że **aktywacja presetu
 * przeniosła się z kliknięcia w kartę na osobny przycisk** — kliknięcie karty rozwija.
 *
 * **Formularz parametrów jest per MODEL, nie per dostawca.** `reasoning_effort`
 * istnieje dla gpt-oss i nie istnieje dla llamy, a dla Qwena ma inny zestaw wartości —
 * żadna wspólna lista pól nie opisze obu naraz. Schemat typu (`getSchemas`) niesie więc
 * wyłącznie pola niezależne od modelu (klucz API, adres serwera), a parametry przychodzą
 * razem z listą modeli (`getModels`, patrz `server/ai/llm/model_catalog.py`).
 *
 * Dostawcy bez odkrywania modeli (STT/TTS) po prostu nie dostają tej sekcji — ich pola
 * w całości pochodzą ze schematu typu.
 */
export class ProviderCrudSection {
  /**
   * @param {object} opts
   * @param {string} opts.idPrefix - np. 'llm', 'stt', 'tts'
   * @param {string} opts.emptyLabel - komunikat gdy lista jest pusta
   * @param {object} opts.api - nazwy metod na `apiClient`: getSchemas, getList, setActive,
   *   create, update, delete_ oraz opcjonalnie getModels (tylko tam, gdzie modele mają sens)
   */
  constructor({ idPrefix, emptyLabel, api }) {
    this.idPrefix = idPrefix;
    this.emptyLabel = emptyLabel;
    this.api = api;
    this._providers = [];
    this._expandedId = null;
    /** @type {Map<string, object>} preset -> odpowiedź `getModels` (cache na czas życia widoku) */
    this._modelsById = new Map();
    /** Parametry aktualnie wybranego modelu — trzymane osobno, bo zmiana modelu
     * przerenderowuje tę część formularza, a wpisane wartości mają przetrwać. */
    this._draftOptions = {};
  }

  render() {
    const p = this.idPrefix;
    return `
      <form id="${p}-form-create-provider" class="agent-composer">
        <div class="agent-composer-row">
          ${renderSelectMarkup(`${p}-provider-type`, { placeholder: 'Ładowanie...' })}
          <input type="text" id="${p}-new-name" class="form-control agent-composer-name"
            placeholder="Nazwa presetu (np. Dom)" aria-label="Nazwa presetu" />
          <button type="submit" class="agent-composer-submit" title="Dodaj preset" aria-label="Dodaj preset">${Icons.Plus()}</button>
        </div>
        <p class="section-hint">Model i parametry ustawisz po utworzeniu — rozwiń preset na liście.</p>
      </form>

      <div class="agent-provider-list" id="${p}-providers-list">
        <div class="skeleton-stack">
          <div class="skeleton-block skeleton-block--card"></div>
          <div class="skeleton-block skeleton-block--card"></div>
        </div>
      </div>
    `;
  }

  async init(apiClient) {
    this.apiClient = apiClient;
    await this.refresh();
    await this._initComposer();
  }

  // --------------------------------------------------------------------------
  // Lista presetów
  // --------------------------------------------------------------------------

  async refresh() {
    const listContainer = document.getElementById(`${this.idPrefix}-providers-list`);
    if (!listContainer) return;

    const [data, schemas] = await Promise.all([
      this.apiClient[this.api.getList](),
      this._schemas(),
    ]);
    this._providers = data?.providers || [];

    if (this._providers.length === 0) {
      this._expandedId = null;
      listContainer.innerHTML = `<div class="card card-sm">${escapeHtml(this.emptyLabel)}</div>`;
      return;
    }
    // Rozwinięty preset mógł zniknąć (usunięty w innej karcie przeglądarki).
    if (this._expandedId && !this._providers.some((p) => p.id === this._expandedId)) {
      this._expandedId = null;
    }

    listContainer.innerHTML = this._providers.map((provider) => this._renderCard(provider, schemas)).join('');
    this._bindCards();
    if (this._expandedId) await this._mountEditor(this._expandedId);
  }

  _renderCard(provider, schemas) {
    const isActive = provider.is_active;
    const isExpanded = provider.id === this._expandedId;
    const typeSpec = schemas?.provider_types?.find((t) => t.type === provider.type);
    const model = provider.options?.model || provider.options?.model_id || '';

    return `
      <div class="agent-provider-card ${isActive ? 'is-active' : ''} ${isExpanded ? 'is-expanded' : ''}"
        data-id="${escapeAttr(provider.id)}">
        <div class="agent-provider-card-head" role="button" tabindex="0"
          aria-expanded="${isExpanded}" data-toggle="${escapeAttr(provider.id)}">
          <span class="agent-provider-card-chevron">${Icons.ChevronRight()}</span>
          <div class="agent-provider-card-main">
            <div class="agent-provider-card-title-row">
              <span class="agent-provider-card-name" title="${escapeAttr(provider.name)}">${escapeHtml(provider.name)}</span>
              <span class="badge badge-chip">${escapeHtml((typeSpec?.label || provider.type || '').toUpperCase())}</span>
            </div>
            <div class="agent-provider-card-meta">${escapeHtml(model || 'model nieustawiony')}</div>
          </div>
          ${
            isActive
              ? `<span class="agent-provider-card-check" title="Aktywny preset">${Icons.CheckCircle2()}</span>`
              : `<button type="button" class="btn btn-sm btn-subtle agent-provider-card-activate"
                   data-activate="${escapeAttr(provider.id)}">Aktywuj</button>`
          }
        </div>
        <div class="agent-provider-card-editor" id="${this.idPrefix}-editor-${escapeAttr(provider.id)}"></div>
      </div>
    `;
  }

  _bindCards() {
    const listContainer = document.getElementById(`${this.idPrefix}-providers-list`);
    listContainer?.querySelectorAll('[data-toggle]').forEach((head) => {
      const toggle = (e) => {
        // Przycisk aktywacji leży wewnątrz nagłówka — nie może przy okazji rozwijać karty.
        if (e.target.closest('[data-activate]')) return;
        this._toggleExpanded(head.getAttribute('data-toggle'));
      };
      head.addEventListener('click', toggle);
      head.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          toggle(e);
        }
      });
    });

    listContainer?.querySelectorAll('[data-activate]').forEach((btn) => {
      btn.addEventListener('click', async (e) => {
        e.stopPropagation();
        try {
          btn.disabled = true;
          await this.apiClient[this.api.setActive](btn.getAttribute('data-activate'));
          await this.refresh();
        } catch (err) {
          btn.disabled = false;
          showToast(`Błąd aktywacji: ${err.message}`, 'error');
        }
      });
    });
  }

  async _toggleExpanded(providerId) {
    this._expandedId = this._expandedId === providerId ? null : providerId;
    this._draftOptions = {};
    await this.refresh();
  }

  // --------------------------------------------------------------------------
  // Edytor presetu
  // --------------------------------------------------------------------------

  async _mountEditor(providerId) {
    const mount = document.getElementById(`${this.idPrefix}-editor-${providerId}`);
    const provider = this._providers.find((p) => p.id === providerId);
    if (!mount || !provider) return;

    mount.innerHTML = '<div class="skeleton-stack"><div class="skeleton-block skeleton-block--field"></div></div>';

    const schemas = await this._schemas();
    const typeSpec = schemas?.provider_types?.find((t) => t.type === provider.type);
    const modelsData = await this._models(provider, typeSpec);

    this._draftOptions = { ...provider.options, ...this._draftOptions };
    const selectedModel = this._draftOptions.model || '';
    const paramSchema = this._paramSchemaFor(modelsData, selectedModel);

    mount.innerHTML = `
      <div class="provider-editor">
        ${this._renderFieldGrid(`${this.idPrefix}-base-${providerId}`, typeSpec?.options_schema || [])}
        ${modelsData ? this._renderModelPicker(providerId, modelsData, selectedModel) : ''}
        <div id="${this.idPrefix}-params-${providerId}">
          ${this._renderFieldGrid(`${this.idPrefix}-param-${providerId}`, paramSchema, 'Parametry generacji')}
        </div>
        <div class="provider-editor-actions">
          <button type="button" class="btn btn-primary btn-sm" data-save="${escapeAttr(providerId)}">Zapisz</button>
          <button type="button" class="btn btn-ghost-danger btn-sm" data-delete="${escapeAttr(providerId)}">Usuń preset</button>
        </div>
      </div>
    `;

    this._mountFieldSelects(`${this.idPrefix}-base-${providerId}`, typeSpec?.options_schema || []);
    this._mountFieldSelects(`${this.idPrefix}-param-${providerId}`, paramSchema);
    if (modelsData) this._mountModelPicker(providerId, modelsData, selectedModel);

    mount.querySelector('[data-save]')?.addEventListener('click', () => this._save(providerId));
    mount.querySelector('[data-delete]')?.addEventListener('click', () => this._delete(providerId));
  }

  _renderModelPicker(providerId, modelsData, selectedModel) {
    const hasList = (modelsData.models || []).length > 0;
    return `
      <div class="provider-editor-group">
        <h5 class="provider-editor-group-title">Model</h5>
        ${
          hasList
            ? `<div class="provider-field">
                 <label>Wybierz z listy</label>
                 ${renderSelectMarkup(`${this.idPrefix}-model-${providerId}`, { placeholder: 'Wybierz model' })}
               </div>`
            : ''
        }
        <div class="provider-field">
          <label for="${this.idPrefix}-model-custom-${providerId}">Identyfikator modelu</label>
          <input type="text" class="form-control" id="${this.idPrefix}-model-custom-${providerId}"
            value="${escapeAttr(selectedModel)}" placeholder="np. openai/gpt-oss-120b" />
          <p class="provider-field-hint">Lista nigdy nie zamyka wyboru — model spoza niej wpisz tutaj.</p>
        </div>
        ${modelsData.detail ? `<p class="provider-field-warning">${Icons.AlertCircle()} ${escapeHtml(modelsData.detail)}</p>` : ''}
      </div>
    `;
  }

  _mountModelPicker(providerId, modelsData, selectedModel) {
    const customInput = document.getElementById(`${this.idPrefix}-model-custom-${providerId}`);
    customInput?.addEventListener('input', (e) => {
      this._draftOptions.model = e.target.value;
    });

    if (!(modelsData.models || []).length) return;
    initSelect({
      idPrefix: `${this.idPrefix}-model-${providerId}`,
      options: modelsData.models.map((m) => ({ value: m.id, label: m.label })),
      value: selectedModel,
      placeholder: 'Wybierz model',
      onChange: async (value) => {
        // Wybór modelu przerenderowuje sekcję parametrów — najpierw zbieramy to, co
        // użytkownik już wpisał, żeby wspólne pola (temperatura, limit) przetrwały zmianę.
        this._collectInto(this._draftOptions, providerId);
        this._draftOptions.model = value;
        if (customInput) customInput.value = value;
        await this._mountEditor(providerId);
      },
    });
  }

  /** Parametry TEGO modelu; dla modelu spoza listy — formularz zapasowy z serwera. */
  _paramSchemaFor(modelsData, modelId) {
    if (!modelsData) return [];
    const match = (modelsData.models || []).find((m) => m.id === modelId);
    return match ? match.options_schema || [] : modelsData.fallback_options_schema || [];
  }

  // --------------------------------------------------------------------------
  // Renderowanie pól ze schematu
  // --------------------------------------------------------------------------

  _renderFieldGrid(idPrefix, schema, title = '') {
    if (!schema || schema.length === 0) return '';
    const fields = schema.map((opt) => this._renderField(idPrefix, opt)).join('');
    return `
      <div class="provider-editor-group">
        ${title ? `<h5 class="provider-editor-group-title">${escapeHtml(title)}</h5>` : ''}
        <div class="provider-field-grid">${fields}</div>
      </div>
    `;
  }

  _renderField(idPrefix, opt) {
    const id = `${idPrefix}-${opt.name}`;
    const value = this._draftOptions[opt.name];
    const hint = opt.hint ? `<p class="provider-field-hint">${escapeHtml(opt.hint)}</p>` : '';

    if (opt.type === 'enum') {
      return `
        <div class="provider-field" data-opt-name="${escapeAttr(opt.name)}" data-opt-kind="enum">
          <label>${escapeHtml(opt.label)}</label>
          ${renderSelectMarkup(id, { placeholder: 'Domyślne modelu', className: 'select--compact' })}
          ${hint}
        </div>
      `;
    }

    // `type="number"` odpada świadomie — natywne strzałki góra/dół przeglądarki są
    // jednym z domyślnych kontrolek, których ten projekt nie używa.
    const inputType = opt.type === 'password' ? 'password' : 'text';
    const shown = value === undefined || value === null ? '' : String(value);
    return `
      <div class="provider-field" data-opt-name="${escapeAttr(opt.name)}" data-opt-kind="input">
        <label for="${id}">${escapeHtml(opt.label)}</label>
        <input type="${inputType}" id="${id}" class="form-control provider-field-input"
          data-opt-name="${escapeAttr(opt.name)}"
          value="${escapeAttr(shown)}" placeholder="${escapeHtml(opt.placeholder || '')}" />
        ${hint}
      </div>
    `;
  }

  _mountFieldSelects(idPrefix, schema) {
    (schema || []).forEach((opt) => {
      if (opt.type !== 'enum') return;
      const current = this._draftOptions[opt.name];
      initSelect({
        idPrefix: `${idPrefix}-${opt.name}`,
        // Pusta opcja jest realnym wyborem: "nie wysyłaj tego parametru w ogóle",
        // co dla modelu znaczy co innego niż jakakolwiek konkretna wartość.
        options: [{ value: '', label: 'Domyślne modelu' }, ...(opt.choices || []).map((c) => ({ value: c.value, label: c.label }))],
        value: current === undefined || current === null ? '' : String(current),
        placeholder: 'Domyślne modelu',
        onChange: (value) => {
          this._draftOptions[opt.name] = value;
        },
      });
    });
  }

  /** Zbiera bieżące wartości pól tekstowych do podanego obiektu (selecty aktualizują
   * `_draftOptions` na bieżąco przez `onChange`, więc ich tu nie czytamy). */
  _collectInto(target, providerId) {
    const mount = document.getElementById(`${this.idPrefix}-editor-${providerId}`);
    mount?.querySelectorAll('.provider-field-input').forEach((input) => {
      target[input.getAttribute('data-opt-name')] = input.value;
    });
    const custom = document.getElementById(`${this.idPrefix}-model-custom-${providerId}`);
    if (custom) target.model = custom.value.trim();
    return target;
  }

  // --------------------------------------------------------------------------
  // Zapis / usunięcie / tworzenie
  // --------------------------------------------------------------------------

  async _save(providerId) {
    const options = this._collectInto({ ...this._draftOptions }, providerId);
    // Puste pole sekretne nie jest wysyłane w ogóle — serwer traktuje jego brak jako
    // "zachowaj obecny klucz" (frontend nigdy nie zna go w jawnej postaci).
    const schemas = await this._schemas();
    const provider = this._providers.find((p) => p.id === providerId);
    const typeSpec = schemas?.provider_types?.find((t) => t.type === provider?.type);
    (typeSpec?.options_schema || [])
      .filter((opt) => opt.type === 'password')
      .forEach((opt) => {
        const value = options[opt.name];
        if (!value || String(value).includes('•')) delete options[opt.name];
      });

    try {
      await this.apiClient[this.api.update](providerId, { options });
      showToast('Zapisano preset.', 'success');
      this._draftOptions = {};
      this._modelsById.delete(providerId);
      await this.refresh();
    } catch (err) {
      showToast(`Błąd zapisu: ${err.message}`, 'error');
    }
  }

  async _delete(providerId) {
    const confirmed = await confirmModal({
      title: 'Usunąć preset?',
      message: 'Ta instancja zostanie trwale usunięta z dysku. Tej operacji nie można cofnąć.',
      confirmLabel: 'Usuń',
      cancelLabel: 'Anuluj',
    });
    if (!confirmed) return;
    try {
      await this.apiClient[this.api.delete_](providerId);
      showToast('Preset został usunięty z dysku.', 'success');
      this._expandedId = null;
      await this.refresh();
    } catch (err) {
      showToast(`Błąd usuwania: ${err.message}`, 'error');
    }
  }

  async _initComposer() {
    const p = this.idPrefix;
    const form = document.getElementById(`${p}-form-create-provider`);
    if (!form) return;

    const schemas = await this._schemas();
    if (!schemas?.provider_types?.length) return;
    this._providerTypes = schemas.provider_types;

    const typeSelect = initSelect({
      idPrefix: `${p}-provider-type`,
      options: this._providerTypes.map((pt) => ({ value: pt.type, label: pt.label })),
      value: this._providerTypes[0]?.type ?? '',
    });

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const type = typeSelect?.getValue() ?? '';
      const nameInput = document.getElementById(`${p}-new-name`);
      const spec = this._providerTypes.find((pt) => pt.type === type);
      // Nazwa presetu jest odtąd własnym bytem, a nie echem nazwy modelu — ale
      // wymuszanie jej przy tworzeniu byłoby zbędnym tarciem; etykieta typu wystarczy
      // jako punkt startowy i i tak jest edytowalna.
      const name = nameInput?.value.trim() || spec?.label || type;

      try {
        const created = await this.apiClient[this.api.create]({ type, name, options: {} });
        showToast('Dodano preset — uzupełnij model i parametry.', 'success');
        if (nameInput) nameInput.value = '';
        this._expandedId = created?.id ?? null;
        this._draftOptions = {};
        await this.refresh();
      } catch (err) {
        showToast(`Błąd tworzenia presetu: ${err.message}`, 'error');
      }
    });
  }

  // --------------------------------------------------------------------------
  // Dane z serwera (cache na czas życia widoku)
  // --------------------------------------------------------------------------

  async _schemas() {
    if (!this._schemasCache) this._schemasCache = await this.apiClient[this.api.getSchemas]();
    return this._schemasCache;
  }

  async _models(provider, typeSpec) {
    if (!this.api.getModels || !typeSpec?.supports_model_discovery) return null;
    if (!this._modelsById.has(provider.id)) {
      try {
        this._modelsById.set(provider.id, await this.apiClient[this.api.getModels](provider.id));
      } catch (err) {
        this._modelsById.set(provider.id, { models: [], detail: err.message, fallback_options_schema: [] });
      }
    }
    return this._modelsById.get(provider.id);
  }
}
