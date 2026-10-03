import { Buffer } from "node:buffer"
import { randomUUID } from "node:crypto"
import { devices, type BrowserContext, type Page } from "@playwright/test"
import { expect, GROUP_CHAT_ACCOUNTS, loginAs, loginWith, test } from "./fixtures"

const LIVE_BASE_URL = process.env.LIVE_BASE_URL
if (!LIVE_BASE_URL) {
  throw new Error("LIVE_BASE_URL must be set to the endpoint printed by scripts/live_stand.py")
}
const CHAT_ATTACHMENT_MAX_SIZE_BYTES = 15 * 1024 * 1024

type LiveUser = { id: string; full_name: string | null; role: string }
type LiveGroup = {
  id: string
  chat_type: string
  name: string | null
  created_by: string | null
  participants: { id: string }[]
}
type LiveMessage = {
  id: string
  attachments: { url: string; filename: string; size: number }[]
}
type OversizedUploadResult = { status: number; attachmentUrl: string | null }
type ChatDeleteResult = { chat_id: string; status: string; deleted_attachments: number }
type LiveChatPage = { items: LiveGroup[]; has_more: boolean; next_cursor: string | null }

async function getCurrentUser(page: Page): Promise<LiveUser> {
  const response = await page.request.get("/api/v1/users/me")
  expect(response.ok()).toBe(true)
  return (await response.json()) as LiveUser
}

async function selectGroupMember(page: Page, fullName: string): Promise<void> {
  const search = page.getByRole("textbox", {
    name: "\u041f\u043e\u0438\u0441\u043a \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u0435\u0439",
  })
  await search.fill(fullName)
  const option = page.getByRole("option").filter({ hasText: fullName })
  await expect(option).toHaveCount(1)
  await option.click()
}

async function createOwnedGroup(
  page: Page,
  name: string,
  participants: LiveUser[]
): Promise<LiveGroup> {
  await page.goto("/messenger")
  await page
    .getByRole("button", {
      name: "\u041d\u043e\u0432\u044b\u0439 \u0447\u0430\u0442",
      exact: true,
    })
    .click()
  await page.getByRole("tab", { name: "\u0413\u0440\u0443\u043f\u043f\u0430", exact: true }).click()
  await page
    .getByRole("textbox", {
      name: "\u041d\u0430\u0437\u0432\u0430\u043d\u0438\u0435 \u0433\u0440\u0443\u043f\u043f\u044b",
    })
    .fill(name)

  for (const participant of participants) {
    if (!participant.full_name) throw new Error("seeded group member is missing a display name")
    await selectGroupMember(page, participant.full_name)
  }

  const createResponsePromise = page.waitForResponse((response) => {
    const request = response.request()
    return (
      request.method() === "POST" && new URL(response.url()).pathname === "/api/v1/chats/groups"
    )
  })
  await page
    .getByRole("button", {
      name: "\u0421\u043e\u0437\u0434\u0430\u0442\u044c \u0433\u0440\u0443\u043f\u043f\u0443",
      exact: true,
    })
    .click()
  const createResponse = await createResponsePromise
  expect(createResponse.ok()).toBe(true)
  return (await createResponse.json()) as LiveGroup
}

async function findOwnedGroupByName(page: Page, name: string): Promise<LiveGroup | null> {
  const matches: LiveGroup[] = []
  let cursor: string | null = null

  do {
    const parameters = new URLSearchParams({ limit: "100" })
    if (cursor) parameters.set("cursor", cursor)
    const response = await page.request.get(`/api/v1/chats?${parameters.toString()}`)
    expect(response.ok()).toBe(true)
    const chatPage = (await response.json()) as LiveChatPage
    matches.push(...chatPage.items.filter((chat) => chat.name === name))
    if (!chatPage.has_more) break
    expect(chatPage.next_cursor).toBeTruthy()
    cursor = chatPage.next_cursor
  } while (cursor)

  expect(matches.length).toBeLessThanOrEqual(1)
  return matches[0] ?? null
}

function expectExactOwnedGroup(
  group: LiveGroup,
  chatId: string,
  groupName: string,
  ownerId: string,
  participantIds: string[]
): void {
  expect(group.id).toBe(chatId)
  expect(group.chat_type).toBe("group")
  expect(group.name).toBe(groupName)
  expect(group.created_by).toBe(ownerId)
  expect(new Set(group.participants.map((participant) => participant.id))).toEqual(
    new Set(participantIds)
  )
}

async function cleanupOwnedGroup(
  ownerPage: Page,
  cleanupPage: Page,
  group: LiveGroup,
  groupName: string,
  ownerId: string,
  participantIds: string[],
  attachmentUploaded: boolean,
  attachmentUrl: string | null
): Promise<void> {
  // Confirm ownership through the creator's normal member session before using
  // the app's admin-only delete operation. The admin context is reserved for
  // cleanup and never fetches the private attachment.
  const ownerSnapshotResponse = await ownerPage.request.get(`/api/v1/chats/${group.id}`)
  if (ownerSnapshotResponse.status() === 404) {
    if (attachmentUrl) await expectAttachmentNotFound(ownerPage, attachmentUrl)
    return
  }
  expect(ownerSnapshotResponse.ok()).toBe(true)
  const ownerSnapshot = (await ownerSnapshotResponse.json()) as LiveGroup
  expectExactOwnedGroup(ownerSnapshot, group.id, groupName, ownerId, participantIds)

  const deletion = await cleanupPage.evaluate(async (chatId) => {
    const csrfCookie = document.cookie
      .split(";")
      .map((part) => part.trim())
      .find((part) => part.startsWith("csrf_token="))
    if (!csrfCookie) return { status: 0, body: null }

    const csrfToken = decodeURIComponent(csrfCookie.slice("csrf_token=".length))
    const response = await fetch(`/api/v1/chats/${encodeURIComponent(chatId)}`, {
      method: "DELETE",
      credentials: "same-origin",
      headers: { "X-CSRF-Token": csrfToken },
    })
    const body = (await response.json().catch(() => null)) as ChatDeleteResult | null
    return { status: response.status, body }
  }, group.id)

  expect(deletion.status).toBe(200)
  expect(deletion.body?.chat_id).toBe(group.id)
  if (attachmentUploaded) expect(deletion.body?.deleted_attachments).toBe(1)
  await expect
    .poll(async () => (await ownerPage.request.get(`/api/v1/chats/${group.id}`)).status())
    .toBe(404)
  if (attachmentUploaded && attachmentUrl) {
    await expectAttachmentNotFound(ownerPage, attachmentUrl)
  }
}

async function expectAttachmentNotFound(ownerPage: Page, attachmentUrl: string): Promise<void> {
  const postCleanupAttachmentResponse = await ownerPage.request.get(attachmentUrl)
  expect(postCleanupAttachmentResponse.status()).toBe(404)
  expect(postCleanupAttachmentResponse.headers()["content-disposition"]).toBeUndefined()
}

async function submitOversizedAttachment(
  page: Page,
  chatId: string,
  marker: string
): Promise<OversizedUploadResult> {
  return page.evaluate(
    async ({ chatId, marker, maxSizeBytes }) => {
      const csrfCookie = document.cookie
        .split(";")
        .map((part) => part.trim())
        .find((part) => part.startsWith("csrf_token="))
      if (!csrfCookie) return { status: 0, attachmentUrl: null }

      const csrfToken = decodeURIComponent(csrfCookie.slice("csrf_token=".length))
      const body = new FormData()
      body.set("content", marker)
      body.set(
        "files",
        new File([new Uint8Array(maxSizeBytes + 1)], `oversized-${marker}.txt`, {
          type: "text/plain",
        })
      )
      const response = await fetch(`/api/v1/chats/${encodeURIComponent(chatId)}/messages`, {
        method: "POST",
        credentials: "same-origin",
        headers: { "X-CSRF-Token": csrfToken },
        body,
      })
      const result = (await response.json().catch(() => null)) as {
        attachments?: { url?: string }[]
      } | null
      return {
        status: response.status,
        attachmentUrl: result?.attachments?.[0]?.url ?? null,
      }
    },
    { chatId, marker, maxSizeBytes: CHAT_ATTACHMENT_MAX_SIZE_BYTES }
  )
}

// Chat payloads contain private content; keep live reports free of traces and screenshots.
test.use({ trace: "off", screenshot: "off" })

test.describe("live private chat attachment isolation", () => {
  test("a non-member cannot download private attachments and oversized uploads are rejected", async ({
    browser,
    page,
  }, testInfo) => {
    const mobile = testInfo.project.name === "mobile"
    const contextOptions = {
      ...(mobile ? devices["Pixel 7"] : devices["Desktop Chrome"]),
      baseURL: LIVE_BASE_URL,
      locale: "ru-RU",
      viewport: mobile ? { width: 390, height: 844 } : { width: 1440, height: 900 },
    }
    const contexts: BrowserContext[] = []
    const groupName = `live-private-attachment-${randomUUID()}`
    let createdGroup: LiveGroup | null = null
    let ownerId: string | null = null
    let expectedParticipantIds: string[] = []
    let attachmentUploaded = false
    let uploadedAttachmentUrl: string | null = null
    let cleanupPage: Page | null = null

    try {
      const teacherContext = await browser.newContext(contextOptions)
      contexts.push(teacherContext)
      const secondMemberContext = await browser.newContext(contextOptions)
      contexts.push(secondMemberContext)
      const outsiderContext = await browser.newContext(contextOptions)
      contexts.push(outsiderContext)
      const cleanupContext = await browser.newContext(contextOptions)
      contexts.push(cleanupContext)

      const teacherPage = await teacherContext.newPage()
      const secondMemberPage = await secondMemberContext.newPage()
      const outsiderPage = await outsiderContext.newPage()
      cleanupPage = await cleanupContext.newPage()

      await loginAs(page, "student")
      await loginAs(teacherPage, "teacher")
      await loginWith(
        secondMemberPage,
        GROUP_CHAT_ACCOUNTS.secondMember.email,
        GROUP_CHAT_ACCOUNTS.secondMember.password
      )
      await loginWith(
        outsiderPage,
        GROUP_CHAT_ACCOUNTS.nonMember.email,
        GROUP_CHAT_ACCOUNTS.nonMember.password
      )
      // Authenticate the real cleanup role before creating any persistent data.
      await loginAs(cleanupPage, "admin")

      const owner = await getCurrentUser(page)
      const teacher = await getCurrentUser(teacherPage)
      const secondMember = await getCurrentUser(secondMemberPage)
      const outsider = await getCurrentUser(outsiderPage)
      const cleanupActor = await getCurrentUser(cleanupPage)
      expect(owner.role).toBe("student")
      expect(teacher.role).toBe("teacher")
      expect(secondMember.role).toBe("student")
      expect(outsider.role).toBe("teacher")
      expect(cleanupActor.role).toBe("admin")
      expect(new Set([owner.id, teacher.id, secondMember.id, outsider.id]).size).toBe(4)
      expect(teacher.full_name).toBeTruthy()
      expect(secondMember.full_name).toBeTruthy()
      ownerId = owner.id
      expectedParticipantIds = [owner.id, teacher.id, secondMember.id]

      createdGroup = await createOwnedGroup(page, groupName, [teacher, secondMember])
      expectExactOwnedGroup(
        createdGroup,
        createdGroup.id,
        groupName,
        owner.id,
        expectedParticipantIds
      )

      await page.goto(`/messenger/${createdGroup.id}`)
      await outsiderPage.goto(`/messenger/${createdGroup.id}`)
      const outsiderChatResponse = await outsiderPage.request.get(
        `/api/v1/chats/${createdGroup.id}`
      )
      expect([403, 404]).toContain(outsiderChatResponse.status())

      const oversizedUploadMarker = `oversized-upload-marker-${randomUUID()}`
      const oversizedUpload = await submitOversizedAttachment(
        page,
        createdGroup.id,
        oversizedUploadMarker
      )
      if (oversizedUpload.attachmentUrl) {
        attachmentUploaded = true
        const oversizedAttachmentUrl = new URL(oversizedUpload.attachmentUrl, LIVE_BASE_URL)
        const liveOrigin = new URL(LIVE_BASE_URL).origin
        if (
          oversizedAttachmentUrl.origin === liveOrigin &&
          !oversizedAttachmentUrl.username &&
          !oversizedAttachmentUrl.password &&
          oversizedAttachmentUrl.pathname.startsWith(
            `/api/v1/chats/${createdGroup.id}/attachments/`
          )
        ) {
          uploadedAttachmentUrl = oversizedAttachmentUrl.href
        }
      }
      expect([400, 413]).toContain(oversizedUpload.status)
      const oversizedHistoryResponse = await page.request.get(
        `/api/v1/chats/${createdGroup.id}/messages?limit=100`
      )
      expect(oversizedHistoryResponse.status()).toBe(200)
      const oversizedHistory = (await oversizedHistoryResponse.json()) as {
        items: { content: string }[]
      }
      expect(oversizedHistory.items.some((item) => item.content === oversizedUploadMarker)).toBe(
        false
      )

      const marker = `synthetic-private-attachment-${randomUUID()}`
      const markerBytes = Buffer.from(marker, "utf8")
      const filename = `private-attachment-${randomUUID()}.txt`
      await page.locator("#chat-attach-btn").click()
      await page.locator("#chat-attach-type-document").click()
      await page.locator('input[type="file"]').setInputFiles({
        name: filename,
        mimeType: "text/plain",
        buffer: markerBytes,
      })
      await expect(page.locator("#chat-send-btn")).toBeEnabled()

      const messageResponsePromise = page.waitForResponse((response) => {
        const request = response.request()
        return (
          request.method() === "POST" &&
          new URL(response.url()).pathname === `/api/v1/chats/${createdGroup?.id}/messages`
        )
      })
      await page.locator("#chat-send-btn").click()
      const messageResponse = await messageResponsePromise
      expect(messageResponse.ok()).toBe(true)
      const message = (await messageResponse.json()) as LiveMessage
      attachmentUploaded = true
      const attachment = message.attachments[0]
      if (!attachment) throw new Error("uploaded message did not return attachment metadata")
      expect(attachment.filename).toBe(filename)
      expect(attachment.size).toBe(markerBytes.length)

      const attachmentUrl = new URL(attachment.url, LIVE_BASE_URL)
      const liveOrigin = new URL(LIVE_BASE_URL).origin
      expect(attachmentUrl.origin).toBe(liveOrigin)
      expect(attachmentUrl.username).toBe("")
      expect(attachmentUrl.password).toBe("")
      expect(
        attachmentUrl.pathname.startsWith(`/api/v1/chats/${createdGroup.id}/attachments/`)
      ).toBe(true)
      expect(attachmentUrl.pathname.includes("chat_uploads")).toBe(false)
      uploadedAttachmentUrl = attachmentUrl.href

      // The non-member is denied before a member performs the successful read.
      const outsiderDownload = await outsiderPage.request.get(attachment.url)
      expect([403, 404]).toContain(outsiderDownload.status())
      const outsiderBody = await outsiderDownload.body()
      expect(outsiderBody.includes(markerBytes)).toBe(false)
      expect(outsiderDownload.headers()["content-disposition"]).toBeUndefined()

      const memberDownload = await page.request.get(attachment.url)
      expect(memberDownload.status()).toBe(200)
      const memberBody = await memberDownload.body()
      expect(memberBody.equals(markerBytes)).toBe(true)
    } finally {
      try {
        let groupToClean = createdGroup
        if (!groupToClean && ownerId) {
          groupToClean = await findOwnedGroupByName(page, groupName)
        }
        if (groupToClean && ownerId && cleanupPage) {
          await cleanupOwnedGroup(
            page,
            cleanupPage,
            groupToClean,
            groupName,
            ownerId,
            expectedParticipantIds,
            attachmentUploaded,
            uploadedAttachmentUrl
          )
        }
      } finally {
        await Promise.all(contexts.map((context) => context.close()))
      }
    }
  })
})
