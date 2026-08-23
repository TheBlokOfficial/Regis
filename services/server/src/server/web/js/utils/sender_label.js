/**
 * Jedna reguła wyświetlania klienta w całym UI: przyjazna nazwa, a gdy jej nie ma —
 * skrócony `sender_id`.
 *
 * Nazwa (`SenderProfile.display_name`, `server/world/models.py`) jest opcjonalna i
 * nadawana wyłącznie w zakładce Klienci; wszystkie pozostałe miejsca (Świat → Nadawcy,
 * picker klienta w podglądzie Kontekstu tury) tylko ją czytają. Trzymanie tego fallbacku
 * w jednym miejscu ma znaczenie, bo inaczej każda lista klientów rozstrzygałaby go po
 * swojemu — a pełny UUID (36 znaków) wygląda jak nagłówek, choć jest tylko identyfikatorem.
 */

/** Skrócony identyfikator — pełny zostaje w `title` u wywołującego. */
export function shortSenderId(senderId) {
  return `…${String(senderId).slice(-8)}`;
}

/**
 * @param {{sender_id: string, display_name?: string|null}} sender
 * @returns {string} nazwa do wyświetlenia
 */
export function senderLabel(sender) {
  const name = (sender?.display_name || '').trim();
  return name || shortSenderId(sender?.sender_id ?? '');
}
