import { Icons } from '../../../icons.js';
import { confirmModal } from '../../../modal_confirm.js';
import { escapeAttr } from '../../../utils/dom.js';

/**
 * Panel "Pokoje" — `Room` jako pełnoprawny byt World, niezależny od Home
 * Assistant Areas. Jeden wypełniony kontener (`.stat-panel`, wzorem
 * pozostałych paneli aplikacji): composer dodawania nowego pokoju zawsze
 * widoczny na górze (bez przycisku odsłaniającego — Enter też submituje),
 * lista istniejących pokoi pod spodem.
 */
export function renderRoomsPanel(view) {
  return `
    <div class="stat-panel ha-rooms-panel">
      <form class="ha-rooms-composer" id="ha-rooms-composer">
        <input type="text" id="ha-room-name-input" class="form-control" placeholder="Nazwa nowego pokoju (np. Salon)" />
        <button type="submit" class="btn btn-icon-square ha-rooms-composer-submit" title="Dodaj pokój" aria-label="Dodaj pokój">${Icons.Plus()}</button>
      </form>
      ${renderRoomsList(view)}
    </div>
  `;
}

function renderRoomsList(view) {
  if (view.rooms.length === 0) {
    return `<p class="ha-empty-hint">Brak pokoi — dodaj pierwszy powyżej.</p>`;
  }
  return `
    <div class="ha-rooms-list">
      ${view.rooms
        .map(
          (room) => `
        <div class="ha-rooms-row" data-room-id="${escapeAttr(room.id)}">
          <input type="text" class="form-control ha-editable-label ha-room-name" data-room-id="${escapeAttr(room.id)}" value="${escapeAttr(room.name)}" />
          <button class="btn btn-ghost-danger btn-icon-square" data-delete-room="${escapeAttr(room.id)}" title="Usuń pokój" aria-label="Usuń pokój">${Icons.Trash2()}</button>
        </div>
      `
        )
        .join('')}
    </div>
  `;
}

export function bindRoomEvents(view) {
  document.getElementById('ha-rooms-composer')?.addEventListener('submit', (e) => {
    e.preventDefault();
    handleCreateRoom(view);
  });
  view.container.querySelectorAll('.ha-room-name')?.forEach((input) => {
    input.addEventListener('change', (e) => handleRenameRoom(view, e.target.getAttribute('data-room-id'), e.target.value));
  });
  view.container.querySelectorAll('[data-delete-room]')?.forEach((btn) => {
    btn.addEventListener('click', () => handleDeleteRoomClick(view, btn.getAttribute('data-delete-room')));
  });
}

async function handleCreateRoom(view) {
  const name = document.getElementById('ha-room-name-input')?.value.trim() || '';
  if (!name) {
    view.showToast('Nazwa pokoju jest wymagana.', 'error');
    return;
  }
  try {
    await view.apiClient.createRoom({ name });
    view.showToast('Utworzono pokój.', 'success');
    await view._refresh();
  } catch (error) {
    view.showToast(error.message || 'Błąd tworzenia pokoju.', 'error');
  }
}

async function handleRenameRoom(view, roomId, name) {
  const trimmed = name.trim();
  if (!trimmed) {
    view.showToast('Nazwa pokoju nie może być pusta.', 'error');
    await view._refresh();
    return;
  }
  try {
    await view.apiClient.updateRoom(roomId, { name: trimmed });
    view.showToast('Zaktualizowano nazwę pokoju.', 'success');
    await view._refresh();
  } catch (error) {
    view.showToast(error.message || 'Błąd aktualizacji pokoju.', 'error');
  }
}

async function handleDeleteRoomClick(view, roomId) {
  const confirmed = await confirmModal({
    title: 'Usunąć pokój?',
    message: 'Urządzenia i nadawcy przypisani do tego pokoju staną się nieprzypisani. Tej operacji nie można cofnąć.',
    confirmLabel: 'Usuń',
    cancelLabel: 'Anuluj',
  });
  if (!confirmed) return;
  try {
    await view.apiClient.deleteRoom(roomId);
    view.showToast('Usunięto pokój. Urządzenia/nadawcy przypisani do niego stają się nieprzypisani.', 'success');
    await view._refresh();
  } catch (error) {
    view.showToast(error.message || 'Błąd usuwania pokoju.', 'error');
  }
}
