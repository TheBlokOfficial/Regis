/**
 * Konfiguracja punktów końcowych API i WebSocket dla wbudowanej konsoli (Same-Origin).
 */

export function getConfig() {
  const origin = window.location.origin;
  const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsHost = `${wsProtocol}//${window.location.host}`;

  return {
    SERVER_HOST: origin,
    WS_HOST: wsHost,
    APP_TITLE: "Regis OS Control Console",
    VERSION: "0.1.0",
  };
}
