import { Icons } from '../icons.js';

/**
 * Widok zarządzania promptami systemowymi Agenta — lista promptów (lewa kolumna)
 * i edytor inline (prawa kolumna).
 */
export class AgentsView {
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

  /** Wywoływane przez TabManager przed opuszczeniem zakładki — chroni przed utratą edycji. */
  hasUnsavedChanges() {
    return this.isDirty;
  }

  render() {
    return `
      <div class="agents-layout" id="agents-layout">
        <div class="agents-panel-list">
          <div class="agents-panel-header">
            <span class="agents-panel-title">Prompty</span>
            <button class="btn btn-sm btn-subtle" id="agents-btn-new">+ Nowy</button>
          </div>
          <div class="agents-list" id="agents-list">
            <div class="agents-list-loading">Ładowanie...</div>
          </div>
        </div>
        <div class="agents-panel-editor" id="agents-panel-editor">
          <div class="agents-editor-empty">
            <div class="agents-editor-empty-icon">${Icons.Cpu()}</div>
            <p>Wybierz prompt z listy lub utwórz nowy.</p>
          </div>
        </div>
      </div>
    `;
  }

  async init(apiClient) {
    this.apiClient = apiClient;
    document.getElementById('agents-btn-new')?.addEventListener('click', () => this._enterNewMode());
    await this._loadAndRender();
  }

  // --------------------------------------------------------------------------
  // Ładowanie i renderowanie listy
  // --------------------------------------------------------------------------

  async _loadAndRender(selectId = null) {
    const data = await this.apiClient.getPrompts();
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
    const list = document.getElementById('agents-list');
    if (list) list.innerHTML = `<div class="agents-list-error">Błąd ładowania listy promptów.</div>`;
  }

  _renderList() {
    const list = document.getElementById('agents-list');
    if (!list) return;

    if (this.prompts.length === 0) {
      list.innerHTML = `<div class="agents-list-empty">Brak zapisanych promptów.</div>`;
      return;
    }

    list.innerHTML = this.prompts
      .map((p) => {
        const isActive = p.id === this.activeId;
        const isSelected = !this.isNewMode && p.id === this.selectedId;
        return `
          <div class="agents-list-item ${isSelected ? 'selected' : ''} ${isActive ? 'is-active' : ''}" data-id="${escapeHtml(p.id)}" role="button" tabindex="0" ${isSelected ? 'aria-current="true"' : ''}>
            <div class="agents-list-item-row">
              <span class="agents-list-item-dot"></span>
              <span class="agents-list-item-name" title="${escapeAttr(p.name)}">${escapeHtml(p.name)}</span>
              ${isActive ? '<span class="agents-badge-active">Aktywny</span>' : ''}
            </div>
            ${p.description ? `<span class="agents-list-item-desc" title="${escapeAttr(p.description)}">${escapeHtml(p.description)}</span>` : ''}
          </div>
        `;
      })
      .join('');

    list.querySelectorAll('.agents-list-item').forEach((el) => {
      el.addEventListener('click', () => this._selectPrompt(el.getAttribute('data-id')));
      el.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          this._selectPrompt(el.getAttribute('data-id'));
        }
      });
    });
  }

  _confirmDiscard() {
    if (!this.isDirty) return true;
    return window.confirm('Masz niezapisane zmiany w edytorze, które zostaną utracone. Kontynuować?');
  }

  _selectPrompt(id) {
    if (id === this.selectedId && !this.isNewMode) return;
    if (!this._confirmDiscard()) return;
    this.isNewMode = false;
    this.selectedId = id;
    this._renderList();
    const prompt = this.prompts.find((p) => p.id === id);
    if (prompt) this._renderEditor(prompt);
    else this._renderEmptyEditor();
  }

  _enterNewMode() {
    if (this.isNewMode) return;
    if (!this._confirmDiscard()) return;
    this.isNewMode = true;
    this.selectedId = null;
    this._renderList();
    this._renderNewEditor();
  }

  // --------------------------------------------------------------------------
  // Renderowanie edytora
  // --------------------------------------------------------------------------

  _renderEmptyEditor() {
    const panel = document.getElementById('agents-panel-editor');
    if (!panel) return;
    panel.innerHTML = `
      <div class="agents-editor-empty">
        <div class="agents-editor-empty-icon">${Icons.Cpu()}</div>
        <p>Wybierz prompt z listy lub utwórz nowy.</p>
      </div>
    `;
  }

  _renderEditor(prompt) {
    const panel = document.getElementById('agents-panel-editor');
    if (!panel) return;
    this.isDirty = false;
    const isActive = prompt.id === this.activeId;

    panel.innerHTML = `
      <div class="agents-editor">
        <div class="agents-editor-header">
          <span class="badge-muted" title="Wewnętrzny identyfikator promptu">ID: ${escapeHtml(prompt.id)}</span>
          ${isActive ? '<span class="agents-badge-active">Aktywny prompt systemowy</span>' : ''}
        </div>
        <div class="agents-editor-fields">
          <div class="form-group agents-field-compact">
            <label for="agents-input-name">Nazwa</label>
            <input type="text" id="agents-input-name" class="form-control" value="${escapeAttr(prompt.name)}" />
          </div>
          <div class="form-group agents-field-compact">
            <label for="agents-input-desc">Opis (opcjonalny)</label>
            <input type="text" id="agents-input-desc" class="form-control" value="${escapeAttr(prompt.description || '')}" />
          </div>
          <div class="form-group agents-editor-content-group">
            <label for="agents-input-content">Treść</label>
            <textarea id="agents-input-content" class="form-control agents-editor-textarea">${escapeHtml(prompt.content)}</textarea>
          </div>
        </div>
        <div class="agents-editor-actions">
          <div class="agents-editor-actions-left">
            <button class="btn btn-primary" id="agents-btn-save">Zapisz</button>
            <button class="btn" id="agents-btn-activate" ${isActive ? 'disabled' : ''}>Aktywuj</button>
          </div>
          <div class="agents-editor-actions-right" id="agents-delete-zone">
            <button class="btn agents-btn-delete" id="agents-btn-delete" ${isActive ? 'disabled title="Nie można usunąć aktywnego promptu"' : ''}>Usuń</button>
          </div>
        </div>
      </div>
    `;

    document.getElementById('agents-btn-save')?.addEventListener('click', () => this._handleSave(prompt.id));
    document.getElementById('agents-btn-activate')?.addEventListener('click', () => this._handleActivate(prompt.id));
    if (!isActive) {
      document.getElementById('agents-btn-delete')?.addEventListener('click', () => this._handleDeleteClick(prompt.id));
    }
    this._bindDirtyTracking();
  }

  _renderNewEditor() {
    const panel = document.getElementById('agents-panel-editor');
    if (!panel) return;
    this.isDirty = false;

    panel.innerHTML = `
      <div class="agents-editor">
        <div class="agents-editor-header">
          <span class="badge-muted">Nowy prompt</span>
        </div>
        <div class="agents-editor-fields">
          <div class="form-group agents-field-compact">
            <label for="agents-input-name">Nazwa</label>
            <input type="text" id="agents-input-name" class="form-control" placeholder="np. Prompt Asystenta Kodu" />
          </div>
          <div class="form-group agents-field-compact">
            <label for="agents-input-desc">Opis (opcjonalny)</label>
            <input type="text" id="agents-input-desc" class="form-control" placeholder="Krótki opis przeznaczenia promptu" />
          </div>
          <div class="form-group agents-editor-content-group">
            <label for="agents-input-content">Treść</label>
            <textarea id="agents-input-content" class="form-control agents-editor-textarea" placeholder="Treść instrukcji systemowej..."></textarea>
          </div>
        </div>
        <div class="agents-editor-actions">
          <div class="agents-editor-actions-left">
            <button class="btn btn-primary" id="agents-btn-save">Zapisz</button>
          </div>
          <div class="agents-editor-actions-right">
            <button class="btn btn-ghost" id="agents-btn-cancel-new">Anuluj</button>
          </div>
        </div>
      </div>
    `;

    document.getElementById('agents-btn-save')?.addEventListener('click', () => this._handleCreate());
    document.getElementById('agents-btn-cancel-new')?.addEventListener('click', () => {
      this.isDirty = false;
      this.isNewMode = false;
      this.selectedId = this.activeId || (this.prompts[0]?.id ?? null);
      this._renderList();
      const prompt = this.prompts.find((p) => p.id === this.selectedId);
      if (prompt) this._renderEditor(prompt);
      else this._renderEmptyEditor();
    });
    this._bindDirtyTracking();

    document.getElementById('agents-input-name')?.focus();
  }

  /** Oznacza edytor jako "brudny" (niezapisane zmiany) przy pierwszym wpisie w dowolne pole. */
  _bindDirtyTracking() {
    ['agents-input-name', 'agents-input-desc', 'agents-input-content'].forEach((id) => {
      document.getElementById(id)?.addEventListener('input', (e) => {
        this.isDirty = true;
        e.target.classList.remove('is-invalid');
      });
    });
  }

  // --------------------------------------------------------------------------
  // Akcje
  // --------------------------------------------------------------------------

  _readForm() {
    const name = document.getElementById('agents-input-name')?.value.trim() || '';
    const description = document.getElementById('agents-input-desc')?.value.trim() || '';
    const content = document.getElementById('agents-input-content')?.value.trim() || '';
    return { name, description, content };
  }

  /** Oznacza puste wymagane pola na czerwono i przenosi focus na pierwsze z nich. Zwraca true jeśli formularz jest poprawny. */
  _validateForm(name, content) {
    const nameEl = document.getElementById('agents-input-name');
    const contentEl = document.getElementById('agents-input-content');
    nameEl?.classList.toggle('is-invalid', !name);
    contentEl?.classList.toggle('is-invalid', !content);
    if (!name) {
      nameEl?.focus();
      return false;
    }
    if (!content) {
      contentEl?.focus();
      return false;
    }
    return true;
  }

  async _handleSave(promptId) {
    const { name, description, content } = this._readForm();
    if (!this._validateForm(name, content)) {
      this._showToast('Nazwa i treść promptu są wymagane.', 'error');
      return;
    }
    try {
      await this.apiClient.updatePrompt(promptId, { name, description: description || null, content });
      this._showToast('Zapisano zmiany w promptcie.', 'success');
      await this._loadAndRender(promptId);
    } catch (error) {
      this._showToast(error.message || 'Błąd zapisu promptu.', 'error');
    }
  }

  async _handleCreate() {
    const { name, description, content } = this._readForm();
    if (!this._validateForm(name, content)) {
      this._showToast('Nazwa i treść promptu są wymagane.', 'error');
      return;
    }
    try {
      const created = await this.apiClient.createPrompt({ name, description: description || null, content });
      this._showToast('Utworzono nowy prompt.', 'success');
      await this._loadAndRender(created.id);
    } catch (error) {
      this._showToast(error.message || 'Błąd tworzenia promptu.', 'error');
    }
  }

  async _handleActivate(promptId) {
    if (!this._confirmDiscard()) return;
    try {
      await this.apiClient.activatePrompt(promptId);
      this._showToast('Aktywowano prompt systemowy.', 'success');
      await this._loadAndRender(promptId);
    } catch (error) {
      this._showToast(error.message || 'Błąd aktywacji promptu.', 'error');
    }
  }

  _handleDeleteClick(promptId) {
    const zone = document.getElementById('agents-delete-zone');
    if (!zone) return;
    zone.innerHTML = `
      <div class="delete-confirm-inline">
        <span class="delete-confirm-text">Usunąć prompt?</span>
        <button class="btn-confirm-yes" id="agents-btn-delete-yes">Tak</button>
        <button class="btn-confirm-no" id="agents-btn-delete-no">Anuluj</button>
      </div>
    `;
    document.getElementById('agents-btn-delete-yes')?.addEventListener('click', () => this._handleDeleteConfirm(promptId));
    document.getElementById('agents-btn-delete-no')?.addEventListener('click', () => {
      // Przywraca tylko strefę przycisku Usuń — pełny re-render edytora
      // wyzerowałby niezapisane zmiany w Nazwie/Opisie/Treści.
      zone.innerHTML = `<button class="btn agents-btn-delete" id="agents-btn-delete">Usuń</button>`;
      document.getElementById('agents-btn-delete')?.addEventListener('click', () => this._handleDeleteClick(promptId));
    });
  }

  async _handleDeleteConfirm(promptId) {
    try {
      await this.apiClient.deletePrompt(promptId);
      this._showToast('Usunięto prompt.', 'success');
      this.selectedId = null;
      await this._loadAndRender();
    } catch (error) {
      this._showToast(error.message || 'Błąd usuwania promptu.', 'error');
    }
  }

  // --------------------------------------------------------------------------
  // Toast
  // --------------------------------------------------------------------------

  _showToast(message, type = 'success') {
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
    }, 3000);
  }
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str ?? '';
  return div.innerHTML;
}

function escapeAttr(str) {
  return escapeHtml(str).replace(/"/g, '&quot;');
}
