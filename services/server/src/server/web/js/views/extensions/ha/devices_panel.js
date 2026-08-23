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

  const hint = (text) => {
    resultsContainer.innerHTML = `<p class="ha-empty-hint">${escapeHtml(text)}</p>`;
  };

  if (view.catalogState === 'loading') {
    hint('Pobieram katalog encji z Home Assistant...');
    return;
  }
  if (view.catalogState === 'idle') {
    hint('Zacznij pisać, żeby przeszukać encje Home Assistant.');
    return;
  }
  if (view.catalogState === 'error' || (view.catalog || []).length === 0) {
    hint('Skonfiguruj serwer, aby zobaczyć dostępne encje.');
    return;
  }

  const query = view.searchQuery.trim().toLowerCase();
  // Pusta fraza NIE wysypuje całego katalogu. Wcześniej tak było i przy realnej
  // instalacji HA dawało setki wierszy nad zadeklarowaną listą — nie do przejrzenia
  // i nie do niczego przydatne, bo i tak szuka się konkretnej encji po nazwie.
  if (!query) {
    hint(`Wpisz nazwę lub entity_id — dostępnych encji: ${(view.catalog || []).length}.`);
    return;
  }

  const declaredIds = new Set(view.declaredDevices.map((d) => d.entity_id));
  const matches = (view.catalog || [])
    .filter((entry) => !declaredIds.has(entry.entity_id))
    .filter((entry) => entry.friendly_name.toLowerCase().includes(query) || entry.entity_id.toLowerCase().includes(query));

  if (matches.length === 0) {
    hint('Brak pasujących encji.');
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

/**
 * Skraca identyfikator encji od ŚRODKA, nie od końca.
 *
 * To nie jest kosmetyka: encje jednego urządzenia wielokrotnego (siedem żarówek
 * Yeelight) różnią się wyłącznie sufiksem, więc ucinanie końca zamieniało całą listę
 * w siedem identycznych wierszy `light.yeelight_colorc_0x1e…`, nie do odróżnienia.
 */
function truncateMiddle(text, max = 34) {
  if (text.length <= max) return text;
  const head = Math.ceil((max - 1) / 2);
  const tail = Math.floor((max - 1) / 2);
  return `${text.slice(0, head)}…${text.slice(-tail)}`;
}

/** Grupuje po pokoju — jedyny wymiar, wzdłuż którego ta lista ma sens (i ten sam,
 * którego używa `WorldEngine` przy renderowaniu urządzeń do promptu). */
function groupByRoom(view) {
  const groups = new Map();
  for (const entry of view.declaredDevices) {
    const key = entry.room_id || '';
    if (!groups.has(key)) groups.set(key, { name: entry.room_name || 'Bez przypisanego pokoju', entries: [] });
    groups.get(key).entries.push(entry);
  }
  // Nieprzypisane na koniec — to lista "do zrobienia", nie pełnoprawny pokój.
  return [...groups.entries()].sort((a, b) => (a[0] === '' ? 1 : b[0] === '' ? -1 : a[1].name.localeCompare(b[1].name)));
}

export function renderDeclaredList(view) {
  const count = view.declaredDevices.length;
  const selected = view.selectedDeviceIds?.size || 0;
  const header = `
    <div class="ha-declared-header">
      <div class="ha-subsection-title">Zadeklarowane urządzenia${count ? ` (${count})` : ''}</div>
      ${
        count
          ? `<div class="ha-bulk-bar ${selected ? 'is-visible' : ''}">
               <span class="ha-bulk-count">${selected} zaznaczonych</span>
               ${renderSelectMarkup('ha-bulk-room', { placeholder: 'Przypisz pokój', className: 'select--compact' })}
             </div>`
          : ''
      }
    </div>
  `;

  if (count === 0) {
    return `${header}<p class="ha-empty-hint">Brak zadeklarowanych urządzeń — dodaj przez wyszukiwarkę powyżej.</p>`;
  }

  const rows = groupByRoom(view)
    .map(
      ([roomId, group]) => `
        <div class="ha-room-group">
          <div class="ha-room-group-head">
            <span class="ha-room-group-name">${escapeHtml(group.name)}</span>
            <span class="ha-room-group-count">${group.entries.length}</span>
          </div>
          ${group.entries.map((entry) => renderDeclaredRow(view, entry)).join('')}
        </div>
      `
    )
    .join('');

  return `
    ${header}
    <div class="ha-declared-table">
      <div class="ha-declared-row ha-declared-row--head">
        <span class="ha-col-check"></span>
        <span class="ha-col-name">Nazwa</span>
        <span class="ha-col-entity">entity_id</span>
        <span class="ha-col-kind">Typ</span>
        <span class="ha-col-room">Pokój</span>
        <span class="ha-col-caps">Możliwości</span>
        <span class="ha-col-actions"></span>
      </div>
      ${rows}
    </div>
  `;
}

/** Możliwości jako zwarte znaczniki zamiast powtórzonego siedem razy ciągu
 * `get_state · turn_off · turn_on` — dla urządzeń tej samej domeny są identyczne,
 * więc jako tekst nie niosły żadnej informacji różnicującej. */
function renderCaps(capabilities) {
  const labels = { get_state: 'odczyt', turn_on: 'wł.', turn_off: 'wył.' };
  return (capabilities || [])
    .map((cap) => `<span class="ha-cap-chip" title="${escapeAttr(cap)}">${escapeHtml(labels[cap] || cap)}</span>`)
    .join('');
}

function renderDeclaredRow(view, entry) {
  const isChecked = view.selectedDeviceIds?.has(entry.entity_id);
  return `
    <div class="ha-declared-row" data-entity-id="${escapeAttr(entry.entity_id)}">
      <span class="ha-col-check">
        <button type="button" class="ha-check ${isChecked ? 'is-checked' : ''}"
          data-select-entity="${escapeAttr(entry.entity_id)}" role="checkbox"
          aria-checked="${isChecked ? 'true' : 'false'}" aria-label="Zaznacz urządzenie">
          ${Icons.Check()}
        </button>
      </span>
      <span class="ha-col-name">
        <input type="text" class="form-control ha-editable-label ha-declared-name-input"
          data-entity-id="${escapeAttr(entry.entity_id)}" value="${escapeAttr(entry.effective_name)}" />
        ${!entry.display_name ? '<span class="ha-declared-default-hint" title="Domyślna nazwa z Home Assistant — warto nadać własną.">●</span>' : ''}
      </span>
      <span class="ha-col-entity ha-declared-entity-id" title="${escapeAttr(entry.entity_id)}">${escapeHtml(truncateMiddle(entry.entity_id))}</span>
      <span class="ha-col-kind"><span class="badge-chip">${escapeHtml(entry.kind || '?')}</span></span>
      <span class="ha-col-room">${renderSelectMarkup(`ha-declared-room-${entry.entity_id}`, { placeholder: '— brak pokoju —', className: 'select--compact ha-declared-room-select' })}</span>
      <span class="ha-col-caps">${renderCaps(entry.capabilities)}</span>
      <span class="ha-col-actions">
        <button class="btn btn-ghost-danger btn-icon-square" data-remove-entity="${escapeAttr(entry.entity_id)}"
          title="Usuń urządzenie" aria-label="Usuń urządzenie">${Icons.Trash2()}</button>
      </span>
    </div>
  `;
}

/** Montuje custom-select picker pokoju dla każdego zadeklarowanego urządzenia — wywoływane po każdym `_render()`. */
export function initDeclaredRoomSelects(view) {
  const roomOptions = view.rooms.map((room) => ({ value: room.id, label: room.name }));

  // Przypisanie pokoju hurtem — przy siedmiu identycznych żarówkach ustawianie go
  // wiersz po wierszu to siedem razy ta sama czynność.
  if (document.getElementById('ha-bulk-room-select')) {
    initSelect({
      idPrefix: 'ha-bulk-room',
      options: [{ value: '', label: '— brak pokoju —' }, ...roomOptions],
      value: '',
      placeholder: 'Przypisz pokój',
      onChange: (value) => handleBulkAssignRoom(view, value),
    });
  }

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
  // Katalog encji dociąga się dopiero tutaj — przy pierwszym realnym kontakcie z
  // wyszukiwarką, a nie przy wejściu w zakładkę (patrz `home_assistant_view.js`,
  // `ensureCatalog`). To jedyny zasób tego widoku, który kosztuje żywe zapytanie
  // do fizycznego Home Assistant.
  const loadCatalogThenRender = () => {
    renderSearchResults(view);
    view.ensureCatalog().then(() => renderSearchResults(view));
  };
  searchInput?.addEventListener('focus', loadCatalogThenRender, { once: true });
  searchInput?.addEventListener('input', (e) => {
    view.searchQuery = e.target.value;
    if (view.catalogState === 'idle') {
      loadCatalogThenRender();
      return;
    }
    renderSearchResults(view);
  });

  view.container.querySelectorAll('.ha-declared-name-input')?.forEach((input) => {
    input.addEventListener('change', (e) => handleRenameDeclaredDevice(view, e.target.getAttribute('data-entity-id'), e.target.value));
  });
  // Zaznaczanie wierszy zyje WYLACZNIE w pamieci widoku (nic nie trafia na serwer) —
  // sluzy tylko do przypisania pokoju hurtem, wiec kasujemy je po kazdej mutacji listy.
  view.container.querySelectorAll('[data-select-entity]')?.forEach((btn) => {
    btn.addEventListener('click', () => {
      const id = btn.getAttribute('data-select-entity');
      if (view.selectedDeviceIds.has(id)) view.selectedDeviceIds.delete(id);
      else view.selectedDeviceIds.add(id);
      view._render();
    });
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

/** Przypisuje pokoj wszystkim zaznaczonym urzadzeniom naraz. Zadania leca rownolegle,
 * ale odswiezenie listy jest JEDNO — przerenderowanie po kazdym z osobna gubiloby
 * pozostale zaznaczenia w trakcie operacji. */
async function handleBulkAssignRoom(view, roomId) {
  const ids = [...view.selectedDeviceIds];
  if (ids.length === 0) return;
  try {
    await Promise.all(ids.map((entityId) => view.apiClient.updateHADeclaredDevice(entityId, { room_id: roomId || null })));
    view.selectedDeviceIds.clear();
    view.showToast(`Przypisano pokoj do ${ids.length} urzadzen.`, 'success');
    await view._refresh();
  } catch (error) {
    view.showToast(error.message || 'Blad przypisywania pokoju.', 'error');
  }
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
