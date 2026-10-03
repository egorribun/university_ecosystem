import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { URL } from "node:url"
import test from "node:test"

const specUrl = new URL("./chat-attachment-isolation.live.spec.ts", import.meta.url)
const configUrl = new URL("../../playwright.live.config.ts", import.meta.url)
const chatApiUrl = new URL("../../../app/api/chat.py", import.meta.url)
const commandServiceUrl = new URL("../../../app/services/chat/command_service.py", import.meta.url)
const storageConfigUrl = new URL("../../../app/core/config/storage.py", import.meta.url)
const fileUtilsUrl = new URL("../../../app/utils/files.py", import.meta.url)

const [spec, config, chatApi, commandService, storageConfig, fileUtils] = await Promise.all([
  readFile(specUrl, "utf8"),
  readFile(configUrl, "utf8"),
  readFile(chatApiUrl, "utf8"),
  readFile(commandServiceUrl, "utf8"),
  readFile(storageConfigUrl, "utf8"),
  readFile(fileUtilsUrl, "utf8"),
])

test("live chat attachment acceptance verifies private access and owner-bounded cleanup", () => {
  assert.match(config, /testDir:\s*["']\.\/tests\/e2e-live["']/u)
  assert.match(config, /testMatch:\s*\/\.\*\\\.live\\\.spec\\\.ts\$\//u)
  assert.match(
    spec,
    /test\([\s\S]*?a non-member cannot download private attachments and oversized uploads are rejected/u
  )
  assert.match(spec, /synthetic-private-attachment-/u)
  assert.match(spec, /randomUUID\(\)/u)
  assert.match(spec, /Buffer\.from\(marker, "utf8"\)/u)
  assert.match(spec, /expect\(\[403, 404\]\)\.toContain\(outsiderDownload\.status\(\)\)/u)
  assert.match(spec, /expect\(memberDownload\.status\(\)\)\.toBe\(200\)/u)
  assert.match(spec, /expect\(deletion\.body\?\.deleted_attachments\)\.toBe\(1\)/u)
  assert.match(spec, /postCleanupAttachmentResponse/u)
  assert.match(spec, /expect\(postCleanupAttachmentResponse\.status\(\)\)\.toBe\(404\)/u)
  assert.match(spec, /expectExactOwnedGroup\(ownerSnapshot/u)
  assert.match(spec, /headers: \{ "X-CSRF-Token": csrfToken \}/u)
  assert.match(spec, /credentials: "same-origin"/u)
  assert.match(spec, /trace: "off", screenshot: "off"/u)
  assert.doesNotMatch(spec, /page\.route|routeWebSocket|\.request\.(?:post|put|patch)\(/u)

  const membershipCheck = chatApi.indexOf("if membership.scalar_one_or_none() is None:")
  const chatScopedAttachmentQuery = chatApi.indexOf("Message.chat_id == chat_id", membershipCheck)
  const storageRead = chatApi.indexOf(
    "_get_storage_backend().read_file(",
    chatScopedAttachmentQuery
  )
  assert.ok(membershipCheck >= 0, "download must require live chat membership")
  assert.ok(
    membershipCheck < chatScopedAttachmentQuery && chatScopedAttachmentQuery < storageRead,
    "the route must authorize membership and scope the attachment before reading storage"
  )
  assert.match(chatApi, /attachment\.size > max_size_bytes/u)
})

test("live attachment acceptance rejects an over-limit upload before persistence", () => {
  assert.ok(
    spec.includes("const CHAT_ATTACHMENT_MAX_SIZE_BYTES = 15 * 1024 * 1024"),
    "the live boundary case follows the tracked backend default limit"
  )
  assert.ok(
    storageConfig.includes("chat_attachment_max_size_bytes: int = 15 * 1024 * 1024"),
    "the tracked backend default must stay aligned with the synthetic fixture"
  )
  assert.ok(spec.includes("new Uint8Array(maxSizeBytes + 1)"))
  assert.ok(spec.includes("const oversizedUpload = await submitOversizedAttachment("))
  assert.ok(spec.includes("expect([400, 413]).toContain(oversizedUpload.status)"))
  assert.ok(spec.includes("oversizedUploadMarker"))
  assert.ok(spec.includes("oversizedHistory.items.some("))
  assert.ok(spec.includes("const oversizedAttachmentUrl = new URL(oversizedUpload.attachmentUrl"))
  assert.ok(spec.includes("oversizedAttachmentUrl.origin === liveOrigin"))
  assert.ok(spec.includes('credentials: "same-origin"'))
  assert.ok(spec.includes('trace: "off", screenshot: "off"'))
  assert.doesNotMatch(spec, /page\.route|routeWebSocket|console\.(?:log|info|debug)\(/u)

  const responseOriginCheck = spec.indexOf("expect(attachmentUrl.origin).toBe(liveOrigin)")
  const cleanupUrlCapture = spec.indexOf("uploadedAttachmentUrl = attachmentUrl.href")
  assert.ok(
    responseOriginCheck >= 0 && cleanupUrlCapture > responseOriginCheck,
    "cleanup must only request an attachment URL after the live-origin check"
  )

  const totalSizeGuard = commandService.indexOf(
    "if total_size > settings.chat_attachment_max_total_bytes:"
  )
  const uploadProcessing = commandService.indexOf(
    "res = await self.attachment_service.process_upload("
  )
  assert.ok(
    totalSizeGuard >= 0 && uploadProcessing > totalSizeGuard,
    "total request size must be rejected before scanner or storage processing"
  )

  const saveAttachment = fileUtils.indexOf("async def save_attachment(")
  const boundedRead = fileUtils.indexOf("data = await _read_limited(upload, limit", saveAttachment)
  const storageWrite = fileUtils.indexOf("url = await backend.save_file(", saveAttachment)
  assert.ok(
    saveAttachment >= 0 && boundedRead > saveAttachment && storageWrite > boundedRead,
    "per-file byte limits must be checked before writing the attachment object"
  )
})
