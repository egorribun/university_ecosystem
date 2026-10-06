import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { URL } from "node:url"
import test from "node:test"
import {
  comparePersistedAvatarIdentity,
  renderedAvatarResourceMatches,
} from "./avatar-resource-identity.mjs"

const rootUrl = new URL("../../../", import.meta.url)
const fixtureUrl = new URL("./fixtures.ts", import.meta.url)
const read = (path) => readFile(new URL(path, rootUrl), "utf8")

test("avatar UI validation matches the image API and live acceptance stays owner-bounded", async () => {
  const [
    backend,
    uploads,
    avatarHook,
    coverHook,
    profileSection,
    english,
    russian,
    spec,
    fixtures,
  ] = await Promise.all([
    read("app/utils/files.py"),
    read("frontend/src/constants/uploads.ts"),
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
  assert.match(uploads, /export const MAX_IMAGE_UPLOAD_BYTES\s*=\s*5 \* 1024 \* 1024/u)
  for (const hook of [avatarHook, coverHook]) {
    assert.match(hook, /import \{ MAX_IMAGE_UPLOAD_BYTES \} from "@\/constants\/uploads"/u)
    assert.match(hook, /new Set\(\["image\/png", "image\/jpeg", "image\/webp"\]\)/u)
    assert.match(hook, /file\.size <= MAX_IMAGE_UPLOAD_BYTES/u)
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
    1,
    "same-mount server rejection preserves the exact displayed resource"
  )
  assert.equal(
    (
      spec.match(
        /expect\(await reloadedAvatar\.getAttribute\("src"\)\)\.toBe\(rejectedReloadedAvatarSrc\)/gu
      ) ?? []
    ).length,
    2,
    "client-side rejections preserve the post-reload rendered resource and its cache version"
  )
  assert.match(
    spec,
    /const mediaOrigin = process\.env\.VITE_BACKEND_ORIGIN \?\? ""/u,
    "profile URL resolution uses the explicitly configured origin, including relative-path mode"
  )
  assert.match(
    spec,
    /await expectSavedAvatarSourceReady\(page, avatar, savedProfile\.avatar_url\)[\s\S]*?await expectImageDecoded\(avatar/u,
    "successful profile refresh and enabled UI state precede the same-mount decode check"
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

test("profile-backed avatar readiness allows only the regenerated cache token", () => {
  const baseUrl = "https://app.example.test/settings/profile"
  const renderedFromProfile = "/api/v1/img/avatars/saved.png?_v=profile-check"
  const currentRender = "https://app.example.test/api/v1/img/avatars/saved.png?_v=live-render"
  assert.equal(renderedAvatarResourceMatches(renderedFromProfile, currentRender, baseUrl), true)
  assert.deepEqual(
    comparePersistedAvatarIdentity({
      savedProfileAvatarUrl: "/static/avatars/saved.png",
      reloadedProfileAvatarUrl: "/static/avatars/saved.png",
      savedRenderedSrc: renderedFromProfile,
      reloadedRenderedSrc: currentRender,
      baseUrl,
    }),
    { profileValueMatches: true, renderedSourceMatches: true }
  )
})

test("profile-backed avatar readiness rejects optimistic or changed resources", () => {
  const baseUrl = "https://app.example.test/settings/profile"
  const saved = "/api/v1/img/avatars/saved.png?_v=profile-check"
  const withUserInfo = new URL(saved, baseUrl)
  withUserInfo.username = String.fromCodePoint(97)
  withUserInfo.password = String.fromCodePoint(98)
  const withDuplicateVersion = new URL(saved, baseUrl)
  withDuplicateVersion.searchParams.append("_v", String(2))
  const savedWithOptions = "/api/v1/img/avatars/saved.png?format=webp&width=96&_v=profile-check"
  const changedQueryValue = "/api/v1/img/avatars/saved.png?format=webp&width=128&_v=live-render"
  const reorderedQuery = "/api/v1/img/avatars/saved.png?width=96&format=webp&_v=live-render"

  for (const current of [
    "blob:https://app.example.test/local-preview",
    "data:image/png;base64,AA==",
    "/api/v1/img/avatars/other.png?_v=live-render",
    "https://cdn.example.test/api/v1/img/avatars/saved.png?_v=live-render",
    "https://gravatar.com/avatar/default?_v=live-render",
    "/api/v1/img/avatars/saved.png",
    withDuplicateVersion.toString(),
    withUserInfo.toString(),
    "/api/v1/img/avatars/saved.png?quality=80&_v=live-render",
    "/api/v1/img/avatars/saved.png?_v=live-render#different",
  ]) {
    assert.equal(renderedAvatarResourceMatches(saved, current, baseUrl), false)
  }
  assert.equal(renderedAvatarResourceMatches(savedWithOptions, changedQueryValue, baseUrl), false)
  assert.equal(renderedAvatarResourceMatches(savedWithOptions, reorderedQuery, baseUrl), false)

  assert.deepEqual(
    comparePersistedAvatarIdentity({
      savedProfileAvatarUrl: "/static/avatars/saved.png",
      reloadedProfileAvatarUrl: "/static/avatars/changed.png",
      savedRenderedSrc: saved,
      reloadedRenderedSrc: saved,
      baseUrl,
    }),
    { profileValueMatches: false, renderedSourceMatches: true }
  )
})
