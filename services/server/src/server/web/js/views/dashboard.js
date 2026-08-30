import { Icons } from '../icons.js';

/**
 * Moduł widoku głównego Dashboard — czysty panel powitalny/statusowy.
 * Zarządzanie konfiguracją przeniesione do zakładki Ustawienia (sekcje Agent/Świat/Klienci).
 *
 * Status węzła w `.stat-panel` (`components/stat_panel.css`, współdzielone
 * z Klientami) i karty skrótów (`.dashboard-shortcut-card`) wzorem klikalnych
 * kart Agent (`.agent-provider-card`, agent.css) — cała karta jest celem
 * kliknięcia, hover-elewacja identyczna jak w Agent.
 */
const SHORTCUTS = [
  { section: 'agent', icon: 'Activity', title: 'Agent', desc: 'Zarządzaj dostawcami LLM' },
  { section: 'world', icon: 'Puzzle', title: 'Świat', desc: 'Pokoje, urządzenia, nadawcy, prompty' },
  { section: 'voice', icon: 'Radio', title: 'Klienci', desc: 'Wake-word, VAD, status pipeline\'u głosowego' },
];

export class DashboardView {
  render() {
    return `
      <div class="dashboard-grid">
        <div class="page-header">
          <div>
            <h2 class="page-header-title">Regis</h2>
            <p class="page-header-desc">Lokalna platforma agentów AI — status węzła i skróty do konfiguracji.</p>
          </div>
          <span class="badge-muted" id="dashboard-version">v—</span>
        </div>

        <div class="stat-panel">
          <div class="stat-panel-header">
            <div>
              <div class="stat-panel-label">Status Węzła</div>
              <div class="stat-panel-title" id="dashboard-status-name">Sprawdzanie...</div>
            </div>
            <div class="stat-panel-badges">
              <span class="badge badge-status" id="dashboard-status-badge">
                <span class="status-dot-pulse"></span>...
              </span>
            </div>
          </div>
        </div>

        <div class="section-header-bar">
          <h3 class="section-title">Skróty</h3>
        </div>
        <div class="dashboard-shortcut-grid">
          ${SHORTCUTS.map(
            (s) => `
            <a href="#" class="dashboard-shortcut-card" data-nav-section="${s.section}">
              <div class="hero-icon-box dashboard-shortcut-icon">${Icons[s.icon]()}</div>
              <div class="dashboard-shortcut-body">
                <div class="dashboard-shortcut-title">${s.title}</div>
                <div class="dashboard-shortcut-desc">${s.desc}</div>
              </div>
              <span class="dashboard-shortcut-arrow">${Icons.ChevronRight()}</span>
            </a>
          `
          ).join('')}
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

    // Wersja produktu przychodzi z `/api/v1/health` (shared/version.py) — jedyne źródło
    // prawdy. Dawniej była wpisana w szablonie na sztywno i milcząco się starzała.
    const versionEl = document.getElementById('dashboard-version');
    if (versionEl && healthData?.version) versionEl.textContent = `v${healthData.version}`;

    if (healthData) {
      nameEl.textContent = healthData.app_name ? `${healthData.app_name} działa poprawnie` : 'Serwer działa poprawnie';
      badgeEl.innerHTML = `<span class="status-dot-pulse"></span>Online`;
    } else {
      nameEl.textContent = 'Brak połączenia z serwerem';
      badgeEl.innerHTML = `<span class="status-dot-pulse"></span>Offline`;
    }
  }
}
