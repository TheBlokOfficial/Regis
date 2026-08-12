import { Icons } from '../icons.js';

/**
 * Moduł widoku Ustawienia Systemowe (Informacje o wdrożeniu, parametry sieciowe i zasoby).
 */
export class SettingsView {
  render() {
    return `
      <div class="dashboard-grid">
        <!-- Minimalistyczny Nagłówek Ustawień -->
        <div class="page-header" style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
          <div>
            <h2 style="font-size: 1.35rem; font-weight: 600; color: var(--text-primary); letter-spacing: -0.01em;">Ustawienia Systemowe</h2>
            <p style="font-size: 0.88rem; color: var(--text-secondary); margin-top: 4px;">Konfiguracja wdrożenia, parametrów sieciowych oraz instancji Regis OS.</p>
          </div>
          <span class="badge-muted">v0.1.0-alpha</span>
        </div>

        <!-- Sekcja 1: Informacje o Instancji i Węźle -->
        <div class="section-header-bar" style="margin-top: 4px;">
          <h3 class="section-title">Informacje o Instancji</h3>
        </div>

        <div class="card">
          <div style="display: flex; align-items: center; gap: 14px; margin-bottom: 16px;">
            <div class="hero-icon-box" style="width: 36px; height: 36px;">
              ${Icons.Server()}
            </div>
            <div>
              <div style="font-size: 0.95rem; font-weight: 500; color: var(--text-primary);">Węzeł Centralny Regis Agent OS</div>
              <div style="font-size: 0.82rem; color: var(--text-secondary);">Lokalna instancja produkcyjna / deweloperska</div>
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
        <div class="section-header-bar" style="margin-top: 12px;">
          <h3 class="section-title">Parametry Sieciowe & WebSocket</h3>
        </div>

        <div class="card">
          <div class="provider-meta-grid" style="border-top: none; margin-top: 0; padding-top: 0;">
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
