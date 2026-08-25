import { confirmModal } from '../modal_confirm.js';
import { initSelect } from './select.js';
import { showToast } from '../utils/toast.js';
import {
  renderProviderSectionMarkup,
  renderListSkeletonMarkup,
  renderEditorSkeletonMarkup,
  renderEmptyListMarkup,
  renderProviderCardMarkup,
  renderProviderEditorMarkup,
} from './provider_crud/provider_crud_template.js';

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
 *
 * Szablon HTML wydzielony do `provider_crud/provider_crud_template.js` (wzorzec
 * `renderXMarkup` z `components/select.js`) — jak w `world_prompts_view.js`, brak
 * kanału SSE i drugiej niezależnej odpowiedzialności, więc reszta (stan, wiązanie
 * zdarzeń, zapis/usuwanie) zostaje w jednej klasie.
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
    /** @type {Map<string, number>} id (nieaktywnego presetu) -> priorytet fallbacku.
     * Puste, dopóki `api.getFallbackChain` nie jest skonfigurowane (dziś: tylko LLM) —
     * patrz `views/providers_config.js`. */
    this._priorities = new Map();
  }

  render() {
    return renderProviderSectionMarkup(this.idPrefix);
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
    await this._loadPriorities();

    if (this._providers.length === 0) {
      this._expandedId = null;
      listContainer.innerHTML = renderEmptyListMarkup(this.emptyLabel);
      return;
    }
    // Rozwinięty preset mógł zniknąć (usunięty w innej karcie przeglądarki).
    if (this._expandedId && !this._providers.some((p) => p.id === this._expandedId)) {
      this._expandedId = null;
    }

    listContainer.innerHTML = this._providers
      .map((provider) =>
        renderProviderCardMarkup(provider, schemas, {
          idPrefix: this.idPrefix,
          expandedId: this._expandedId,
          hasFallbackChain: !!this.api.getFallbackChain,
          fallbackPriority: this._priorities.get(provider.id),
        })
      )
      .join('');
    this._bindCards();
    if (this._expandedId) await this._mountEditor(this._expandedId);
  }

  /** Wypełnia `_priorities` z zapisanego łańcucha fallbacku — no-op, gdy ta domena
   * (STT/TTS) nie ma skonfigurowanych metod `getFallbackChain` w `api`. Aktywny
   * preset jest zawsze Priorytetem 0 (patrz `LLMRouter._candidate_ids`), więc
   * ewentualny jego wpis w zapisanym łańcuchu jest tu świadomie pomijany —
   * karta aktywnego presetu w ogóle nie renderuje pola priorytetu.
   *
   * **Filtrowanie po `knownIds` jest obowiązkowe, nie kosmetyczne**: preset
   * usunięty z listy (np. w innej karcie przeglądarki) mógł zostać w zapisanym
   * `priority_ids` na dysku — `set_fallback_chain` na backendzie odrzuca CAŁY
   * zapis, gdy choć jeden ID jest nieznany. Bez tego filtra edycja priorytetu
   * zupełnie INNEGO presetu wysyłałaby ten martwy ID z powrotem i psuła zapis
   * (obserwowane na żywo: `Nieznane ID presetów w łańcuchu fallbacku: [...]`). */
  async _loadPriorities() {
    this._priorities = new Map();
    if (!this.api.getFallbackChain) return;
    const chainData = await this.apiClient[this.api.getFallbackChain]();
    const activeId = this._providers.find((p) => p.is_active)?.id;
    const knownIds = new Set(this._providers.map((p) => p.id));
    (chainData?.priority_ids || [])
      .filter((id) => id !== activeId && knownIds.has(id))
      .forEach((id, index) => this._priorities.set(id, index + 1));
  }

  _bindCards() {
    const listContainer = document.getElementById(`${this.idPrefix}-providers-list`);
    listContainer?.querySelectorAll('[data-toggle]').forEach((head) => {
      const toggle = (e) => {
        // Przycisk aktywacji i pole priorytetu leżą wewnątrz nagłówka — nie mogą
        // przy okazji rozwijać karty.
        if (e.target.closest('[data-activate]') || e.target.closest('[data-priority-for]')) return;
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

    listContainer?.querySelectorAll('[data-priority-for]').forEach((input) => {
      input.addEventListener('click', (e) => e.stopPropagation());
      input.addEventListener('change', (e) => this._changePriority(e.target));
    });
  }

  async _toggleExpanded(providerId) {
    this._expandedId = this._expandedId === providerId ? null : providerId;
    this._draftOptions = {};
    await this.refresh();
  }

  /** Zapis natychmiastowy po zmianie pola priorytetu (ten sam wzorzec co "Aktywuj" —
   * bez osobnego przycisku "Zapisz", bo to jedna wartość, nie formularz). Puste/nie-
   * liczbowe/nie-dodatnie pole wyklucza preset z łańcucha fallbacku w całości. */
  async _changePriority(input) {
    const id = input.getAttribute('data-priority-for');
    const raw = input.value.trim();
    const value = raw === '' ? NaN : parseInt(raw, 10);
    if (!raw || !Number.isInteger(value) || value < 1) {
      this._priorities.delete(id);
    } else {
      this._priorities.set(id, value);
    }

    const priorityIds = [...this._priorities.entries()].sort((a, b) => a[1] - b[1]).map(([pid]) => pid);
    try {
      await this.apiClient[this.api.setFallbackChain](priorityIds);
      showToast('Zaktualizowano priorytet fallbacku.', 'success');
      await this.refresh();
    } catch (err) {
      showToast(`Błąd zapisu priorytetu: ${err.message}`, 'error');
      await this.refresh();
    }
  }

  // --------------------------------------------------------------------------
  // Edytor presetu
  // --------------------------------------------------------------------------

  async _mountEditor(providerId) {
    const mount = document.getElementById(`${this.idPrefix}-editor-${providerId}`);
    const provider = this._providers.find((p) => p.id === providerId);
    if (!mount || !provider) return;

    mount.innerHTML = renderEditorSkeletonMarkup();

    const schemas = await this._schemas();
    const typeSpec = schemas?.provider_types?.find((t) => t.type === provider.type);
    const modelsData = await this._models(provider, typeSpec);

    this._draftOptions = { ...provider.options, ...this._draftOptions };
    const selectedModel = this._draftOptions.model || '';
    const paramSchema = this._paramSchemaFor(modelsData, selectedModel);

    mount.innerHTML = renderProviderEditorMarkup({
      idPrefix: this.idPrefix,
      providerId,
      provider,
      typeSpec,
      modelsData,
      selectedModel,
      paramSchema,
      draftOptions: this._draftOptions,
    });

    this._mountFieldSelects(`${this.idPrefix}-base-${providerId}`, typeSpec?.options_schema || []);
    this._mountFieldSelects(`${this.idPrefix}-param-${providerId}`, paramSchema);
    if (modelsData) this._mountModelPicker(providerId, modelsData, selectedModel);

    mount.querySelector('[data-save]')?.addEventListener('click', () => this._save(providerId));
    mount.querySelector('[data-delete]')?.addEventListener('click', () => this._delete(providerId));
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

    const name = document.getElementById(`${this.idPrefix}-name-${providerId}`)?.value.trim();
    try {
      await this.apiClient[this.api.update](providerId, { name: name || null, options });
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
