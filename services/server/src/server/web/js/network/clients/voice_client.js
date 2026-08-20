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
}
