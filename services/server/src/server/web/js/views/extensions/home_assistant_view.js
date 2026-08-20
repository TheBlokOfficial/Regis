import { renderConfigForm, bindConfigEvents } from './ha/config_panel.js';
import { renderRoomsList, renderRoomForm, bindRoomEvents } from './ha/rooms_panel.js';
import { renderDeviceSearch, renderSearchResults, renderDeclaredList, initDeclaredRoomSelects, bindDeviceEvents } from './ha/devices_panel.js';
import { renderGroupsList, renderGroupForm, bindGroupEvents } from './ha/groups_panel.js';
import { renderThisBrowserHint, renderSatellitesList, renderSatelliteForm, bindSatelliteEvents } from './ha/satellites_panel.js';

/**
 * Widok konfiguracji silnika świata (WorldEngine) — w pełni domenowy (nie
 * generyczny/schema-driven, w przeciwieństwie do formularzy dostawców LLM).
 * Pięć sekcji: Konfiguracja (singleton Home Assistant — jeden
 * `base_url`/`access_token`), Pokoje (pełnoprawny byt World, niezależny od
 * Home Assistant Areas — te są wyłącznie podpowiedzią/importem jednorazowym),
 * Urządzenia (wyszukiwarka nad surowym katalogiem HA + opt-in zadeklarowana
 * lista, jedyne źródło prawdy o tym, co widzi agent — każde z przypisanym
 * pokojem), Grupy (multi-select nad zadeklarowaną listą), Nadawcy
 * (przypisanie `sender_id -> pokój` — World nie wie nic o kanale komunikacji
 * ani o typie fizycznego urządzenia; Web UI jest pierwszym, zawsze dostępnym
 * nadawcą, więc sekcja od razu proponuje jej własny, trwały `sender_id` do
 * rejestracji).
 *
 * Wizualnie ten sam system co Agent: pełne (nie kreskowane) subtelne
 * obramowania, listy jako jeden kontener z hairline-separatorami (nie ramka
 * na każdym wierszu), custom dropdown (`components/select.js`) zamiast
 * natywnego <select>, kwadratowe czerwone ikony usuwania + potwierdzenie
 * przez `confirmModal()` (dawniej: zero potwierdzenia przy kasowaniu).
 *
 * Klasa jest tu cienkim koordynatorem: trzyma współdzielony stan (urządzenia
 * potrzebują listy pokoi, grupy potrzebują zadeklarowanych urządzeń) i deleguje
 * render/zdarzenia do pięciu paneli domenowych w `./ha/` — każdy odpowiada
 * jednej sekcji widoku i operuje na tym stanie przez przekazane `view` (this).
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
    this.senders = [];
    this.rooms = [];

    this.isCreatingGroup = false;
    this.isRegisteringSender = false;
    this.isCreatingRoom = false;
  }

  async mount(container, apiClient, showToast) {
    this.container = container;
    this.apiClient = apiClient;
    this.showToast = showToast;
    await this._loadAndRender();
  }

  async _loadAndRender() {
    const [config, declared, groups, catalog, senders, rooms] = await Promise.all([
      this.apiClient.getHAConfig(),
      this.apiClient.getHADeclaredDevices(),
      this.apiClient.getHAGroups(),
      this.apiClient.getHACatalog(),
      this.apiClient.getSenders(),
      this.apiClient.getRooms(),
    ]);
    this.config = config || { base_url: '', access_token: '' };
    this.declaredDevices = declared || [];
    this.groups = groups || [];
    this.catalog = catalog || [];
    this.senders = senders || [];
    this.rooms = rooms || [];
    this._render();
  }

  _render() {
    this.container.innerHTML = `
      <div class="ha-view">
        <section class="ha-section">
          <div class="ha-section-header">
            <span class="ha-section-title">Konfiguracja</span>
          </div>
          ${renderConfigForm(this)}
        </section>

        <section class="ha-section">
          <div class="ha-section-header">
            <span class="ha-section-title">Pokoje</span>
            <div class="ha-section-header-actions">
              <button class="btn btn-sm btn-ghost" id="ha-btn-import-rooms" title="Jednorazowy import — bez ciągłej synchronizacji">Zaimportuj z HA Areas</button>
              <button class="btn btn-sm btn-primary" id="ha-btn-new-room">+ Nowy pokój</button>
            </div>
          </div>
          <div class="ha-rooms-list">${renderRoomsList(this)}</div>
          <div id="ha-room-form"></div>
        </section>

        <section class="ha-section">
          <div class="ha-section-header">
            <span class="ha-section-title">Urządzenia</span>
          </div>
          ${renderDeviceSearch(this)}
          <div id="ha-search-results"></div>
          ${renderDeclaredList(this)}
        </section>

        <section class="ha-section">
          <div class="ha-section-header">
            <span class="ha-section-title">Grupy</span>
            <button class="btn btn-sm btn-primary" id="ha-btn-new-group">+ Nowa grupa</button>
          </div>
          <div class="ha-groups-list">${renderGroupsList(this)}</div>
          <div id="ha-group-form"></div>
        </section>

        <section class="ha-section">
          <div class="ha-section-header">
            <span class="ha-section-title">Nadawcy</span>
            <button class="btn btn-sm btn-primary" id="ha-btn-new-satellite">+ Nowa rejestracja</button>
          </div>
          ${renderThisBrowserHint(this)}
          <div class="ha-satellites-list">${renderSatellitesList(this)}</div>
          <div id="ha-satellite-form"></div>
        </section>
      </div>
    `;
    this._bindEvents();
    renderSearchResults(this);
    initDeclaredRoomSelects(this);
    if (this.isCreatingRoom) renderRoomForm(this);
    if (this.isCreatingGroup) renderGroupForm(this);
    if (this.isRegisteringSender) renderSatelliteForm(this);
  }

  _bindEvents() {
    bindConfigEvents(this);
    bindRoomEvents(this);
    bindDeviceEvents(this);
    bindGroupEvents(this);
    bindSatelliteEvents(this);
  }
}
