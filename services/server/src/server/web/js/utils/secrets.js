/**
 * Referencje do sekretów po stronie Web UI — lustro `packages/shared/src/shared/secrets.py`.
 *
 * Wartość pola sekretnego (klucz API dostawcy, token Home Assistant) może być literałem
 * albo wskazaniem `env:NAZWA`. Serwer **nie maskuje** referencji w odpowiedzi REST, bo
 * to nazwa zmiennej środowiskowej, a nie sekret — a UI musi to rozróżnienie pokazać,
 * inaczej użytkownik nie ma jak stwierdzić, skąd dana instancja bierze klucz.
 *
 * Rozpoznanie żyje tutaj, a nie w komponentach: mają je już dwa niezależne miejsca
 * (presety dostawców AI i konfiguracja Home Assistant), a to dwie różne domeny UI,
 * które nie powinny sięgać do siebie nawzajem.
 */

export const SECRET_REF_PREFIX = 'env:';

/** Czy wartość jest referencją `env:NAZWA` (a nie literalnym sekretem). */
export function isSecretRef(value) {
  return typeof value === 'string' && value.trim().startsWith(SECRET_REF_PREFIX);
}
