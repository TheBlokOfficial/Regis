import { Icons } from '../../../icons.js';
import { confirmModal } from '../../../modal_confirm.js';
import { escapeHtml, escapeAttr } from '../../../utils/dom.js';

/**
 * Panel "Grupy" — multi-select nad zadeklarowaną listą urządzeń.
 */
export function renderGroupsList(view) {
  if (view.groups.length === 0) {
    return `<p class="ha-empty-hint">Brak skonfigurowanych grup.</p>`;
  }
  return `
    <div class="ha-list">
      ${view.groups
        .map(
          (g) => `
        <div class="ha-list-row">
          <div class="ha-group-info">
            <span class="ha-group-name">${escapeHtml(g.name)}</span>
            <span class="ha-group-meta">${g.device_ids.length} urządzeń</span>
          </div>
          <button class="btn btn-ghost-danger btn-icon-square" data-delete-group="${escapeAttr(g.id)}" title="Usuń grupę" aria-label="Usuń grupę">${Icons.Trash2()}</button>
        </div>
      `
        )
        .join('')}
    </div>
  `;
}

export function renderGroupForm(view) {
  const formContainer = document.getElementById('ha-group-form');
  if (!formContainer) return;

  const options = view.declaredDevices.map((entry) => ({ ref: entry.entity_id, label: entry.effective_name }));

  formContainer.innerHTML = `
    <div class="form-card">
      <div class="form-card-title">Nowa grupa</div>
      <div class="form-group">
        <label for="ha-group-name">Nazwa grupy</label>
        <input type="text" id="ha-group-name" class="form-control" placeholder="np. Łazienka" />
      </div>
      <div class="form-group">
        <label>Urządzenia</label>
        <div class="ha-group-device-options">
          ${
            options.length === 0
              ? '<p class="ha-empty-hint">Brak zadeklarowanych urządzeń do wyboru.</p>'
              : options
                  .map(
                    (opt) => `
                  <button type="button" class="ha-group-device-option" role="checkbox"
                    aria-checked="false" data-ref="${escapeAttr(opt.ref)}">
                    <span class="ha-check">${Icons.Check()}</span>
                    <span>${escapeHtml(opt.label)}</span>
                  </button>
                `
                  )
                  .join('')
          }
        </div>
      </div>
      <div class="form-actions">
        <button class="btn btn-primary" id="ha-btn-save-group">Utwórz grupę</button>
        <button class="btn btn-ghost" id="ha-btn-cancel-group">Anuluj</button>
      </div>
    </div>
  `;

  // Ostatni natywny checkbox w projekcie zastapiony wlasnym przelacznikiem — zaznaczenie
  // zyje na `aria-checked`, czyli tam, gdzie i tak musi byc dla czytnikow ekranu, zamiast
  // w rownoleglym stanie JS.
  formContainer.querySelectorAll('.ha-group-device-option').forEach((btn) => {
    btn.addEventListener('click', () => {
      const next = btn.getAttribute('aria-checked') !== 'true';
      btn.setAttribute('aria-checked', String(next));
      btn.classList.toggle('is-checked', next);
    });
  });

  document.getElementById('ha-btn-save-group')?.addEventListener('click', () => handleCreateGroup(view));
  document.getElementById('ha-btn-cancel-group')?.addEventListener('click', () => {
    view.isCreatingGroup = false;
    formContainer.innerHTML = '';
  });
}

export function bindGroupEvents(view) {
  document.getElementById('ha-btn-new-group')?.addEventListener('click', () => {
    view.isCreatingGroup = true;
    renderGroupForm(view);
  });
  view.container.querySelectorAll('[data-delete-group]')?.forEach((btn) => {
    btn.addEventListener('click', () => handleDeleteGroupClick(view, btn.getAttribute('data-delete-group')));
  });
}

async function handleCreateGroup(view) {
  const name = document.getElementById('ha-group-name')?.value.trim() || '';
  const deviceIds = Array.from(
    view.container.querySelectorAll('.ha-group-device-option[aria-checked="true"]')
  ).map((el) => el.getAttribute('data-ref'));

  if (!name) {
    view.showToast('Nazwa grupy jest wymagana.', 'error');
    return;
  }

  try {
    await view.apiClient.createHAGroup({ name, device_ids: deviceIds });
    view.showToast('Utworzono grupę.', 'success');
    view.isCreatingGroup = false;
    await view._refresh();
  } catch (error) {
    view.showToast(error.message || 'Błąd tworzenia grupy.', 'error');
  }
}

async function handleDeleteGroupClick(view, groupId) {
  const confirmed = await confirmModal({
    title: 'Usunąć grupę?',
    message: 'Zadeklarowane urządzenia zostaną zachowane — usunięte zostanie tylko ich grupowanie. Tej operacji nie można cofnąć.',
    confirmLabel: 'Usuń',
    cancelLabel: 'Anuluj',
  });
  if (!confirmed) return;
  try {
    await view.apiClient.deleteHAGroup(groupId);
    view.showToast('Usunięto grupę.', 'success');
    await view._refresh();
  } catch (error) {
    view.showToast(error.message || 'Błąd usuwania grupy.', 'error');
  }
}
