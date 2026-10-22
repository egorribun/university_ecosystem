import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"

function requireMatch(source, pattern, message) {
  assert.ok(pattern.test(source), message)
}

function requireNoMatch(source, pattern, message) {
  assert.equal(pattern.test(source), false, message)
}

async function readPrivateAttachmentRoute() {
  const source = await readFile(new URL("../../app/api/chat.py", import.meta.url), "utf8")
  const routeStart = source.indexOf("async def download_chat_attachment(")
  assert.notEqual(routeStart, -1, "chat attachment download route must exist")
  const routeEnd = source.indexOf("\n\n@router.", routeStart)
  assert.notEqual(routeEnd, -1, "chat attachment route must end before the next route")
  return source.slice(routeStart, routeEnd)
}

function assertBoundedStorageRead(route) {
  assert.equal(
    (route.match(/\.read_file\(/gu) ?? []).length,
    1,
    "the route must have exactly one storage read, covered by the size and URL guards"
  )
  requireMatch(
    route,
    /if max_size_bytes <= 0 or attachment\.size < 0 or attachment\.size > max_size_bytes:\s*raise_not_found[\s\S]*?\.read_file\(\s*storage_url,\s*max_bytes=attachment\.size\s*\)/u,
    "storage reads must be bounded by the authorized attachment size"
  )
  requireMatch(
    route,
    /parsed_storage_url = urlsplit\(attachment\.url\)\s*storage_url = urlunsplit\(parsed_storage_url\._replace\(query="", fragment=""\)\)\s*data = await _get_storage_backend\(\)\.read_file\(\s*storage_url,\s*max_bytes=attachment\.size\s*\)/u,
    "storage reads must normalize query and fragment without changing the authorized resource"
  )
  requireMatch(
    route,
    /if len\(data\) != attachment\.size:\s*raise_not_found/u,
    "the downloaded body must match its authorized metadata size"
  )
}

test("private attachment route checks membership before storage access", async () => {
  const route = await readPrivateAttachmentRoute()

  const membershipCheck = route.indexOf("membership.scalar_one_or_none()")
  const attachmentLookup = route.indexOf("select(Attachment)")
  const storageRead = route.indexOf(".read_file(")
  assert.ok(membershipCheck >= 0, "route must make a current membership decision")
  assert.ok(
    membershipCheck < attachmentLookup && attachmentLookup < storageRead,
    "membership must be checked before attachment metadata lookup and storage reads"
  )
  requireMatch(
    route,
    /if membership\.scalar_one_or_none\(\) is None:[\s\S]*?raise_forbidden/u,
    "the route must deny users with no current chat membership"
  )
  assertBoundedStorageRead(route)
})

for (const [label, before, after] of [
  [
    "single guarded storage read",
    "max_size_bytes = int(settings.chat_attachment_max_size_bytes)",
    "await _get_storage_backend().read_file(attachment.url)\n    max_size_bytes = int(settings.chat_attachment_max_size_bytes)",
  ],
  ["zero configured limit", "max_size_bytes <= 0", "max_size_bytes < 0"],
  ["negative metadata size", "attachment.size < 0", "False"],
  ["oversized metadata", "attachment.size > max_size_bytes", "False"],
  ["read byte limit", "max_bytes=attachment.size", "max_bytes=None"],
  [
    "normalized read URL",
    "storage_url, max_bytes=attachment.size",
    "attachment.url, max_bytes=attachment.size",
  ],
  ["query removal", 'query=""', "query=parsed_storage_url.query"],
  ["fragment removal", 'fragment=""', "fragment=parsed_storage_url.fragment"],
  ["body length check", "if len(data) != attachment.size:", "if len(data) == attachment.size:"],
]) {
  test("private attachment contract rejects missing " + label, async () => {
    const route = await readPrivateAttachmentRoute()
    assert.ok(route.includes(before), "the mutation must target the current route")
    assert.throws(() => assertBoundedStorageRead(route.replace(before, after)), {
      name: "AssertionError",
    })
  })
}

test("live attachment isolation scenario uses real member and outsider requests with owned cleanup", async () => {
  const spec = await readFile(
    new URL("../tests/e2e-live/chat-attachment-isolation.live.spec.ts", import.meta.url),
    "utf8"
  )

  requireMatch(
    spec,
    /test\.use\(\{[^}]*trace:\s*["']off["'][^}]*screenshot:\s*["']off["']/su,
    "live output must not retain chat payloads"
  )
  requireMatch(
    spec,
    /loginAs\(page,\s*["']student["']\)/u,
    "a normal seeded member must upload the file"
  )
  requireMatch(spec, /GROUP_CHAT_ACCOUNTS\.nonMember/u, "the non-member must be a seeded account")
  requireMatch(
    spec,
    /browser\.newContext\(/u,
    "the outsider must have a separate authenticated context"
  )
  requireMatch(spec, /setInputFiles\(/u, "the attachment must use the real browser upload flow")
  requireMatch(
    spec,
    /const outsiderDownload = await outsiderPage\.request\.get\(attachment\.url\)/u,
    "the outsider must request the real attachment API URL"
  )
  requireMatch(
    spec,
    /const memberDownload = await page\.request\.get\(attachment\.url\)/u,
    "a group member must verify the stored object after denial"
  )
  requireMatch(
    spec,
    /expect\(\[403,\s*404\]\)\.toContain\(outsiderDownload\.status\(\)\)/u,
    "the outsider request must be denied"
  )
  requireMatch(
    spec,
    /outsiderBody\.includes\(markerBytes\)/u,
    "no marker bytes may reach the outsider"
  )
  requireMatch(
    spec,
    /memberBody\.equals\(markerBytes\)\)\.toBe\(true\)/u,
    "the authorized member must retrieve the exact uploaded bytes"
  )

  const deniedRead = spec.indexOf("const outsiderDownload =")
  const authorizedRead = spec.indexOf("const memberDownload =")
  assert.ok(
    deniedRead >= 0 && authorizedRead > deniedRead,
    "outsider denial must precede authorized retrieval"
  )

  requireMatch(
    spec,
    /finally\s*\{[\s\S]*cleanupOwnedGroup/u,
    "created resources must be cleaned in finally"
  )
  requireMatch(spec, /function cleanupOwnedGroup/u, "cleanup must be scoped to the created group")
  requireMatch(
    spec,
    /function expectExactOwnedGroup[\s\S]*created_by[\s\S]*participants/u,
    "cleanup must validate the creator and exact participant set"
  )
  const adminPreflight = spec.indexOf('loginAs(cleanupPage, "admin")')
  const firstResourceCreate = spec.indexOf("createOwnedGroup(page")
  assert.ok(adminPreflight >= 0 && firstResourceCreate > adminPreflight)
  requireNoMatch(
    spec,
    /routeWebSocket|WebSocket\s*=\s*new\s+Mock|delete_file\(/u,
    "the scenario must use real transport and supported cleanup"
  )

  const cleanupStart = spec.indexOf("async function cleanupOwnedGroup")
  const cleanupEnd = spec.indexOf("\n}\n\n// Chat payloads", cleanupStart) + 2
  assert.ok(
    cleanupStart >= 0 && cleanupEnd > cleanupStart,
    "cleanup helper must be a bounded function"
  )
  const cleanup = spec.slice(cleanupStart, cleanupEnd)
  requireMatch(cleanup, /ownerSnapshotResponse/u, "cleanup must first verify the owned chat")
  requireMatch(
    cleanup,
    /expectExactOwnedGroup\(ownerSnapshot/u,
    "cleanup must refuse a chat with unexpected ownership or members"
  )
  requireMatch(
    cleanup,
    /cleanupPage\.evaluate/u,
    "cleanup must use the authenticated application API"
  )
  requireMatch(cleanup, /chatId/u, "cleanup must delete only the verified chat id")
  requireNoMatch(
    cleanup,
    /request\.get\(attachment\.url\)/u,
    "the cleanup admin must not fetch the private attachment"
  )
})
