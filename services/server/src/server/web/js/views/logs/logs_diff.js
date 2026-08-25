import { escapeHtml } from '../../utils/dom.js';

/**
 * Porównanie dwóch kolejnych zrzutów kontekstu — jedyna rzecz w tym panelu, której
 * logi zewnętrznego proxy (np. OpenRoutera) mieć nie mogą.
 *
 * Powód jest w naszym potoku: system prompt **nie jest stałym prefiksem konwersacji**.
 * Buduje go silnik świata przy każdej turze i użytkownik może go zmienić w UI w środku
 * rozmowy. Bez porównania z poprzednim wywołaniem tej samej sesji taka zmiana jest
 * niewidoczna — dwa wpisy wyglądają identycznie, dopóki nie przeczyta się obu po 5000
 * znaków. Diff liniowy (nie znakowy) wystarcza, bo prompt jest markdownem z nagłówkami:
 * realna zmiana to prawie zawsze dopisana/usunięta linia, nie przestawione słowo.
 */

/**
 * Najdłuższy wspólny podciąg linii — tablica par indeksów [i, j] wspólnych linii.
 * Klasyczne DP; prompty mają rzędy setek linii, więc O(n*m) jest tu bez znaczenia.
 */
function commonLineIndices(oldLines, newLines) {
  const lengths = Array.from({ length: oldLines.length + 1 }, () => new Array(newLines.length + 1).fill(0));

  for (let i = oldLines.length - 1; i >= 0; i -= 1) {
    for (let j = newLines.length - 1; j >= 0; j -= 1) {
      lengths[i][j] =
        oldLines[i] === newLines[j] ? lengths[i + 1][j + 1] + 1 : Math.max(lengths[i + 1][j], lengths[i][j + 1]);
    }
  }

  const pairs = [];
  let i = 0;
  let j = 0;
  while (i < oldLines.length && j < newLines.length) {
    if (oldLines[i] === newLines[j]) {
      pairs.push([i, j]);
      i += 1;
      j += 1;
    } else if (lengths[i + 1][j] >= lengths[i][j + 1]) {
      i += 1;
    } else {
      j += 1;
    }
  }
  return pairs;
}

/**
 * Zwraca listę segmentów `{ type: 'same' | 'add' | 'del', text }` w kolejności czytania.
 */
export function diffLines(oldText, newText) {
  const oldLines = String(oldText ?? '').split('\n');
  const newLines = String(newText ?? '').split('\n');
  const pairs = commonLineIndices(oldLines, newLines);

  const segments = [];
  let i = 0;
  let j = 0;
  const emit = (type, text) => segments.push({ type, text });

  for (const [oi, nj] of pairs) {
    while (i < oi) emit('del', oldLines[i++]);
    while (j < nj) emit('add', newLines[j++]);
    emit('same', newLines[nj]);
    i = oi + 1;
    j = nj + 1;
  }
  while (i < oldLines.length) emit('del', oldLines[i++]);
  while (j < newLines.length) emit('add', newLines[j++]);

  return segments;
}

export function hasChanges(oldText, newText) {
  return String(oldText ?? '') !== String(newText ?? '');
}

/**
 * Renderuje diff, zwijając długie ciągi niezmienionych linii — w promptcie na 150 linii
 * zmiana dotyczy zwykle trzech, a reszta jest szumem zasłaniającym odpowiedź.
 */
export function renderDiffMarkup(oldText, newText, contextLines = 2) {
  const segments = diffLines(oldText, newText);
  const rows = [];

  let pendingSame = [];
  const flushSame = (isTail) => {
    if (pendingSame.length === 0) return;
    const head = pendingSame.slice(0, contextLines);
    const tail = pendingSame.slice(-contextLines);
    const hiddenCount = pendingSame.length - head.length - (pendingSame.length > contextLines ? tail.length : 0);

    const rowsFor = (lines) =>
      lines.map((line) => `<div class="diff-line diff-same">${escapeHtml(line) || '&nbsp;'}</div>`);

    if (hiddenCount <= 0) {
      rows.push(...rowsFor(pendingSame));
    } else {
      // Pierwszy blok (przed pierwszą zmianą) pokazuje tylko ogon, ostatni tylko głowę
      // — kontekst jest przydatny po stronie sąsiadującej ze zmianą, nie po obu.
      if (rows.length > 0) rows.push(...rowsFor(head));
      rows.push(`<div class="diff-line diff-skip">… ${hiddenCount} niezmienionych linii …</div>`);
      if (!isTail) rows.push(...rowsFor(tail));
    }
    pendingSame = [];
  };

  segments.forEach((segment) => {
    if (segment.type === 'same') {
      pendingSame.push(segment.text);
      return;
    }
    flushSame(false);
    const cls = segment.type === 'add' ? 'diff-add' : 'diff-del';
    const sign = segment.type === 'add' ? '+' : '−';
    rows.push(`<div class="diff-line ${cls}"><span class="diff-sign">${sign}</span>${escapeHtml(segment.text) || '&nbsp;'}</div>`);
  });
  flushSame(true);

  return `<div class="diff-block">${rows.join('')}</div>`;
}
