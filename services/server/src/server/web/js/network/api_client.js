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

  async getProviderSchemas() {
    try {
      const response = await fetch(`${this.baseUrl}/api/llm/providers/schemas`);
      if (!response.ok) {
        throw new Error(`HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('[ApiClient] Błąd pobierania schematów dostawców LLM:', error);
      return null;
    }
  }

  async getLLMProviders() {
    try {
      const response = await fetch(`${this.baseUrl}/api/llm/providers`);
      if (!response.ok) {
        throw new Error(`HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('[ApiClient] Błąd pobierania listy dostawców LLM:', error);
      return null;
    }
  }

  async setActiveLLMProvider(providerId) {
    try {
      const response = await fetch(`${this.baseUrl}/api/llm/providers/active`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider_id: providerId }),
      });
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('[ApiClient] Błąd aktywacji dostawcy LLM:', error);
      throw error;
    }
  }

  async createLLMProvider(providerData) {
    try {
      const response = await fetch(`${this.baseUrl}/api/llm/providers`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(providerData),
      });
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('[ApiClient] Błąd tworzenia dostawcy LLM:', error);
      throw error;
    }
  }

  async deleteLLMProvider(providerId) {
    try {
      const response = await fetch(`${this.baseUrl}/api/llm/providers/${providerId}`, {
        method: 'DELETE',
      });
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('[ApiClient] Błąd usuwania dostawcy LLM:', error);
      throw error;
    }
  }
}
