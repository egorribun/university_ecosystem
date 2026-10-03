import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { URL } from "node:url"
import test from "node:test"

const rootUrl = new URL("../../../", import.meta.url)
const specUrl = new URL("./settings-password-change-rollback.live.spec.ts", import.meta.url)
const read = (path) => readFile(new URL(path, rootUrl), "utf8")

test("live password-settings acceptance proves invalid-change rollback and persisted correction", async () => {
  let spec
  try {
    spec = await readFile(specUrl, "utf8")
  } catch {
    assert.fail("the live password-settings browser scenario must exist")
  }

  const [config, api, service, schema, hook, section, fixtures] = await Promise.all([
    read("frontend/playwright.live.config.ts"),
    read("app/api/users.py"),
    read("app/services/auth_service.py"),
    read("app/schemas/identity.py"),
    read("frontend/src/pages/settings/hooks/usePasswordChange.ts"),
    read("frontend/src/pages/settings/sections/PasswordSection.tsx"),
    read("frontend/tests/e2e-live/fixtures.ts"),
  ])

  assert.match(config, /name:\s*["']desktop["']/u)
  assert.match(config, /name:\s*["']mobile["']/u)
  assert.match(config, /trace:\s*["']off["']/u)
  assert.match(config, /screenshot:\s*["']off["']/u)
  assert.match(config, /video:\s*["']off["']/u)
  assert.match(api, /@users_router\.post\(\s*["']\/me\/password["']/u)
  assert.match(
    service,
    /if not await verify_password\([\s\S]*?payload\.current_password[\s\S]*?raise_validation_error\(["']errors\.users\.invalid_password/u
  )
  const changePassword = service.slice(
    service.indexOf("async def change_password("),
    service.indexOf("async def refresh_pending_email(")
  )
  const invalidPassword = changePassword.indexOf(
    'raise_validation_error("errors.users.invalid_password"'
  )
  const credentialUpdate = changePassword.indexOf(
    "await self.user_repo.change_password_if_current("
  )
  assert.ok(
    invalidPassword >= 0 && credentialUpdate > invalidPassword,
    "the current password is verified before the atomic credential update"
  )
  assert.match(
    changePassword,
    /change_password_if_current\([\s\S]*?expected_hash=verified_hash, new_hash=hashed_password[\s\S]*?if next_epoch is None:[\s\S]*?raise_unauthorized/u,
    "a concurrently replaced credential fails closed rather than being overwritten"
  )
  assert.match(
    schema,
    /class UserPasswordChangeIn[\s\S]*?new_password:\s*str = Field\(min_length=8/u
  )
  assert.match(hook, /api\.post<\{[\s\S]*?\}>\(["']\/users\/me\/password["']/u)
  assert.match(hook, /setCurrentPasswordError\(detail\)/u)
  assert.match(section, /currentPasswordError/u)
  assert.match(section, /label=\{t\("settings:security\.password\.currentLabel"\)\}/u)
  assert.match(section, /onSubmit=|onSubmit\(\)/u)
  assert.match(fixtures, /export async function loginWith\(/u)
  assert.match(fixtures, /export async function stubBreachedPasswordLookup\(/u)

  assert.match(
    spec,
    /password settings reject a wrong current password and persist a corrected change/u
  )
  assert.match(spec, /crypto\.randomUUID\(\)/u)
  assert.match(spec, /freshPassword\(\)/u)
  assert.match(spec, /stubBreachedPasswordLookup\(page\)/u)
  assert.match(spec, /await loginWith\(page, email, currentPassword\)/u)
  assert.match(
    spec,
    /currentPasswordField\.fill\(incorrectCurrentPassword\)[\s\S]*?failedResponse\.status\(\)[\s\S]*?\.toBe\(400\)/u
  )
  assert.match(
    spec,
    /await expect\(currentPasswordField\)\.toHaveAttribute\("aria-invalid", "true"\)/u
  )
  assert.match(
    spec,
    /await page\.reload\(\)[\s\S]*?await openPasswordSection\(page\)[\s\S]*?const reloadedPasswordInputValues = await Promise\.all\([\s\S]*?currentPasswordField\.inputValue\(\)[\s\S]*?newPasswordField\.inputValue\(\)[\s\S]*?confirmPasswordField\.inputValue\(\)[\s\S]*?const passwordInputsAreCleared = reloadedPasswordInputValues\.every\(\(value\) => value === ""\)[\s\S]*?const passwordErrorIsCleared = \(await page\.getByRole\("alert"\)\.count\(\)\) === 0[\s\S]*?const passwordFormRestoredAfterReload =[\s\S]*?expect\(\s*passwordFormRestoredAfterReload,[\s\S]*?\.toBe\(true\)/u,
    "after the server rejects a change, reload restores the original empty password form without exposing field contents"
  )
  assert.match(spec, /loginWith\(verificationPage, email, currentPassword\)/u)
  assert.match(spec, /savedResponse\.status\(\)[\s\S]*?\.toBe\(200\)/u)
  assert.match(spec, /await page\.reload\(\)/u)
  assert.match(spec, /loginWith\(updatedPage, email, updatedPassword\)/u)
  assert.match(spec, /\/api\/v1\/users\/me\/password/u)
  assert.match(spec, /entry\.email === email && entry\.full_name === fullName/u)
  assert.match(spec, /X-CSRF-Token/u)
  assert.doesNotMatch(spec, /console\.(?:log|info|warn|error)\(/u)
  assert.doesNotMatch(spec, /page\.route\(["']\*\*\/api|routeWebSocket/u)
})
