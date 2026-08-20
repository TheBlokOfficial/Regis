import { Icons } from '../../../icons.js';
import { escapeAttr } from '../../../utils/dom.js';

/**
 * Panel "Konfiguracja" — singleton Home Assistant (`base_url`/`access_token`).
 * Operuje na współdzielonym stanie koordynatora (`view` = `HomeAssistantExtensionView`).
 */
export function renderConfigForm(view) {
  const isConfigured = Boolean(view.config.base_url && view.config.access_token);
  const tokenPlaceholder = isConfigured ? truncateMaskedToken(view.config.access_token) : 'eyJhbGciOi...';
  return `
    <div class="form-card ha-config-form-card">
      <div class="form-row">
        <div class="form-group">
          <label for="ha-input-base-url">Adres serwera</label>
          <input type="text" id="ha-input-base-url" class="form-control" value="${escapeAttr(view.config.base_url)}" placeholder="http://homeassistant.local:8123" />
        </div>
        <div class="form-group">
          <label for="ha-input-token">Długoterminowy token dostępu</label>
          <input type="password" id="ha-input-token" class="form-control" placeholder="${escapeAttr(tokenPlaceholder)}" />
        </div>
        <button class="btn btn-ghost btn-icon-square ha-config-submit" id="ha-btn-save-config" title="Aktualizuj połączenie" aria-label="Aktualizuj połączenie">${Icons.RefreshCw()}</button>
      </div>
    </div>
  `;
}

export function bindConfigEvents(view) {
  document.getElementById('ha-btn-save-config')?.addEventListener('click', () => handleSaveConfig(view));
}

async function handleSaveConfig(view) {
  const baseUrl = document.getElementById('ha-input-base-url')?.value.trim() || '';
  const token = document.getElementById('ha-input-token')?.value || '';

  if (!baseUrl) {
    view.showToast('Adres serwera jest wymagany.', 'error');
    return;
  }

  try {
    const payload = { base_url: baseUrl, access_token: token || view.config.access_token };
    await view.apiClient.updateHAConfig(payload);
    view.showToast('Zapisano konfigurację.', 'success');
    await view._loadAndRender();
  } catch (error) {
    view.showToast(error.message || 'Błąd zapisu konfiguracji.', 'error');
  }
}

function truncateMaskedToken(masked) {
  // Backend maskuje token do jego pełnej długości kropkami (z ostatnimi 4 znakami
  // widocznymi) — dla długich tokenów (JWT) to ściana kropek wychodząca poza kartę.
  // Wizualnie ograniczamy do stałej liczby kropek, sens (zamaskowane + końcówka) zostaje.
  const MAX_DOTS = 24;
  const visibleSuffix = masked.replace(/^•+/, '');
  const dotsCount = masked.length - visibleSuffix.length;
  if (dotsCount <= MAX_DOTS) return masked;
  return `${'•'.repeat(MAX_DOTS)}${visibleSuffix}`;
}
