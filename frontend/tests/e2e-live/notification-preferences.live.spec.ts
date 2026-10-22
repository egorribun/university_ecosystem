import { Page } from "@playwright/test"
import {
  withLiveRegistrationAdmission,
  expect,
  freshPassword,
  loginAs,
  loginWith,
  stubBreachedPasswordLookup,
} from "./fixtures"
import { test } from "./native-push-profile-fixtures"
import { reportAuthHttpStatus } from "./auth-notification-diagnostic"

test.use({ channel: "chromium" })
test.use({ nativePushChannel: "chromium" })

const expandPushAccordion = async (page: Page): Promise<void> => {
  const accordion = page.getByRole("button", { name: /Push notifications|Push-уведомления/u })
  if ((await accordion.getAttribute("aria-expanded")) !== "true") {
    await accordion.click()
  }
  await expect(accordion).toHaveAttribute("aria-expanded", "true")
}

interface UserProfileResponse {
  id: string
  email: string
  role: string
  dnd_enabled: boolean
  dnd_start: string | null
  dnd_end: string | null
}

interface PushTopicsResponse {
  allowed: string[]
  topics: string[]
  has_preferences: boolean
}

interface AdminUserTopicsResponse {
  user_id: string
  email: string
  topics: string[]
  allowed_topics: string[]
}

interface AdminUserRow {
  id: string
  email: string
  full_name: string | null
}

const diagnosticProject = (projectName: string): "desktop" | "mobile" =>
  projectName.toLowerCase().includes("mobile") ? "mobile" : "desktop"

const TOPICS = [
  { key: "news.published", label: "Опубликованные новости" },
  { key: "schedule.changed", label: "Изменения расписания" },
  { key: "events.published", label: "Опубликованные мероприятия" },
  { key: "chat.message.created", label: "Сообщения чата" },
  { key: "system.release", label: "Системные релизы" },
] as const

const SELECTED_TOPICS = ["news.published", "events.published", "system.release"]

const waitForProfileUpdate = (page: Page) =>
  page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === "/api/v1/users/me" &&
      response.request().method() === "PUT"
  )

const waitForPushAction = (page: Page, path: string, method: string) =>
  page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === path && response.request().method() === method
  )

const readProfile = async (
  page: Page,
  project: "desktop" | "mobile"
): Promise<UserProfileResponse> => {
  const response = await page.request.get("/api/v1/users/me")
  reportAuthHttpStatus(project, "profile_read", response.status())
  expect(response.status(), "the signed-in synthetic user can read its profile").toBe(200)
  return (await response.json()) as UserProfileResponse
}

const waitForOwnedProfileIdentityReady = async (
  page: Page,
  expectedEmail: string,
  project: "desktop" | "mobile"
): Promise<void> => {
  const response = await page.request.get("/api/v1/users/me")
  reportAuthHttpStatus(project, "profile_identity_read", response.status())
  if (response.status() !== 200) {
    throw new Error("the notification-settings owner profile is not available")
  }
  const profile = (await response.json()) as { email?: unknown; full_name?: unknown }
  if (
    profile.email !== expectedEmail ||
    typeof profile.full_name !== "string" ||
    profile.full_name.length === 0
  ) {
    throw new Error("the notification-settings owner identity could not be verified")
  }

  const isMobile = (page.viewportSize()?.width ?? 1280) <= 1024
  await expect
    .poll(async () => {
      if (isMobile) {
        const buttons = page.getByRole("button", { name: "Открыть профиль", exact: true })
        const buttonCount = await buttons.count()
        let matchingVisibleButtons = 0
        for (let index = 0; index < buttonCount; index += 1) {
          const button = buttons.nth(index)
          if (!(await button.isVisible()) || !(await button.isEnabled())) continue
          const avatar = button.locator("img")
          if (
            (await avatar.count()) === 1 &&
            (await avatar.getAttribute("alt")) === `Аватар пользователя ${profile.full_name}`
          ) {
            matchingVisibleButtons += 1
          }
        }
        return matchingVisibleButtons === 1
      }

      const button = page.getByRole("button", {
        name: `Открыть профиль: ${profile.full_name}`,
        exact: true,
        includeHidden: true,
      })
      return (await button.count()) === 1 && (await button.isEnabled())
    }, "the signed-in notification owner is rendered in the profile navigation")
    .toBe(true)
}

const readTopicPreferences = async (
  page: Page,
  project: "desktop" | "mobile"
): Promise<PushTopicsResponse> => {
  const response = await page.request.get("/api/v1/push/topics")
  reportAuthHttpStatus(project, "push_topics_read", response.status())
  expect(response.status(), "the signed-in user can read only its canonical preferences").toBe(200)
  return (await response.json()) as PushTopicsResponse
}

const readAdminTopicPreferences = async (
  adminPage: Page,
  userId: string,
  project: "desktop" | "mobile"
): Promise<AdminUserTopicsResponse> => {
  const response = await adminPage.request.get(`/api/v1/push/admin/topics/${userId}`)
  reportAuthHttpStatus(project, "admin_topics_read", response.status())
  expect(response.status(), "admin can inspect the exact target's persisted preferences").toBe(200)
  return (await response.json()) as AdminUserTopicsResponse
}

const expectTopicSelection = async (page: Page, selectedTopics: readonly string[]) => {
  for (const topic of TOPICS) {
    const toggle = page.getByRole("switch", { name: topic.label, exact: true })
    if (selectedTopics.includes(topic.key)) await expect(toggle).toBeChecked()
    else await expect(toggle).not.toBeChecked()
  }
}

const deleteOnlyCreatedAccount = async (
  adminPage: Page,
  email: string,
  fullName: string,
  project: "desktop" | "mobile"
): Promise<void> => {
  const query = new URLSearchParams({ search: fullName, limit: "200" })
  const response = await adminPage.request.get(`/api/v1/users?${query.toString()}`)
  reportAuthHttpStatus(project, "admin_account_search", response.status())
  expect(response.status(), "admin can locate the test-owned synthetic account").toBe(200)

  const users = (await response.json()) as AdminUserRow[]
  const matches = users.filter((entry) => entry.email === email && entry.full_name === fullName)
  expect(
    matches.length,
    "the generated identity must resolve to at most one account"
  ).toBeLessThanOrEqual(1)

  const [match] = matches
  if (!match) return

  const deleted = await adminPage.evaluate(async (userId) => {
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
  reportAuthHttpStatus(project, "admin_account_delete", deleted.status)
  expect(deleted.status, "cleanup uses the CSRF-protected admin endpoint").toBe(200)
  expect(deleted.deleted, "cleanup deletes only the exact generated account id").toBe(true)
}

test("notification topics and quiet hours persist across reload and opt-out", async ({
  page,
  browser,
}, testInfo) => {
  const liveBaseUrl = process.env.LIVE_BASE_URL
  if (!liveBaseUrl) throw new Error("LIVE_BASE_URL must be set by the live acceptance runner")

  const identity = crypto.randomUUID()
  const email = `live-notification-${testInfo.project.name}-${identity}@university.dev`
  const fullName = `Live Notification Preferences ${testInfo.project.name} ${identity}`
  const password = freshPassword()
  let registrationAttempted = false
  let subscriptionMayExist = false
  let topicPatchRequests = 0

  page.on("request", (request) => {
    if (
      request.method() === "PATCH" &&
      new URL(request.url()).pathname === "/api/v1/push/subscribe/topics"
    ) {
      topicPatchRequests += 1
    }
  })

  const adminContext = await browser.newContext({
    baseURL: liveBaseUrl,
    ignoreHTTPSErrors: true,
    locale: "ru-RU",
  })
  const adminPage = await adminContext.newPage()

  try {
    const origin = new URL(liveBaseUrl).origin
    await page.context().grantPermissions(["notifications"], { origin })
    await loginAs(adminPage, "admin")
    await stubBreachedPasswordLookup(page)

    await page.goto("/register")
    await page.getByLabel("Имя", { exact: true }).fill(fullName)
    await page.getByRole("textbox", { name: "E-mail" }).fill(email)
    await page.getByLabel("Пароль", { exact: true }).fill(password)
    await page.getByLabel("Повторите пароль", { exact: true }).fill(password)
    await withLiveRegistrationAdmission(page, 1, async () => {
      registrationAttempted = true
      const expectedOrigin = new URL(page.url()).origin
      const registrationResponsePromise = page.waitForResponse((response) => {
        const request = response.request()
        const responseUrl = new URL(response.url())
        return (
          request.method() === "POST" &&
          responseUrl.origin === expectedOrigin &&
          responseUrl.pathname === "/api/v1/auth/register" &&
          responseUrl.search === "" &&
          responseUrl.hash === ""
        )
      })
      const result = await Promise.all([
        page.getByRole("button", { name: "Зарегистрироваться" }).click(),
        registrationResponsePromise,
      ])
      return result[1]
    })
    await expect(page).toHaveURL(/\/login/u)
    await loginWith(page, email, password)

    const createdProfile = await readProfile(page, diagnosticProject(testInfo.project.name))
    expect(createdProfile.email).toBe(email)
    expect(createdProfile.role, "registration creates the expected least-privileged role").toBe(
      "student"
    )

    await page.goto("/settings?tab=3")
    await expandPushAccordion(page)
    const pushSwitch = page.getByRole("switch", { name: "Включить уведомления", exact: true })
    await expect(pushSwitch).toBeVisible()
    await expect(pushSwitch).toBeEnabled()
    await expect(pushSwitch).not.toBeChecked()
    const browserBeforeOptIn = await page.evaluate(async () => {
      const registration = await navigator.serviceWorker.ready
      return {
        hasSubscription: (await registration.pushManager.getSubscription()) !== null,
        permission: Notification.permission,
      }
    })
    expect(browserBeforeOptIn.permission).toBe("granted")
    expect(browserBeforeOptIn.hasSubscription).toBe(false)

    const initialTopics = await readTopicPreferences(page, diagnosticProject(testInfo.project.name))
    expect(initialTopics.allowed).toEqual(TOPICS.map((topic) => topic.key))
    expect(initialTopics.topics).toEqual([])
    expect(initialTopics.has_preferences).toBe(false)
    await expectTopicSelection(
      page,
      TOPICS.map((topic) => topic.key)
    )

    // Before browser opt-in, topic changes are pending UI choices only. The
    // canonical server preference is persisted when the owned endpoint binds.
    for (const topic of TOPICS.filter((entry) => !SELECTED_TOPICS.includes(entry.key))) {
      await page.getByRole("switch", { name: topic.label, exact: true }).click()
    }
    await expectTopicSelection(page, SELECTED_TOPICS)
    expect(topicPatchRequests, "settings edits alone do not write without an owned endpoint").toBe(
      0
    )

    const subscriptionSaved = waitForPushAction(page, "/api/v1/push/subscribe", "POST")
    const topicSelectionSaved = waitForPushAction(page, "/api/v1/push/subscribe/topics", "PATCH")
    subscriptionMayExist = true
    await pushSwitch.click()
    const subscriptionResponse = await subscriptionSaved
    reportAuthHttpStatus(
      diagnosticProject(testInfo.project.name),
      "push_subscribe",
      subscriptionResponse.status()
    )
    expect(subscriptionResponse.status(), "explicit opt-in binds a native endpoint").toBe(200)
    const topicSelectionResponse = await topicSelectionSaved
    reportAuthHttpStatus(
      diagnosticProject(testInfo.project.name),
      "push_topics_initial",
      topicSelectionResponse.status()
    )
    expect(topicSelectionResponse.status(), "the selected topics persist for this endpoint").toBe(
      200
    )
    await expect(pushSwitch).toBeChecked()

    const ownerTopics = await readTopicPreferences(page, diagnosticProject(testInfo.project.name))
    expect(ownerTopics.allowed).toEqual(TOPICS.map((topic) => topic.key))
    expect(ownerTopics.topics).toEqual(SELECTED_TOPICS)
    expect(ownerTopics.has_preferences).toBe(true)
    const studentAdminRead = await page.request.get(
      `/api/v1/push/admin/topics/${createdProfile.id}`
    )
    reportAuthHttpStatus(
      diagnosticProject(testInfo.project.name),
      "student_admin_read",
      studentAdminRead.status()
    )
    expect(
      studentAdminRead.status(),
      "a student cannot use the administrator-only topic inspection route"
    ).toBe(403)
    const adminTopics = await readAdminTopicPreferences(
      adminPage,
      createdProfile.id,
      diagnosticProject(testInfo.project.name)
    )
    expect(adminTopics.user_id).toBe(createdProfile.id)
    expect(adminTopics.email).toBe(email)
    expect(adminTopics.allowed_topics).toEqual(TOPICS.map((topic) => topic.key))
    expect(adminTopics.topics).toEqual(SELECTED_TOPICS)

    await page.reload()
    await expandPushAccordion(page)
    await expect(
      page.getByRole("switch", { name: "Включить уведомления", exact: true })
    ).toBeChecked()
    await expectTopicSelection(page, SELECTED_TOPICS)
    expect(
      (await readTopicPreferences(page, diagnosticProject(testInfo.project.name))).topics
    ).toEqual(SELECTED_TOPICS)

    // An explicit empty topic list means opt out of every push topic. It must
    // remain distinct from the no-preference default after endpoint removal.
    for (const topic of TOPICS.filter((entry) => SELECTED_TOPICS.includes(entry.key))) {
      const topicSave = waitForPushAction(page, "/api/v1/push/subscribe/topics", "PATCH")
      await page.getByRole("switch", { name: topic.label, exact: true }).click()
      const response = await topicSave
      reportAuthHttpStatus(
        diagnosticProject(testInfo.project.name),
        "push_topics_optout",
        response.status()
      )
      expect(response.status(), `opting out of ${topic.key} persists`).toBe(200)
    }
    await expectTopicSelection(page, [])
    const allTopicsOptedOut = await readTopicPreferences(
      page,
      diagnosticProject(testInfo.project.name)
    )
    expect(allTopicsOptedOut.has_preferences).toBe(true)
    expect(allTopicsOptedOut.topics).toEqual([])
    expect(
      (
        await readAdminTopicPreferences(
          adminPage,
          createdProfile.id,
          diagnosticProject(testInfo.project.name)
        )
      ).topics
    ).toEqual([])

    const pushOptOut = waitForPushAction(page, "/api/v1/push/unsubscribe", "POST")
    await page.getByRole("switch", { name: "Включить уведомления", exact: true }).click()
    const pushOptOutResponse = await pushOptOut
    reportAuthHttpStatus(
      diagnosticProject(testInfo.project.name),
      "push_unsubscribe",
      pushOptOutResponse.status()
    )
    expect(
      pushOptOutResponse.status(),
      "push opt-out removes the endpoint owned by this user"
    ).toBe(200)
    const pushOptOutBody = (await pushOptOutResponse.json()) as { ok?: unknown; removed?: unknown }
    expect(pushOptOutBody.ok === true && pushOptOutBody.removed === true).toBe(true)
    const browserAfterPushOptOut = await page.evaluate(async () => {
      const registration = await navigator.serviceWorker.ready
      return (await registration.pushManager.getSubscription()) === null
    })
    expect(browserAfterPushOptOut, "the browser also revokes the test-owned subscription").toBe(
      true
    )
    subscriptionMayExist = false

    await page.reload()
    await expandPushAccordion(page)
    await expect(
      page.getByRole("switch", { name: "Включить уведомления", exact: true })
    ).not.toBeChecked()
    await expectTopicSelection(page, [])
    const optedOutTopicsAfterReload = await readTopicPreferences(
      page,
      diagnosticProject(testInfo.project.name)
    )
    expect(optedOutTopicsAfterReload.has_preferences).toBe(true)
    expect(optedOutTopicsAfterReload.topics).toEqual([])
    const optedOutAdminTopics = await readAdminTopicPreferences(
      adminPage,
      createdProfile.id,
      diagnosticProject(testInfo.project.name)
    )
    expect(optedOutAdminTopics.user_id).toBe(createdProfile.id)
    expect(optedOutAdminTopics.topics).toEqual([])
    expect(topicPatchRequests).toBe(1 + SELECTED_TOPICS.length)

    const topicPatchRequestsBeforeRebind = topicPatchRequests
    const optedOutPushRebind = waitForPushAction(page, "/api/v1/push/subscribe", "POST")
    subscriptionMayExist = true
    await pushSwitch.click()
    const reboundSubscription = await optedOutPushRebind
    reportAuthHttpStatus(
      diagnosticProject(testInfo.project.name),
      "push_rebind",
      reboundSubscription.status()
    )
    expect(
      reboundSubscription.status(),
      "push can be re-enabled after explicit topic opt-out"
    ).toBe(200)
    await expect(pushSwitch).toBeChecked()
    await expectTopicSelection(page, [])
    const reboundTopics = await readTopicPreferences(page, diagnosticProject(testInfo.project.name))
    expect(reboundTopics.has_preferences).toBe(true)
    expect(reboundTopics.topics).toEqual([])
    expect(topicPatchRequests).toBe(topicPatchRequestsBeforeRebind)

    await page.reload()
    await expandPushAccordion(page)
    await expect(pushSwitch).toBeChecked()
    await expectTopicSelection(page, [])
    const reboundTopicsAfterReload = await readTopicPreferences(
      page,
      diagnosticProject(testInfo.project.name)
    )
    expect(reboundTopicsAfterReload.has_preferences).toBe(true)
    expect(reboundTopicsAfterReload.topics).toEqual([])
    expect(
      (
        await readAdminTopicPreferences(
          adminPage,
          createdProfile.id,
          diagnosticProject(testInfo.project.name)
        )
      ).topics
    ).toEqual([])

    await waitForOwnedProfileIdentityReady(
      page,
      createdProfile.email,
      diagnosticProject(testInfo.project.name)
    )
    const quietHours = page.getByRole("switch", { name: "Включить тихий период" })
    const startTime = page.getByLabel("С", { exact: true })
    const endTime = page.getByLabel("До", { exact: true })

    await expect(quietHours).toBeVisible()
    await expect(quietHours).not.toBeChecked()

    const enableSave = waitForProfileUpdate(page)
    await quietHours.click()
    const enabledResponse = await enableSave
    reportAuthHttpStatus(
      diagnosticProject(testInfo.project.name),
      "profile_update_enable",
      enabledResponse.status()
    )
    expect(enabledResponse.status(), "enabling quiet hours persists through /users/me").toBe(200)
    await expect(quietHours).toBeChecked()
    await expect(startTime).toHaveValue("22:00")
    await expect(endTime).toHaveValue("07:00")

    const startSave = waitForProfileUpdate(page)
    await startTime.fill("21:35")
    await startTime.press("Tab")
    const startResponse = await startSave
    reportAuthHttpStatus(
      diagnosticProject(testInfo.project.name),
      "profile_update_start",
      startResponse.status()
    )
    expect(startResponse.status(), "editing the start time persists through /users/me").toBe(200)
    await expect(startTime).toBeEnabled()

    const endSave = waitForProfileUpdate(page)
    await endTime.fill("06:45")
    await endTime.press("Tab")
    const endResponse = await endSave
    reportAuthHttpStatus(
      diagnosticProject(testInfo.project.name),
      "profile_update_end",
      endResponse.status()
    )
    expect(endResponse.status(), "editing the end time persists through /users/me").toBe(200)
    await expect(endTime).toBeEnabled()

    await page.reload()
    await expandPushAccordion(page)
    await expect(page.getByRole("switch", { name: "Включить тихий период" })).toBeChecked()
    await expect(page.getByLabel("С", { exact: true })).toHaveValue("21:35")
    await expect(page.getByLabel("До", { exact: true })).toHaveValue("06:45")

    const persistedProfile = await readProfile(page, diagnosticProject(testInfo.project.name))
    expect(persistedProfile.dnd_enabled).toBe(true)
    expect(persistedProfile.dnd_start).toMatch(/^21:35(?::00)?$/u)
    expect(persistedProfile.dnd_end).toMatch(/^06:45(?::00)?$/u)
    expect(createdProfile.id).toMatch(/^[0-9a-f-]{36}$/iu)

    const equalStartSave = waitForProfileUpdate(page)
    await startTime.fill("00:00")
    await startTime.press("Tab")
    const equalStartResponse = await equalStartSave
    reportAuthHttpStatus(
      diagnosticProject(testInfo.project.name),
      "profile_update_midnight_start",
      equalStartResponse.status()
    )
    expect(equalStartResponse.status(), "the midnight start boundary is accepted").toBe(200)

    const equalEndSave = waitForProfileUpdate(page)
    await endTime.fill("00:00")
    await endTime.press("Tab")
    const equalEndResponse = await equalEndSave
    reportAuthHttpStatus(
      diagnosticProject(testInfo.project.name),
      "profile_update_midnight_end",
      equalEndResponse.status()
    )
    expect(equalEndResponse.status(), "matching midnight endpoints are accepted").toBe(200)

    await page.reload()
    await expandPushAccordion(page)
    await expect(quietHours).toBeChecked()
    await expect(startTime).toHaveValue("00:00")
    await expect(endTime).toHaveValue("00:00")
    const equalBoundaryProfile = await readProfile(page, diagnosticProject(testInfo.project.name))
    expect(equalBoundaryProfile.dnd_enabled).toBe(true)
    expect(equalBoundaryProfile.dnd_start).toMatch(/^00:00(?::00)?$/u)
    expect(equalBoundaryProfile.dnd_end).toMatch(/^00:00(?::00)?$/u)

    const disableSave = waitForProfileUpdate(page)
    await quietHours.click()
    const disabledResponse = await disableSave
    reportAuthHttpStatus(
      diagnosticProject(testInfo.project.name),
      "profile_update_disable",
      disabledResponse.status()
    )
    expect(disabledResponse.status(), "disabling quiet hours persists through /users/me").toBe(200)
    await expect(quietHours).not.toBeChecked()

    await page.reload()
    await expandPushAccordion(page)
    const quietHoursAfterOptOut = page.getByRole("switch", { name: "Включить тихий период" })
    await expect(quietHoursAfterOptOut).not.toBeChecked()
    const optedOutProfile = await readProfile(page, diagnosticProject(testInfo.project.name))
    expect(optedOutProfile.dnd_enabled).toBe(false)
    expect(optedOutProfile.dnd_start).toBeNull()
    expect(optedOutProfile.dnd_end).toBeNull()
  } finally {
    try {
      if (subscriptionMayExist) {
        const cleanup = await page
          .evaluate(async () => {
            const registration = await navigator.serviceWorker.getRegistration()
            const subscription = await registration?.pushManager.getSubscription()
            if (!subscription) return { serverRemoved: true, browserRevoked: true }

            const csrfCookie = document.cookie
              .split(";")
              .map((part) => part.trim())
              .find((part) => part.startsWith("csrf_token="))
            if (!csrfCookie) {
              return { serverRemoved: false, browserRevoked: await subscription.unsubscribe() }
            }

            const csrfToken = decodeURIComponent(csrfCookie.slice("csrf_token=".length))
            const response = await fetch("/api/v1/push/unsubscribe", {
              method: "POST",
              credentials: "same-origin",
              headers: {
                "Content-Type": "application/json",
                "X-CSRF-Token": csrfToken,
              },
              body: JSON.stringify({ endpoint: subscription.endpoint }),
            })
            const body = (await response.json().catch(() => null)) as {
              removed?: unknown
            } | null
            return {
              serverRemoved: response.ok && body?.removed === true,
              browserRevoked: await subscription.unsubscribe(),
            }
          })
          .catch(() => ({ serverRemoved: false, browserRevoked: false }))
        expect(
          cleanup.serverRemoved && cleanup.browserRevoked,
          "a failed run must remove only its browser endpoint before account cleanup"
        ).toBe(true)
      }
    } finally {
      try {
        if (registrationAttempted)
          await deleteOnlyCreatedAccount(
            adminPage,
            email,
            fullName,
            diagnosticProject(testInfo.project.name)
          )
      } finally {
        await adminContext.close()
      }
    }
  }
})
