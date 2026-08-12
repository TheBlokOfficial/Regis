import { Icons } from '../icons.js';

/**
 * Moduł widoku głównego Dashboard (Czysty nagłówek bez zbędnych kart).
 */
export class DashboardView {
  render() {
    return `
      <div class="dashboard-grid">
        <!-- Baner Główny: Regis Agent OS Engine -->
        <div class="card card-hero">
          <div class="card-hero-header">
            <div>
              <span class="badge badge-subtle">Regis Agent OS Engine</span>
              <h2 class="hero-title">System Przeglądu</h2>
            </div>
            <div class="hero-icon-box">
              ${Icons.Activity()}
            </div>
          </div>
        </div>
      </div>
    `;
  }

  /**
   * Aktualizacja widoku (brak zbędnych kart do odświeżania na dashboardzie).
   */
  updateStatus(healthData) {
    // Wszystkie wskaźniki sieciowe znajdują się w stopce Sidebaru
  }
}
