import { URL } from "node:url"
import type { APIRequestContext, APIResponse } from "@playwright/test"
import * as v from "valibot"

const INVALID_IDENTITY = "Invalid owned reset account identity"
const UNAVAILABLE_IDENTITY = "Owned reset account identity unavailable"
const MAX_RECEIPT_BYTES = 65_536
const CanonicalUuid = v.pipe(
  v.string(),
  v.length(36),
  v.regex(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/u)
)
const OwnedProject = v.union([v.literal("desktop"), v.literal("mobile")])
const OwnedAccount = v.object({ email: v.string(), fullName: v.string() })
const StudentReceipt = v.object({
  id: CanonicalUuid,
  email: v.string(),
  full_name: v.string(),
  role: v.literal("student"),
})
const StudentPage = v.pipe(v.array(StudentReceipt), v.length(1))

export type OwnedResetAccount = v.InferOutput<typeof OwnedAccount>

export function createOwnedResetAccount(project: unknown, nonce: unknown): OwnedResetAccount {
  const parsedProject = v.safeParse(OwnedProject, project)
  const parsedNonce = v.safeParse(CanonicalUuid, nonce)
  if (!parsedProject.success || !parsedNonce.success) throw new Error(INVALID_IDENTITY)
  return {
    email: `live-reset-${parsedProject.output}-${parsedNonce.output}@university.dev`,
    fullName: `Live Reset ${parsedProject.output} ${parsedNonce.output}`,
  }
}

function validateOwnedAccount(account: unknown): OwnedResetAccount {
  const parsed = v.safeParse(OwnedAccount, account)
  if (!parsed.success) throw new Error(INVALID_IDENTITY)
  const match = /^Live Reset (desktop|mobile) ([0-9a-f-]+)$/u.exec(parsed.output.fullName)
  if (match === null) throw new Error(INVALID_IDENTITY)
  const expected = createOwnedResetAccount(match[1], match[2])
  if (expected.email !== parsed.output.email || expected.fullName !== parsed.output.fullName) {
    throw new Error(INVALID_IDENTITY)
  }
  return expected
}

function ownedRequestUrl(origin: unknown, path: string, timeoutMs: unknown): URL {
  if (
    typeof origin !== "string" ||
    typeof timeoutMs !== "number" ||
    !Number.isInteger(timeoutMs) ||
    timeoutMs < 1 ||
    timeoutMs > 5_000
  ) {
    throw new Error(INVALID_IDENTITY)
  }
  try {
    const url = new URL(origin)
    if (
      !["http:", "https:"].includes(url.protocol) ||
      !["localhost", "127.0.0.1"].includes(url.hostname) ||
      !url.port ||
      url.port === "0" ||
      url.username ||
      url.password ||
      (origin !== url.origin && origin !== `${url.origin}/`)
    ) {
      throw new Error(INVALID_IDENTITY)
    }
    return new URL(path, url.origin)
  } catch {
    throw new Error(INVALID_IDENTITY)
  }
}

async function readIdentity(
  api: APIRequestContext,
  origin: string,
  account: OwnedResetAccount,
  timeoutMs: number,
  fallback: boolean
): Promise<string> {
  const expected = validateOwnedAccount(account)
  const url = ownedRequestUrl(origin, fallback ? "/api/v1/users" : "/api/v1/users/me", timeoutMs)
  if (fallback) {
    url.searchParams.set("full_name", expected.fullName)
    url.searchParams.set("role", "student")
    url.searchParams.set("limit", "2")
  }
  let response: APIResponse | undefined
  let identity: string | undefined
  try {
    response = await api.get(url.href, {
      timeout: timeoutMs,
      maxRedirects: 0,
      maxRetries: 0,
    })
    if (response.status() !== 200) throw new Error(UNAVAILABLE_IDENTITY)
    // APIRequestContext has already buffered the response; this bounds JSON parsing,
    // not the transport's allocation. Redirects and helper retries are disabled.
    const body = await response.body()
    if (body.byteLength > MAX_RECEIPT_BYTES) throw new Error(UNAVAILABLE_IDENTITY)
    const payload: unknown = JSON.parse(body.toString("utf8"))
    const parsed = fallback
      ? v.safeParse(StudentPage, payload)
      : v.safeParse(StudentReceipt, payload)
    if (!parsed.success) throw new Error(UNAVAILABLE_IDENTITY)
    const student = Array.isArray(parsed.output) ? parsed.output[0] : parsed.output
    if (
      student === undefined ||
      student.email !== expected.email ||
      student.full_name !== expected.fullName
    ) {
      throw new Error(UNAVAILABLE_IDENTITY)
    }
    identity = student.id
  } catch {
    // Upstream errors and response bodies must not escape in Playwright reports.
    identity = undefined
  } finally {
    if (response !== undefined) {
      try {
        await response.dispose()
      } catch {
        identity = undefined
      }
    }
  }
  if (identity === undefined) throw new Error(UNAVAILABLE_IDENTITY)
  return identity
}

export function readOwnedResetUserId(
  api: APIRequestContext,
  origin: string,
  account: OwnedResetAccount,
  timeoutMs: number
): Promise<string> {
  return readIdentity(api, origin, account, timeoutMs, false)
}

export function findOwnedResetUserId(
  api: APIRequestContext,
  origin: string,
  account: OwnedResetAccount,
  timeoutMs: number
): Promise<string> {
  return readIdentity(api, origin, account, timeoutMs, true)
}
