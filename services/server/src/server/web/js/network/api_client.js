import { getConfig } from '../config.js';

/**
 * Klient REST API do komunikacji z serwerem Regis OS (Same-Origin).
 */
export class ApiClient {
  constructor(baseUrl = getConfig().SERVER_HOST) {
    this.baseUrl = baseUrl;
  }

  async getHealth() {
    try {
      const response = await fetch(`${this.baseUrl}/api/health`);
      if (!response.ok) {
        throw new Error(`HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('[ApiClient] Błąd sprawdzania statusu serwera:', error);
      return null;
    }
  }
}
