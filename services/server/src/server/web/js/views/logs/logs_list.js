import { escapeHtml, escapeAttr } from '../../utils/dom.js';
import { renderListEmptyMarkup } from './logs_template.js';

/**
 * Lista wywołań LLM, grupowana po turze.
 *
 * Grupowanie jest tu **darmowe**, a nie drugim modelem danych: rekordy niosą
 * `turn_id` i `call_index`, więc widok „po turach/sesjach" powstaje z tego samego
 * zapisu request-first, co widok płaski. Ma to konkretne znaczenie diagnostyczne —
 * jedna tura z pętlą ReAct to N wywołań, a różnica między nimi (rosnący kontekst,
 * inny `finish_reason`) jest najczęstszym powodem zaglądania tutaj.
 *
 * Wiersz jest dwuliniowy i ma stałą wysokość — kolumnowa tabela z ośmioma metrykami
 * nie mieści się w panelu master-detail bez poziomego przewijania.
 */

const STATUS_LABELS = {
  ok: 'ok',
  error: 'błąd',
  cancelled: 'przerwane',
  no_generation: 'bez wywołania',
};

function formatTime(seconds) {
  const date = new Date(seconds * 1000);
  return date.toLocaleTimeString('pl-PL', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function formatDay(seconds) {
  return new Date(seconds * 1000).toLocaleDateString('pl-PL', { day: '2-digit', month: 'short' });
}

export function formatMs(value) {
  if (value === null || value === undefined) return '—';
  return value >= 1000 ? `${(value / 1000).toFixed(2)} s` : `${Math.round(value)} ms`;
}

export function formatTokens(entry) {
  const input = entry.prompt_tokens ?? '—';
  const output = entry.completion_tokens ?? '—';
  const cached = entry.cached_tokens ? ` (${entry.cached_tokens} z cache)` : '';
  return `${input} → ${output} tok${cached}`;
}

function metricsLine(entry) {
  const parts = [formatTokens(entry)];
  if (entry.ttft_ms !== null && entry.ttft_ms !== undefined) parts.push(`TTFT ${formatMs(entry.ttft_ms)}`);
  if (entry.output_tps) parts.push(`${entry.output_tps.toFixed(1)} tok/s`);
  if (entry.tool_calls > 0) parts.push(`${entry.tool_calls} × narzędzie`);
  return parts.join(' · ');
}

function rowBadges(entry) {
  const badges = [];
  if (entry.finish_reason) badges.push(`<span class="badge-chip">${escapeHtml(entry.finish_reason)}</span>`);
  if (entry.attempt_count > 1) {
    badges.push(`<span class="badge-chip logs-badge-warn">fallback ×${entry.attempt_count}</span>`);
  }
  if (entry.estimated && entry.status === 'ok') {
    badges.push('<span class="badge-chip logs-badge-muted" title="Dostawca nie zwrócił rozliczenia tokenów">estymata</span>');
  }
  return badges.join('');
}

function renderRow(entry, isActive) {
  return `
    <button class="logs-row ${isActive ? 'active' : ''}" data-record-id="${escapeAttr(String(entry.id))}">
      <span class="logs-row-status logs-status--${escapeAttr(entry.status)}" title="${escapeAttr(
        STATUS_LABELS[entry.status] || entry.status
      )}"></span>
      <span class="logs-row-index">#${entry.call_index}</span>
      <span class="logs-row-main">
        <span class="logs-row-top">
          <span class="logs-row-model">${escapeHtml(entry.model || '—')}</span>
          <span class="logs-row-badges">${rowBadges(entry)}</span>
        </span>
        <span class="logs-row-metrics">${escapeHtml(metricsLine(entry))}</span>
      </span>
      <span class="logs-row-time">${escapeHtml(formatTime(entry.created_at))}</span>
    </button>
  `;
}

function renderGroup(group, activeId) {
  const first = group.entries[0];
  const provider = first.instance_name || first.provider_type || 'brak dostawcy';
  const callWord = group.entries.length === 1 ? 'wywołanie' : 'wywołania';
  return `
    <div class="logs-group">
      <div class="logs-group-header">
        <span class="logs-group-title" title="${escapeAttr(first.session_id || '')}">
          ${escapeHtml(provider)}
        </span>
        <span class="logs-group-meta">
          ${escapeHtml(formatDay(first.created_at))} · ${group.entries.length} ${callWord}
        </span>
      </div>
      ${group.entries.map((entry) => renderRow(entry, entry.id === activeId)).join('')}
    </div>
  `;
}

/**
 * Skleja sąsiadujące wpisy tej samej tury w jedną grupę. Lista przychodzi
 * posortowana malejąco po `id`, więc wpisy jednej tury są zawsze obok siebie —
 * grupowanie nie wymaga przechodzenia całej listy dwa razy ani sortowania.
 */
export function groupByTurn(entries) {
  const groups = [];
  entries.forEach((entry) => {
    const last = groups[groups.length - 1];
    if (last && last.turnId !== null && last.turnId === entry.turn_id) {
      last.entries.push(entry);
      return;
    }
    groups.push({ turnId: entry.turn_id, entries: [entry] });
  });
  // W obrębie tury pokazujemy wywołania w kolejności chronologicznej — czyta się je
  // jako przebieg pętli, a nie jako "od najnowszego".
  groups.forEach((group) => group.entries.sort((a, b) => a.call_index - b.call_index));
  return groups;
}

export function renderList(container, entries, activeId) {
  if (!container) return;
  if (entries.length === 0) {
    container.innerHTML = renderListEmptyMarkup();
    return;
  }
  container.innerHTML = groupByTurn(entries)
    .map((group) => renderGroup(group, activeId))
    .join('');
}
