/**
 * Diagnostic final-HTML root inventory, not budget or artifact admission.
 *
 * inspectFinalHtml(clientDir) will read only _shell.html, index.html and bounded
 * local script roots. It must never execute JavaScript or load network resources.
 * Limits for the future implementation: 1 MiB per HTML document, 4 MiB per
 * unique script asset, 16 MiB total unique asset bytes, 128 roots per document,
 * 100,000 AST nodes per script, 256 import occurrences per script, and 32,767
 * serialized JSON bytes. Missing, unsafe or excessive file input returns null.
 * Unknown HTML/JavaScript forms remain bounded counters with complete: false.
 * Imports are described, not recursively followed; no execution closure is proved.
 * The caller owns checkout/run provenance; this API cannot establish it.
 *
 * This tests-first scaffold deliberately rejects every input. No production
 * capture or budget exception is enabled by importing it.
 */
export function inspectFinalHtml() {
  return null
}
