import { Icons } from '../../icons.js';
import { renderSelectMarkup } from '../../components/select.js';

/**
 * Szablon zakładki „Logi" — czyste funkcje renderujące HTML (wzorzec
 * `renderXMarkup` z `views/chat/chat_template.js`). Zero `this`, zero side-effectów.
 *
 * Układ jest **master-detail o stałym podziale**, nie pełnoekranową nakładką jak
 * w logach OpenRoutera: konsola ma własny sidebar, więc nakładka byłaby w niej
 * obcym ciałem, a przede wszystkim — podział ustalony z góry nie przeskakuje
 * przy zaznaczeniu wiersza (karty i kontenery mają stałe wymiary).
 */

export function renderLogsLayoutMarkup() {
  return `
    <div class="logs-layout">
      <div class="logs-toolbar">
        <div class="logs-toolbar-left">
          <div class="logs-toolbar-title">
            <span class="logs-toolbar-icon" id="icon-logs-title"></span>
            <span>Wywołania LLM</span>
            <span class="badge-chip" id="logs-count-badge">0</span>
          </div>
          ${renderSelectMarkup('logs-status-filter', {
            placeholder: 'Wszystkie statusy',
            className: 'select--compact logs-filter-select',
          })}
        </div>
        <div class="logs-toolbar-right">
          <label class="logs-auto-toggle" title="Odświeża listę co 5 sekund">
            <input type="checkbox" id="logs-auto-refresh" />
            <span>Auto</span>
          </label>
          <button class="btn btn-subtle btn-sm" id="btn-logs-refresh" title="Odśwież listę">
            <span id="icon-logs-refresh"></span>
            <span>Odśwież</span>
          </button>
          <button class="btn btn-ghost-danger btn-sm" id="btn-logs-clear" title="Usuń wszystkie zapisane zrzuty">
            <span id="icon-logs-clear"></span>
            <span>Wyczyść</span>
          </button>
        </div>
      </div>

      <div class="logs-body">
        <div class="logs-list-pane">
          <div class="logs-list" id="logs-list"></div>
          <div class="logs-list-footer">
            <button class="btn btn-subtle btn-sm hidden" id="btn-logs-more">Wczytaj starsze</button>
          </div>
        </div>
        <div class="logs-inspector" id="logs-inspector">
          ${renderInspectorEmptyMarkup()}
        </div>
      </div>
    </div>
  `;
}

export function renderInspectorEmptyMarkup() {
  return `
    <div class="logs-empty">
      <div class="logs-empty-icon">${Icons.FileText()}</div>
      <div class="logs-empty-title">Wybierz wywołanie</div>
      <div class="logs-empty-desc">
        Zobaczysz dokładny kontekst wysłany do modelu — łącznie z system promptem
        i faktami tury, których nie ma w historii czatu.
      </div>
    </div>
  `;
}

export function renderListEmptyMarkup() {
  return `
    <div class="logs-empty logs-empty--list">
      <div class="logs-empty-icon">${Icons.Activity()}</div>
      <div class="logs-empty-title">Brak zapisanych wywołań</div>
      <div class="logs-empty-desc">Wyślij wiadomość na zakładce Czat — zrzut pojawi się tutaj.</div>
    </div>
  `;
}
