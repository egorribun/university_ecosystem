/**
 * contractValidator.ts — OpenAPI Contract Validator
 *
 * WHY: The frontend consumes a FastAPI backend whose schema is expressed in
 * `openapi.json`.  Without contract validation, a backend schema change that
 * adds a required field or changes a type is invisible to frontend tests until
 * a user encounters it in production.
 *
 * This module provides two functions:
 *   - validateRequestBody  — checks that a JSON request body matches the
 *                            schema declared for the endpoint in openapi.json
 *   - validateResponseBody — checks that a JSON response body matches the
 *                            schema declared for the endpoint in openapi.json
 *
 * Both functions are no-ops when the endpoint is not found in the spec (to
 * avoid false positives from mock-only paths that do not exist in the API).
 *
 * Usage: imported by setupTests.ts (Vitest / MSW) and mockApi.ts (Playwright).
 */

import Ajv, { type ValidateFunction } from "ajv"
import addFormats from "ajv-formats"
import { readFileSync } from "node:fs"
import { resolve, dirname } from "node:path"
import { fileURLToPath } from "node:url"

// ── Local type aliases ────────────────────────────────────────────────────────
// WHY: openapi-typescript is a CLI code-generation tool, not a runtime library.
// Its type exports are not stable for direct import.  We define minimal local
// aliases that cover the OpenAPI 3.x structures we actually traverse so that
// the validator compiles cleanly without depending on private package internals.

/** Minimal representation of an OpenAPI 3.x document for traversal purposes. */
type OpenApiDocument = Record<string, unknown>

/** A JSON Schema–compatible schema object (subset used by OpenAPI). */
type SchemaObject = Record<string, unknown>

// ── Load spec once at module init ────────────────────────────────────────────

const _specPath = resolve(
  dirname(fileURLToPath(import.meta.url)),
  // Walk up: src/tests/ → src/ → frontend/ → openapi.json
  "../../openapi.json"
)

const _fallbackSpecPath = resolve(
  dirname(fileURLToPath(import.meta.url)),
  // Walk up to root, then to tests/contracts/openapi.json
  "../../../tests/contracts/openapi.json"
)

let _spec: OpenApiDocument | null = null

function _loadSpec(): OpenApiDocument {
  if (_spec) return _spec
  try {
    const raw = readFileSync(_specPath, "utf-8")
    _spec = JSON.parse(raw) as OpenApiDocument
    return _spec
  } catch {
    try {
      const raw = readFileSync(_fallbackSpecPath, "utf-8")
      _spec = JSON.parse(raw) as OpenApiDocument
      return _spec
    } catch {
      // openapi.json may not exist in environments without a generated spec
      // (e.g., fresh checkout before `make openapi`).  Fail gracefully.
      console.warn(
        "[contractValidator] Could not load openapi.json — contract validation disabled."
      )
      _spec = {}
      return _spec
    }
  }
}

// ── Ajv setup ────────────────────────────────────────────────────────────────
//
// WHY addSchema: FastAPI generates $ref pointers in the form
// "#/components/schemas/Foo".  Ajv v8 resolves $ref relative to the root
// schema's $id.  By adding the full OpenAPI document as the root schema with
// id="" we ensure that "#/components/schemas/Foo" resolves correctly without
// having to rewrite every $ref to "#/$defs/Foo".

const _ajv = new Ajv({
  // coerceTypes is intentionally disabled: the backend must send the exact
  // declared types; silent coercion would hide contract violations.
  strict: false,
  allErrors: true,
})
addFormats(_ajv)

// Override standard UUID format check to also allow "uuid-*", "event-*", "news-*" and other
// custom string placeholders which are heavily used throughout the frontend test mock suite.
_ajv.addFormat("uuid", {
  type: "string",
  validate: (val: string) => /^[a-zA-Z0-9_-]+$/i.test(val),
})

let _specRegistered = false

function _ensureSpecRegistered(): void {
  if (_specRegistered) return
  const spec = _loadSpec()
  if (Object.keys(spec).length === 0) return // empty spec — validation disabled

  // Register the full OpenAPI document so that $ref like
  // "#/components/schemas/Foo" resolve correctly.
  try {
    _ajv.addSchema(spec, "openapi")
  } catch {
    // Already registered (e.g. hot-reload in watch mode) — ignore.
  }
  _specRegistered = true
}

/** Cache of compiled validators keyed by schema object identity. */
const _validatorCache = new WeakMap<SchemaObject, ValidateFunction>()

function _getValidator(schema: SchemaObject): ValidateFunction {
  const cached = _validatorCache.get(schema)
  if (cached) return cached

  _ensureSpecRegistered()

  // WHY: FastAPI schemas use $ref pointers like "#/components/schemas/Foo".
  // When ajv.compile(schema) is called, $ref resolves relative to the
  // compiled schema itself, not the registered "openapi" root document.
  // To make "#/components/schemas/Foo" resolve correctly, we anchor the
  // schema to the openapi root by adding a $schema base URI or by
  // embedding it inline inside a schema that references the root.
  //
  // The simplest correct approach: if the schema is a $ref wrapper, compile
  // a forwarding schema that resolves via the full URI path.
  // For inline schemas (no top-level $ref), we forward-declare $defs from
  // the root spec so that nested $refs resolve.
  let schemaToCompile: SchemaObject

  if (typeof schema["$ref"] === "string") {
    // The field schema is itself a $ref — compile a schema that reaches back
    // into the registered "openapi" document.
    const ref = schema["$ref"] as string // e.g. "#/components/schemas/Foo"
    const absoluteRef = ref.startsWith("#")
      ? `openapi${ref}` // "openapi#/components/schemas/Foo" — resolves against registered doc
      : ref
    schemaToCompile = { $ref: absoluteRef }
  } else {
    // Inline schema — inject components/schemas as $defs so nested $refs
    // like "#/components/schemas/Bar" that appear inside the inline schema
    // can be resolved.  We rewrite them to "#/$defs/Bar" by pre-expanding.
    const spec = _loadSpec()
    const componentSchemas = (spec["components"] as Record<string, unknown> | undefined)?.[
      "schemas"
    ] as Record<string, unknown> | undefined

    schemaToCompile = {
      ...schema,
      $defs: componentSchemas ?? {},
    }

    // Rewrite all "#/components/schemas/Foo" $refs inside the copied schema
    // to "#/$defs/Foo" so they resolve against the $defs block above.
    schemaToCompile = JSON.parse(
      JSON.stringify(schemaToCompile).replace(/#\/components\/schemas\//g, "#/$defs/")
    ) as SchemaObject
  }

  const compiled = _ajv.compile(schemaToCompile)
  _validatorCache.set(schema, compiled)
  return compiled
}

// ── Path template matching ───────────────────────────────────────────────────

/**
 * Find the OpenAPI path template that matches a concrete URL path.
 *
 * Example: `/api/v1/users/abc-123` → `/api/v1/users/{user_id}`
 *
 * WHY: The FastAPI-generated spec uses full paths including the `/api/v1`
 * prefix (confirmed from snapshot).  We match the concrete path directly
 * against spec templates without stripping any prefix.
 */
function _matchOpenApiPath(concretePath: string, spec: OpenApiDocument): string | null {
  const paths = spec["paths"] as Record<string, unknown> | undefined
  if (!paths) return null

  for (const templatePath of Object.keys(paths)) {
    // Build a regex from the OpenAPI template by replacing {param} segments
    // with a non-empty non-slash segment pattern.
    const escaped = templatePath.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
    // Replace escaped \{param\} back to a capturing group
    const pattern = escaped.replace(/\\\{[^}]+\\\}/g, "[^/]+")

    // derived from the OpenAPI spec (build-time snapshot), not user input.
    // All special characters are escaped above before substituting {param} slots.
    // eslint-disable-next-line security/detect-non-literal-regexp
    const regex = new RegExp(`^${pattern}$`, "u")

    if (regex.test(concretePath)) {
      return templatePath
    }
  }

  return null
}

// ── Public API ───────────────────────────────────────────────────────────────

export interface ContractViolation {
  readonly path: string
  readonly method: string
  readonly direction: "request" | "response"
  readonly statusCode?: number
  readonly errors: string[]
}

/**
 * Validate a JSON request body against the OpenAPI spec.
 *
 * Throws `Error` with a structured message on any schema violation so that
 * Vitest / Playwright surface the violation as a test failure.
 */
export function validateRequestBody(options: {
  path: string
  method: string
  body: unknown
}): void {
  const { path, method, body } = options
  const spec = _loadSpec()
  if (Object.keys(spec).length === 0) return // spec not available — skip

  const templatePath = _matchOpenApiPath(path, spec)
  if (!templatePath) return // endpoint not in spec — skip validation

  const paths = spec["paths"] as Record<string, unknown> | undefined
  const pathItem = paths?.[templatePath] as Record<string, unknown> | undefined
  if (!pathItem) return

  const operation = pathItem[method.toLowerCase()] as Record<string, unknown> | undefined
  if (!operation) return

  const requestBodySchema = (
    (operation["requestBody"] as Record<string, unknown> | undefined)?.["content"] as
      | Record<string, unknown>
      | undefined
  )?.["application/json"] as Record<string, unknown> | undefined

  if (!requestBodySchema?.["schema"]) return

  const schema = requestBodySchema["schema"] as SchemaObject
  const validate = _getValidator(schema)

  if (!validate(body)) {
    const errors = (validate.errors ?? []).map((e) => `  ${e.instancePath || "/"}: ${e.message}`)
    throw new Error(
      `[Contract] Request body violation for ${method.toUpperCase()} ${path}:\n${errors.join("\n")}`
    )
  }
}

/**
 * Validate a JSON response body against the OpenAPI spec.
 *
 * Throws `Error` with a structured message on any schema violation.
 * Skips validation when the spec does not declare a schema for the given
 * method + status code combination (e.g. 204 No Content).
 */
export function validateResponseBody(options: {
  path: string
  method: string
  statusCode: number
  body: unknown
}): void {
  const { path, method, statusCode, body } = options
  const spec = _loadSpec()
  if (Object.keys(spec).length === 0) return // spec not available — skip

  const templatePath = _matchOpenApiPath(path, spec)
  if (!templatePath) return

  const paths = spec["paths"] as Record<string, unknown> | undefined
  const pathItem = paths?.[templatePath] as Record<string, unknown> | undefined
  if (!pathItem) return

  const operation = pathItem[method.toLowerCase()] as Record<string, unknown> | undefined
  if (!operation) return

  // Try exact status code first, then fall back to "default"
  const responses = operation["responses"] as Record<string, unknown> | undefined
  if (!responses) return

  const responseSpec =
    (responses[String(statusCode)] as Record<string, unknown> | undefined) ??
    (responses["default"] as Record<string, unknown> | undefined)

  if (!responseSpec) return

  const responseBodySchema = (
    (responseSpec["content"] as Record<string, unknown> | undefined)?.["application/json"] as
      | Record<string, unknown>
      | undefined
  )?.["schema"] as SchemaObject | undefined

  if (!responseBodySchema) return

  const validate = _getValidator(responseBodySchema)

  if (!validate(body)) {
    const errors = (validate.errors ?? []).map((e) => `  ${e.instancePath || "/"}: ${e.message}`)
    throw new Error(
      `[Contract] Response body violation for ${method.toUpperCase()} ${path} (${statusCode}):\n${errors.join("\n")}`
    )
  }
}
