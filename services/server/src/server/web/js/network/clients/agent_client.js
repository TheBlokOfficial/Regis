/**
 * Klient REST domeny Agent (Kernel, dawny Kernel) — health, dostawcy LLM,
 * fallback prompt domyślny (bez podłączonego świata).
 */
export class AgentClient {
  constructor(baseUrl) {
    this.baseUrl = baseUrl;
  }

  async getHealth() {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/health`);
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
      const response = await fetch(`${this.baseUrl}/api/v1/llm/providers/schemas`);
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
      const response = await fetch(`${this.baseUrl}/api/v1/llm/providers`);
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
      const response = await fetch(`${this.baseUrl}/api/v1/llm/providers/active`, {
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
      const response = await fetch(`${this.baseUrl}/api/v1/llm/providers`, {
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

  async updateLLMProvider(providerId, providerData) {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/llm/providers/${providerId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(providerData),
      });
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('[ApiClient] Błąd edycji dostawcy LLM:', error);
      throw error;
    }
  }

  /** Modele dostępne dla tego presetu wraz z formularzem parametrów każdego z nich.
   * Odkrywanie idzie przez serwer (potrzebuje klucza API, który nigdy nie opuszcza
   * serwera w jawnej postaci) — patrz `server/ai/llm/model_catalog.py`. */
  async getLLMProviderModels(providerId) {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/llm/providers/${providerId}/models`);
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('[ApiClient] Błąd pobierania listy modeli:', error);
      throw error;
    }
  }

  async deleteLLMProvider(providerId) {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/llm/providers/${providerId}`, {
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

  async getAgentDefaultPrompt() {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/agent/prompt`);
      if (!response.ok) {
        throw new Error(`HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('[ApiClient] Błąd pobierania promptu domyślnego agenta:', error);
      return null;
    }
  }

  async setAgentDefaultPrompt(content) {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/agent/prompt`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content }),
      });
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('[ApiClient] Błąd zapisu promptu domyślnego agenta:', error);
      throw error;
    }
  }
}
