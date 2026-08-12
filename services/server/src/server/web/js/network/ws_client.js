import { getConfig } from '../config.js';

/**
 * Klient WebSocket do połączenia strumieniowego z serwerem Regis OS.
 */
export class WebSocketClient {
  constructor(url = `${getConfig().WS_HOST}/ws/satellite/web-console-01`) {
    this.url = url;
    this.ws = null;
  }

  connect() {
    console.log(`[WebSocketClient] Łączenie z ${this.url}...`);
    this.ws = new WebSocket(this.url);

    this.ws.onopen = () => {
      console.log('[WebSocketClient] Połączenie aktywne.');
    };

    this.ws.onmessage = (event) => {
      console.log('[WebSocketClient] Odebrano wiadomość:', event.data);
    };

    this.ws.onerror = (error) => {
      console.error('[WebSocketClient] Błąd WebSocket:', error);
    };

    this.ws.onclose = () => {
      console.log('[WebSocketClient] Połączenie zamknięte.');
    };
  }
}
