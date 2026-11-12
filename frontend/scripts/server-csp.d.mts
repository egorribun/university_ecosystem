import type { Transform } from "node:stream"

export const CSP_NONCE_PLACEHOLDER: "__CSP_NONCE__"
export interface NodeCspOptions {
  /** Defaults to true. Set false only for loopback plain-HTTP requests. */
  upgradeInsecureRequests?: boolean
}
export function shouldUpgradeInsecureRequests(request?: {
  host?: unknown
  forwardedProto?: unknown
}): boolean
export function buildNodeCspHeaders(
  nonce: string,
  options?: NodeCspOptions
): Readonly<Record<string, string>>
/** Add the approved Node CSP only to HTML responses; preserve the body stream. */
export function applyNodeCspToHtmlResponse(
  response: Response,
  nonce: string,
  options?: NodeCspOptions
): Response
export function replaceCspNoncePlaceholder(html: string, nonce: string): string
export function createCspNoncePlaceholderTransform(nonce: string): Transform
