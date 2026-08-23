import { renderConfigForm, bindConfigEvents } from './ha/config_panel.js';
import { renderRoomsPanel, bindRoomEvents } from './ha/rooms_panel.js';
import { renderDeviceSearch, renderSearchResults, renderDeclaredList, initDeclaredRoomSelects, bindDeviceEvents } from './ha/devices_panel.js';
import { renderGroupsList, renderGroupForm, bindGroupEvents } from './ha/groups_panel.js';
import { renderSatellitesList, initSatelliteRoomSelects } from './ha/satellites_panel.js';

/**
 * Szkielet o GEOMETRII docelowego widoku — te same nagłówki sekcji i zbliżone
 * wysokości bloków. Chodzi wyłącznie o to, żeby wejście w zakładkę nie przesuwało
 * kontenerów w pionie: dawny placeholder był jedną niską kartą, którą zastępowała
 * pełna, wysoka treść (patrz `css/components/skeleton.css`).
 */
function renderSkeleton() {
  const section = (title, blocks) => `
    <section class="ha-section">
      <h3 class="section-heading">${title}</h3>
      <div class="skeleton-stack">${blocks}</div>
    </section>
  `;
  const block = (modifier, count = 1) =>
    Array.from({ length: count }, () => `<div class="skeleton-block ${modifier}"></div>`).join('');

  return `
    <div class="ha-view" aria-busy="true">
      ${section('Konfiguracja', block('skeleton-block--field', 2))}
      ${section('Pokoje', block('skeleton-block--row', 2))}
      ${section('Urządzenia', block('skeleton-block--field') + block('skeleton-block--row', 3))}
      ${section('Grupy', block('skeleton-block--row', 2))}
      ${section('Nadawcy', block('skeleton-block--row', 2))}
    </div>
  `;
}

/**
 * Widok konfiguracji silnika świata (WorldEngine) — w pełni domenowy (nie
 * generyczny/schema-driven, w przeciwieństwie do formularzy dostawców LLM).
 * Pięć sekcji: Konfiguracja (singleton Home Assistant — jeden
 * `base_url`/`access_token`), Pokoje (pełnoprawny byt World, niezależny od
 * Home Assistant Areas — te są wyłącznie podpowiedzią/importem jednorazowym),
 * Urządzenia (wyszukiwarka nad surowym katalogiem HA + opt-in zadeklarowana
 * lista, jedyne źródło prawdy o tym, co widzi agent — każde z przypisanym
 * pokojem), Grupy (multi-select nad zadeklarowaną listą), Nadawcy (lista już
 * zarejestrowanych `sender_id -> pokój`, z pickerem pokoju per wiersz —
 * **bez tworzenia nowych rejestracji tutaj**, to żyje w zakładce Głos,
 * `voice_config.js`, bo pierwszy kontakt z nadawcą jest koncepcyjnie domeną
 * `voice`, nie `world`).
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
    // 'idle' -> nikt jeszcze nie tknął wyszukiwarki, katalogu nie pobieramy w ogóle.
    this.catalogState = 'idle';
    this._catalogPromise = null;
    this.searchQuery = '';
    this.senders = [];
    this.rooms = [];

    this.isCreatingGroup = false;
  }

  async mount(container, apiClient, showToast) {
    this.container = container;
    this.apiClient = apiClient;
    this.showToast = showToast;
    // Szkielet leci SYNCHRONICZNIE, zanim poleci pierwszy request — inaczej kontener
    // ma przez moment zerową wysokość i cała strona podskakuje, gdy treść dojedzie.
    this.container.innerHTML = renderSkeleton();
    await this._loadAndRender();
  }

  async _loadAndRender() {
    // Katalog encji HA jest tu świadomie NIEOBECNY. To jedyny z tych zasobów, który
    // realnie kosztuje (żywe HTTP do fizycznego Home Assistant, zero cache po stronie
    // `WorldEngine`), a potrzebuje go wyłącznie wyszukiwarka urządzeń — dociągamy go
    // przy pierwszym użyciu pola szukania (`ensureCatalog`), nie przy wejściu w zakładkę.
    const [config, declared, groups, senders, rooms] = await Promise.all([
      this.apiClient.getHAConfig(),
      this.apiClient.getHADeclaredDevices(),
      this.apiClient.getHAGroups(),
      this.apiClient.getSenders(),
      this.apiClient.getRooms(),
    ]);
    this.config = config || { base_url: '', access_token: '' };
    this.declaredDevices = declared || [];
    this.groups = groups || [];
    this.senders = senders || [];
    this.rooms = rooms || [];
    this._render();
  }

  /**
   * Dociąga surowy katalog encji Home Assistant — dokładnie raz, przy pierwszym
   * realnym użyciu wyszukiwarki. Kolejne wywołania zwracają tę samą, już rozpoczętą
   * obietnicę, żeby szybkie wpisywanie nie odpaliło N równoległych zapytań do HA.
   */
  ensureCatalog() {
    if (this.catalogState === 'ready') return Promise.resolve();
    if (this._catalogPromise) return this._catalogPromise;

    this.catalogState = 'loading';
    this._catalogPromise = this.apiClient
      .getHACatalog()
      .then((catalog) => {
        this.catalog = catalog || [];
        this.catalogState = 'ready';
      })
      .catch((error) => {
        this.catalogState = 'error';
        this.showToast?.(error.message || 'Nie udało się pobrać katalogu encji.', 'error');
      })
      .finally(() => {
        this._catalogPromise = null;
      });
    return this._catalogPromise;
  }

  /** Wołane po zapisie konfiguracji HA — patrz `ha/config_panel.js`. */
  invalidateCatalog() {
    this.catalog = [];
    this.catalogState = 'idle';
    this._catalogPromise = null;
  }

  /**
   * Odświeżenie po typowej mutacji (pokój/urządzenie/grupa/nadawca). Nie rusza
   * katalogu — nie jest potrzebny do poprawnego odświeżenia żadnej z list tego widoku
   * (wyszukiwarka filtruje względem świeżych `declaredDevices`, pickery pokoju budują
   * opcje ze świeżych `rooms`), a raz pobrany zostaje w pamięci widoku.
   */
  async _refresh() {
    const [config, declared, groups, senders, rooms] = await Promise.all([
      this.apiClient.getHAConfig(),
      this.apiClient.getHADeclaredDevices(),
      this.apiClient.getHAGroups(),
      this.apiClient.getSenders(),
      this.apiClient.getRooms(),
    ]);
    this.config = config || { base_url: '', access_token: '' };
    this.declaredDevices = declared || [];
    this.groups = groups || [];
    this.senders = senders || [];
    this.rooms = rooms || [];
    this._render();
  }

  _render() {
    this.container.innerHTML = `
      <div class="ha-view">
        <section class="ha-section">
          <h3 class="section-heading">Konfiguracja</h3>
          ${renderConfigForm(this)}
        </section>

        <section class="ha-section">
          <h3 class="section-heading">Pokoje</h3>
          ${renderRoomsPanel(this)}
        </section>

        <section class="ha-section">
          <h3 class="section-heading">Urządzenia</h3>
          ${renderDeviceSearch(this)}
          <div id="ha-search-results"></div>
          ${renderDeclaredList(this)}
        </section>

        <section class="ha-section">
          <div class="ha-section-header">
            <h3 class="section-heading">Grupy</h3>
            <button class="btn btn-sm btn-subtle" id="ha-btn-new-group">+ Nowa grupa</button>
          </div>
          <div class="ha-groups-list">${renderGroupsList(this)}</div>
          <div id="ha-group-form"></div>
        </section>

        <section class="ha-section">
          <h3 class="section-heading">Nadawcy</h3>
          <div class="ha-satellites-list">${renderSatellitesList(this)}</div>
        </section>
      </div>
    `;
    this._bindEvents();
    renderSearchResults(this);
    initDeclaredRoomSelects(this);
    initSatelliteRoomSelects(this);
    if (this.isCreatingGroup) renderGroupForm(this);
  }

  _bindEvents() {
    bindConfigEvents(this);
    bindRoomEvents(this);
    bindDeviceEvents(this);
    bindGroupEvents(this);
    // Nadawcy nie mają tu żadnych zdarzeń do podpięcia: picker pokoju wiąże się sam
    // w `initSatelliteRoomSelects`, a usuwanie rejestracji (cykl życia klienta)
    // należy do zakładki Klienci, nie do Świata.
  }
}
