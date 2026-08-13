import { Icons } from '../icons.js';

/**
 * Moduł widoku Ustawienia Systemowe (Informacje o wdrożeniu, parametry sieciowe i zasoby).
 */
export class SettingsView {
  render() {
    return `
      <div class="dashboard-grid">
        <!-- Minimalistyczny Nagłówek Ustawień -->
        <div class="page-header">
          <div>
            <h2 class="page-header-title">Ustawienia Systemowe</h2>
            <p class="page-header-desc">Konfiguracja wdrożenia, parametrów sieciowych oraz instancji Regis OS.</p>
          </div>
          <span class="badge-muted">v0.1.0-alpha</span>
        </div>

        <!-- Sekcja 1: Informacje o Instancji i Węźle -->
        <div class="section-header-bar">
          <h3 class="section-title">Informacje o Instancji</h3>
        </div>

        <div class="settings-section">
          <div class="settings-row-header">
            <div class="hero-icon-box hero-icon-box-sm">
              ${Icons.Server()}
            </div>
            <div>
              <div class="settings-row-title">Węzeł Centralny Regis Agent OS</div>
              <div class="settings-row-desc">Lokalna instancja produkcyjna / deweloperska</div>
            </div>
          </div>

          <div class="provider-meta-grid">
            <div class="provider-meta-item">
              <span class="provider-meta-label">Nazwa Aplikacji</span>
              <span class="provider-meta-value">Regis Agent OS</span>
            </div>
            <div class="provider-meta-item">
              <span class="provider-meta-label">Wersja Systemu</span>
              <span class="provider-meta-value">v0.1.0-alpha</span>
            </div>
            <div class="provider-meta-item">
              <span class="provider-meta-label">Środowisko Uruchomieniowe</span>
              <span class="provider-meta-value">Python 3.11+ (uv)</span>
            </div>
          </div>
        </div>

        <!-- Sekcja 2: Parametry Sieciowe & Bramka WebSocket -->
        <div class="section-header-bar">
          <h3 class="section-title">Parametry Sieciowe & WebSocket</h3>
        </div>

        <div class="settings-section">
          <div class="provider-meta-grid provider-meta-grid-flush">
            <div class="provider-meta-item">
              <span class="provider-meta-label">Bramka HTTP / REST</span>
              <span class="provider-meta-value">http://127.0.0.1:8000/</span>
            </div>
            <div class="provider-meta-item">
              <span class="provider-meta-label">Bramka WebSocket</span>
              <span class="provider-meta-value">ws://127.0.0.1:8000/ws</span>
            </div>
            <div class="provider-meta-item">
              <span class="provider-meta-label">Magistrala Zdarzeń</span>
              <span class="provider-meta-value">EventBus (asyncio)</span>
            </div>
          </div>
        </div>
      </div>
    `;
  }

  renderProvidersList() {
    // Sekcja dostawców przeniesiona do Dashboardu
  }

  initForm() {
    // Brak formularza w sekcji systemowej
  }
}
