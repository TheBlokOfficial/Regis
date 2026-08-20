import { Icons } from '../../../icons.js';
import { confirmModal } from '../../../modal_confirm.js';
import { renderSelectMarkup, initSelect } from '../../../components/select.js';
import { escapeHtml, escapeAttr } from '../../../utils/dom.js';

/**
 * Panel "Nadawcy" — lista już zarejestrowanych `sender_id`, z możliwością
 * przypisania/zmiany pokoju per wiersz i usunięcia. **Świadomie bez tworzenia
 * nowych rejestracji tutaj** — to żyło tu wcześniej (formularz "+ Nowa
 * rejestracja", w tym skrót dla ID tej przeglądarki), ale rejestracja
 * (w tym pierwszy kontakt z podłączoną, jeszcze nieznaną satelitą) jest
 * koncepcyjnie i pod maską domeną `voice`, nie `world` — przeniesione do
 * zakładki Głos (`voice_config.js`, sekcja Satelity). Świat dostaje z powrotem
 * jedną odpowiedzialność: zarządzanie już zatwierdzonymi encjami.
 */
export function renderSatellitesList(view) {
  if (view.senders.length === 0) {
    return `<p class="ha-empty-hint">Brak zarejestrowanych nadawców — zarejestruj w zakładce Głos.</p>`;
  }
  return `
    <div class="ha-list">
      ${view.senders
        .map(
          (s) => `
        <div class="ha-list-row">
          <span class="ha-satellite-name">${escapeHtml(s.sender_id)}</span>
          ${renderSelectMarkup(`ha-sender-room-${s.sender_id}`, { placeholder: '— brak pokoju —', className: 'select--compact ha-sender-room-select' })}
          <button class="btn btn-ghost-danger btn-icon-square" data-delete-satellite="${escapeAttr(s.sender_id)}" title="Usuń rejestrację" aria-label="Usuń rejestrację">${Icons.Trash2()}</button>
        </div>
      `
        )
        .join('')}
    </div>
  `;
}

/** Montuje custom-select picker pokoju dla każdego zarejestrowanego nadawcy — wywoływane po każdym `_render()`. */
export function initSatelliteRoomSelects(view) {
  const roomOptions = view.rooms.map((room) => ({ value: room.id, label: room.name }));
  view.senders.forEach((s) => {
    initSelect({
      idPrefix: `ha-sender-room-${s.sender_id}`,
      options: roomOptions,
      value: s.room_id || '',
      placeholder: '— brak pokoju —',
      onChange: (value) => handleAssignSenderRoom(view, s.sender_id, value),
    });
  });
}

export function bindSatelliteEvents(view) {
  view.container.querySelectorAll('[data-delete-satellite]')?.forEach((btn) => {
    btn.addEventListener('click', () => handleDeleteSatelliteClick(view, btn.getAttribute('data-delete-satellite')));
  });
}

/** `POST /senders` jest upsertem (`WorldEngine.register_sender`: "rejestruje lub nadpisuje") —
 * to samo wywołanie tworzące nowego nadawcę służy tu do zmiany pokoju istniejącego. */
async function handleAssignSenderRoom(view, senderId, roomId) {
  try {
    await view.apiClient.registerSender({ sender_id: senderId, room_id: roomId || null });
    view.showToast('Zaktualizowano pokój.', 'success');
    await view._refresh();
  } catch (error) {
    view.showToast(error.message || 'Błąd aktualizacji pokoju.', 'error');
  }
}

async function handleDeleteSatelliteClick(view, senderId) {
  const confirmed = await confirmModal({
    title: 'Usunąć rejestrację nadawcy?',
    message: 'Ta operacja jest nieodwracalna.',
    confirmLabel: 'Usuń',
    cancelLabel: 'Anuluj',
  });
  if (!confirmed) return;
  try {
    await view.apiClient.deleteSender(senderId);
    view.showToast('Usunięto rejestrację nadawcy.', 'success');
    await view._refresh();
  } catch (error) {
    view.showToast(error.message || 'Błąd usuwania nadawcy.', 'error');
  }
}
