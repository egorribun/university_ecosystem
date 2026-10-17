import type { Transform } from "node:stream"

export const CSP_NONCE_PLACEHOLDER: "__CSP_NONCE__"
export function buildNodeCspHeaders(nonce: string): Readonly<Record<string, string>>
/** Add the approved Node CSP only to HTML responses; preserve the body stream. */
export function applyNodeCspToHtmlResponse(response: Response, nonce: string): Response
export function replaceCspNoncePlaceholder(html: string, nonce: string): string
export function createCspNoncePlaceholderTransform(nonce: string): Transform
