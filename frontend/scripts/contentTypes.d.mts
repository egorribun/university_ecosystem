/**
 * TypeScript declarations for `contentTypes.mjs`.
 *
 * Added in Wave 175 SW8 so that the vitest regression test
 * (`frontend/src/__tests__/serverProdContentTypes.test.ts`) can import
 * the map + helper with proper type-checking without converting the
 * runtime module to `.mts` (server-prod.mjs imports it at Node runtime
 * outside the TS build).
 */
export const CONTENT_TYPES: Readonly<Record<string, string>>

export function getContentType(filePath: string): string
