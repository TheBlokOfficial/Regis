import { Icons } from '../../../icons.js';
import { confirmModal } from '../../../modal_confirm.js';
import { escapeAttr } from '../../../utils/dom.js';

/**
 * Panel "Pokoje" — `Room` jako pełnoprawny byt World, niezależny od Home
 * Assistant Areas (te są wyłącznie podpowiedzią/importem jednorazowym).
 */
export function renderRoomsList(view) {
  if (view.rooms.length === 0) {
    return `<p class="ha-empty-hint">Brak pokoi — utwórz ręcznie albo zaimportuj z HA Areas.</p>`;
  }
  return `
    <div class="ha-list">
      ${view.rooms
        .map(
          (room) => `
        <div class="ha-list-row" data-room-id="${escapeAttr(room.id)}">
          <div class="ha-group-info">
            <input type="text" class="form-control ha-room-name" data-room-id="${escapeAttr(room.id)}" value="${escapeAttr(room.name)}" />
          </div>
          <button class="btn btn-ghost-danger btn-icon-square" data-delete-room="${escapeAttr(room.id)}" title="Usuń pokój" aria-label="Usuń pokój">${Icons.Trash2()}</button>
        </div>
      `
        )
        .join('')}
    </div>
  `;
}

export function renderRoomForm(view) {
  const formContainer = document.getElementById('ha-room-form');
  if (!formContainer) return;

  formContainer.innerHTML = `
    <div class="form-card">
      <div class="form-card-title">Nowy pokój</div>
      <div class="form-group">
        <label for="ha-room-name">Nazwa pokoju</label>
        <input type="text" id="ha-room-name" class="form-control" placeholder="np. Salon" />
      </div>
      <div class="form-actions">
        <button class="btn btn-primary" id="ha-btn-save-room">Utwórz pokój</button>
        <button class="btn btn-ghost" id="ha-btn-cancel-room">Anuluj</button>
      </div>
    </div>
  `;

  document.getElementById('ha-btn-save-room')?.addEventListener('click', () => handleCreateRoom(view));
  document.getElementById('ha-btn-cancel-room')?.addEventListener('click', () => {
    view.isCreatingRoom = false;
    formContainer.innerHTML = '';
  });
}

export function bindRoomEvents(view) {
  document.getElementById('ha-btn-new-room')?.addEventListener('click', () => {
    view.isCreatingRoom = true;
    renderRoomForm(view);
  });
  document.getElementById('ha-btn-import-rooms')?.addEventListener('click', () => handleImportRoomsFromHA(view));
  view.container.querySelectorAll('.ha-room-name')?.forEach((input) => {
    input.addEventListener('change', (e) => handleRenameRoom(view, e.target.getAttribute('data-room-id'), e.target.value));
  });
  view.container.querySelectorAll('[data-delete-room]')?.forEach((btn) => {
    btn.addEventListener('click', () => handleDeleteRoomClick(view, btn.getAttribute('data-delete-room')));
  });
}

async function handleCreateRoom(view) {
  const name = document.getElementById('ha-room-name')?.value.trim() || '';
  if (!name) {
    view.showToast('Nazwa pokoju jest wymagana.', 'error');
    return;
  }
  try {
    await view.apiClient.createRoom({ name });
    view.showToast('Utworzono pokój.', 'success');
    view.isCreatingRoom = false;
    await view._loadAndRender();
  } catch (error) {
    view.showToast(error.message || 'Błąd tworzenia pokoju.', 'error');
  }
}

async function handleRenameRoom(view, roomId, name) {
  const trimmed = name.trim();
  if (!trimmed) {
    view.showToast('Nazwa pokoju nie może być pusta.', 'error');
    await view._loadAndRender();
    return;
  }
  try {
    await view.apiClient.updateRoom(roomId, { name: trimmed });
    view.showToast('Zaktualizowano nazwę pokoju.', 'success');
    await view._loadAndRender();
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
    await view._loadAndRender();
  } catch (error) {
    view.showToast(error.message || 'Błąd usuwania pokoju.', 'error');
  }
}

async function handleImportRoomsFromHA(view) {
  try {
    const created = await view.apiClient.importRoomsFromHA();
    view.showToast(created.length > 0 ? `Zaimportowano ${created.length} pokoi z HA Areas.` : 'Brak nowych pokoi do importu.', 'success');
    await view._loadAndRender();
  } catch (error) {
    view.showToast(error.message || 'Błąd importu pokoi z HA.', 'error');
  }
}
