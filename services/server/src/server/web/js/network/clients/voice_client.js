/**
 * Klient REST domeny Voice (`server/voice`) — status pipeline'u głosowego oraz
 * config dostawców STT/TTS (Groq/ElevenLabs).
 */
export class VoiceClient {
  constructor(baseUrl) {
    this.baseUrl = baseUrl;
  }

  async getVoiceStatus() {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/voice/status`);
      if (!response.ok) {
        throw new Error(`HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error("[ApiClient] Błąd pobierania statusu pipeline'u głosowego:", error);
      return null;
    }
  }

  async getConnectedSenders() {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/voice/connected`);
      if (!response.ok) {
        throw new Error(`HTTP Error: ${response.status}`);
      }
      const data = await response.json();
      return data?.sender_ids || [];
    } catch (error) {
      console.error('[ApiClient] Błąd pobierania podłączonych satelit:', error);
      return [];
    }
  }

  async getVoiceProvidersConfig() {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/voice/providers/config`);
      if (!response.ok) {
        throw new Error(`HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('[ApiClient] Błąd pobierania configu dostawców STT/TTS:', error);
      return null;
    }
  }

  async updateVoiceProvidersConfig(data) {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/voice/providers/config`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('[ApiClient] Błąd zapisu configu dostawców STT/TTS:', error);
      throw error;
    }
  }

  // --------------------------------------------------------------------------
  // CRUD dostawców STT (`/api/v1/voice/stt/providers*`) — mirror 1:1 pięciu
  // metod LLM w `agent_client.js`.
  // --------------------------------------------------------------------------

  async getSttProviderSchemas() {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/voice/stt/providers/schemas`);
      if (!response.ok) {
        throw new Error(`HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('[ApiClient] Błąd pobierania schematów dostawców STT:', error);
      return null;
    }
  }

  async getSttProviders() {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/voice/stt/providers`);
      if (!response.ok) {
        throw new Error(`HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('[ApiClient] Błąd pobierania listy dostawców STT:', error);
      return null;
    }
  }

  async setActiveSttProvider(providerId) {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/voice/stt/providers/active`, {
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
      console.error('[ApiClient] Błąd aktywacji dostawcy STT:', error);
      throw error;
    }
  }

  async createSttProvider(providerData) {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/voice/stt/providers`, {
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
      console.error('[ApiClient] Błąd tworzenia dostawcy STT:', error);
      throw error;
    }
  }

  async deleteSttProvider(providerId) {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/voice/stt/providers/${providerId}`, {
        method: 'DELETE',
      });
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('[ApiClient] Błąd usuwania dostawcy STT:', error);
      throw error;
    }
  }

  // --------------------------------------------------------------------------
  // CRUD dostawców TTS (`/api/v1/voice/tts/providers*`) — mirror 1:1.
  // --------------------------------------------------------------------------

  async getTtsProviderSchemas() {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/voice/tts/providers/schemas`);
      if (!response.ok) {
        throw new Error(`HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('[ApiClient] Błąd pobierania schematów dostawców TTS:', error);
      return null;
    }
  }

  async getTtsProviders() {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/voice/tts/providers`);
      if (!response.ok) {
        throw new Error(`HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('[ApiClient] Błąd pobierania listy dostawców TTS:', error);
      return null;
    }
  }

  async setActiveTtsProvider(providerId) {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/voice/tts/providers/active`, {
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
      console.error('[ApiClient] Błąd aktywacji dostawcy TTS:', error);
      throw error;
    }
  }

  async createTtsProvider(providerData) {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/voice/tts/providers`, {
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
      console.error('[ApiClient] Błąd tworzenia dostawcy TTS:', error);
      throw error;
    }
  }

  async deleteTtsProvider(providerId) {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/voice/tts/providers/${providerId}`, {
        method: 'DELETE',
      });
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('[ApiClient] Błąd usuwania dostawcy TTS:', error);
      throw error;
    }
  }
}
