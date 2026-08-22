/**
 * Klient REST domeny Voice (`server/voice`) — rejestr klientów, konfiguracja
 * wake-worda/VAD i CRUD dostawców STT/TTS (Groq/ElevenLabs).
 */
export class VoiceClient {
  constructor(baseUrl) {
    this.baseUrl = baseUrl;
  }

  /** Zwraca `[{sender_id, capabilities}]` — capabilities pochodzą z handshake WS i są
   * potrzebne przy rejestracji, żeby zapisać w World realne możliwości klienta zamiast
   * zgadywać jego typ po stronie UI. */
  async getConnectedSenders() {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/voice/connected`);
      if (!response.ok) {
        throw new Error(`HTTP Error: ${response.status}`);
      }
      const data = await response.json();
      return data?.senders || [];
    } catch (error) {
      console.error('[ApiClient] Błąd pobierania podłączonych satelit:', error);
      return [];
    }
  }

  async getClientsStatus() {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/voice/clients/status`);
      if (!response.ok) {
        throw new Error(`HTTP Error: ${response.status}`);
      }
      const data = await response.json();
      return data?.states || {};
    } catch (error) {
      console.error('[ApiClient] Błąd pobierania statusu klientów:', error);
      return {};
    }
  }

  /**
   * Długożyjący kanał SSE (`GET .../clients/watch`) — mirror `streamChatMessage`/
   * `watchSession` (chat_client.js): jeden globalny strumień zdarzeń wszystkich
   * satelitów (connected/disconnected/state_changed/wake_word_detected), nigdy się
   * nie kończy sam. Zwraca się (bez rzucania) gdy strumień serwera się zakończy —
   * wywołujący decyduje, czy i kiedy ponowić połączenie.
   */
  async watchClients(
    { onConnected = null, onDisconnected = null, onStateChanged = null, onWakeWordDetected = null } = {},
    signal = null
  ) {
    const response = await fetch(`${this.baseUrl}/api/v1/voice/clients/watch`, { signal });
    if (!response.ok) {
      throw new Error(`HTTP Error: ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) return;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed.startsWith('data:')) continue;
        const rawData = trimmed.replace(/^data:\s*/, '');
        try {
          const parsed = JSON.parse(rawData);
          switch (parsed.type) {
            case 'voice.satellite_connected':
              if (onConnected) onConnected(parsed.sender_id);
              break;
            case 'voice.satellite_disconnected':
              if (onDisconnected) onDisconnected(parsed.sender_id);
              break;
            case 'voice.satellite_state_changed':
              if (onStateChanged) onStateChanged(parsed.sender_id, parsed.state);
              break;
            case 'voice.satellite_wake_word_detected':
              if (onWakeWordDetected) onWakeWordDetected(parsed.sender_id, parsed.score);
              break;
            default:
              console.warn('[ApiClient] Nieznany typ ramki kanału klientów:', parsed);
          }
        } catch (e) {
          console.warn('[ApiClient] Błąd parsowania ramki kanału klientów:', rawData, e);
        }
      }
    }
  }

  async getClientConfig() {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/voice/client-config`);
      if (!response.ok) {
        throw new Error(`HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('[ApiClient] Błąd pobierania konfiguracji klienta (wake-word/VAD):', error);
      return null;
    }
  }

  async updateClientConfig(data) {
    const response = await fetch(`${this.baseUrl}/api/v1/voice/client-config`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!response.ok) {
      const errData = await response.json().catch(() => ({}));
      throw new Error(errData.detail || `HTTP Error: ${response.status}`);
    }
    return await response.json();
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
