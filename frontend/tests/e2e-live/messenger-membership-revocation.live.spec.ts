import { Buffer } from "node:buffer"
import { randomUUID } from "node:crypto"
import { devices, type BrowserContext, type Page } from "@playwright/test"
import { expect, GROUP_CHAT_ACCOUNTS, loginAs, loginWith, test } from "./fixtures"

const LIVE_BASE_URL = process.env.LIVE_BASE_URL
if (!LIVE_BASE_URL) {
  throw new Error("LIVE_BASE_URL must be set to the endpoint printed by scripts/live_stand.py")
}

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
type LiveChatPage = { items: LiveGroup[]; has_more: boolean; next_cursor: string | null }
type MutationResult = { status: number; body: unknown }
type ChatDeleteResult = { chat_id: string; deleted_attachments: number }

async function currentUser(page: Page): Promise<LiveUser> {
  const response = await page.request.get("/api/v1/users/me")
  expect(response.ok()).toBe(true)
  return (await response.json()) as LiveUser
}

async function selectGroupMember(page: Page, fullName: string): Promise<void> {
  const search = page.getByRole("textbox", { name: "Поиск пользователей" })
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
  await page.getByRole("button", { name: "Новый чат", exact: true }).click()
  await page.getByRole("tab", { name: "Группа", exact: true }).click()
  await page.getByRole("textbox", { name: "Название группы" }).fill(name)

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
  await page.getByRole("button", { name: "Создать группу", exact: true }).click()
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

function expectOwnedGroup(
  group: LiveGroup,
  groupId: string,
  groupName: string,
  ownerId: string,
  participantIds: string[]
): void {
  expect(group.id).toBe(groupId)
  expect(group.chat_type).toBe("group")
  expect(group.name).toBe(groupName)
  expect(group.created_by).toBe(ownerId)
  expect(new Set(group.participants.map((participant) => participant.id))).toEqual(
    new Set(participantIds)
  )
}

async function sameOriginMutation(
  page: Page,
  path: string,
  method: "DELETE" | "POST",
  formFields: Record<string, string> | null = null
): Promise<MutationResult> {
  return page.evaluate(
    async ({ path, method, formFields }) => {
      const readCsrfToken = (): string | null => {
        const cookie = document.cookie
          .split(";")
          .map((part) => part.trim())
          .find((part) => part.startsWith("csrf_token="))
        return cookie ? decodeURIComponent(cookie.slice("csrf_token=".length)) : null
      }

      let csrfToken = readCsrfToken()
      if (!csrfToken) {
        await fetch("/api/v1/auth/csrf-cookie", { credentials: "same-origin" })
        csrfToken = readCsrfToken()
      }
      if (!csrfToken) return { status: 0, body: null }

      const body = formFields ? new FormData() : undefined
      if (body && formFields) {
        for (const [key, value] of Object.entries(formFields)) body.set(key, value)
      }
      const response = await fetch(path, {
        method,
        credentials: "same-origin",
        headers: { "X-CSRF-Token": csrfToken },
        body,
      })
      const responseBody = await response.json().catch(() => null)
      return { status: response.status, body: responseBody }
    },
    { path, method, formFields }
  )
}

function isDenied(status: number): boolean {
  return status === 403 || status === 404
}

async function cleanupOwnedGroup(
  ownerPage: Page,
  adminPage: Page,
  group: LiveGroup,
  groupName: string,
  ownerId: string,
  allowedParticipantSets: string[][],
  attachmentUrl: string | null
): Promise<void> {
  const snapshotResponse = await ownerPage.request.get(`/api/v1/chats/${group.id}`)
  if (snapshotResponse.status() === 404) return
  expect(snapshotResponse.ok()).toBe(true)
  const snapshot = (await snapshotResponse.json()) as LiveGroup
  expect(snapshot.id).toBe(group.id)
  expect(snapshot.chat_type).toBe("group")
  expect(snapshot.name).toBe(groupName)
  expect(snapshot.created_by).toBe(ownerId)
  const participantIds = snapshot.participants.map((participant) => participant.id)
  expect(
    allowedParticipantSets.some(
      (allowed) =>
        allowed.length === participantIds.length &&
        allowed.every((participantId) => participantIds.includes(participantId))
    )
  ).toBe(true)

  const deletion = await sameOriginMutation(
    adminPage,
    `/api/v1/chats/${encodeURIComponent(group.id)}`,
    "DELETE"
  )
  expect(deletion.status).toBe(200)
  const result = deletion.body as ChatDeleteResult | null
  expect(result?.chat_id).toBe(group.id)
  if (attachmentUrl) expect(result?.deleted_attachments).toBe(1)
  await expect
    .poll(async () => (await ownerPage.request.get(`/api/v1/chats/${group.id}`)).status())
    .toBe(404)
  if (attachmentUrl) {
    const deletedAttachment = await ownerPage.request.get(attachmentUrl)
    expect(deletedAttachment.status()).toBe(404)
    expect(deletedAttachment.headers()["content-disposition"]).toBeUndefined()
  }
}

// Chat payloads and login requests can contain private data; keep reports clean.
test.use({ trace: "off", screenshot: "off" })

test.describe("live Messenger membership revocation", () => {
  test("a removed member loses detail, history, reactor, and attachment access", async ({
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
    const groupName = `live-membership-revocation-${randomUUID()}`
    let group: LiveGroup | null = null
    let ownerId: string | null = null
    let removedUserId: string | null = null
    let remainingUserId: string | null = null
    let attachmentUrl: string | null = null
    let attachmentUploaded = false
    let adminPage: Page | null = null

    try {
      const removedContext = await browser.newContext(contextOptions)
      contexts.push(removedContext)
      const remainingContext = await browser.newContext(contextOptions)
      contexts.push(remainingContext)
      const adminContext = await browser.newContext(contextOptions)
      contexts.push(adminContext)
      const removedPage = await removedContext.newPage()
      const remainingPage = await remainingContext.newPage()
      adminPage = await adminContext.newPage()

      await loginAs(page, "student")
      await loginAs(removedPage, "teacher")
      await loginWith(
        remainingPage,
        GROUP_CHAT_ACCOUNTS.secondMember.email,
        GROUP_CHAT_ACCOUNTS.secondMember.password
      )
      await loginAs(adminPage, "admin")

      const owner = await currentUser(page)
      const removedUser = await currentUser(removedPage)
      const remainingUser = await currentUser(remainingPage)
      const cleanupActor = await currentUser(adminPage)
      expect(owner.role).toBe("student")
      expect(removedUser.role).toBe("teacher")
      expect(remainingUser.role).toBe("student")
      expect(cleanupActor.role).toBe("admin")
      expect(new Set([owner.id, removedUser.id, remainingUser.id, cleanupActor.id]).size).toBe(4)
      expect(removedUser.full_name).toBeTruthy()
      expect(remainingUser.full_name).toBeTruthy()
      ownerId = owner.id
      removedUserId = removedUser.id
      remainingUserId = remainingUser.id

      group = await createOwnedGroup(page, groupName, [removedUser, remainingUser])
      const groupId = group.id
      const originalParticipants = [owner.id, removedUser.id, remainingUser.id]
      const remainingParticipants = [owner.id, remainingUser.id]
      expectOwnedGroup(group, groupId, groupName, owner.id, originalParticipants)

      await page.goto(`/messenger/${groupId}`)
      await removedPage.goto(`/messenger/${groupId}`)
      await remainingPage.goto(`/messenger/${groupId}`)

      const messageContent = `membership-revocation-message-${randomUUID()}`
      const attachmentContent = Buffer.from(`membership-revocation-file-${randomUUID()}`, "utf8")
      const filename = `revocation-proof-${randomUUID()}.txt`
      await page.locator("#chat-attach-btn").click()
      await page.locator("#chat-attach-type-document").click()
      await page.locator('input[type="file"]').setInputFiles({
        name: filename,
        mimeType: "text/plain",
        buffer: attachmentContent,
      })
      await page.locator("#chat-message-input").fill(messageContent)
      await expect(page.locator("#chat-send-btn")).toBeEnabled()

      const messageResponsePromise = page.waitForResponse((response) => {
        const request = response.request()
        return (
          request.method() === "POST" &&
          new URL(response.url()).pathname === `/api/v1/chats/${groupId}/messages`
        )
      })
      await page.locator("#chat-send-btn").click()
      const messageResponse = await messageResponsePromise
      expect(messageResponse.ok()).toBe(true)
      const message = (await messageResponse.json()) as LiveMessage
      const attachment = message.attachments[0]
      if (!attachment) throw new Error("uploaded message did not return attachment metadata")
      attachmentUploaded = true
      expect(attachment.filename).toBe(filename)
      expect(attachment.size).toBe(attachmentContent.length)
      const parsedAttachmentUrl = new URL(attachment.url, LIVE_BASE_URL)
      expect(parsedAttachmentUrl.origin).toBe(new URL(LIVE_BASE_URL).origin)
      expect(parsedAttachmentUrl.username).toBe("")
      expect(parsedAttachmentUrl.password).toBe("")
      expect(parsedAttachmentUrl.pathname.startsWith(`/api/v1/chats/${groupId}/attachments/`)).toBe(
        true
      )
      attachmentUrl = parsedAttachmentUrl.href

      const reaction = await sameOriginMutation(
        remainingPage,
        `/api/v1/chats/${groupId}/messages/${message.id}/reactions`,
        "POST",
        { emoji: "👍" }
      )
      expect(reaction.status).toBe(200)

      const reactorsPath = `/api/v1/chats/${groupId}/messages/${message.id}/reactions?emoji=${encodeURIComponent("👍")}`
      const memberReads = await Promise.all([
        removedPage.request.get(`/api/v1/chats/${groupId}`),
        removedPage.request.get(`/api/v1/chats/${groupId}/messages?limit=100`),
        removedPage.request.get(reactorsPath),
        removedPage.request.get(attachmentUrl),
      ])
      expect(memberReads.map((response) => response.status())).toEqual([200, 200, 200, 200])
      const memberHistory = (await memberReads[1]!.json()) as {
        items: { content: string }[]
      }
      expect(memberHistory.items.some((item) => item.content === messageContent)).toBe(true)
      const memberReactors = (await memberReads[2]!.json()) as { user_id: string }[]
      expect(memberReactors.some((reactor) => reactor.user_id === remainingUser.id)).toBe(true)
      expect((await memberReads[3]!.body()).equals(attachmentContent)).toBe(true)

      const removal = await sameOriginMutation(
        page,
        `/api/v1/chats/${groupId}/participants/${removedUser.id}`,
        "DELETE"
      )
      expect(removal.status).toBe(200)

      await expect
        .poll(async () => {
          const response = await removedPage.request.get(`/api/v1/chats/${groupId}`)
          return isDenied(response.status())
        })
        .toBe(true)

      const revokedReads = await Promise.all([
        removedPage.request.get(`/api/v1/chats/${groupId}`),
        removedPage.request.get(`/api/v1/chats/${groupId}/messages?limit=100`),
        removedPage.request.get(reactorsPath),
        removedPage.request.get(attachmentUrl),
      ])
      expect(revokedReads.every((response) => isDenied(response.status()))).toBe(true)
      const revokedBodies = await Promise.all(revokedReads.map((response) => response.body()))
      expect(revokedBodies.some((body) => body.includes(Buffer.from(messageContent)))).toBe(false)
      expect(revokedBodies.some((body) => body.includes(attachmentContent))).toBe(false)
      expect(revokedReads[3]!.headers()["content-disposition"]).toBeUndefined()

      const ownerSnapshotResponse = await page.request.get(`/api/v1/chats/${groupId}`)
      expect(ownerSnapshotResponse.ok()).toBe(true)
      const ownerSnapshot = (await ownerSnapshotResponse.json()) as LiveGroup
      expectOwnedGroup(ownerSnapshot, groupId, groupName, owner.id, remainingParticipants)
    } finally {
      try {
        let groupToClean = group
        if (!groupToClean && ownerId) groupToClean = await findOwnedGroupByName(page, groupName)
        if (groupToClean && ownerId && removedUserId && remainingUserId && adminPage) {
          await cleanupOwnedGroup(
            page,
            adminPage,
            groupToClean,
            groupName,
            ownerId,
            [
              [ownerId, removedUserId, remainingUserId],
              [ownerId, remainingUserId],
            ],
            attachmentUploaded ? attachmentUrl : null
          )
        }
      } finally {
        await Promise.all(contexts.map((context) => context.close()))
      }
    }
  })
})
