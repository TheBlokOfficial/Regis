import { Icons } from '../../../icons.js';
import { confirmModal } from '../../../modal_confirm.js';
import { renderSelectMarkup, initSelect } from '../../../components/select.js';
import { getSenderId } from '../../../sender_id.js';
import { escapeHtml, escapeAttr } from '../../../utils/dom.js';

/**
 * Panel "Nadawcy" — przypisanie `sender_id -> pokój`. World nie wie nic
 * o kanale komunikacji ani o typie fizycznego urządzenia; Web UI jest
 * pierwszym, zawsze dostępnym nadawcą, więc panel od razu proponuje jej
 * własny, trwały `sender_id` do rejestracji.
 */
export function renderThisBrowserHint(view) {
  const thisId = getSenderId();
  const alreadyRegistered = view.senders.some((s) => s.sender_id === thisId);
  return `
    <p class="ha-empty-hint ha-satellite-self-hint">
      ID tej przeglądarki: <span class="ha-satellite-id">${escapeHtml(thisId)}</span>
      ${alreadyRegistered ? '<span class="badge-chip">zarejestrowana</span>' : '<button type="button" class="btn btn-sm btn-ghost" id="ha-btn-use-this-browser">Zarejestruj tę przeglądarkę</button>'}
    </p>
  `;
}

export function renderSatellitesList(view) {
  if (view.senders.length === 0) {
    return `<p class="ha-empty-hint">Brak zarejestrowanych nadawców.</p>`;
  }
  return `
    <div class="ha-list">
      ${view.senders
        .map(
          (s) => `
        <div class="ha-list-row">
          <div class="ha-satellite-info">
            <span class="ha-satellite-name">${escapeHtml(s.sender_id)}</span>
            <span class="ha-satellite-meta">
              ${s.room_name ? `<span class="ha-satellite-id">${escapeHtml(s.room_name)}</span>` : '<span class="ha-satellite-id">— brak pokoju —</span>'}
            </span>
          </div>
          <button class="btn btn-ghost-danger btn-icon-square" data-delete-satellite="${escapeAttr(s.sender_id)}" title="Usuń rejestrację" aria-label="Usuń rejestrację">${Icons.Trash2()}</button>
        </div>
      `
        )
        .join('')}
    </div>
  `;
}

export function renderSatelliteForm(view, prefillSenderId = '') {
  const formContainer = document.getElementById('ha-satellite-form');
  if (!formContainer) return;

  formContainer.innerHTML = `
    <div class="form-card">
      <div class="form-card-title">Nowa rejestracja nadawcy</div>
      <div class="form-row">
        <div class="form-group">
          <label for="ha-sat-sender-id">sender_id</label>
          <input type="text" id="ha-sat-sender-id" class="form-control" placeholder="opaque identyfikator nadawcy" value="${escapeAttr(prefillSenderId)}" />
        </div>
        <div class="form-group">
          <label>Pokój (opcjonalnie)</label>
          ${renderSelectMarkup('ha-sat-room', { placeholder: '— brak —' })}
        </div>
      </div>
      <div class="form-actions">
        <button class="btn btn-primary" id="ha-btn-save-satellite">Zarejestruj</button>
        <button class="btn btn-ghost" id="ha-btn-cancel-satellite">Anuluj</button>
      </div>
    </div>
  `;

  initSelect({
    idPrefix: 'ha-sat-room',
    options: view.rooms.map((room) => ({ value: room.id, label: room.name })),
    value: '',
    placeholder: '— brak —',
  });

  document.getElementById('ha-btn-save-satellite')?.addEventListener('click', () => handleRegisterSatellite(view));
  document.getElementById('ha-btn-cancel-satellite')?.addEventListener('click', () => {
    view.isRegisteringSender = false;
    formContainer.innerHTML = '';
  });
}

export function bindSatelliteEvents(view) {
  document.getElementById('ha-btn-new-satellite')?.addEventListener('click', () => {
    view.isRegisteringSender = true;
    renderSatelliteForm(view);
  });
  document.getElementById('ha-btn-use-this-browser')?.addEventListener('click', () => {
    view.isRegisteringSender = true;
    renderSatelliteForm(view, getSenderId());
  });
  view.container.querySelectorAll('[data-delete-satellite]')?.forEach((btn) => {
    btn.addEventListener('click', () => handleDeleteSatelliteClick(view, btn.getAttribute('data-delete-satellite')));
  });
}

async function handleRegisterSatellite(view) {
  const senderId = document.getElementById('ha-sat-sender-id')?.value.trim() || '';
  const roomId = document.getElementById('ha-sat-room-value')?.value || null;

  if (!senderId) {
    view.showToast('sender_id jest wymagany.', 'error');
    return;
  }

  try {
    await view.apiClient.registerSender({
      sender_id: senderId,
      room_id: roomId || null,
    });
    view.showToast('Zarejestrowano nadawcę.', 'success');
    view.isRegisteringSender = false;
    await view._loadAndRender();
  } catch (error) {
    view.showToast(error.message || 'Błąd rejestracji nadawcy.', 'error');
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
    await view._loadAndRender();
  } catch (error) {
    view.showToast(error.message || 'Błąd usuwania nadawcy.', 'error');
  }
}
