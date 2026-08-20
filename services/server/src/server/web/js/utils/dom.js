/**
 * Escapowanie tekstu do wstawienia w HTML — wspólne dla wszystkich widoków
 * budujących markup przez konkatenację stringów.
 */
export function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str ?? '';
  return div.innerHTML;
}

export function escapeAttr(str) {
  return escapeHtml(str).replace(/"/g, '&quot;');
}
