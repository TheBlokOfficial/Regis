import { Icons } from '../../../icons.js';
import { confirmModal } from '../../../modal_confirm.js';
import { renderSelectMarkup, initSelect } from '../../../components/select.js';
import { escapeHtml, escapeAttr } from '../../../utils/dom.js';

/**
 * Panel "Urządzenia" — wyszukiwarka nad surowym katalogiem HA + opt-in
 * zadeklarowana lista (jedyne źródło prawdy o tym, co widzi agent), każde
 * z przypisanym pokojem.
 */
export function renderDeviceSearch(view) {
  return `
    <div class="form-group ha-device-search">
      <label for="ha-search-input">Dodaj urządzenie</label>
      <input type="text" id="ha-search-input" class="form-control" placeholder="Szukaj po nazwie lub entity_id..." value="${escapeAttr(view.searchQuery)}" />
    </div>
  `;
}

export function renderSearchResults(view) {
  const resultsContainer = document.getElementById('ha-search-results');
  if (!resultsContainer) return;

  const declaredIds = new Set(view.declaredDevices.map((d) => d.entity_id));
  const query = view.searchQuery.trim().toLowerCase();
  const matches = (view.catalog || [])
    .filter((entry) => !declaredIds.has(entry.entity_id))
    .filter((entry) => !query || entry.friendly_name.toLowerCase().includes(query) || entry.entity_id.toLowerCase().includes(query));

  if (matches.length === 0) {
    resultsContainer.innerHTML = `<p class="ha-empty-hint">${view.catalog.length === 0 ? 'Skonfiguruj serwer, aby zobaczyć dostępne encje.' : 'Brak pasujących encji.'}</p>`;
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
    btn.addEventListener('click', () => handleAddDeclaredDevice(view, btn.getAttribute('data-add-entity')));
  });
}

export function renderDeclaredList(view) {
  const count = view.declaredDevices.length;
  const header = `<div class="ha-subsection-title">Zadeklarowane urządzenia${count ? ` (${count})` : ''}</div>`;

  if (count === 0) {
    return `${header}<p class="ha-empty-hint">Brak zadeklarowanych urządzeń — dodaj przez wyszukiwarkę powyżej.</p>`;
  }

  return `
    ${header}
    <div class="ha-declared-list">
      ${view.declaredDevices
        .map(
          (entry) => `
          <div class="ha-declared-card" data-entity-id="${escapeAttr(entry.entity_id)}">
            <span class="ha-declared-entity-id" title="${escapeAttr(entry.entity_id)}">${escapeHtml(entry.entity_id)}</span>
            <input type="text" class="form-control ha-declared-label" data-entity-id="${escapeAttr(entry.entity_id)}" value="${escapeAttr(entry.effective_name)}" />
            ${!entry.display_name ? '<span class="ha-declared-default-hint" title="Domyślna nazwa z Home Assistant — warto nadać własną.">●</span>' : ''}
            <span class="ha-declared-kind">${escapeHtml(entry.kind || '?')}</span>
            ${renderSelectMarkup(`ha-declared-room-${entry.entity_id}`, { placeholder: '— brak pokoju —', className: 'select--compact ha-declared-room-select' })}
            <span class="ha-declared-caps-text">${(entry.capabilities || []).map((cap) => escapeHtml(cap)).join(' · ')}</span>
            <button class="btn btn-ghost-danger btn-icon-square" data-remove-entity="${escapeAttr(entry.entity_id)}" title="Usuń urządzenie" aria-label="Usuń urządzenie">${Icons.Trash2()}</button>
          </div>
        `
        )
        .join('')}
    </div>
  `;
}

/** Montuje custom-select picker pokoju dla każdego zadeklarowanego urządzenia — wywoływane po każdym `_render()`. */
export function initDeclaredRoomSelects(view) {
  const roomOptions = view.rooms.map((room) => ({ value: room.id, label: room.name }));
  view.declaredDevices.forEach((entry) => {
    initSelect({
      idPrefix: `ha-declared-room-${entry.entity_id}`,
      options: roomOptions,
      value: entry.room_id || '',
      placeholder: '— brak pokoju —',
      onChange: (value) => handleAssignDeclaredDeviceRoom(view, entry.entity_id, value),
    });
  });
}

export function bindDeviceEvents(view) {
  const searchInput = document.getElementById('ha-search-input');
  searchInput?.addEventListener('input', (e) => {
    view.searchQuery = e.target.value;
    renderSearchResults(view);
  });

  view.container.querySelectorAll('.ha-declared-label')?.forEach((input) => {
    input.addEventListener('change', (e) => handleRenameDeclaredDevice(view, e.target.getAttribute('data-entity-id'), e.target.value));
  });
  view.container.querySelectorAll('[data-remove-entity]')?.forEach((btn) => {
    btn.addEventListener('click', () => handleRemoveDeclaredDeviceClick(view, btn.getAttribute('data-remove-entity')));
  });
}

async function handleAddDeclaredDevice(view, entityId) {
  try {
    await view.apiClient.addHADeclaredDevice({ entity_id: entityId });
    view.showToast('Dodano urządzenie.', 'success');
    view.searchQuery = '';
    await view._refresh();
  } catch (error) {
    view.showToast(error.message || 'Błąd dodawania urządzenia.', 'error');
  }
}

async function handleRenameDeclaredDevice(view, entityId, displayName) {
  await handleUpdateDeclaredDevice(view, entityId, { display_name: displayName.trim() || null }, 'Zaktualizowano nazwę.');
}

async function handleAssignDeclaredDeviceRoom(view, entityId, roomId) {
  await handleUpdateDeclaredDevice(view, entityId, { room_id: roomId || null }, 'Zaktualizowano pokój.');
}

/** PUT /declared/{id} nadpisuje cały wpis — łączymy nowe pole ze stanem istniejącego wpisu. */
async function handleUpdateDeclaredDevice(view, entityId, patch, successMessage) {
  const current = view.declaredDevices.find((d) => d.entity_id === entityId);
  const payload = {
    display_name: current?.display_name ?? null,
    room_id: current?.room_id ?? null,
    ...patch,
  };
  try {
    await view.apiClient.updateHADeclaredDevice(entityId, payload);
    view.showToast(successMessage, 'success');
    await view._refresh();
  } catch (error) {
    view.showToast(error.message || 'Błąd aktualizacji urządzenia.', 'error');
  }
}

async function handleRemoveDeclaredDeviceClick(view, entityId) {
  const confirmed = await confirmModal({
    title: 'Usunąć urządzenie z listy?',
    message: 'Urządzenie zniknie z kontekstu agenta, dopóki nie zostanie ponownie zadeklarowane przez wyszukiwarkę.',
    confirmLabel: 'Usuń',
    cancelLabel: 'Anuluj',
  });
  if (!confirmed) return;
  try {
    await view.apiClient.deleteHADeclaredDevice(entityId);
    view.showToast('Usunięto urządzenie z listy.', 'success');
    await view._refresh();
  } catch (error) {
    view.showToast(error.message || 'Błąd usuwania urządzenia.', 'error');
  }
}
