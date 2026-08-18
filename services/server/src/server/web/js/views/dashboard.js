/**
 * Moduł widoku głównego Dashboard — czysty panel powitalny/statusowy.
 * Zarządzanie dostawcami LLM przeniesione do zakładki Kernel (`kernel_config.js`).
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
                <span class="modal-provider-name">Kernel</span>
              </div>
              <div class="modal-provider-actions">
                <a href="#" class="btn btn-subtle btn-sm" data-nav-tab="kernel_config">Zarządzaj dostawcami LLM →</a>
              </div>
            </div>
          </div>
          <div class="modal-provider-item">
            <div class="modal-provider-main-row">
              <div class="modal-provider-title-group">
                <span class="modal-provider-name">Świat</span>
              </div>
              <div class="modal-provider-actions">
                <a href="#" class="btn btn-subtle btn-sm" data-nav-tab="extensions">Pokoje, urządzenia, nadawcy →</a>
              </div>
            </div>
          </div>
          <div class="modal-provider-item">
            <div class="modal-provider-main-row">
              <div class="modal-provider-title-group">
                <span class="modal-provider-name">Głos</span>
              </div>
              <div class="modal-provider-actions">
                <a href="#" class="btn btn-subtle btn-sm" data-nav-tab="voice_config">Status pipeline'u głosowego →</a>
              </div>
            </div>
          </div>
        </div>
      </div>
    `;
  }

  init() {
    this.container = document.getElementById('workspace-content');
    this.container?.querySelectorAll('[data-nav-tab]').forEach((link) => {
      link.addEventListener('click', (e) => {
        e.preventDefault();
        document.getElementById(`nav-${link.getAttribute('data-nav-tab').replace(/_/g, '-')}`)?.click();
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
