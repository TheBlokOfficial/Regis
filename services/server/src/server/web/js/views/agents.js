/**
 * Widok zarządzania promptami systemowymi Agenta — split layout (lista + edytor inline).
 */
export class AgentsView {
  constructor() {
    /** @type {import('../network/api_client.js').ApiClient|null} */
    this.apiClient = null;
    /** @type {Array<{id:string, name:string, description:string|null, content:string, is_active:boolean}>} */
    this.prompts = [];
    this.activeId = null;
    this.selectedId = null;
    this._isNewMode = false;
  }

  render() {
    return `
      <div class="agents-layout" id="agents-layout">
        <!-- Panel lewy: lista promptów -->
        <div class="agents-panel-list">
          <div class="agents-panel-header">
            <span class="agents-panel-title">Prompty</span>
            <button class="btn btn-sm btn-subtle" id="agents-btn-new">+ Nowy</button>
          </div>
          <div class="agents-list" id="agents-list">
            <div class="agents-list-loading">Ładowanie...</div>
          </div>
        </div>

        <!-- Panel prawy: edytor -->
        <div class="agents-panel-editor" id="agents-panel-editor">
          <div class="agents-editor-empty">
            <div class="agents-editor-empty-icon">◈</div>
            <p>Wybierz prompt z listy lub utwórz nowy.</p>
          </div>
        </div>
      </div>
    `;
  }

  async init(apiClient) {
    this.apiClient = apiClient;
    await this._loadAndRender();
    this._bindPanelEvents();
  }

  // ---------------------------------------------------------------------------
  // Ładowanie danych
  // ---------------------------------------------------------------------------

  async _loadAndRender(selectId = null) {
    const data = await this.apiClient.getPrompts();
    if (!data) {
      this._renderListError();
      return;
    }
    this.prompts = data.prompts || [];
    this.activeId = data.active_id;

    // Ustal ID do zaznaczenia
    if (selectId && this.prompts.find((p) => p.id === selectId)) {
      this.selectedId = selectId;
    } else if (!this.selectedId || !this.prompts.find((p) => p.id === this.selectedId)) {
      this.selectedId = this.activeId || (this.prompts[0]?.id ?? null);
    }

    this._isNewMode = false;
    this._renderList();

    if (this.selectedId) {
      const prompt = this.prompts.find((p) => p.id === this.selectedId);
      if (prompt) this._renderEditor(prompt);
    }
  }

  // ---------------------------------------------------------------------------
  // Renderowanie listy
  // ---------------------------------------------------------------------------

  _renderList() {
    const list = document.getElementById('agents-list');
    if (!list) return;

    if (this.prompts.length === 0) {
      list.innerHTML = `<div class="agents-list-loading">Brak promptów. Utwórz pierwszy.</div>`;
      return;
    }

    list.innerHTML = this.prompts
      .map(
        (p) => `
        <div
          class="agents-list-item${p.id === this.selectedId ? ' selected' : ''}"
          data-id="${escHtml(p.id)}"
        >
          <div class="agents-item-name">
            ${p.is_active ? '<span class="agents-active-dot" title="Aktywny"></span>' : '<span style="width:7px;min-width:7px"></span>'}
            <span class="agents-item-name-text">${escHtml(p.name)}</span>
          </div>
          ${p.description ? `<div class="agents-item-desc">${escHtml(p.description)}</div>` : ''}
        </div>
      `
      )
      .join('');

    list.querySelectorAll('.agents-list-item').forEach((item) => {
      item.addEventListener('click', () => {
        if (this._isNewMode) {
          // Wyjście z trybu nowego bez zapisywania
          this._isNewMode = false;
        }
        this.selectedId = item.getAttribute('data-id');
        this._renderList();
        const prompt = this.prompts.find((p) => p.id === this.selectedId);
        if (prompt) this._renderEditor(prompt);
      });
    });
  }

  _renderListError() {
    const list = document.getElementById('agents-list');
    if (list) {
      list.innerHTML = `<div class="agents-list-loading" style="color:var(--accent-danger)">Błąd ładowania.</div>`;
    }
  }

  // ---------------------------------------------------------------------------
  // Renderowanie edytora (istniejący prompt)
  // ---------------------------------------------------------------------------

  _renderEditor(prompt) {
    const panel = document.getElementById('agents-panel-editor');
    if (!panel) return;

    const isActive = prompt.id === this.activeId;

    panel.innerHTML = `
      <div class="agents-editor-header">
        <div class="agents-editor-title-group">
          <span class="agents-editor-prompt-name">${escHtml(prompt.name)}</span>
          ${
            isActive
              ? `<span class="badge-active"><span class="badge-active-dot"></span>Aktywny</span>`
              : `<span class="badge-inactive">Nieaktywny</span>`
          }
        </div>
        <span class="agents-dirty-indicator hidden" id="agents-dirty-label">● niezapisane zmiany</span>
      </div>

      <div class="agents-editor-body">
        <div class="agents-editor-row">
          <div class="agents-editor-field">
            <label for="agents-input-name">Nazwa</label>
            <input
              type="text"
              id="agents-input-name"
              class="form-control"
              value="${escHtml(prompt.name)}"
              placeholder="Nazwa promptu"
            />
          </div>
          <div class="agents-editor-field">
            <label for="agents-input-desc">
              Opis <span style="opacity:.45;font-weight:400;text-transform:none">(opcjonalny)</span>
            </label>
            <input
              type="text"
              id="agents-input-desc"
              class="form-control"
              value="${escHtml(prompt.description || '')}"
              placeholder="Krótki opis przeznaczenia"
            />
          </div>
        </div>

        <div class="agents-editor-field">
          <label for="agents-input-content">Treść instrukcji systemowej</label>
          <textarea
            id="agents-input-content"
            class="agents-content-textarea"
            placeholder="Wpisz lub wklej treść instrukcji systemowej..."
            spellcheck="false"
          >${escHtml(prompt.content)}</textarea>
        </div>
      </div>

      <div class="agents-editor-footer">
        <button
          class="btn btn-subtle btn-sm"
          id="agents-btn-activate"
          ${isActive ? 'disabled' : ''}
          title="${isActive ? 'Ten prompt jest już aktywny' : 'Ustaw jako aktywny prompt systemowy Agenta'}"
        >
          ${isActive ? '✓ Aktywny' : 'Aktywuj'}
        </button>

        <div class="agents-editor-footer-spacer"></div>

        <button
          class="btn btn-ghost-danger btn-sm"
          id="agents-btn-delete"
          ${isActive ? 'disabled' : ''}
          title="${isActive ? 'Nie można usunąć aktywnego promptu' : 'Usuń prompt'}"
        >
          Usuń
        </button>

        <button class="btn btn-primary btn-sm" id="agents-btn-save">
          Zapisz zmiany
        </button>
      </div>
    `;

    this._bindEditorEvents(prompt);
  }

  // ---------------------------------------------------------------------------
  // Renderowanie edytora (nowy prompt)
  // ---------------------------------------------------------------------------

  _renderNewEditor() {
    const panel = document.getElementById('agents-panel-editor');
    if (!panel) return;

    panel.innerHTML = `
      <div class="agents-editor-header">
        <div class="agents-editor-title-group">
          <span class="agents-editor-prompt-name">Nowy Prompt</span>
          <span class="badge-draft">Roboczy</span>
        </div>
      </div>

      <div class="agents-editor-body">
        <div class="agents-editor-row">
          <div class="agents-editor-field">
            <label for="agents-input-name">Nazwa</label>
            <input
              type="text"
              id="agents-input-name"
              class="form-control"
              value=""
              placeholder="Nazwa promptu"
              autofocus
            />
          </div>
          <div class="agents-editor-field">
            <label for="agents-input-desc">
              Opis <span style="opacity:.45;font-weight:400;text-transform:none">(opcjonalny)</span>
            </label>
            <input
              type="text"
              id="agents-input-desc"
              class="form-control"
              value=""
              placeholder="Krótki opis przeznaczenia"
            />
          </div>
        </div>

        <div class="agents-editor-field">
          <label for="agents-input-content">Treść instrukcji systemowej</label>
          <textarea
            id="agents-input-content"
            class="agents-content-textarea"
            placeholder="Wpisz lub wklej treść instrukcji systemowej..."
            spellcheck="false"
          ></textarea>
        </div>
      </div>

      <div class="agents-editor-footer">
        <button class="btn btn-subtle btn-sm" id="agents-btn-discard">
          Odrzuć
        </button>
        <div class="agents-editor-footer-spacer"></div>
        <button class="btn btn-primary btn-sm" id="agents-btn-create">
          Utwórz Prompt
        </button>
      </div>
    `;

    this._bindNewEditorEvents();
  }

  // ---------------------------------------------------------------------------
  // Powiązanie eventów — panel statyczny
  // ---------------------------------------------------------------------------

  _bindPanelEvents() {
    const btnNew = document.getElementById('agents-btn-new');
    if (btnNew) {
      btnNew.addEventListener('click', () => {
        this._isNewMode = true;
        this.selectedId = null;
        this._renderList();
        this._renderNewEditor();
      });
    }
  }

  // ---------------------------------------------------------------------------
  // Powiązanie eventów — edytor istniejącego promptu
  // ---------------------------------------------------------------------------

  _bindEditorEvents(prompt) {
    const inputName    = document.getElementById('agents-input-name');
    const inputDesc    = document.getElementById('agents-input-desc');
    const inputContent = document.getElementById('agents-input-content');
    const dirtyLabel   = document.getElementById('agents-dirty-label');
    const btnSave      = document.getElementById('agents-btn-save');
    const btnActivate  = document.getElementById('agents-btn-activate');
    const btnDelete    = document.getElementById('agents-btn-delete');

    // Śledzenie niezapisanych zmian
    const markDirty = () => {
      if (dirtyLabel) dirtyLabel.classList.remove('hidden');
    };
    [inputName, inputDesc, inputContent].forEach((el) => {
      if (el) el.addEventListener('input', markDirty);
    });

    // Aktualizacja nazwy w nagłówku edytora i liście przy wpisywaniu
    if (inputName) {
      inputName.addEventListener('input', () => {
        const nameDisplay = document.querySelector('.agents-editor-prompt-name');
        if (nameDisplay) nameDisplay.textContent = inputName.value || 'Nowy Prompt';
      });
    }

    // Zapisz
    if (btnSave) {
      btnSave.addEventListener('click', async () => {
        const name = inputName?.value?.trim();
        if (!name) { this._toast('Nazwa promptu nie może być pusta.', 'error'); return; }

        btnSave.disabled = true;
        btnSave.textContent = 'Zapisywanie...';
        try {
          await this.apiClient.updatePrompt(prompt.id, {
            name: inputName.value.trim(),
            description: inputDesc?.value?.trim() || null,
            content: inputContent?.value ?? '',
          });
          this._toast('Prompt zapisany.', 'success');
          await this._loadAndRender(prompt.id);
        } catch (err) {
          this._toast(`Błąd zapisu: ${err.message}`, 'error');
          btnSave.disabled = false;
          btnSave.textContent = 'Zapisz zmiany';
        }
      });
    }

    // Aktywuj
    if (btnActivate && !btnActivate.disabled) {
      btnActivate.addEventListener('click', async () => {
        btnActivate.disabled = true;
        btnActivate.textContent = '...';
        try {
          await this.apiClient.activatePrompt(prompt.id);
          this._toast(`Prompt „${prompt.name}" jest teraz aktywny.`, 'success');
          await this._loadAndRender(prompt.id);
        } catch (err) {
          this._toast(`Błąd aktywacji: ${err.message}`, 'error');
          await this._loadAndRender(prompt.id);
        }
      });
    }

    // Usuń — dwukliknięcie z potwierdzeniem inline
    if (btnDelete && !btnDelete.disabled) {
      let confirmPending = false;
      let confirmTimer = null;

      btnDelete.addEventListener('click', () => {
        if (!confirmPending) {
          confirmPending = true;
          btnDelete.textContent = 'Potwierdź usunięcie';
          btnDelete.style.color = 'var(--accent-danger)';
          btnDelete.style.borderColor = 'rgba(239,68,68,0.4)';
          confirmTimer = setTimeout(() => {
            confirmPending = false;
            btnDelete.textContent = 'Usuń';
            btnDelete.style.color = '';
            btnDelete.style.borderColor = '';
          }, 3000);
        } else {
          clearTimeout(confirmTimer);
          this._doDelete(prompt.id);
        }
      });
    }
  }

  // ---------------------------------------------------------------------------
  // Powiązanie eventów — edytor nowego promptu
  // ---------------------------------------------------------------------------

  _bindNewEditorEvents() {
    const btnCreate  = document.getElementById('agents-btn-create');
    const btnDiscard = document.getElementById('agents-btn-discard');

    if (btnDiscard) {
      btnDiscard.addEventListener('click', () => {
        this._isNewMode = false;
        if (this.prompts.length > 0) {
          this.selectedId = this.activeId || this.prompts[0].id;
          this._renderList();
          const prompt = this.prompts.find((p) => p.id === this.selectedId);
          if (prompt) this._renderEditor(prompt);
        } else {
          const panel = document.getElementById('agents-panel-editor');
          if (panel) {
            panel.innerHTML = `
              <div class="agents-editor-empty">
                <div class="agents-editor-empty-icon">◈</div>
                <p>Wybierz prompt z listy lub utwórz nowy.</p>
              </div>
            `;
          }
        }
      });
    }

    if (btnCreate) {
      btnCreate.addEventListener('click', async () => {
        const name    = document.getElementById('agents-input-name')?.value?.trim();
        const desc    = document.getElementById('agents-input-desc')?.value?.trim();
        const content = document.getElementById('agents-input-content')?.value ?? '';

        if (!name)          { this._toast('Nazwa promptu nie może być pusta.', 'error'); return; }
        if (!content.trim()) { this._toast('Treść promptu nie może być pusta.', 'error'); return; }

        btnCreate.disabled = true;
        btnCreate.textContent = 'Tworzenie...';
        try {
          const created = await this.apiClient.createPrompt({
            name,
            description: desc || null,
            content,
          });
          this._toast(`Prompt „${name}" utworzony.`, 'success');
          this._isNewMode = false;
          await this._loadAndRender(created.id);
        } catch (err) {
          this._toast(`Błąd tworzenia: ${err.message}`, 'error');
          btnCreate.disabled = false;
          btnCreate.textContent = 'Utwórz Prompt';
        }
      });
    }
  }

  // ---------------------------------------------------------------------------
  // Akcja usuwania
  // ---------------------------------------------------------------------------

  async _doDelete(promptId) {
    try {
      await this.apiClient.deletePrompt(promptId);
      this._toast('Prompt usunięty.', 'success');
      this.selectedId = null;
      await this._loadAndRender();
    } catch (err) {
      this._toast(`Błąd usuwania: ${err.message}`, 'error');
    }
  }

  // ---------------------------------------------------------------------------
  // Powiadomienia Toast (DRY — ten sam wzorzec co DashboardView)
  // ---------------------------------------------------------------------------

  _toast(message, type = 'info') {
    let container = document.getElementById('toast-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'toast-container';
      container.className = 'toast-container';
      document.body.appendChild(container);
    }
    const toast = document.createElement('div');
    toast.className = `toast-notification toast-${type}`;
    toast.innerHTML = `<span>${escHtml(message)}</span>`;
    container.appendChild(toast);
    setTimeout(() => {
      toast.classList.add('toast-leaving');
      setTimeout(() => toast.remove(), 200);
    }, 3200);
  }
}

// ---------------------------------------------------------------------------
// Helper
// ---------------------------------------------------------------------------

function escHtml(str) {
  if (str == null) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
