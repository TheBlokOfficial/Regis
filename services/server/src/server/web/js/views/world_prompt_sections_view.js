import { Icons } from '../icons.js';
import { renderSelectMarkup, initSelect } from '../components/select.js';
import { confirmModal } from '../modal_confirm.js';
import { flashButtonResult, lockButtonForAction } from '../utils/button_flash.js';
import { escapeAttr, escapeHtml } from '../utils/dom.js';
import { senderLabel } from '../utils/sender_label.js';
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
 * **Każda sekcja ma DWIE gałęzie tekstu** — co powiedzieć, gdy warunek jest spełniony,
 * i co gdy nie jest. Wcześniej ta druga wymagała osobnej sekcji z checkboxem "NIE",
 * przez co jedna decyzja była rozbita na dwa wpisy, które nic formalnie nie łączyło
 * (dało się je niezależnie przestawić w odległe miejsca promptu). Przy okazji zniknął
 * checkbox — jedna z ostatnich natywnych kontrolek przeglądarki w tym projekcie.
 *
 * **Przestawianie przez drag-and-drop** (HTML5 DnD, zero zależności i build stepu):
 * strzałki góra/dół przerenderowywały całą listę na każde kliknięcie, więc przesunięcie
 * sekcji o kilka pozycji było serią skoków z gubionym fokusem. Uchwyt jest osobnym
 * elementem, nie całą kartą — inaczej nie dałoby się zaznaczyć tekstu w polach.
 * Dostępność z klawiatury zostaje: uchwyt przyjmuje fokus i reaguje na strzałki.
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
    /** Indeks przeciąganej sekcji; `null` poza trwającym gestem. */
    this._dragFrom = null;
  }

  /** Szkielet o geometrii docelowej listy — patrz `css/components/skeleton.css`. */
  render() {
    return `
      <div id="wps-root" aria-busy="true">
        <div class="skeleton-stack">
          <div class="skeleton-block skeleton-block--row"></div>
          <div class="skeleton-block skeleton-block--section"></div>
          <div class="skeleton-block skeleton-block--section"></div>
          <div class="skeleton-block skeleton-block--section"></div>
        </div>
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
    // Przy warunku "Zawsze" gałąź "gdy NIE" jest martwa z definicji — nie pokazujemy jej
    // wcale, zamiast wyszarzać pole, którego nic nigdy nie użyje.
    const hasNegatedBranch = section.condition !== 'always';

    return `
      <div class="wps-section" data-index="${index}" draggable="false">
        <div class="wps-section-header">
          <span class="wps-drag-handle" data-drag-handle="${index}" draggable="true" tabindex="0"
            role="button" aria-label="Przeciągnij, żeby zmienić kolejność (strzałki góra/dół z klawiatury)"
            title="Przeciągnij, żeby zmienić kolejność">${Icons.GripVertical()}</span>
          <input type="text" class="wps-label-input" data-field="label" value="${escapeAttr(section.label)}"
            aria-label="Nazwa sekcji" />
          <span class="wps-section-actions">
            <button type="button" class="btn btn-ghost-danger btn-icon-square" data-remove="1"
              title="Usuń sekcję" aria-label="Usuń sekcję">${Icons.Trash2()}</button>
          </span>
        </div>

        <div class="wps-condition-row">
          <span class="wps-condition-label">Warunek</span>
          ${renderSelectMarkup(`wps-cond-${index}`, { placeholder: 'Wybierz warunek', className: 'select--compact' })}
          ${needsParam ? renderSelectMarkup(`wps-param-${index}`, { placeholder: 'Wybierz pokój', className: 'select--compact' }) : ''}
        </div>

        <div class="wps-branches ${hasNegatedBranch ? '' : 'wps-branches--single'}">
          <div class="wps-branch">
            <label class="wps-branch-label wps-branch-label--yes">${hasNegatedBranch ? 'Gdy spełniony' : 'Tekst sekcji'}</label>
            <textarea class="wps-textarea" data-field="text" rows="3"
              placeholder="(puste — przy tym wyniku sekcja nic nie dokłada)">${escapeHtml(section.text)}</textarea>
          </div>
          ${
            hasNegatedBranch
              ? `<div class="wps-branch">
                   <label class="wps-branch-label wps-branch-label--no">Gdy niespełniony</label>
                   <textarea class="wps-textarea" data-field="text_negated" rows="3"
                     placeholder="(puste — przy tym wyniku sekcja nic nie dokłada)">${escapeHtml(section.text_negated || '')}</textarea>
                 </div>`
              : ''
          }
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
      el.querySelector('[data-field="text_negated"]')?.addEventListener('input', (e) => this._patch(index, { text_negated: e.target.value }));
      el.querySelector('[data-remove]')?.addEventListener('click', () => this._remove(index));
      this._bindDragHandle(el, index);
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
          label: c.room_name ? `${senderLabel(c)} (${c.room_name})` : senderLabel(c),
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

  /**
   * Przeciąganie za uchwyt. Podświetlenie miejsca upuszczenia idzie przez klasę na
   * elemencie pod kursorem, a nie przez podmianę listy w locie — przestawianie tablicy
   * na każdym `dragover` przerenderowywałoby DOM w trakcie przeciągania i przeglądarka
   * gubiłaby trwający gest.
   */
  _bindDragHandle(sectionEl, index) {
    const handle = sectionEl.querySelector('[data-drag-handle]');
    if (!handle) return;

    handle.addEventListener('dragstart', (e) => {
      this._dragFrom = index;
      sectionEl.classList.add('is-dragging');
      e.dataTransfer.effectAllowed = 'move';
      // Firefox nie wystartuje przeciągania bez jakichkolwiek danych w transferze.
      e.dataTransfer.setData('text/plain', String(index));
      e.dataTransfer.setDragImage(sectionEl, 20, 20);
    });

    handle.addEventListener('dragend', () => {
      this._dragFrom = null;
      document.querySelectorAll('.wps-section').forEach((el) => {
        el.classList.remove('is-dragging', 'is-drop-before', 'is-drop-after');
      });
    });

    // Strzałki z klawiatury zostają jako równoważna ścieżka — uchwyt jest fokusowalny,
    // więc przestawianie działa bez myszy (drag-and-drop sam w sobie jest niedostępny).
    handle.addEventListener('keydown', (e) => {
      if (e.key !== 'ArrowUp' && e.key !== 'ArrowDown') return;
      e.preventDefault();
      this._moveTo(index, index + (e.key === 'ArrowUp' ? -1 : 1), { focusHandleAt: true });
    });

    sectionEl.addEventListener('dragover', (e) => {
      if (this._dragFrom === null || this._dragFrom === undefined || this._dragFrom === index) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      const rect = sectionEl.getBoundingClientRect();
      const dropAfter = e.clientY > rect.top + rect.height / 2;
      sectionEl.classList.toggle('is-drop-before', !dropAfter);
      sectionEl.classList.toggle('is-drop-after', dropAfter);
    });

    sectionEl.addEventListener('dragleave', () => {
      sectionEl.classList.remove('is-drop-before', 'is-drop-after');
    });

    sectionEl.addEventListener('drop', (e) => {
      if (this._dragFrom === null || this._dragFrom === undefined) return;
      e.preventDefault();
      const rect = sectionEl.getBoundingClientRect();
      const dropAfter = e.clientY > rect.top + rect.height / 2;
      this._moveTo(this._dragFrom, dropAfter ? index + 1 : index);
      this._dragFrom = null;
    });
  }

  /** Przenosi sekcję na wskazaną POZYCJĘ (nie zamienia dwóch miejscami) — przy
   * przeciąganiu przez kilka pozycji zamiana dałaby zupełnie inny wynik niż wstawienie. */
  _moveTo(from, to, { focusHandleAt = false } = {}) {
    const next = [...this._sections];
    const [moved] = next.splice(from, 1);
    // Po wyjęciu elementu indeksy za nim przesuwają się o jeden w lewo.
    const insertAt = Math.max(0, Math.min(next.length, to > from ? to - 1 : to));
    if (insertAt === from) return;
    next.splice(insertAt, 0, moved);
    this._sections = next;
    this._markDirty();
    this._render();
    if (focusHandleAt) {
      document.querySelector(`[data-drag-handle="${insertAt}"]`)?.focus();
    }
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
        text_negated: '',
        condition: 'always',
        condition_param: null,
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
