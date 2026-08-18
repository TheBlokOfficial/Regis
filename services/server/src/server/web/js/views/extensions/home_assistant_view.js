import { getSenderId } from '../../sender_id.js';

/**
 * Widok konfiguracji silnika świata (WorldEngine) — w pełni domenowy (nie
 * generyczny/schema-driven, w przeciwieństwie do formularzy dostawców LLM).
 * Cztery sekcje: Konfiguracja (singleton Home Assistant — jeden
 * `base_url`/`access_token`), Urządzenia (wyszukiwarka nad surowym katalogiem
 * HA + opt-in zadeklarowana lista, jedyne źródło prawdy o tym, co widzi
 * agent), Grupy (multi-select nad zadeklarowaną listą), Satelity (rejestr
 * `sender_id -> pokój/kanał komunikacji` — to konsola Web UI jest pierwszym,
 * zawsze dostępnym "satelitą", więc sekcja od razu proponuje jej własny,
 * trwały `sender_id` do rejestracji).
 */
export class HomeAssistantExtensionView {
  constructor() {
    this.container = null;
    this.apiClient = null;
    this.showToast = null;

    this.config = { base_url: '', access_token: '' };
    this.declaredDevices = [];
    this.groups = [];
    this.catalog = [];
    this.searchQuery = '';
    this.satellites = [];
    this.areas = [];

    this.isCreatingGroup = false;
    this.isRegisteringSatellite = false;
  }

  async mount(container, apiClient, showToast) {
    this.container = container;
    this.apiClient = apiClient;
    this.showToast = showToast;
    await this._loadAndRender();
  }

  async _loadAndRender() {
    const [config, declared, groups, catalog, satellites, areas] = await Promise.all([
      this.apiClient.getHAConfig(),
      this.apiClient.getHADeclaredDevices(),
      this.apiClient.getHAGroups(),
      this.apiClient.getHACatalog(),
      this.apiClient.getSatellites(),
      this.apiClient.getWorldAreas(),
    ]);
    this.config = config || { base_url: '', access_token: '' };
    this.declaredDevices = declared || [];
    this.groups = groups || [];
    this.catalog = catalog || [];
    this.satellites = satellites || [];
    this.areas = areas || [];
    this._render();
  }

  _render() {
    this.container.innerHTML = `
      <div class="ha-view">
        <section class="ha-section">
          <div class="ha-section-header">
            <span class="ha-section-title">Konfiguracja</span>
          </div>
          ${this._renderConfigForm()}
        </section>

        <section class="ha-section">
          <div class="ha-section-header">
            <span class="ha-section-title">Urządzenia</span>
          </div>
          ${this._renderDeviceSearch()}
          <div id="ha-search-results"></div>
          ${this._renderDeclaredList()}
        </section>

        <section class="ha-section">
          <div class="ha-section-header">
            <span class="ha-section-title">Grupy</span>
            <button class="btn btn-sm btn-primary" id="ha-btn-new-group">+ Nowa grupa</button>
          </div>
          <div class="ha-groups-list">${this._renderGroupsList()}</div>
          <div id="ha-group-form"></div>
        </section>

        <section class="ha-section">
          <div class="ha-section-header">
            <span class="ha-section-title">Satelity</span>
            <button class="btn btn-sm btn-primary" id="ha-btn-new-satellite">+ Nowa rejestracja</button>
          </div>
          ${this._renderThisBrowserHint()}
          <div class="ha-satellites-list">${this._renderSatellitesList()}</div>
          <div id="ha-satellite-form"></div>
        </section>
      </div>
    `;
    this._bindEvents();
    this._renderSearchResults();
    if (this.isCreatingGroup) this._renderGroupForm();
    if (this.isRegisteringSatellite) this._renderSatelliteForm();
  }

  // --------------------------------------------------------------------------
  // Konfiguracja
  // --------------------------------------------------------------------------

  _renderConfigForm() {
    const isConfigured = Boolean(this.config.base_url && this.config.access_token);
    return `
      <div class="form-card ha-config-form-card">
        <div class="form-row">
          <div class="form-group">
            <label for="ha-input-base-url">Adres serwera</label>
            <input type="text" id="ha-input-base-url" class="form-control" value="${escapeAttr(this.config.base_url)}" placeholder="http://homeassistant.local:8123" />
          </div>
          <div class="form-group">
            <label for="ha-input-token">Długoterminowy token dostępu</label>
            <input type="password" id="ha-input-token" class="form-control" placeholder="${isConfigured ? 'Zostaw puste, aby zachować obecny' : 'eyJhbGciOi...'}" />
          </div>
        </div>
        ${isConfigured ? `<p class="ha-empty-hint">Obecny token: ${escapeHtml(truncateMaskedToken(this.config.access_token))}</p>` : ''}
        <div class="form-actions">
          <button class="btn btn-primary" id="ha-btn-save-config">Zapisz</button>
        </div>
      </div>
    `;
  }

  // --------------------------------------------------------------------------
  // Wyszukiwarka i zadeklarowana lista urządzeń (opt-in)
  // --------------------------------------------------------------------------

  _renderDeviceSearch() {
    return `
      <div class="form-group ha-device-search">
        <label for="ha-search-input">Dodaj urządzenie</label>
        <input type="text" id="ha-search-input" class="form-control" placeholder="Szukaj po nazwie lub entity_id..." value="${escapeAttr(this.searchQuery)}" />
      </div>
    `;
  }

  _renderSearchResults() {
    const resultsContainer = document.getElementById('ha-search-results');
    if (!resultsContainer) return;

    const declaredIds = new Set(this.declaredDevices.map((d) => d.entity_id));
    const query = this.searchQuery.trim().toLowerCase();
    const matches = (this.catalog || [])
      .filter((entry) => !declaredIds.has(entry.entity_id))
      .filter((entry) => !query || entry.friendly_name.toLowerCase().includes(query) || entry.entity_id.toLowerCase().includes(query));

    if (matches.length === 0) {
      resultsContainer.innerHTML = `<p class="ha-empty-hint">${this.catalog.length === 0 ? 'Skonfiguruj serwer, aby zobaczyć dostępne encje.' : 'Brak pasujących encji.'}</p>`;
      return;
    }
    resultsContainer.innerHTML = `
      <div class="ha-search-dropdown-wrap">
        <div class="ha-search-dropdown">
          ${matches
            .map(
              (entry) => `
            <button type="button" class="ha-search-result" data-add-entity="${escapeAttr(entry.entity_id)}">
              <span class="ha-search-result-name">${escapeHtml(entry.friendly_name)}</span>
              <span class="ha-search-result-meta">${escapeHtml(entry.entity_id)} · <span class="badge-chip">${escapeHtml(entry.kind)}</span></span>
            </button>
          `
            )
            .join('')}
        </div>
      </div>
    `;
    resultsContainer.querySelectorAll('[data-add-entity]').forEach((btn) => {
      btn.addEventListener('click', () => this._handleAddDeclaredDevice(btn.getAttribute('data-add-entity')));
    });
  }

  _renderDeclaredList() {
    const count = this.declaredDevices.length;
    const header = `<div class="ha-subsection-title">Zadeklarowane urządzenia${count ? ` (${count})` : ''}</div>`;

    if (count === 0) {
      return `${header}<p class="ha-empty-hint">Brak zadeklarowanych urządzeń — dodaj przez wyszukiwarkę powyżej.</p>`;
    }
    return `
      ${header}
      <div class="ha-declared-list">
        ${this.declaredDevices
          .map(
            (entry) => `
            <div class="ha-declared-card" data-entity-id="${escapeAttr(entry.entity_id)}">
              <span class="ha-declared-entity-id" title="${escapeAttr(entry.entity_id)}">${escapeHtml(entry.entity_id)}</span>
              <input type="text" class="form-control ha-declared-label" data-entity-id="${escapeAttr(entry.entity_id)}" value="${escapeAttr(entry.effective_name)}" />
              ${!entry.display_name ? '<span class="ha-declared-default-hint" title="Domyślna nazwa z Home Assistant — warto nadać własną.">●</span>' : ''}
              <span class="ha-declared-kind">${escapeHtml(entry.kind || '?')}</span>
              <span class="ha-declared-caps-text">${(entry.capabilities || []).map((cap) => escapeHtml(cap)).join(' · ')}</span>
              <button class="btn btn-sm btn-ghost-danger ha-declared-remove" data-remove-entity="${escapeAttr(entry.entity_id)}" title="Usuń">✕</button>
            </div>
          `
          )
          .join('')}
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

  _renderGroupForm() {
    const formContainer = document.getElementById('ha-group-form');
    if (!formContainer) return;

    const options = this.declaredDevices.map((entry) => ({ ref: entry.entity_id, label: entry.effective_name }));

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
                ? '<p class="ha-empty-hint">Brak zadeklarowanych urządzeń do wyboru.</p>'
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
  // Satelity — sender_id -> pokój/kanał komunikacji
  // --------------------------------------------------------------------------

  _renderThisBrowserHint() {
    const thisId = getSenderId();
    const alreadyRegistered = this.satellites.some((s) => s.sender_id === thisId);
    return `
      <p class="ha-empty-hint ha-satellite-self-hint">
        ID tej przeglądarki: <span class="ha-satellite-id">${escapeHtml(thisId)}</span>
        ${alreadyRegistered ? '<span class="badge-chip">zarejestrowana</span>' : '<button type="button" class="btn btn-sm btn-ghost" id="ha-btn-use-this-browser">Zarejestruj tę przeglądarkę</button>'}
      </p>
    `;
  }

  _renderSatellitesList() {
    if (this.satellites.length === 0) {
      return `<p class="ha-empty-hint">Brak zarejestrowanych satelit.</p>`;
    }
    return this.satellites
      .map(
        (s) => `
        <div class="ha-satellite-row">
          <div class="ha-satellite-info">
            <span class="ha-satellite-name">${escapeHtml(s.display_name || s.sender_id)}</span>
            <span class="ha-satellite-meta">
              <span class="ha-satellite-id">${escapeHtml(s.sender_id)}</span>
              ${s.room_label ? ` · ${escapeHtml(s.room_label)}` : ''}
              · <span class="badge-chip">${s.channel === 'voice' ? 'głos' : 'tekst'}</span>
            </span>
          </div>
          <button class="btn btn-sm btn-ghost-danger" data-delete-satellite="${escapeAttr(s.sender_id)}">Usuń</button>
        </div>
      `
      )
      .join('');
  }

  _renderSatelliteForm(prefillSenderId = '') {
    const formContainer = document.getElementById('ha-satellite-form');
    if (!formContainer) return;

    const areaOptions = this.areas.map((area) => `<option value="${escapeAttr(area)}">${escapeHtml(area)}</option>`).join('');

    formContainer.innerHTML = `
      <div class="form-card">
        <div class="form-card-title">Nowa rejestracja satelity</div>
        <div class="form-row">
          <div class="form-group">
            <label for="ha-sat-sender-id">sender_id</label>
            <input type="text" id="ha-sat-sender-id" class="form-control" placeholder="opaque identyfikator nadawcy" value="${escapeAttr(prefillSenderId)}" />
          </div>
          <div class="form-group">
            <label for="ha-sat-display-name">Nazwa (opcjonalnie)</label>
            <input type="text" id="ha-sat-display-name" class="form-control" placeholder="np. Kuchenny ekran" />
          </div>
        </div>
        <div class="form-row">
          <div class="form-group">
            <label for="ha-sat-room">Pokój (opcjonalnie)</label>
            <select id="ha-sat-room" class="form-control">
              <option value="">— brak —</option>
              ${areaOptions}
            </select>
          </div>
          <div class="form-group">
            <label for="ha-sat-channel">Kanał komunikacji</label>
            <select id="ha-sat-channel" class="form-control">
              <option value="text">Tekst</option>
              <option value="voice">Głos</option>
            </select>
          </div>
        </div>
        <div class="form-actions">
          <button class="btn btn-primary" id="ha-btn-save-satellite">Zarejestruj</button>
          <button class="btn btn-ghost" id="ha-btn-cancel-satellite">Anuluj</button>
        </div>
      </div>
    `;

    document.getElementById('ha-btn-save-satellite')?.addEventListener('click', () => this._handleRegisterSatellite());
    document.getElementById('ha-btn-cancel-satellite')?.addEventListener('click', () => {
      this.isRegisteringSatellite = false;
      formContainer.innerHTML = '';
    });
  }

  async _handleRegisterSatellite() {
    const senderId = document.getElementById('ha-sat-sender-id')?.value.trim() || '';
    const displayName = document.getElementById('ha-sat-display-name')?.value.trim() || null;
    const roomKey = document.getElementById('ha-sat-room')?.value || null;
    const channel = document.getElementById('ha-sat-channel')?.value || 'text';

    if (!senderId) {
      this.showToast('sender_id jest wymagany.', 'error');
      return;
    }

    try {
      await this.apiClient.registerSatellite({
        sender_id: senderId,
        room_key: roomKey || null,
        room_label: roomKey || null,
        channel,
        display_name: displayName,
      });
      this.showToast('Zarejestrowano satelitę.', 'success');
      this.isRegisteringSatellite = false;
      await this._loadAndRender();
    } catch (error) {
      this.showToast(error.message || 'Błąd rejestracji satelity.', 'error');
    }
  }

  async _handleDeleteSatellite(senderId) {
    try {
      await this.apiClient.deleteSatellite(senderId);
      this.showToast('Usunięto rejestrację satelity.', 'success');
      await this._loadAndRender();
    } catch (error) {
      this.showToast(error.message || 'Błąd usuwania satelity.', 'error');
    }
  }

  // --------------------------------------------------------------------------
  // Zdarzenia
  // --------------------------------------------------------------------------

  _bindEvents() {
    document.getElementById('ha-btn-save-config')?.addEventListener('click', () => this._handleSaveConfig());

    const searchInput = document.getElementById('ha-search-input');
    searchInput?.addEventListener('input', (e) => {
      this.searchQuery = e.target.value;
      this._renderSearchResults();
    });

    this.container.querySelectorAll('.ha-declared-label')?.forEach((input) => {
      input.addEventListener('change', (e) => this._handleRenameDeclaredDevice(e.target.getAttribute('data-entity-id'), e.target.value));
    });
    this.container.querySelectorAll('[data-remove-entity]')?.forEach((btn) => {
      btn.addEventListener('click', () => this._handleRemoveDeclaredDevice(btn.getAttribute('data-remove-entity')));
    });

    document.getElementById('ha-btn-new-group')?.addEventListener('click', () => {
      this.isCreatingGroup = true;
      this._renderGroupForm();
    });
    this.container.querySelectorAll('[data-delete-group]')?.forEach((btn) => {
      btn.addEventListener('click', () => this._handleDeleteGroup(btn.getAttribute('data-delete-group')));
    });

    document.getElementById('ha-btn-new-satellite')?.addEventListener('click', () => {
      this.isRegisteringSatellite = true;
      this._renderSatelliteForm();
    });
    document.getElementById('ha-btn-use-this-browser')?.addEventListener('click', () => {
      this.isRegisteringSatellite = true;
      this._renderSatelliteForm(getSenderId());
    });
    this.container.querySelectorAll('[data-delete-satellite]')?.forEach((btn) => {
      btn.addEventListener('click', () => this._handleDeleteSatellite(btn.getAttribute('data-delete-satellite')));
    });
  }

  async _handleSaveConfig() {
    const baseUrl = document.getElementById('ha-input-base-url')?.value.trim() || '';
    const token = document.getElementById('ha-input-token')?.value || '';

    if (!baseUrl) {
      this.showToast('Adres serwera jest wymagany.', 'error');
      return;
    }

    try {
      const payload = { base_url: baseUrl, access_token: token || this.config.access_token };
      await this.apiClient.updateHAConfig(payload);
      this.showToast('Zapisano konfigurację.', 'success');
      await this._loadAndRender();
    } catch (error) {
      this.showToast(error.message || 'Błąd zapisu konfiguracji.', 'error');
    }
  }

  async _handleAddDeclaredDevice(entityId) {
    try {
      await this.apiClient.addHADeclaredDevice({ entity_id: entityId });
      this.showToast('Dodano urządzenie.', 'success');
      this.searchQuery = '';
      await this._loadAndRender();
    } catch (error) {
      this.showToast(error.message || 'Błąd dodawania urządzenia.', 'error');
    }
  }

  async _handleRenameDeclaredDevice(entityId, displayName) {
    try {
      await this.apiClient.updateHADeclaredDevice(entityId, { display_name: displayName.trim() || null });
      this.showToast('Zaktualizowano nazwę.', 'success');
      await this._loadAndRender();
    } catch (error) {
      this.showToast(error.message || 'Błąd aktualizacji nazwy.', 'error');
    }
  }

  async _handleRemoveDeclaredDevice(entityId) {
    try {
      await this.apiClient.deleteHADeclaredDevice(entityId);
      this.showToast('Usunięto urządzenie z listy.', 'success');
      await this._loadAndRender();
    } catch (error) {
      this.showToast(error.message || 'Błąd usuwania urządzenia.', 'error');
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

function truncateMaskedToken(masked) {
  // Backend maskuje token do jego pełnej długości kropkami (z ostatnimi 4 znakami
  // widocznymi) — dla długich tokenów (JWT) to ściana kropek wychodząca poza kartę.
  // Wizualnie ograniczamy do stałej liczby kropek, sens (zamaskowane + końcówka) zostaje.
  const MAX_DOTS = 24;
  const visibleSuffix = masked.replace(/^•+/, '');
  const dotsCount = masked.length - visibleSuffix.length;
  if (dotsCount <= MAX_DOTS) return masked;
  return `${'•'.repeat(MAX_DOTS)}${visibleSuffix}`;
}
