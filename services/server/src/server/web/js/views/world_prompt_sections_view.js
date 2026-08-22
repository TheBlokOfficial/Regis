import { Icons } from '../icons.js';
import { renderSelectMarkup, initSelect } from '../components/select.js';
import { confirmModal } from '../modal_confirm.js';
import { flashButtonResult, lockButtonForAction } from '../utils/button_flash.js';
import { escapeAttr, escapeHtml } from '../utils/dom.js';
import { showToast } from '../utils/toast.js';

/**
 * Panel "Kontekst tury" — komponowalna lista bloków tekstu wstrzykiwanych agentowi
 * przed każdym pytaniem (`server/world/prompt_sections.py`).
 *
 * Sekcje można dodawać, usuwać i przestawiać; każda ma warunek pojawienia się
 * wybierany z listy dostarczonej przez serwer (z opcjonalną negacją). Etykiety
 * warunków i podstawień pochodzą z `GET /prompt-sections`, nie są duplikowane
 * tutaj — jedno źródło prawdy.
 *
 * **Stan trzymany jest w pamięci widoku, zapisywany jawnym przyciskiem.** Lista
 * jest jednym bytem (kolejność ma znaczenie), więc zapis per pole nie miałby sensu:
 * przestawienie i usunięcie to ta sama operacja co edycja tekstu.
 *
 * Przestawianie **przyciskami góra/dół, nie drag-and-drop** — projekt nie ma build
 * stepu ani zależności, a strzałki są przewidywalne i działają z klawiatury.
 */
export class WorldPromptSectionsView {
  constructor() {
    this.apiClient = null;
    this._sections = [];
    this._conditions = [];
    this._placeholders = [];
    this._rooms = [];
    this._clients = [];
    this._previewSenderId = '';
    this._dirty = false;
  }

  render() {
    return `
      <div id="wps-root">
        <p class="section-hint wps-intro">Ładowanie sekcji kontekstu tury...</p>
      </div>
    `;
  }

  async init(apiClient) {
    this.apiClient = apiClient;
    const [data, rooms, clients] = await Promise.all([
      this.apiClient.getPromptSections(),
      this.apiClient.getRooms(),
      this.apiClient.getSenders(),
    ]);
    this._applyServerData(data);
    this._rooms = rooms || [];
    this._clients = clients || [];
    this._previewSenderId = this._clients[0]?.sender_id || '';
    this._render();
  }

  hasUnsavedChanges() {
    return this._dirty;
  }

  _applyServerData(data) {
    if (!data) return;
    this._sections = data.sections || [];
    this._conditions = data.conditions || [];
    this._placeholders = data.placeholders || [];
    this._dirty = false;
  }

  // --------------------------------------------------------------------------
  // Render
  // --------------------------------------------------------------------------

  _render() {
    const root = document.getElementById('wps-root');
    if (!root) return;

    root.innerHTML = `
      <p class="section-hint wps-intro">
        Bloki tekstu wstrzykiwane agentowi tuż przed każdym pytaniem, w tej kolejności.
        Silnik dostarcza dane; warunek decyduje, czy blok w ogóle się pojawi.
      </p>
      ${this._renderPlaceholderLegend()}
      <div id="wps-list">${this._sections.map((s, i) => this._renderSection(s, i)).join('')}</div>
      <div class="wps-toolbar">
        <button type="button" class="btn btn-sm btn-subtle" id="wps-add">${Icons.Plus()} Nowa sekcja</button>
        <span class="wps-toolbar-right">
          <button type="button" class="btn btn-sm btn-ghost" id="wps-reset">Przywróć zestaw domyślny</button>
          <button type="button" class="btn" id="wps-save" ${this._dirty ? '' : 'disabled'}>Zapisz</button>
        </span>
      </div>
      ${this._renderPreview()}
    `;

    this._bind();
  }

  _renderPlaceholderLegend() {
    const always = this._placeholders.filter((p) => !p.guaranteed_by.length);
    const conditional = this._placeholders.filter((p) => p.guaranteed_by.length);
    const chip = (p) => `<code class="wps-placeholder" title="${escapeAttr(p.label)}">${escapeHtml(p.token)}</code>`;
    return `
      <div class="wps-legend">
        <span class="wps-legend-group"><span class="wps-legend-label">Zawsze dostępne:</span> ${always.map(chip).join(' ')}</span>
        <span class="wps-legend-group"><span class="wps-legend-label">Wymagają warunku:</span> ${conditional.map(chip).join(' ')}</span>
      </div>
    `;
  }

  _renderSection(section, index) {
    const spec = this._conditions.find((c) => c.key === section.condition);
    const needsParam = Boolean(spec?.param_source);
    const warnings = section.warnings || [];

    return `
      <div class="wps-section" data-index="${index}">
        <div class="wps-section-header">
          <input type="text" class="wps-label-input" data-field="label" value="${escapeAttr(section.label)}"
            aria-label="Nazwa sekcji" />
          <span class="wps-section-actions">
            <button type="button" class="btn btn-ghost btn-icon-square" data-move="up" ${index === 0 ? 'disabled' : ''}
              title="W górę" aria-label="Przesuń w górę">${Icons.ChevronDown()}</button>
            <button type="button" class="btn btn-ghost btn-icon-square" data-move="down"
              ${index === this._sections.length - 1 ? 'disabled' : ''} title="W dół" aria-label="Przesuń w dół">${Icons.ChevronDown()}</button>
            <button type="button" class="btn btn-ghost-danger btn-icon-square" data-remove="1"
              title="Usuń sekcję" aria-label="Usuń sekcję">${Icons.Trash2()}</button>
          </span>
        </div>

        <div class="wps-condition-row">
          <span class="wps-condition-label">Pokaż gdy</span>
          <label class="wps-negate">
            <input type="checkbox" data-field="negated" ${section.negated ? 'checked' : ''} />
            <span>NIE</span>
          </label>
          ${renderSelectMarkup(`wps-cond-${index}`, { placeholder: 'Wybierz warunek', className: 'select--compact' })}
          ${needsParam ? renderSelectMarkup(`wps-param-${index}`, { placeholder: 'Wybierz pokój', className: 'select--compact' }) : ''}
        </div>

        <div class="wps-box">
          <textarea class="wps-textarea" data-field="text" rows="3"
            placeholder="(puste — sekcja nie trafi do promptu)">${escapeHtml(section.text)}</textarea>
        </div>

        ${warnings.map((w) => `<p class="wps-warning">${Icons.AlertCircle()} ${escapeHtml(w)}</p>`).join('')}
      </div>
    `;
  }

  _renderPreview() {
    const options = this._clients.length
      ? renderSelectMarkup('wps-preview-client', { placeholder: 'Wybierz klienta', className: 'select--compact' })
      : '<span class="wps-preview-empty">Brak zarejestrowanych klientów — zarejestruj któregoś w zakładce Klienci.</span>';
    return `
      <h4 class="section-subheading wps-preview-heading">Podgląd</h4>
      <p class="section-hint">
        Dokładnie ten tekst dostanie agent. Składany tą samą ścieżką co realna tura,
        więc widać też skutki warunków — sekcja, która nigdy się nie pojawia, po prostu tu nie będzie.
      </p>
      <div class="wps-preview-controls">
        ${options}
        <button type="button" class="btn btn-sm btn-subtle" id="wps-preview-refresh" ${this._clients.length ? '' : 'disabled'}>
          ${Icons.RefreshCw()} Odśwież
        </button>
      </div>
      <pre class="wps-preview-output" id="wps-preview-output">(kliknij „Odśwież”, żeby zobaczyć złożony kontekst)</pre>
    `;
  }

  // --------------------------------------------------------------------------
  // Zdarzenia
  // --------------------------------------------------------------------------

  _bind() {
    const list = document.getElementById('wps-list');

    list?.querySelectorAll('.wps-section').forEach((el) => {
      const index = Number(el.dataset.index);
      el.querySelector('[data-field="label"]')?.addEventListener('input', (e) => this._patch(index, { label: e.target.value }));
      el.querySelector('[data-field="text"]')?.addEventListener('input', (e) => this._patch(index, { text: e.target.value }));
      el.querySelector('[data-field="negated"]')?.addEventListener('change', (e) => this._patch(index, { negated: e.target.checked }, true));
      el.querySelector('[data-move="up"]')?.addEventListener('click', () => this._move(index, -1));
      el.querySelector('[data-move="down"]')?.addEventListener('click', () => this._move(index, 1));
      el.querySelector('[data-remove]')?.addEventListener('click', () => this._remove(index));
    });

    // Custom-select (projekt świadomie nie używa natywnego <select>) montuje się
    // po wstawieniu markupu, osobno dla warunku i jego parametru.
    this._sections.forEach((section, index) => {
      initSelect({
        idPrefix: `wps-cond-${index}`,
        options: this._conditions.map((c) => ({ value: c.key, label: c.label })),
        value: section.condition,
        placeholder: 'Wybierz warunek',
        onChange: (value) => this._patch(index, { condition: value, condition_param: null }, true),
      });
      const spec = this._conditions.find((c) => c.key === section.condition);
      if (spec?.param_source) {
        initSelect({
          idPrefix: `wps-param-${index}`,
          options: this._rooms.map((r) => ({ value: r.id, label: r.name })),
          value: section.condition_param || '',
          placeholder: 'Wybierz pokój',
          onChange: (value) => this._patch(index, { condition_param: value || null }, true),
        });
      }
    });

    document.getElementById('wps-add')?.addEventListener('click', () => this._add());
    document.getElementById('wps-save')?.addEventListener('click', () => this._save());
    document.getElementById('wps-reset')?.addEventListener('click', () => this._reset());
    document.getElementById('wps-preview-refresh')?.addEventListener('click', () => this._refreshPreview());

    if (this._clients.length) {
      initSelect({
        idPrefix: 'wps-preview-client',
        options: this._clients.map((c) => ({
          value: c.sender_id,
          label: c.room_name ? `…${c.sender_id.slice(-8)} (${c.room_name})` : `…${c.sender_id.slice(-8)}`,
        })),
        value: this._previewSenderId,
        placeholder: 'Wybierz klienta',
        onChange: (value) => {
          this._previewSenderId = value;
          this._refreshPreview();
        },
      });
    }
  }

  /** `rerender` tylko tam, gdzie zmiana wpływa na KSZTAŁT formularza (warunek może
   * dołożyć/zabrać picker parametru). Przy pisaniu w polu tekstowym re-render
   * zabrałby fokus w połowie zdania. */
  _patch(index, changes, rerender = false) {
    this._sections[index] = { ...this._sections[index], ...changes };
    this._markDirty();
    if (rerender) this._render();
  }

  _markDirty() {
    this._dirty = true;
    const btn = document.getElementById('wps-save');
    if (btn) btn.disabled = false;
  }

  _move(index, delta) {
    const target = index + delta;
    if (target < 0 || target >= this._sections.length) return;
    const next = [...this._sections];
    [next[index], next[target]] = [next[target], next[index]];
    this._sections = next;
    this._markDirty();
    this._render();
  }

  async _remove(index) {
    const confirmed = await confirmModal({
      title: 'Usunąć sekcję?',
      message: 'Sekcja zniknie z promptu po zapisaniu listy.',
      confirmLabel: 'Usuń',
      cancelLabel: 'Anuluj',
    });
    if (!confirmed) return;
    this._sections = this._sections.filter((_, i) => i !== index);
    this._markDirty();
    this._render();
  }

  _add() {
    this._sections = [
      ...this._sections,
      {
        id: `sec_${Math.random().toString(16).slice(2, 10)}`,
        label: 'Nowa sekcja',
        text: '',
        condition: 'always',
        condition_param: null,
        negated: false,
        warnings: [],
      },
    ];
    this._markDirty();
    this._render();
  }

  async _save() {
    const btn = document.getElementById('wps-save');
    if (!btn) return;
    lockButtonForAction(btn);
    let ok = false;
    try {
      const payload = this._sections.map(({ warnings, ...section }) => section);
      this._applyServerData(await this.apiClient.updatePromptSections(payload));
      ok = true;
    } catch (error) {
      showToast(error.message || 'Błąd zapisu sekcji.', 'error');
    }
    flashButtonResult(btn, ok, { successHtml: Icons.Check(), errorHtml: Icons.X() });
    // Re-render dopiero PO rozbłysku — inaczej przycisk zniknąłby z DOM w trakcie
    // animacji i użytkownik nie zobaczyłby potwierdzenia zapisu.
    if (ok) setTimeout(() => this._render(), 2100);
  }

  async _reset() {
    const confirmed = await confirmModal({
      title: 'Przywrócić zestaw domyślny?',
      message: 'Wszystkie własne sekcje i zmiany zostaną zastąpione zestawem startowym.',
      confirmLabel: 'Przywróć',
      cancelLabel: 'Anuluj',
    });
    if (!confirmed) return;
    try {
      this._applyServerData(await this.apiClient.resetPromptSections());
      this._render();
      showToast('Przywrócono zestaw domyślny.', 'success');
    } catch (error) {
      showToast(error.message || 'Błąd przywracania zestawu domyślnego.', 'error');
    }
  }

  async _refreshPreview() {
    const output = document.getElementById('wps-preview-output');
    if (!output) return;
    if (this._dirty) {
      output.textContent = 'Podgląd pokazuje stan ZAPISANY — zapisz zmiany, żeby zobaczyć ich efekt.';
      return;
    }
    const result = await this.apiClient.previewPromptSections(this._previewSenderId);
    output.textContent = result?.turn_context || '(pusty kontekst — żadna sekcja nie spełnia warunku)';
  }
}
