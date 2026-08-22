/**
 * Rozbłysk wyniku akcji bezpośrednio na przycisku (kolor + ikona na chwilę),
 * zamiast osobnej plakietki/toastu obok — wydzielone z pierwszego użycia w
 * `views/extensions/ha/config_panel.js::handleTestConnection`. Przycisk
 * PRZEJMUJE znaczenie wyniku, potem wraca do stanu spoczynku.
 *
 * Rozmiar przycisku (SZEROKOŚĆ **i WYSOKOŚĆ**) jest zamrożony PRZED zmianą
 * zawartości: ikona SVG (20px) jest wyższa niż linia tekstu przycisku (~17px
 * przy `font-size: 0.9rem`), więc sama zamiana treści na checkmark rozpychała
 * przycisk w pionie — kontener ma trzymać stały rozmiar i pozycję niezależnie
 * od tego, co się w nim chwilowo znajduje (zasada "stabilność layoutu w UI").
 *
 * `disabled` zostaje `true` przez cały czas rozbłysku (realnie nieklikalny, nie
 * tylko przygaszony wizualnie) — `.btn-flash-*:disabled` w buttons.css nadpisuje
 * domyślne przygaszenie `:disabled`, żeby kolor wyniku zostawał żywy mimo blokady.
 */
export function flashButtonResult(btn, ok, { successHtml, errorHtml, durationMs = 2000 } = {}) {
  const originalHtml = btn.innerHTML;
  lockButtonForAction(btn);
  btn.classList.add(ok ? 'btn-flash-success' : 'btn-flash-error');
  btn.innerHTML = ok ? successHtml : errorHtml;

  setTimeout(() => {
    btn.classList.remove('btn-flash-success', 'btn-flash-error');
    btn.innerHTML = originalHtml;
    btn.disabled = false;
    unlockButtonSize(btn);
  }, durationMs);
}

/** Zamraża rozmiar (szerokość + wysokość) i blokuje przycisk PRZED wywołaniem async
 * akcji — idempotentne, więc `flashButtonResult` może to wołać ponownie po
 * wcześniejszym `lockButtonForAction` bez utrwalania rozmiaru już zamrożonego
 * przycisku (druga blokada mierzy tę samą, wciąż oryginalną geometrię). */
export function lockButtonForAction(btn) {
  const rect = btn.getBoundingClientRect();
  btn.style.width = `${rect.width}px`;
  btn.style.height = `${rect.height}px`;
  btn.disabled = true;
}

function unlockButtonSize(btn) {
  btn.style.width = '';
  btn.style.height = '';
}
