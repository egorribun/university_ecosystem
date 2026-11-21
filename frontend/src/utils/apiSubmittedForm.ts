/**
 * Attributes for a form that script submits through the API client, never as a
 * native form post.
 *
 * These forms carry no hidden anti-CSRF field. The API client echoes the
 * double-submit `csrf_token` cookie in the `X-CSRF-Token` header, and the
 * backend CSRF middleware rejects unsafe requests without it (see
 * `api/client.ts`). The marker lets the DAST scan report such forms as
 * informational instead of missing a token: ZAP rules 10202 and 20012 read it
 * through `rules.csrf.ignore.attname` and `rules.csrf.ignore.attvalue`
 * (`scripts/quality/zap_runner.py`, ADR-047).
 */
export const API_SUBMITTED_FORM = { "data-csrf": "header" } as const
