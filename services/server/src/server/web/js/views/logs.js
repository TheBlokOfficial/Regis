import { Icons } from '../icons.js';
import { initSelect } from '../components/select.js';
import { confirmModal } from '../modal_confirm.js';
import { showToast } from '../utils/toast.js';
import { renderLogsLayoutMarkup, renderInspectorEmptyMarkup } from './logs/logs_template.js';
import { renderList } from './logs/logs_list.js';
import { renderInspectorMarkup, bindInspectorEvents } from './logs/logs_inspector.js';

/**
 * Zakładka „Logi" — podgląd zrzutów wywołań LLM (`server/telemetry`).
 *
 * Cienki klej, wzorem `ChatView`: szablon w `logs/logs_template.js`, lista w
 * `logs/logs_list.js`, inspektor w `logs/logs_inspector.js`, porównanie w
 * `logs/logs_diff.js`. Tu zostaje stan (co wybrane, jaki filtr) i sieć.
 *
 * Odświeżanie jest na żądanie plus opcjonalny odpytywanie co 5 s — świadomie bez
 * osobnego kanału SSE. Panel czyta stan zapisany na dysku, a nie przebieg tury na
 * żywo (od tego jest zakładka Czat), więc stały strumień byłby kosztem bez pokrycia.
 */

const PAGE_SIZE = 50;
const AUTO_REFRESH_MS = 5000;

const STATUS_OPTIONS = [
  { value: '', label: 'Wszystkie statusy' },
  { value: 'ok', label: 'Zakończone' },
  { value: 'error', label: 'Błędy' },
  { value: 'cancelled', label: 'Przerwane' },
  { value: 'no_generation', label: 'Bez wywołania modelu' },
];

export class LogsView {
  constructor() {
    this.apiClient = null;
    this.entries = [];
    this.nextBeforeId = null;
    this.statusFilter = '';
    this.activeId = null;
    this.autoRefreshTimer = null;
    // Szczegóły są niezmienne (rekord nigdy się nie zmienia po zapisie), więc cache
    // jest bezpieczny bezterminowo — a przy porównywaniu z poprzednim wywołaniem
    // ten sam wpis pobierałby się w kółko.
    this.detailCache = new Map();
  }

  render() {
    return renderLogsLayoutMarkup();
  }

  async init(apiClient) {
    this.apiClient = apiClient;
    this.mountIcons();
    this.bindEvents();
    await this.loadFirstPage();
  }

  /** Wołane przez TabManager przy opuszczaniu zakładki — bez tego timer żyłby dalej. */
  destroy() {
    this.stopAutoRefresh();
  }

  mountIcons() {
    const icons = {
      'icon-logs-title': Icons.Activity(),
      'icon-logs-refresh': Icons.RefreshCw(),
      'icon-logs-clear': Icons.Trash2(),
    };
    Object.entries(icons).forEach(([id, svg]) => {
      const el = document.getElementById(id);
      if (el) el.innerHTML = svg;
    });
  }

  bindEvents() {
    initSelect({
      idPrefix: 'logs-status-filter',
      options: STATUS_OPTIONS,
      value: this.statusFilter,
      onChange: async (value) => {
        this.statusFilter = value;
        await this.loadFirstPage();
      },
    });

    document.getElementById('btn-logs-refresh')?.addEventListener('click', () => this.loadFirstPage());
    document.getElementById('btn-logs-more')?.addEventListener('click', () => this.loadNextPage());
    document.getElementById('btn-logs-clear')?.addEventListener('click', () => this.clearAll());

    document.getElementById('logs-auto-refresh')?.addEventListener('change', (event) => {
      if (event.target.checked) this.startAutoRefresh();
      else this.stopAutoRefresh();
    });

    document.getElementById('logs-list')?.addEventListener('click', (event) => {
      const row = event.target.closest('.logs-row');
      if (row) this.selectRecord(Number(row.getAttribute('data-record-id')));
    });
  }

  // --------------------------------------------------------------------------
  // Lista
  // --------------------------------------------------------------------------

  async loadFirstPage() {
    const response = await this.apiClient.getGenerations({
      limit: PAGE_SIZE,
      status: this.statusFilter || null,
    });
    this.entries = response.entries;
    this.nextBeforeId = response.next_before_id;
    this.paintList();
  }

  async loadNextPage() {
    if (this.nextBeforeId === null) return;
    const response = await this.apiClient.getGenerations({
      limit: PAGE_SIZE,
      beforeId: this.nextBeforeId,
      status: this.statusFilter || null,
    });
    this.entries = [...this.entries, ...response.entries];
    this.nextBeforeId = response.next_before_id;
    this.paintList();
  }

  paintList() {
    renderList(document.getElementById('logs-list'), this.entries, this.activeId);

    const countBadge = document.getElementById('logs-count-badge');
    if (countBadge) countBadge.textContent = String(this.entries.length);

    const moreButton = document.getElementById('btn-logs-more');
    if (moreButton) moreButton.classList.toggle('hidden', this.nextBeforeId === null);
  }

  // --------------------------------------------------------------------------
  // Inspektor
  // --------------------------------------------------------------------------

  async selectRecord(recordId) {
    this.activeId = recordId;
    this.paintList();

    const detail = await this.fetchDetail(recordId);
    const container = document.getElementById('logs-inspector');
    if (!container) return;
    if (!detail) {
      container.innerHTML = renderInspectorEmptyMarkup();
      return;
    }

    const previous = await this.fetchPreviousInSession(detail);
    container.innerHTML = renderInspectorMarkup(detail, previous);
    container.scrollTop = 0;
    bindInspectorEvents(container);
  }

  async fetchDetail(recordId) {
    if (this.detailCache.has(recordId)) return this.detailCache.get(recordId);
    const detail = await this.apiClient.getGeneration(recordId);
    if (detail) this.detailCache.set(recordId, detail);
    return detail;
  }

  /**
   * Poprzednie wywołanie TEJ SAMEJ sesji — punkt odniesienia dla diffu.
   *
   * Sesja, nie tura: zmiana system promptu zachodzi między turami (użytkownik
   * edytuje profil w Ustawieniach), więc porównanie ograniczone do jednej tury
   * nigdy by jej nie pokazało. Szukamy w już wczytanej liście, bo interesuje nas
   * sąsiad, a ten prawie zawsze jest na tej samej stronie.
   */
  async fetchPreviousInSession(detail) {
    if (!detail.session_id) return null;
    const previousEntry = this.entries.find((e) => e.session_id === detail.session_id && e.id < detail.id);
    if (!previousEntry) return null;
    return this.fetchDetail(previousEntry.id);
  }

  // --------------------------------------------------------------------------

  startAutoRefresh() {
    this.stopAutoRefresh();
    this.autoRefreshTimer = setInterval(() => this.loadFirstPage(), AUTO_REFRESH_MS);
  }

  stopAutoRefresh() {
    if (this.autoRefreshTimer === null) return;
    clearInterval(this.autoRefreshTimer);
    this.autoRefreshTimer = null;
  }

  async clearAll() {
    const confirmed = await confirmModal({
      title: 'Wyczyścić telemetrię?',
      message: 'Usunie to wszystkie zapisane zrzuty wywołań LLM. Historia czatu pozostaje nietknięta.',
      confirmLabel: 'Usuń wszystko',
    });
    if (!confirmed) return;

    try {
      const result = await this.apiClient.clearGenerations();
      this.detailCache.clear();
      this.activeId = null;
      const inspector = document.getElementById('logs-inspector');
      if (inspector) inspector.innerHTML = renderInspectorEmptyMarkup();
      await this.loadFirstPage();
      showToast(`Usunięto ${result.deleted} wpisów telemetrii.`, 'success');
    } catch (error) {
      showToast(`Nie udało się wyczyścić telemetrii: ${error.message}`, 'error');
    }
  }
}
