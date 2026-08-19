/**
 * Moduł widoku głównego Dashboard — czysty panel powitalny/statusowy.
 * Zarządzanie konfiguracją przeniesione do zakładki Ustawienia (sekcje Agent/Świat/Głos).
 */
export class DashboardView {
  render() {
    return `
      <div class="dashboard-grid">
        <div class="page-header">
          <div>
            <h2 class="page-header-title">Regis Agent OS</h2>
            <p class="page-header-desc">Lokalna platforma agentów AI — status węzła i skróty do konfiguracji.</p>
          </div>
          <span class="badge-muted">v0.1.0</span>
        </div>

        <div class="dashboard-hero-top">
          <div>
            <div class="provider-section-label">Status Węzła</div>
            <div class="dashboard-hero-name" id="dashboard-status-name">Sprawdzanie...</div>
          </div>
          <div class="dashboard-hero-badges">
            <span class="badge badge-status" id="dashboard-status-badge">
              <span class="status-dot-pulse"></span>...
            </span>
          </div>
        </div>

        <div class="section-header-bar">
          <h3 class="section-title">Skróty</h3>
        </div>
        <div class="modal-provider-list">
          <div class="modal-provider-item">
            <div class="modal-provider-main-row">
              <div class="modal-provider-title-group">
                <span class="modal-provider-name">Agent</span>
              </div>
              <div class="modal-provider-actions">
                <a href="#" class="btn btn-subtle btn-sm" data-nav-section="agent">Zarządzaj dostawcami LLM →</a>
              </div>
            </div>
          </div>
          <div class="modal-provider-item">
            <div class="modal-provider-main-row">
              <div class="modal-provider-title-group">
                <span class="modal-provider-name">Świat</span>
              </div>
              <div class="modal-provider-actions">
                <a href="#" class="btn btn-subtle btn-sm" data-nav-section="world">Pokoje, urządzenia, nadawcy, prompty →</a>
              </div>
            </div>
          </div>
          <div class="modal-provider-item">
            <div class="modal-provider-main-row">
              <div class="modal-provider-title-group">
                <span class="modal-provider-name">Głos</span>
              </div>
              <div class="modal-provider-actions">
                <a href="#" class="btn btn-subtle btn-sm" data-nav-section="voice">Status pipeline'u głosowego →</a>
              </div>
            </div>
          </div>
        </div>
      </div>
    `;
  }

  init(navigateTo) {
    this.container = document.getElementById('workspace-content');
    this.container?.querySelectorAll('[data-nav-section]').forEach((link) => {
      link.addEventListener('click', (e) => {
        e.preventDefault();
        navigateTo?.('settings', { section: link.getAttribute('data-nav-section') });
      });
    });
  }

  updateStatus(healthData) {
    const nameEl = document.getElementById('dashboard-status-name');
    const badgeEl = document.getElementById('dashboard-status-badge');
    if (!nameEl || !badgeEl) return;

    if (healthData) {
      nameEl.textContent = healthData.app_name ? `${healthData.app_name} działa poprawnie` : 'Serwer działa poprawnie';
      badgeEl.innerHTML = `<span class="status-dot-pulse"></span>Online`;
    } else {
      nameEl.textContent = 'Brak połączenia z serwerem';
      badgeEl.innerHTML = `<span class="status-dot-pulse"></span>Offline`;
    }
  }
}
