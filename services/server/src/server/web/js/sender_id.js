/**
 * Opaque identyfikator tej przeglądarki — Web UI jest, tak jak ESP32 czy
 * przyszła usługa desktopowa, zwykłym nadawcą (satelitą) z punktu widzenia
 * kernela. Generowany raz i trwale zapisywany w localStorage, żeby ten sam
 * `sender_id` przetrwał odświeżenie strony i mógł zostać zarejestrowany
 * (przypisany do pokoju/kanału) w widoku Świat.
 */
const STORAGE_KEY = 'regis_sender_id';

export function getSenderId() {
  let id = localStorage.getItem(STORAGE_KEY);
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem(STORAGE_KEY, id);
  }
  return id;
}
