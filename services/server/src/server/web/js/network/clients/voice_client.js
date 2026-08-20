/**
 * Klient REST domeny Voice (`server/voice`) — status pipeline'u głosowego,
 * wyłącznie do odczytu.
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
}
