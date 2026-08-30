/**
 * Opaque identyfikator tej przeglądarki — Web UI jest, tak jak ESP32 czy
 * przyszła usługa desktopowa, zwykłym nadawcą (satelitą) z punktu widzenia
 * kernela. Generowany raz i trwale zapisywany w localStorage, żeby ten sam
 * `sender_id` przetrwał odświeżenie strony i mógł zostać zarejestrowany
 * (przypisany do pokoju/kanału) w widoku Świat.
 */
const STORAGE_KEY = 'regis_sender_id';

function createUuidV4() {
  // `crypto.randomUUID()` wymaga secure context, więc nie istnieje przy typowym
  // wdrożeniu LAN przez `http://adres-pi:8000`. `getRandomValues()` jest jedyną
  // metodą Web Crypto dostępną także w insecure context i daje tę samą jakość
  // losowości. Bity wersji/wariantu ustawiamy zgodnie z UUID v4 (RFC 9562).
  if (typeof crypto.randomUUID === 'function') return crypto.randomUUID();

  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = [...bytes].map((value) => value.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export function getSenderId() {
  let id = localStorage.getItem(STORAGE_KEY);
  if (!id) {
    id = createUuidV4();
    localStorage.setItem(STORAGE_KEY, id);
  }
  return id;
}
