import { Icons } from '../icons.js';
import { confirmModal } from '../modal_confirm.js';
import { escapeHtml, escapeAttr } from '../utils/dom.js';
import { showToast } from '../utils/toast.js';

const MAX_PROFILES = 3;

/**
 * Widok zarządzania profilami promptu Świata. World jest jedynym autorem promptu tury,
 * gdy podłączony — ten CRUD (do 3 przełączalnych profili tożsamości) żył wcześniej
 * w agent/ ("Prompty"), dziś należy do world/ (patrz docs/manifest.md).
 *
 * **Układ jednokolumnowy z pill-tabami, nie lista obok edytora.** Poprzedni wariant
 * (wąska kolumna listy po lewej, edytor po prawej) miał trzy niezależne problemy, które
 * wszystkie wynikały z tej samej pomyłki — traktowania trzech pozycji jak listy:
 * kolumna miała stałą wysokość i ~380 px pustki pod dwoma wpisami, choć limit to i tak
 * `MAX_PROFILES`; edytor dostawał połowę szerokości, więc pole Treść — najdłuższy tekst
 * w całej aplikacji — pokazywało kilka linii i scrollowało się WEWNĄTRZ i tak
 * scrollowanej strony; a akcje rozjeżdżały się na dwie kolumny. Przy trzech pozycjach
 * właściwą kontrolką jest przełącznik, nie lista — stąd te same pill-taby co w nagłówku
 * Ustawień (`components/pill_tabs.css`), a pod nimi edytor pełnej szerokości.
 *
 * Identyfikator profilu zszedł z pozycji nagłówka do stopki: to metadana techniczna,
 * a nie tytuł, więc nie ma prawa konkurować wzrokowo z nazwą.
 */
export class WorldPromptsView {
  constructor() {
    /** @type {import('../network/api_client.js').ApiClient|null} */
    this.apiClient = null;
    /** @type {Array<{id:string, name:string, description:string|null, content:string, is_active:boolean}>} */
    this.prompts = [];
    this.activeId = null;
    this.selectedId = null;
    this.isNewMode = false;
    /** Czy edytor ma niezapisane zmiany od ostatniego renderu/zapisu. */
    this.isDirty = false;
  }

  /** Wywoływane przez SettingsView/ExtensionsView przed opuszczeniem zakładki — chroni przed utratą edycji. */
  hasUnsavedChanges() {
    return this.isDirty;
  }

  render() {
    return `
      <div class="wp-layout" id="wp-layout">
        <nav class="pill-tabs wp-profile-tabs" id="wp-list"></nav>
        <div class="wp-panel-editor" id="wp-panel-editor">
          <div class="skeleton-stack">
            <div class="skeleton-block skeleton-block--field"></div>
            <div class="skeleton-block skeleton-block--section"></div>
          </div>
        </div>
      </div>
    `;
  }

  async init(apiClient) {
    this.apiClient = apiClient;
    await this._loadAndRender();
  }

  // --------------------------------------------------------------------------
  // Ładowanie i renderowanie listy
  // --------------------------------------------------------------------------

  async _loadAndRender(selectId = null) {
    const data = await this.apiClient.getWorldPrompts();
    if (!data) {
      this._renderListError();
      return;
    }
    this.prompts = data.prompts || [];
    this.activeId = data.active_id;
    this.isNewMode = false;

    if (selectId && this.prompts.some((p) => p.id === selectId)) {
      this.selectedId = selectId;
    } else if (!this.selectedId || !this.prompts.some((p) => p.id === this.selectedId)) {
      this.selectedId = this.activeId || (this.prompts[0]?.id ?? null);
    }

    this._renderList();
    const selected = this.prompts.find((p) => p.id === this.selectedId);
    if (selected) {
      this._renderEditor(selected);
    } else {
      this._renderEmptyEditor();
    }
  }

  _renderListError() {
    const list = document.getElementById('wp-list');
    if (list) list.innerHTML = `<div class="wp-list-error">Błąd ładowania listy profili promptu.</div>`;
  }

  /** Przełącznik profili — pill-taby, bo pozycji jest najwyżej `MAX_PROFILES`.
   * Kropka aktywności siedzi w samym tabie, więc widać ją bez wchodzenia w profil. */
  _renderList() {
    const list = document.getElementById('wp-list');
    if (!list) return;

    const atLimit = this.prompts.length >= MAX_PROFILES;
    const tabs = this.prompts
      .map((p) => {
        const isActive = p.id === this.activeId;
        const isSelected = !this.isNewMode && p.id === this.selectedId;
        return `
          <button type="button" class="pill-tab wp-profile-tab ${isSelected ? 'active' : ''}"
            data-id="${escapeAttr(p.id)}" title="${escapeAttr(p.description || p.name)}"
            ${isSelected ? 'aria-current="true"' : ''}>
            ${isActive ? '<span class="wp-profile-tab-dot" title="Aktywny profil"></span>' : ''}
            <span class="wp-profile-tab-name">${escapeHtml(p.name)}</span>
          </button>
        `;
      })
      .join('');

    const newTab = `
      <button type="button" class="pill-tab wp-profile-tab wp-profile-tab--new ${this.isNewMode ? 'active' : ''}"
        id="wp-btn-new" ${atLimit ? 'disabled' : ''}
        title="${atLimit ? `Osiągnięto limit ${MAX_PROFILES} profili` : 'Nowy profil'}">
        ${Icons.Plus()} Nowy
      </button>
    `;

    list.innerHTML = tabs + newTab;

    list.querySelectorAll('.wp-profile-tab[data-id]').forEach((el) => {
      el.addEventListener('click', () => this._selectPrompt(el.getAttribute('data-id')));
    });
    document.getElementById('wp-btn-new')?.addEventListener('click', () => this._enterNewMode());
  }

  async _confirmDiscard() {
    if (!this.isDirty) return true;
    return confirmModal({
      title: 'Niezapisane zmiany',
      message: 'Masz niezapisane zmiany w edytorze, które zostaną utracone. Kontynuować?',
      confirmLabel: 'Odrzuć zmiany',
    });
  }

  async _selectPrompt(id) {
    if (id === this.selectedId && !this.isNewMode) return;
    if (!(await this._confirmDiscard())) return;
    this.isNewMode = false;
    this.selectedId = id;
    this._renderList();
    const prompt = this.prompts.find((p) => p.id === id);
    if (prompt) this._renderEditor(prompt);
    else this._renderEmptyEditor();
  }

  async _enterNewMode() {
    if (this.isNewMode) return;
    if (this.prompts.length >= MAX_PROFILES) {
      this._showToast(`Osiągnięto limit ${MAX_PROFILES} profili promptu.`, 'error');
      return;
    }
    if (!(await this._confirmDiscard())) return;
    this.isNewMode = true;
    this.selectedId = null;
    this._renderList();
    this._renderNewEditor();
  }

  // --------------------------------------------------------------------------
  // Renderowanie edytora
  // --------------------------------------------------------------------------

  _renderEmptyEditor() {
    const panel = document.getElementById('wp-panel-editor');
    if (!panel) return;
    panel.innerHTML = `
      <div class="wp-editor-empty">
        <div class="wp-editor-empty-icon">${Icons.Cpu()}</div>
        <p>Wybierz prompt z listy lub utwórz nowy.</p>
      </div>
    `;
  }

  /**
   * Jeden szablon edytora dla obu trybów (edycja istniejącego / nowy profil) — wcześniej
   * były to dwa niemal identyczne bloki HTML, rozjeżdżające się przy każdej zmianie.
   * Różnią się wyłącznie zawartością stopki i paska akcji.
   */
  _editorMarkup({ name, description, content, footerLeft, actionsRight, activateButton = '', namePlaceholder = '' }) {
    return `
      <div class="wp-editor">
        <div class="wp-editor-topline">
          <div class="wp-editor-identity">
            <input type="text" id="wp-input-name" class="form-control wp-input-name"
              value="${escapeAttr(name)}" placeholder="${escapeAttr(namePlaceholder || 'Nazwa profilu')}"
              aria-label="Nazwa profilu" />
            <input type="text" id="wp-input-desc" class="form-control wp-input-desc"
              value="${escapeAttr(description)}" placeholder="Opis (opcjonalny)" aria-label="Opis profilu" />
          </div>
          <div class="wp-editor-topline-right">
            <span class="wp-dirty-badge hidden" id="wp-dirty-badge">Niezapisane zmiany</span>
            ${activateButton}
          </div>
        </div>

        <div class="wp-editor-content-wrap">
          <div class="wp-line-gutter" id="wp-line-gutter">1</div>
          <textarea id="wp-input-content" class="form-control wp-editor-textarea"
            placeholder="Treść instrukcji systemowej... (może być pusta)"
            aria-label="Treść profilu">${escapeHtml(content)}</textarea>
        </div>

        <div class="wp-editor-actions">
          <div class="wp-editor-actions-left">${footerLeft}</div>
          <div class="wp-editor-actions-right" id="wp-delete-zone">${actionsRight}</div>
        </div>
      </div>
    `;
  }

  _renderEditor(prompt) {
    const panel = document.getElementById('wp-panel-editor');
    if (!panel) return;
    this.isDirty = false;
    const isActive = prompt.id === this.activeId;

    panel.innerHTML = this._editorMarkup({
      name: prompt.name,
      description: prompt.description || '',
      content: prompt.content,
      activateButton: isActive
        ? '<span class="wp-badge-active" title="Ten profil trafia do promptu tury">Aktywny</span>'
        : '<button class="btn btn-sm btn-subtle" id="wp-btn-activate" title="Ustaw jako aktywny profil promptu">Ustaw jako aktywny</button>',
      // Identyfikator to metadana, nie tytuł — stopka, nie nagłówek.
      footerLeft: `
        <button class="btn btn-primary" id="wp-btn-save" disabled>Zapisz</button>
        <span class="wp-char-count" id="wp-char-count">0 znaków</span>
        <button class="wp-btn-copy-id" id="wp-btn-copy-id" title="Skopiuj ID profilu: ${escapeAttr(prompt.id)}"
          aria-label="Skopiuj ID profilu">${Icons.Copy()}<span>${escapeHtml(prompt.id)}</span></button>
      `,
      actionsRight: isActive
        ? `<span class="wp-delete-hint">Aby usunąć, najpierw ustaw inny profil jako aktywny</span>
           <button class="btn wp-btn-delete" id="wp-btn-delete" disabled title="Nie można usunąć aktywnego profilu">Usuń</button>`
        : '<button class="btn wp-btn-delete" id="wp-btn-delete">Usuń</button>',
    });

    document.getElementById('wp-btn-save')?.addEventListener('click', () => this._handleSave(prompt.id));
    if (!isActive) {
      document.getElementById('wp-btn-activate')?.addEventListener('click', () => this._handleActivate(prompt.id));
      document.getElementById('wp-btn-delete')?.addEventListener('click', () => this._handleDeleteClick(prompt.id));
    }
    document.getElementById('wp-btn-copy-id')?.addEventListener('click', () => this._handleCopyId(prompt.id));
    this._bindDirtyTracking(true);
    this._bindContentEditorExtras();
  }

  _renderNewEditor() {
    const panel = document.getElementById('wp-panel-editor');
    if (!panel) return;
    this.isDirty = false;

    panel.innerHTML = this._editorMarkup({
      name: '',
      description: '',
      content: '',
      namePlaceholder: 'np. Dom',
      footerLeft: `
        <button class="btn btn-primary" id="wp-btn-save">Zapisz</button>
        <span class="wp-char-count" id="wp-char-count">0 znaków</span>
      `,
      actionsRight: '<button class="btn btn-ghost" id="wp-btn-cancel-new">Anuluj</button>',
    });

    document.getElementById('wp-btn-save')?.addEventListener('click', () => this._handleCreate());
    document.getElementById('wp-btn-cancel-new')?.addEventListener('click', () => {
      this.isDirty = false;
      this.isNewMode = false;
      this.selectedId = this.activeId || (this.prompts[0]?.id ?? null);
      this._renderList();
      const prompt = this.prompts.find((p) => p.id === this.selectedId);
      if (prompt) this._renderEditor(prompt);
      else this._renderEmptyEditor();
    });
    this._bindDirtyTracking();
    this._bindContentEditorExtras();

    document.getElementById('wp-input-name')?.focus();
  }

  /**
   * Oznacza edytor jako "brudny" (niezapisane zmiany) przy pierwszym wpisie w dowolne pole.
   * `lockSaveUntilDirty` odblokowuje przycisk Zapisz dopiero po realnej zmianie — dotyczy
   * tylko edycji istniejącego profilu, nie tworzenia nowego (tam Zapisz jest potrzebny od razu).
   */
  _bindDirtyTracking(lockSaveUntilDirty = false) {
    const saveBtn = document.getElementById('wp-btn-save');
    ['wp-input-name', 'wp-input-desc', 'wp-input-content'].forEach((id) => {
      document.getElementById(id)?.addEventListener('input', (e) => {
        this.isDirty = true;
        e.target.classList.remove('is-invalid');
        document.getElementById('wp-dirty-badge')?.classList.remove('hidden');
        if (lockSaveUntilDirty && saveBtn) saveBtn.disabled = false;
      });
    });
  }

  /** Numeracja linii (zsynchronizowana ze scrollem) i licznik znaków dla pola Treść. */
  _bindContentEditorExtras() {
    const textarea = document.getElementById('wp-input-content');
    const gutter = document.getElementById('wp-line-gutter');
    const charCount = document.getElementById('wp-char-count');
    if (!textarea) return;

    const update = () => {
      const lineCount = textarea.value.split('\n').length;
      if (gutter) {
        gutter.innerHTML = Array.from({ length: lineCount }, (_, i) => i + 1).join('<br>');
      }
      if (charCount) {
        charCount.textContent = `${textarea.value.length} znaków`;
      }
    };

    textarea.addEventListener('input', update);
    textarea.addEventListener('scroll', () => {
      if (gutter) gutter.scrollTop = textarea.scrollTop;
    });
    update();
  }

  // --------------------------------------------------------------------------
  // Akcje
  // --------------------------------------------------------------------------

  _readForm() {
    const name = document.getElementById('wp-input-name')?.value.trim() || '';
    const description = document.getElementById('wp-input-desc')?.value.trim() || '';
    const content = document.getElementById('wp-input-content')?.value.trim() || '';
    return { name, description, content };
  }

  /** Oznacza puste wymagane pola (Nazwa) na czerwono i przenosi focus. Treść może być pusta (brak persony). Zwraca true jeśli formularz jest poprawny. */
  _validateForm(name) {
    const nameEl = document.getElementById('wp-input-name');
    nameEl?.classList.toggle('is-invalid', !name);
    if (!name) {
      nameEl?.focus();
      return false;
    }
    return true;
  }

  async _handleSave(promptId) {
    const { name, description, content } = this._readForm();
    if (!this._validateForm(name)) {
      this._showToast('Nazwa profilu jest wymagana.', 'error');
      return;
    }
    try {
      await this.apiClient.updateWorldPrompt(promptId, { name, description: description || null, content });
      this._showToast('Zapisano zmiany w profilu.', 'success');
      await this._loadAndRender(promptId);
    } catch (error) {
      this._showToast(error.message || 'Błąd zapisu profilu.', 'error');
    }
  }

  async _handleCreate() {
    const { name, description, content } = this._readForm();
    if (!this._validateForm(name)) {
      this._showToast('Nazwa profilu jest wymagana.', 'error');
      return;
    }
    try {
      const created = await this.apiClient.createWorldPrompt({ name, description: description || null, content });
      this._showToast('Utworzono nowy profil.', 'success');
      await this._loadAndRender(created.id);
    } catch (error) {
      this._showToast(error.message || 'Błąd tworzenia profilu.', 'error');
    }
  }

  async _handleActivate(promptId) {
    if (!(await this._confirmDiscard())) return;
    try {
      await this.apiClient.activateWorldPrompt(promptId);
      this._showToast('Aktywowano profil promptu.', 'success');
      await this._loadAndRender(promptId);
    } catch (error) {
      this._showToast(error.message || 'Błąd aktywacji profilu.', 'error');
    }
  }

  async _handleCopyId(promptId) {
    try {
      await navigator.clipboard.writeText(promptId);
      this._showToast('Skopiowano ID profilu.', 'success');
    } catch (error) {
      this._showToast('Nie udało się skopiować ID.', 'error');
    }
  }

  _handleDeleteClick(promptId) {
    const zone = document.getElementById('wp-delete-zone');
    if (!zone) return;
    zone.innerHTML = `
      <div class="delete-confirm-inline">
        <span class="delete-confirm-text">Usunąć profil?</span>
        <button class="btn-confirm-yes" id="wp-btn-delete-yes">Tak</button>
        <button class="btn-confirm-no" id="wp-btn-delete-no">Anuluj</button>
      </div>
    `;
    document.getElementById('wp-btn-delete-yes')?.addEventListener('click', () => this._handleDeleteConfirm(promptId));
    document.getElementById('wp-btn-delete-no')?.addEventListener('click', () => {
      // Przywraca tylko strefę przycisku Usuń — pełny re-render edytora
      // wyzerowałby niezapisane zmiany w Nazwie/Opisie/Treści.
      zone.innerHTML = `<button class="btn wp-btn-delete" id="wp-btn-delete">Usuń</button>`;
      document.getElementById('wp-btn-delete')?.addEventListener('click', () => this._handleDeleteClick(promptId));
    });
  }

  async _handleDeleteConfirm(promptId) {
    try {
      await this.apiClient.deleteWorldPrompt(promptId);
      this._showToast('Usunięto profil.', 'success');
      this.selectedId = null;
      await this._loadAndRender();
    } catch (error) {
      this._showToast(error.message || 'Błąd usuwania profilu.', 'error');
    }
  }

  // --------------------------------------------------------------------------
  // Toast
  // --------------------------------------------------------------------------

  _showToast(message, type = 'success') {
    showToast(message, type);
  }
}
