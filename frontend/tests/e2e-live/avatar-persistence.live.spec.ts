import type { Page } from "@playwright/test"
import {
  expect,
  freshPassword,
  loginAs,
  loginWith,
  stubBreachedPasswordLookup,
  test,
} from "./fixtures"

interface OwnerAvatarProfile {
  id: string
  email: string
  full_name: string | null
  avatar_url: string | null
}

interface AdminUserRow {
  id: string
  email: string
  full_name: string | null
}

const TINY_PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
  "base64"
)

const readOwnerProfile = async (page: Page): Promise<OwnerAvatarProfile> => {
  const response = await page.request.get("/api/v1/users/me")
  expect(response.status(), "the signed-in synthetic user can read its own profile").toBe(200)
  return (await response.json()) as OwnerAvatarProfile
}

const deleteOnlyCreatedAccount = async (
  adminPage: Page,
  email: string,
  fullName: string
): Promise<void> => {
  const query = new URLSearchParams({ search: fullName, limit: "200" })
  const response = await adminPage.request.get(`/api/v1/users?${query.toString()}`)
  expect(response.status(), "admin can locate the test-owned synthetic account").toBe(200)

  const users = (await response.json()) as AdminUserRow[]
  const matches = users.filter((entry) => entry.email === email && entry.full_name === fullName)
  expect(
    matches.length,
    "the generated identity resolves to at most one account"
  ).toBeLessThanOrEqual(1)
  const [match] = matches
  if (!match) return

  const deletion = await adminPage.evaluate(async (userId) => {
    const csrfCookie = document.cookie
      .split(";")
      .map((part) => part.trim())
      .find((part) => part.startsWith("csrf_token="))
    if (!csrfCookie) return { status: 0, deleted: false }

    const csrfToken = decodeURIComponent(csrfCookie.slice("csrf_token=".length))
    const result = await fetch(`/api/v1/users/${encodeURIComponent(userId)}`, {
      method: "DELETE",
      credentials: "same-origin",
      headers: { "X-CSRF-Token": csrfToken },
    })
    const body = (await result.json().catch(() => null)) as { deleted?: boolean } | null
    return { status: result.status, deleted: body?.deleted === true }
  }, match.id)

  expect(deletion.status, "cleanup deletes only the generated synthetic account").toBe(200)
  expect(deletion.deleted).toBe(true)
}

const removeOwnerAvatar = async (page: Page): Promise<void> => {
  await page.goto("/settings?tab=1")
  const avatarSection = page.getByRole("button", { name: /Фото профиля|Profile photo/u })
  if ((await avatarSection.getAttribute("aria-expanded")) !== "true") {
    await avatarSection.click()
  }

  const removeButton = page.getByRole("button", { name: /Удалить фото|Remove photo/u })
  const removal = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === "/api/v1/users/me/avatar" &&
      response.request().method() === "DELETE"
  )
  await removeButton.click()
  const response = await removal
  expect(response.status(), "the owner removes its avatar before account cleanup").toBe(200)
}

const chooseAvatarFile = async (
  page: Page,
  file: { name: string; mimeType: string; buffer: Buffer }
): Promise<void> => {
  const fileChooserPromise = page.waitForEvent("filechooser")
  await page.getByRole("button", { name: /Сменить|Change/u }).click()
  const fileChooser = await fileChooserPromise
  await fileChooser.setFiles(file)
}

test("avatar upload persists across reload and rolls back server-rejected content", async ({
  page,
  browser,
}, testInfo) => {
  const liveBaseUrl = process.env.LIVE_BASE_URL
  if (!liveBaseUrl) throw new Error("LIVE_BASE_URL must be set by the live acceptance runner")

  const identity = crypto.randomUUID()
  const fullName = `Live Avatar ${testInfo.project.name} ${identity}`
  const email = `live-avatar-${testInfo.project.name}-${identity}@university.dev`
  const password = freshPassword()
  let registrationAttempted = false
  let ownerAuthenticated = false
  let avatarPostCount = 0

  const adminContext = await browser.newContext({
    baseURL: liveBaseUrl,
    ignoreHTTPSErrors: true,
    locale: "ru-RU",
  })
  const adminPage = await adminContext.newPage()

  page.on("request", (request) => {
    if (
      new URL(request.url()).pathname === "/api/v1/users/me/avatar" &&
      request.method() === "POST"
    ) {
      avatarPostCount += 1
    }
  })

  try {
    await loginAs(adminPage, "admin")
    await stubBreachedPasswordLookup(page)

    await page.goto("/register")
    await page.getByLabel("Имя", { exact: true }).fill(fullName)
    await page.getByRole("textbox", { name: "E-mail" }).fill(email)
    await page.getByLabel("Пароль", { exact: true }).fill(password)
    await page.getByLabel("Повторите пароль", { exact: true }).fill(password)
    registrationAttempted = true
    await page.getByRole("button", { name: "Зарегистрироваться" }).click()
    await expect(page).toHaveURL(/\/login/u)
    await loginWith(page, email, password)
    ownerAuthenticated = true

    const initialProfile = await readOwnerProfile(page)
    expect(initialProfile.email).toBe(email)
    expect(initialProfile.full_name).toBe(fullName)
    expect(initialProfile.avatar_url).toBeNull()

    await page.goto("/settings?tab=1")
    const avatarSection = page.getByRole("button", { name: /Фото профиля|Profile photo/u })
    await avatarSection.click()

    const uploadResponse = page.waitForResponse(
      (response) =>
        new URL(response.url()).pathname === "/api/v1/users/me/avatar" &&
        response.request().method() === "POST"
    )
    await chooseAvatarFile(page, {
      name: "synthetic-avatar.png",
      mimeType: "image/png",
      buffer: TINY_PNG,
    })
    const savedResponse = await uploadResponse
    expect(savedResponse.status(), "the supported PNG upload succeeds").toBe(200)
    const uploadRequestHeaders = await savedResponse.request().allHeaders()
    expect(
      Boolean(uploadRequestHeaders["x-csrf-token"]),
      "the owner avatar mutation carries CSRF protection without exposing its value"
    ).toBe(true)
    expect(avatarPostCount).toBe(1)

    const savedProfile = await readOwnerProfile(page)
    expect(savedProfile.avatar_url).toBeTruthy()
    expect(savedProfile.avatar_url).not.toBe(initialProfile.avatar_url)

    const avatar = page.getByRole("tabpanel").getByRole("img", { name: fullName })
    await expect(avatar).toBeVisible()
    await expect(avatar).not.toHaveAttribute("src", /gravatar\.com/u)
    await expect
      .poll(() => avatar.evaluate((image) => (image as HTMLImageElement).naturalWidth))
      .toBeGreaterThan(0)

    await page.reload()
    const reloadedProfile = await readOwnerProfile(page)
    expect(reloadedProfile.avatar_url).toBe(savedProfile.avatar_url)
    const reloadedAvatarSection = page.getByRole("button", {
      name: /Фото профиля|Profile photo/u,
    })
    await reloadedAvatarSection.click()
    const reloadedAvatar = page.getByRole("tabpanel").getByRole("img", { name: fullName })
    await expect(reloadedAvatar).toBeVisible()
    await expect(reloadedAvatar).not.toHaveAttribute("src", /gravatar\.com/u)
    await expect
      .poll(() => reloadedAvatar.evaluate((image) => (image as HTMLImageElement).naturalWidth))
      .toBeGreaterThan(0)
    const persistedAvatarSrc = await reloadedAvatar.getAttribute("src")

    // The browser accepts this declared PNG MIME, but the server rejects the
    // synthetic non-image bytes. The optimistic preview must roll back to the
    // previously persisted, test-owned avatar.
    const postsBeforeServerRejectedImage = avatarPostCount
    const rejectedImageUpload = page.waitForResponse(
      (response) =>
        new URL(response.url()).pathname === "/api/v1/users/me/avatar" &&
        response.request().method() === "POST"
    )
    await chooseAvatarFile(page, {
      name: "invalid-content-avatar.png",
      mimeType: "image/png",
      buffer: Buffer.from("not a valid PNG image"),
    })
    const rejectedImageResponse = await rejectedImageUpload
    expect(rejectedImageResponse.status(), "server rejects invalid image bytes").toBe(415)
    expect(avatarPostCount, "the client permits one server-validated image upload").toBe(
      postsBeforeServerRejectedImage + 1
    )
    await expect(
      page.getByText(/Не удалось загрузить аватар|Couldn't upload avatar/u)
    ).toBeVisible()
    expect((await readOwnerProfile(page)).avatar_url).toBe(savedProfile.avatar_url)
    expect(await reloadedAvatar.getAttribute("src")).toBe(persistedAvatarSrc)

    await page.reload()
    const rejectedReloadedProfile = await readOwnerProfile(page)
    const rejectedReloadedSection = page.getByRole("button", {
      name: /Фото профиля|Profile photo/u,
    })
    if ((await rejectedReloadedSection.getAttribute("aria-expanded")) !== "true") {
      await rejectedReloadedSection.click()
    }
    const rejectedReloadedAvatar = page.getByRole("tabpanel").getByRole("img", { name: fullName })
    const rejectedReloadedAvatarSrc = await rejectedReloadedAvatar.getAttribute("src")
    const savedAvatarRestoredAfterRejectedReload =
      rejectedReloadedProfile.avatar_url === savedProfile.avatar_url &&
      rejectedReloadedAvatarSrc === persistedAvatarSrc
    expect(
      savedAvatarRestoredAfterRejectedReload,
      "the previous owner avatar remains saved and displayed after rejected upload and reload"
    ).toBe(true)

    const postsBeforeInvalidFiles = avatarPostCount
    await chooseAvatarFile(page, {
      name: "unsupported-avatar.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("synthetic unsupported file"),
    })
    await expect(
      page.getByText(/Поддерживаются форматы: PNG, JPG, WebP|Supported formats: PNG, JPG, WebP/u)
    ).toBeVisible()
    expect(avatarPostCount, "unsupported MIME types are rejected before upload").toBe(
      postsBeforeInvalidFiles
    )
    expect((await readOwnerProfile(page)).avatar_url).toBe(savedProfile.avatar_url)
    expect(await reloadedAvatar.getAttribute("src")).toBe(persistedAvatarSrc)

    await chooseAvatarFile(page, {
      name: "oversized-avatar.png",
      mimeType: "image/png",
      buffer: Buffer.alloc(5 * 1024 * 1024 + 1),
    })
    await expect(page.getByText(/Файл больше 5 МБ|File is larger than 5 MB/u)).toBeVisible()
    expect(avatarPostCount, "oversized files are rejected before upload").toBe(
      postsBeforeInvalidFiles
    )
    expect((await readOwnerProfile(page)).avatar_url).toBe(savedProfile.avatar_url)
    expect(await reloadedAvatar.getAttribute("src")).toBe(persistedAvatarSrc)
    expect(reloadedProfile.id).toMatch(/^[0-9a-f-]{36}$/iu)
  } finally {
    try {
      if (ownerAuthenticated) await removeOwnerAvatar(page)
    } finally {
      try {
        if (registrationAttempted) await deleteOnlyCreatedAccount(adminPage, email, fullName)
      } finally {
        await adminContext.close()
      }
    }
  }
})
