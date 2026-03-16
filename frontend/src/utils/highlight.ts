/**
 * Search highlight rendering utility.
 *
 * RZ-W8-03: The backend returns search highlights with non-HTML sentinel
 * delimiters (\x00MARK_OPEN\x00 / \x00MARK_CLOSE\x00) instead of raw <mark>
 * tags.  This prevents stored XSS — Elasticsearch does not HTML-escape
 * surrounding document content, so raw <mark> delimiters would let injected
 * HTML in document fields pass through as live markup.
 *
 * USAGE:
 *   - Always call renderHighlight() before inserting into the DOM.
 *   - Use dangerouslySetInnerHTML={{ __html: renderHighlight(raw) }} or
 *     equivalent — the output is HTML-safe because we escape the content
 *     before replacing sentinels.
 *   - Never insert raw API highlight strings directly into innerHTML.
 */

const MARK_OPEN = "\x00MARK_OPEN\x00";
const MARK_CLOSE = "\x00MARK_CLOSE\x00";

/**
 * Convert a raw search highlight string (with sentinel delimiters) to safe HTML.
 *
 * Steps:
 * 1. HTML-escape the entire string (prevents XSS from document content)
 * 2. Replace escaped sentinels with <mark> / </mark> tags
 *
 * @param raw - Raw highlight string from the search API
 * @returns HTML-safe string with <mark> tags around matched terms
 */
export function renderHighlight(raw: string): string {
  const escaped = raw
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#x27;");

  return escaped
    .replace(new RegExp(escapeRegExp(MARK_OPEN), "g"), "<mark>")
    .replace(new RegExp(escapeRegExp(MARK_CLOSE), "g"), "</mark>");
}

/**
 * Render multiple highlight fragments joined by an ellipsis separator.
 *
 * @param fragments - Array of raw highlight strings from the API
 * @returns HTML-safe string with fragments separated by " … "
 */
export function renderHighlightFragments(fragments: string[]): string {
  return fragments.map(renderHighlight).join(" … ");
}

function escapeRegExp(str: string): string {
  return str.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
