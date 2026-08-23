import { renderSelectMarkup, initSelect } from '../../../components/select.js';
import { escapeAttr, escapeHtml } from '../../../utils/dom.js';
import { senderLabel } from '../../../utils/sender_label.js';

/**
 * Panel "Nadawcy" — lista zarejestrowanych klientów z pickerem pokoju per wiersz.
 *
 * **Wyłącznie odczyt + przypisanie pokoju.** Świat nie tworzy rejestracji ani ich
 * nie usuwa: jedno i drugie to cykl życia klienta, czyli domena zakładki Klienci
 * (`views/voice_config.js`). Świat zna tylko encje już zatwierdzone i to, gdzie
 * stoją.
 *
 * Historia obu przenosin: najpierw wyjechało stąd *tworzenie* rejestracji
 * (formularz "+ Nowa rejestracja"), bo pierwszy kontakt z nieznanym nadawcą jest
 * pod maską domeną `voice`. Kasowanie zostało wtedy przeoczone i wisiało tu
 * dalej — czyli operacja odwrotna do rejestracji żyła w innej zakładce niż sama
 * rejestracja. Naprawione: obie są w Klientach.
 */
export function renderSatellitesList(view) {
  if (view.senders.length === 0) {
    return `<p class="ha-empty-hint">Brak zarejestrowanych klientów — zarejestruj w zakładce Klienci.</p>`;
  }
  return `
    <div class="ha-list">
      ${view.senders
        .map(
          (s) => `
        <div class="ha-list-row">
          <span class="ha-satellite-name" title="${escapeAttr(s.sender_id)}">${escapeHtml(senderLabel(s))}</span>
          ${renderSelectMarkup(`ha-sender-room-${s.sender_id}`, { placeholder: '— brak pokoju —', className: 'select--compact ha-sender-room-select' })}
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

/** `POST /senders` jest upsertem (`WorldEngine.register_sender`: "rejestruje lub nadpisuje") —
 * to samo wywołanie tworzące nowego nadawcę służy tu do zmiany pokoju istniejącego.
 * Pominięte `capabilities` backend zachowuje (patrz `world/routes.py::register_sender`),
 * więc zmiana pokoju nie kasuje możliwości klienta. */
async function handleAssignSenderRoom(view, senderId, roomId) {
  try {
    await view.apiClient.registerSender({ sender_id: senderId, room_id: roomId || null });
    view.showToast('Zaktualizowano pokój.', 'success');
    await view._refresh();
  } catch (error) {
    view.showToast(error.message || 'Błąd aktualizacji pokoju.', 'error');
  }
}
