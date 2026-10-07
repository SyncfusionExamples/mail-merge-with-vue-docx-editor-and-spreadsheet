// Word-level diff helper, ported from the react-docx-editor-with-ai
// sample's `highlightDifferences` (AIPopup.jsx). Used by the AI
// rewrite dialog to render the "From" / "To" panes — words that
// appeared in the source are struck through in red, words that
// appear only in the rewrite are highlighted in green.
//
// Algorithm: classic longest-common-subsequence (LCS) over the
// whitespace-split token lists, with a Levenshtein-distance match
// (≤1) for fuzzy equality so a 1-char typo still counts as the same
// word. Output is plain HTML with <span class="e-original-word"> and
// <span class="e-improved-word"> wrappers around changed words.

function levenshtein(a, b) {
  if (!a || !b) return Math.max((a || '').length, (b || '').length);
  const dp = Array.from({ length: a.length + 1 }, () =>
    new Array(b.length + 1).fill(0),
  );
  for (let i = 0; i <= a.length; i++) dp[i][0] = i;
  for (let j = 0; j <= b.length; j++) dp[0][j] = j;
  for (let i = 1; i <= a.length; i++) {
    for (let j = 1; j <= b.length; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      dp[i][j] = Math.min(
        dp[i - 1][j] + 1,
        dp[i][j - 1] + 1,
        dp[i - 1][j - 1] + cost,
      );
    }
  }
  return dp[a.length][b.length];
}

function isSimilar(a, b, threshold = 1) {
  if (!a || !b) return false;
  return levenshtein(a, b) <= threshold;
}

/**
 * Compute HTML for two word-aligned views: the original with deleted
 * words highlighted, and the modified with added words highlighted.
 *
 * @param {string} original — the source text (plain or HTML; HTML is
 *   stripped to plain text before diffing).
 * @param {string} modified — the rewritten text.
 * @returns {{ highlightedOriginal: string, highlightedModified: string }}
 */
export function highlightDifferences(original, modified) {
  const stripHtml = (s) =>
    String(s || '')
      .replace(/<[^>]+>/g, ' ')
      .replace(/&nbsp;/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
  const oWords = stripHtml(original).split(' ').filter(Boolean);
  const mWords = stripHtml(modified).split(' ').filter(Boolean);

  // Build LCS table (with fuzzy match) — `lcs[i][j]` is the LCS length
  // for oWords[0..i) and mWords[0..j).
  const lcs = Array.from({ length: oWords.length + 1 }, () =>
    new Array(mWords.length + 1).fill(0),
  );
  for (let i = 0; i < oWords.length; i++) {
    for (let j = 0; j < mWords.length; j++) {
      if (oWords[i] === mWords[j] || isSimilar(oWords[i], mWords[j])) {
        lcs[i + 1][j + 1] = lcs[i][j] + 1;
      } else {
        lcs[i + 1][j + 1] = Math.max(lcs[i + 1][j], lcs[i][j + 1]);
      }
    }
  }

  // Walk the table back to find which (i, j) pairs are unchanged.
  const unchanged = new Set();
  let x = oWords.length;
  let y = mWords.length;
  while (x > 0 && y > 0) {
    if (
      oWords[x - 1] === mWords[y - 1] ||
      isSimilar(oWords[x - 1], mWords[y - 1])
    ) {
      unchanged.add(`${x - 1}|${y - 1}`);
      x--;
      y--;
    } else if (lcs[x - 1][y] >= lcs[x][y - 1]) {
      x--;
    } else {
      y--;
    }
  }

  // Escape words so special chars don't break the HTML.
  const esc = (s) =>
    String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');

  const highlightedOriginal = oWords
    .map((w, i) =>
      [...unchanged].some((k) => k.startsWith(`${i}|`))
        ? esc(w)
        : `<span class="e-original-word">${esc(w)}</span>`,
    )
    .join(' ');

  const highlightedModified = mWords
    .map((w, j) =>
      [...unchanged].some((k) => k.endsWith(`|${j}`))
        ? esc(w)
        : `<span class="e-improved-word">${esc(w)}</span>`,
    )
    .join(' ');

  return { highlightedOriginal, highlightedModified };
}

/**
 * Convert a fragment of HTML to plain text with paragraph breaks
 * preserved (matches the reference sample's `htmlToPlain`).
 */
export function htmlToPlain(html) {
  const div = document.createElement('div');
  div.innerHTML = String(html || '')
    .replace(/<\/(p|div|li|h[1-6]|tr)>/gi, '\n')
    .replace(/<br\s*\/?>/gi, '\n');
  const text = div.textContent || '';
  return String(text)
    .replace(/[ \t]+/g, ' ')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}
