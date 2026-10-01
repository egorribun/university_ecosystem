import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { URL } from "node:url"
import test from "node:test"

const rootUrl = new URL("../../../", import.meta.url)
const fixtureUrl = new URL("./fixtures.ts", import.meta.url)
const read = (path) => readFile(new URL(path, rootUrl), "utf8")

test("avatar UI validation matches the image API and live acceptance stays owner-bounded", async () => {
  const [backend, avatarHook, coverHook, profileSection, english, russian, spec, fixtures] =
    await Promise.all([
      read("app/utils/files.py"),
      read("frontend/src/pages/settings/hooks/useAvatarUpload.ts"),
      read("frontend/src/pages/settings/hooks/useCoverUpload.ts"),
      read("frontend/src/pages/settings/sections/ProfileSection.tsx"),
      read("frontend/src/i18n/locales/en/settings.json"),
      read("frontend/src/i18n/locales/ru/settings.json"),
      read("frontend/tests/e2e-live/avatar-persistence.live.spec.ts"),
      readFile(fixtureUrl, "utf8"),
    ])

  assert.match(
    backend,
    /ALLOWED_IMAGE_TYPES:[\s\S]*?"image\/jpeg"[\s\S]*?"image\/png"[\s\S]*?"image\/webp"/u
  )
  assert.match(backend, /MAX_IMAGE_SIZE:[\s\S]*?5 \* 1024 \* 1024/u)
  for (const hook of [avatarHook, coverHook]) {
    assert.match(hook, /MAX_FILE_SIZE_BYTES\s*=\s*5 \* 1024 \* 1024/u)
    assert.match(hook, /new Set\(\["image\/png", "image\/jpeg", "image\/webp"\]\)/u)
    assert.match(hook, /file\.size <= MAX_FILE_SIZE_BYTES/u)
  }

  assert.equal(
    (profileSection.match(/accept="image\/png,image\/jpeg,image\/webp"/gu) ?? []).length,
    2,
    "both profile image pickers advertise only API-supported formats"
  )
  assert.match(english, /"supportedFormats":\s*"Supported formats: PNG, JPG, WebP"/u)
  assert.match(english, /"fileTooLarge":\s*"File is larger than 5 MB"/u)
  assert.match(english, /"subtitle":\s*"PNG, JPG, or WebP up to 5 MB"/u)
  assert.match(russian, /"supportedFormats":\s*"Поддерживаются форматы: PNG, JPG, WebP"/u)
  assert.match(russian, /"fileTooLarge":\s*"Файл больше 5 МБ"/u)
  assert.match(russian, /"subtitle":\s*"PNG, JPG или WebP до 5 МБ"/u)

  assert.match(spec, /avatar upload persists across reload and rolls back server-rejected content/u)
  assert.ok(
    /avatar upload persists across reload and rolls back server-rejected content/u.test(spec),
    "the live avatar acceptance must cover a client-accepted file rejected by server content validation"
  )
  assert.match(spec, /crypto\.randomUUID\(\)/u)
  assert.match(spec, /live-avatar-\$\{testInfo\.project\.name\}-\$\{identity\}@university\.dev/u)
  assert.match(spec, /name:\s*"synthetic-avatar\.png"[\s\S]*?mimeType:\s*"image\/png"/u)
  assert.match(spec, /name:\s*"invalid-content-avatar\.png"[\s\S]*?mimeType:\s*"image\/png"/u)
  assert.match(spec, /Buffer\.from\("not a valid PNG image"\)/u)
  assert.match(spec, /rejectedImageResponse\.status\(\)[\s\S]*?\.toBe\(415\)/u)
  assert.match(spec, /postsBeforeServerRejectedImage \+ 1/u)
  assert.match(spec, /Couldn't upload avatar/u)
  assert.match(
    spec,
    /expect\(\(await readOwnerProfile\(page\)\)\.avatar_url\)\.toBe\(savedProfile\.avatar_url\)/u
  )
  const rejectedContentResponse = spec.indexOf(
    "const rejectedImageResponse = await rejectedImageUpload"
  )
  const rejectedContentReload = spec.indexOf("await page.reload()", rejectedContentResponse)
  const restoredAvatarCheck = spec.indexOf(
    "const savedAvatarRestoredAfterRejectedReload =",
    rejectedContentResponse
  )
  assert.ok(
    rejectedContentResponse >= 0 &&
      rejectedContentReload > rejectedContentResponse &&
      restoredAvatarCheck > rejectedContentReload &&
      /savedAvatarRestoredAfterRejectedReload,[\s\S]*?\.toBe\(true\)/u.test(
        spec.slice(restoredAvatarCheck)
      ),
    "after the API rejects invalid image bytes, reload must preserve the previous owner avatar in both profile data and UI"
  )
  assert.match(spec, /await page\.reload\(\)/u)
  assert.match(spec, /savedResponse\.request\(\)\.allHeaders\(\)/u)
  assert.match(spec, /Boolean\(uploadRequestHeaders\["x-csrf-token"\]\)/u)
  assert.match(spec, /avatarPostCount, "unsupported MIME types are rejected before upload"/u)
  assert.match(spec, /avatarPostCount, "oversized files are rejected before upload"/u)
  assert.match(spec, /Buffer\.alloc\(5 \* 1024 \* 1024 \+ 1\)/u)
  assert.match(
    spec,
    /expect\(\(await readOwnerProfile\(page\)\)\.avatar_url\)\.toBe\(savedProfile\.avatar_url\)/u
  )
  assert.equal(
    (
      spec.match(
        /expect\(await reloadedAvatar\.getAttribute\("src"\)\)\.toBe\(persistedAvatarSrc\)/gu
      ) ?? []
    ).length,
    3,
    "server-rejected content and client-rejected files preserve the displayed persisted avatar"
  )
  assert.match(spec, /await removeOwnerAvatar\(page\)/u)
  assert.match(spec, /entry\.email === email && entry\.full_name === fullName/u)
  assert.match(spec, /headers:\s*\{\s*"X-CSRF-Token": csrfToken\s*\}/u)
  assert.doesNotMatch(spec, /adminPage\.request\.delete\(/u)
  assert.doesNotMatch(spec, /return\s+csrfToken|console\.(?:log|info)\([^\n]*csrfToken/u)
  assert.doesNotMatch(spec, /page\.route|routeWebSocket|vi\.mock/u)
  assert.match(spec, /stubBreachedPasswordLookup\(page\)/u)
  assert.equal(
    (fixtures.match(/page\.route\(/gu) ?? []).length,
    1,
    "the live avatar flow only intercepts its third-party password-range lookup"
  )
  assert.match(fixtures, /await page\.route\("https:\/\/api\.pwnedpasswords\.com\/\*\*"/u)
})
