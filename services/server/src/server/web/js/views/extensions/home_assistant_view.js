/**
 * Widok szczegółowy rozszerzenia Home Assistant — w pełni domenowy (nie
 * generyczny/schema-driven, w przeciwieństwie do formularzy dostawców LLM).
 * Trzy sekcje: Połączenia (CRUD, `base_url`/`access_token` hardcoded),
 * Katalog urządzeń per połączenie (deklaracja widoczności/nazwy), Grupy
 * (multi-select nad sumą włączonych wpisów katalogu wszystkich włączonych
 * połączeń).
 */
export class HomeAssistantExtensionView {
  constructor() {
    this.container = null;
    this.apiClient = null;
    this.showToast = null;

    this.connections = [];
    this.groups = [];
    this.selectedConnectionId = null;
    this.catalog = [];

    this.isEditingConnection = null; // id połączenia w edycji, lub 'new', lub null
    this.isCreatingGroup = false;
  }

  async mount(container, apiClient, showToast) {
    this.container = container;
    this.apiClient = apiClient;
    this.showToast = showToast;
    await this._loadAndRender();
  }

  async _loadAndRender() {
    const [connections, groups] = await Promise.all([this.apiClient.getHAConnections(), this.apiClient.getHAGroups()]);
    this.connections = connections || [];
    this.groups = groups || [];

    if (!this.selectedConnectionId || !this.connections.some((c) => c.id === this.selectedConnectionId)) {
      this.selectedConnectionId = this.connections[0]?.id ?? null;
    }
    await this._loadCatalog();
    this._render();
  }

  async _loadCatalog() {
    if (!this.selectedConnectionId) {
      this.catalog = [];
      return;
    }
    this.catalog = (await this.apiClient.getHACatalog(this.selectedConnectionId)) || [];
  }

  _render() {
    this.container.innerHTML = `
      <div class="ha-view">
        <section class="ha-section">
          <div class="ha-section-header">
            <span class="ha-section-title">Połączenia</span>
            <button class="btn btn-sm btn-primary" id="ha-btn-new-connection">+ Nowe połączenie</button>
          </div>
          <div class="ha-connections-list">${this._renderConnectionsList()}</div>
          <div id="ha-connection-form">${this.isEditingConnection ? this._renderConnectionForm() : ''}</div>
        </section>

        <section class="ha-section">
          <div class="ha-section-header">
            <span class="ha-section-title">Katalog urządzeń</span>
            ${this.connections.length > 0 ? this._renderConnectionSelect() : ''}
          </div>
          ${this._renderCatalog()}
        </section>

        <section class="ha-section">
          <div class="ha-section-header">
            <span class="ha-section-title">Grupy</span>
            <button class="btn btn-sm btn-primary" id="ha-btn-new-group">+ Nowa grupa</button>
          </div>
          <div class="ha-groups-list">${this._renderGroupsList()}</div>
          <div id="ha-group-form"></div>
        </section>
      </div>
    `;
    this._bindEvents();
    if (this.isCreatingGroup) this._renderGroupForm();
  }

  // --------------------------------------------------------------------------
  // Połączenia
  // --------------------------------------------------------------------------

  _renderConnectionsList() {
    if (this.connections.length === 0) {
      return `<p class="ha-empty-hint">Brak skonfigurowanych połączeń.</p>`;
    }
    return this.connections
      .map(
        (c) => `
        <div class="ha-connection-row ${c.id === this.selectedConnectionId ? 'selected' : ''}">
          <div class="ha-connection-info">
            <span class="ha-connection-name">${escapeHtml(c.name)}</span>
            <span class="ha-connection-meta">${escapeHtml(c.base_url)} · token ${escapeHtml(c.access_token)}</span>
          </div>
          <div class="ha-connection-actions">
            <span class="badge-status ${c.enabled ? 'ha-badge-on' : 'ha-badge-off'}">${c.enabled ? 'włączone' : 'wyłączone'}</span>
            <button class="btn btn-sm btn-subtle" data-select-connection="${escapeAttr(c.id)}">Katalog</button>
            <button class="btn btn-sm btn-subtle" data-edit-connection="${escapeAttr(c.id)}">Edytuj</button>
            <button class="btn btn-sm btn-ghost-danger" data-delete-connection="${escapeAttr(c.id)}">Usuń</button>
          </div>
        </div>
      `
      )
      .join('');
  }

  _renderConnectionForm() {
    const isNew = this.isEditingConnection === 'new';
    const existing = isNew ? null : this.connections.find((c) => c.id === this.isEditingConnection);
    if (!isNew && !existing) return '';

    return `
      <div class="form-card ha-connection-form-card">
        <div class="form-card-title">${isNew ? 'Nowe połączenie' : `Edycja: ${escapeHtml(existing.name)}`}</div>
        <div class="form-row">
          <div class="form-group">
            <label for="ha-input-name">Nazwa</label>
            <input type="text" id="ha-input-name" class="form-control" value="${isNew ? '' : escapeAttr(existing.name)}" placeholder="np. HA — parter" />
          </div>
          <div class="form-group">
            <label for="ha-input-base-url">Adres serwera</label>
            <input type="text" id="ha-input-base-url" class="form-control" value="${isNew ? '' : escapeAttr(existing.base_url)}" placeholder="http://homeassistant.local:8123" />
          </div>
        </div>
        <div class="form-row">
          <div class="form-group">
            <label for="ha-input-token">Długoterminowy token dostępu</label>
            <input type="password" id="ha-input-token" class="form-control" placeholder="${isNew ? 'eyJhbGciOi...' : 'Zostaw puste, aby zachować obecny'}" />
          </div>
          <div class="form-group">
            <label for="ha-input-enabled">Stan</label>
            <select id="ha-input-enabled" class="form-control">
              <option value="true" ${isNew || existing?.enabled ? 'selected' : ''}>Włączone</option>
              <option value="false" ${!isNew && !existing?.enabled ? 'selected' : ''}>Wyłączone</option>
            </select>
          </div>
        </div>
        <div class="form-actions">
          <button class="btn btn-primary" id="ha-btn-save-connection">Zapisz</button>
          <button class="btn btn-ghost" id="ha-btn-cancel-connection">Anuluj</button>
        </div>
      </div>
    `;
  }

  // --------------------------------------------------------------------------
  // Katalog
  // --------------------------------------------------------------------------

  _renderConnectionSelect() {
    return `
      <select class="form-control ha-connection-select" id="ha-catalog-connection-select">
        ${this.connections.map((c) => `<option value="${escapeAttr(c.id)}" ${c.id === this.selectedConnectionId ? 'selected' : ''}>${escapeHtml(c.name)}</option>`).join('')}
      </select>
    `;
  }

  _renderCatalog() {
    if (!this.selectedConnectionId) {
      return `<p class="ha-empty-hint">Dodaj połączenie, aby zobaczyć katalog urządzeń.</p>`;
    }
    if (this.catalog.length === 0) {
      return `<p class="ha-empty-hint">Brak wykrytych urządzeń dla tego połączenia.</p>`;
    }
    return `
      <table class="ha-catalog-table">
        <thead>
          <tr><th></th><th>Nazwa</th><th>Rodzaj</th><th>Możliwości</th></tr>
        </thead>
        <tbody>
          ${this.catalog
            .map(
              (entry) => `
              <tr data-ref="${escapeAttr(entry.ref)}">
                <td><input type="checkbox" class="ha-catalog-enabled" data-ref="${escapeAttr(entry.ref)}" ${entry.enabled ? 'checked' : ''} /></td>
                <td><input type="text" class="form-control ha-catalog-label" data-ref="${escapeAttr(entry.ref)}" value="${escapeAttr(entry.label)}" /></td>
                <td><span class="badge-chip">${escapeHtml(entry.kind)}</span></td>
                <td>${(entry.capabilities || []).map((cap) => `<span class="badge-chip">${escapeHtml(cap)}</span>`).join(' ')}</td>
              </tr>
            `
            )
            .join('')}
        </tbody>
      </table>
      <div class="form-actions">
        <button class="btn btn-primary btn-sm" id="ha-btn-save-catalog">Zapisz katalog</button>
      </div>
    `;
  }

  // --------------------------------------------------------------------------
  // Grupy
  // --------------------------------------------------------------------------

  _renderGroupsList() {
    if (this.groups.length === 0) {
      return `<p class="ha-empty-hint">Brak skonfigurowanych grup.</p>`;
    }
    return this.groups
      .map(
        (g) => `
        <div class="ha-group-row">
          <div class="ha-group-info">
            <span class="ha-group-name">${escapeHtml(g.name)}</span>
            <span class="ha-group-meta">${g.device_ids.length} urządzeń</span>
          </div>
          <button class="btn btn-sm btn-ghost-danger" data-delete-group="${escapeAttr(g.id)}">Usuń</button>
        </div>
      `
      )
      .join('');
  }

  async _renderGroupForm() {
    const formContainer = document.getElementById('ha-group-form');
    if (!formContainer) return;

    // Suma wpisów enabled=true katalogu wszystkich włączonych połączeń.
    const enabledConnections = this.connections.filter((c) => c.enabled);
    const catalogs = await Promise.all(enabledConnections.map((c) => this.apiClient.getHACatalog(c.id)));
    const options = [];
    catalogs.forEach((catalog, idx) => {
      (catalog || [])
        .filter((entry) => entry.enabled)
        .forEach((entry) => options.push({ ref: entry.ref, label: `${enabledConnections[idx].name} — ${entry.label}` }));
    });

    formContainer.innerHTML = `
      <div class="form-card">
        <div class="form-card-title">Nowa grupa</div>
        <div class="form-group">
          <label for="ha-group-name">Nazwa grupy</label>
          <input type="text" id="ha-group-name" class="form-control" placeholder="np. Łazienka" />
        </div>
        <div class="form-group">
          <label>Urządzenia</label>
          <div class="ha-group-device-options">
            ${
              options.length === 0
                ? '<p class="ha-empty-hint">Brak włączonych urządzeń do wyboru — sprawdź katalogi połączeń.</p>'
                : options
                    .map(
                      (opt) => `
                    <label class="ha-group-device-option">
                      <input type="checkbox" value="${escapeAttr(opt.ref)}" />
                      <span>${escapeHtml(opt.label)}</span>
                    </label>
                  `
                    )
                    .join('')
            }
          </div>
        </div>
        <div class="form-actions">
          <button class="btn btn-primary" id="ha-btn-save-group">Utwórz grupę</button>
          <button class="btn btn-ghost" id="ha-btn-cancel-group">Anuluj</button>
        </div>
      </div>
    `;

    document.getElementById('ha-btn-save-group')?.addEventListener('click', () => this._handleCreateGroup());
    document.getElementById('ha-btn-cancel-group')?.addEventListener('click', () => {
      this.isCreatingGroup = false;
      formContainer.innerHTML = '';
    });
  }

  // --------------------------------------------------------------------------
  // Zdarzenia
  // --------------------------------------------------------------------------

  _bindEvents() {
    document.getElementById('ha-btn-new-connection')?.addEventListener('click', () => {
      this.isEditingConnection = 'new';
      this._render();
    });
    this.container.querySelectorAll('[data-edit-connection]')?.forEach((btn) => {
      btn.addEventListener('click', () => {
        this.isEditingConnection = btn.getAttribute('data-edit-connection');
        this._render();
      });
    });
    document.getElementById('ha-btn-cancel-connection')?.addEventListener('click', () => {
      this.isEditingConnection = null;
      this._render();
    });
    document.getElementById('ha-btn-save-connection')?.addEventListener('click', () => this._handleSaveConnection());
    this.container.querySelectorAll('[data-delete-connection]')?.forEach((btn) => {
      btn.addEventListener('click', () => this._handleDeleteConnection(btn.getAttribute('data-delete-connection')));
    });
    this.container.querySelectorAll('[data-select-connection]')?.forEach((btn) => {
      btn.addEventListener('click', () => this._handleSelectConnection(btn.getAttribute('data-select-connection')));
    });

    document.getElementById('ha-catalog-connection-select')?.addEventListener('change', (e) => this._handleSelectConnection(e.target.value));
    document.getElementById('ha-btn-save-catalog')?.addEventListener('click', () => this._handleSaveCatalog());

    document.getElementById('ha-btn-new-group')?.addEventListener('click', () => {
      this.isCreatingGroup = true;
      this._renderGroupForm();
    });
    this.container.querySelectorAll('[data-delete-group]')?.forEach((btn) => {
      btn.addEventListener('click', () => this._handleDeleteGroup(btn.getAttribute('data-delete-group')));
    });
  }

  async _handleSelectConnection(connectionId) {
    this.selectedConnectionId = connectionId;
    await this._loadCatalog();
    this._render();
  }

  async _handleSaveConnection() {
    const name = document.getElementById('ha-input-name')?.value.trim() || '';
    const baseUrl = document.getElementById('ha-input-base-url')?.value.trim() || '';
    const token = document.getElementById('ha-input-token')?.value || '';
    const enabled = document.getElementById('ha-input-enabled')?.value === 'true';

    if (!name || !baseUrl) {
      this.showToast('Nazwa i adres serwera są wymagane.', 'error');
      return;
    }

    try {
      if (this.isEditingConnection === 'new') {
        if (!token) {
          this.showToast('Token dostępu jest wymagany dla nowego połączenia.', 'error');
          return;
        }
        const created = await this.apiClient.createHAConnection({ name, base_url: baseUrl, access_token: token, enabled });
        this.showToast('Utworzono połączenie.', 'success');
        this.selectedConnectionId = created.id;
      } else {
        const payload = { name, base_url: baseUrl, enabled };
        if (token) payload.access_token = token;
        await this.apiClient.updateHAConnection(this.isEditingConnection, payload);
        this.showToast('Zaktualizowano połączenie.', 'success');
      }
      this.isEditingConnection = null;
      await this._loadAndRender();
    } catch (error) {
      this.showToast(error.message || 'Błąd zapisu połączenia.', 'error');
    }
  }

  async _handleDeleteConnection(connectionId) {
    try {
      await this.apiClient.deleteHAConnection(connectionId);
      this.showToast('Usunięto połączenie.', 'success');
      if (this.selectedConnectionId === connectionId) this.selectedConnectionId = null;
      await this._loadAndRender();
    } catch (error) {
      this.showToast(error.message || 'Błąd usuwania połączenia.', 'error');
    }
  }

  async _handleSaveCatalog() {
    const rows = this.container.querySelectorAll('.ha-catalog-table tbody tr');
    const entries = Array.from(rows).map((row) => {
      const ref = row.getAttribute('data-ref');
      const enabled = row.querySelector('.ha-catalog-enabled')?.checked ?? true;
      const displayName = row.querySelector('.ha-catalog-label')?.value.trim() || null;
      return { ref, enabled, display_name: displayName };
    });

    try {
      await this.apiClient.updateHACatalog(this.selectedConnectionId, entries);
      this.showToast('Zapisano katalog urządzeń.', 'success');
      await this._loadCatalog();
      this._render();
    } catch (error) {
      this.showToast(error.message || 'Błąd zapisu katalogu.', 'error');
    }
  }

  async _handleCreateGroup() {
    const name = document.getElementById('ha-group-name')?.value.trim() || '';
    const deviceIds = Array.from(this.container.querySelectorAll('.ha-group-device-option input:checked')).map((el) => el.value);

    if (!name) {
      this.showToast('Nazwa grupy jest wymagana.', 'error');
      return;
    }

    try {
      await this.apiClient.createHAGroup({ name, device_ids: deviceIds });
      this.showToast('Utworzono grupę.', 'success');
      this.isCreatingGroup = false;
      await this._loadAndRender();
    } catch (error) {
      this.showToast(error.message || 'Błąd tworzenia grupy.', 'error');
    }
  }

  async _handleDeleteGroup(groupId) {
    try {
      await this.apiClient.deleteHAGroup(groupId);
      this.showToast('Usunięto grupę.', 'success');
      await this._loadAndRender();
    } catch (error) {
      this.showToast(error.message || 'Błąd usuwania grupy.', 'error');
    }
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
