import {
  awaitMail,
  expect,
  freshPassword,
  loginWith,
  stubBreachedPasswordLookup,
  submitLogin,
  test,
} from "./fixtures"

const RESET_LINK = /\/reset-password\?token=([\w.~-]+)/

test("a new student registers, resets the password from the e-mail link and signs in", async ({
  page,
}, testInfo) => {
  await stubBreachedPasswordLookup(page)
  const email = `live-${testInfo.project.name}-${Date.now()}@university.dev`
  const firstPassword = freshPassword()
  const newPassword = freshPassword()

  await page.goto("/register")
  await page.getByLabel("Имя", { exact: true }).fill("Live Acceptance")
  await page.getByRole("textbox", { name: "E-mail" }).fill(email)
  await page.getByLabel("Пароль", { exact: true }).fill(firstPassword)
  await page.getByLabel("Повторите пароль", { exact: true }).fill(firstPassword)
  await page.getByRole("button", { name: "Зарегистрироваться" }).click()
  await expect(page).toHaveURL(/\/login/)
  await loginWith(page, email, firstPassword)
  await page.context().clearCookies()

  await page.goto("/forgot-password")
  await page.getByRole("textbox", { name: "E-mail" }).fill(email)
  await page.getByRole("button", { name: "Отправить ссылку" }).click()
  await expect(page.getByText("Проверьте почту")).toBeVisible()

  const [, token] = await awaitMail(email, RESET_LINK)
  await page.goto(`/reset-password?token=${token}`)
  await page.getByLabel("Пароль", { exact: true }).fill(newPassword)
  await page.getByLabel("Повторите пароль", { exact: true }).fill(newPassword)
  await page.getByRole("button", { name: "Сохранить пароль" }).click()
  await expect(page.getByText("Пароль обновлён")).toBeVisible()

  await submitLogin(page, email, firstPassword)
  await expect(page.getByRole("alert")).toBeVisible()
  await expect(page).toHaveURL(/\/login/)
  await loginWith(page, email, newPassword)
  await page.context().clearCookies()

  // The link is single-use: a second reset with the same token is refused.
  await page.goto(`/reset-password?token=${token}`)
  const replayPassword = freshPassword()
  await page.getByLabel("Пароль", { exact: true }).fill(replayPassword)
  await page.getByLabel("Повторите пароль", { exact: true }).fill(replayPassword)
  await page.getByRole("button", { name: "Сохранить пароль" }).click()
  await expect(page.getByRole("alert")).toBeVisible()
  await expect(page.getByText("Пароль обновлён")).toBeHidden()
  await submitLogin(page, email, replayPassword)
  await expect(page).toHaveURL(/\/login/)
})
