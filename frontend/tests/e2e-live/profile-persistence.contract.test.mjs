import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { URL } from "node:url"
import test from "node:test"
import { isProfileMutationRequest } from "./profile-mutation-domain.mjs"

const specUrl = new URL("./profile-persistence.live.spec.ts", import.meta.url)
const configUrl = new URL("../../playwright.live.config.ts", import.meta.url)
const profilePageUrl = new URL("../../src/pages/Profile.tsx", import.meta.url)
const profileEditorUrl = new URL("../../src/components/profile/ProfileEditor.tsx", import.meta.url)
const usersApiUrl = new URL("../../../app/api/users.py", import.meta.url)
const usersSchemaUrl = new URL("../../../app/schemas/users.py", import.meta.url)
const userMapperUrl = new URL("../../../app/schemas/mappers/user_mapper.py", import.meta.url)
const usersModelUrl = new URL("../../../app/models/users.py", import.meta.url)
const profileBoundsMigrationUrl = new URL(
  "../../../alembic/versions/202602270002_bound_user_profile_string_columns.py",
  import.meta.url
)
const fixtureUrl = new URL("./fixtures.ts", import.meta.url)
const packageUrl = new URL("../../package.json", import.meta.url)

test("profile mutation tracking includes writes only within the users API domain", () => {
  const writeMethods = ["POST", "PUT", "PATCH", "DELETE"]
  const userPaths = [
    "/api/v1/users",
    "/api/v1/users/",
    "/api/v1/users/me",
    "/api/v1/users/me/avatar",
  ]
  const unrelatedPaths = [
    "/api/v1/users-extra",
    "/api/v1/notifications/check-schedule",
    "/api/v1/auth/refresh",
    "/api/v1/push/subscribe",
  ]

  for (const method of writeMethods) {
    for (const pathname of userPaths) {
      assert.equal(isProfileMutationRequest(method, pathname), true, method + " " + pathname)
    }
    for (const pathname of unrelatedPaths) {
      assert.equal(isProfileMutationRequest(method, pathname), false, method + " " + pathname)
    }
  }

  for (const method of ["GET", "HEAD", "OPTIONS"]) {
    assert.equal(isProfileMutationRequest(method, "/api/v1/users/me"), false, method)
  }
})

test("live profile persistence covers real self-edit and cleans only its synthetic user", async () => {
  let spec
  try {
    spec = await readFile(specUrl, "utf8")
  } catch {
    assert.fail("the live profile-persistence browser scenario must exist")
  }
  const [
    config,
    profilePage,
    profileEditor,
    usersApi,
    usersSchema,
    userMapper,
    usersModel,
    profileBoundsMigration,
    fixtures,
    packageJson,
  ] = await Promise.all([
    readFile(configUrl, "utf8"),
    readFile(profilePageUrl, "utf8"),
    readFile(profileEditorUrl, "utf8"),
    readFile(usersApiUrl, "utf8"),
    readFile(usersSchemaUrl, "utf8"),
    readFile(userMapperUrl, "utf8"),
    readFile(usersModelUrl, "utf8"),
    readFile(profileBoundsMigrationUrl, "utf8"),
    readFile(fixtureUrl, "utf8"),
    readFile(packageUrl, "utf8"),
  ])

  assert.match(usersApi, /@users_router\.put\(\s*["']\/me["']/u)
  assert.match(
    usersApi,
    /@users_router\.put\(\s*["']\/me["'][\s\S]*?user:\s*UserAuthDTO\s*=\s*Depends\(deps\.get_current_user_auth_dto\)[\s\S]*?service\.update_user_profile\(user, data, request\)/u,
    "the profile mutation is authenticated and scoped to the current user"
  )
  assert.match(usersSchema, /class UserProfileUpdate[\s\S]*?full_name:\s*str \| None/u)
  assert.match(usersSchema, /profile_detail:\s*UserProfileBase \| None/u)
  assert.match(
    userMapper,
    /"profile_detail":\s*\(\s*\{\s*"about":\s*get_attr\(profile,\s*"about"\)/u,
    "the owner response serializes the nested field consumed by the profile editor"
  )
  assert.match(usersModel, /about:\s*Mapped\[str \| None\]\s*=\s*mapped_column\(String\(4096\)/u)
  assert.match(profileBoundsMigration, /\("about",\s*4096\)/u)
  assert.match(profilePage, /api\.put<User>\(["']\/users\/me["']/u)
  assert.match(profilePage, /full_name:\s*fullName/u)
  assert.match(
    profilePage,
    /user\?\.profile_detail\?\.about/u,
    "the profile screen renders the nested profile detail returned by the owner API"
  )
  assert.match(profilePage, /profile_detail:\s*\{\s*about/u)
  assert.match(profileEditor, /id="profile-full-name"/u)
  assert.match(profileEditor, /id="profile-about"/u)

  assert.match(
    spec,
    /profile editor cancellation and rejected oversized save preserve values before success/u
  )
  assert.match(spec, /crypto\.randomUUID\(\)/u)
  assert.match(spec, /freshPassword\(\)/u)
  assert.match(spec, /loginWith\(page, email, password\)/u)
  assert.match(spec, /expect\(createdProfile\.role\)\.toBe\("student"\)/u)
  assert.match(spec, /loginAs\(adminPage, "admin"\)/u)
  assert.match(
    spec,
    /interface OwnerProfileResponse[\s\S]*?profile_detail:\s*\{\s*about:\s*string \| null\s*\}\s*\|\s*null/u,
    "the owner API response type includes the nested UI profile payload"
  )
  assert.match(
    spec,
    /const ownerAbout = \(profile: OwnerProfileResponse\): string => profile\.profile_detail\?\.about \?\? ""/u,
    "owner profile verification reads the nested payload used by the UI"
  )
  assert.match(
    spec,
    /const initialAbout = ownerAbout\(createdProfile\)/u,
    "the persisted baseline is read from the same nested path as the profile UI"
  )
  assert.match(spec, /expect\(savedProfile\.profile_detail\?\.about\)\.toBe\(about\)/u)
  assert.match(spec, /expect\(reloadedProfile\.profile_detail\?\.about\)\.toBe\(about\)/u)
  assert.match(spec, /getByLabel\("Имя",\s*\{\s*exact:\s*true\s*\}\)/u)
  assert.match(spec, /getByLabel\("О себе",\s*\{\s*exact:\s*true\s*\}\)/u)
  assert.match(spec, /await expect\(aboutField\)\.toHaveValue\(initialAbout\)/u)
  assert.match(spec, /await page\.reload\(\)/u)
  assert.match(spec, /const oversizedAbout = "x"\.repeat\(4097\)/u)
  assert.match(spec, /await expect\(profileFeedback\.getByRole\("alert"\)\)\.toBeVisible\(\)/u)
  assert.match(spec, /expect\(rejectedProfile\.full_name\)\.toBe\(initialName\)/u)
  assert.match(spec, /expect\(ownerAbout\(rejectedProfile\)\)\.toBe\(initialAbout\)/u)
  assert.match(spec, /retainedDraft\.length\)\.toBe\(oversizedAbout\.length\)/u)
  assert.match(spec, /expect\(retainedDraft === oversizedAbout\)\.toBe\(true\)/u)
  assert.match(
    spec,
    /expect\(profileMutationPaths\)\.toEqual\(\[\s*"PUT \/api\/v1\/users\/me",\s*"PUT \/api\/v1\/users\/me",?\s*\]\)/u,
    "the owned profile flow writes only its self-profile endpoint"
  )
  assert.match(
    spec,
    /import \{ isProfileMutationRequest \} from "\.\/profile-mutation-domain\.mjs"/u,
    "the collector uses the tested profile mutation predicate"
  )
  assert.match(
    spec,
    /if \(isProfileMutationRequest\(method, path\)\)/u,
    "the profile path assertion is scoped through the tested predicate"
  )
  assert.match(spec, /const cancelledName = /u)
  assert.match(spec, /const cancelledAbout = /u)
  assert.match(spec, /getByRole\("button",\s*\{\s*name: "ОТМЕНА", exact: true\s*\}\)\.click\(\)/u)
  assert.match(spec, /expect\(profileUpdateRequests\)\.toBe\(0\)/u)
  assert.match(spec, /const cancelledProfile = await readOwnerProfile\(page\)/u)
  assert.match(spec, /expect\(cancelledProfile\.full_name\)\.toBe\(initialName\)/u)
  assert.match(spec, /expect\(ownerAbout\(cancelledProfile\)\)\.toBe\(initialAbout\)/u)
  assert.ok(
    spec.includes('page.request.get("/api/v1/users/me")'),
    "the owner-visible profile API must confirm persisted values"
  )
  assert.match(
    spec,
    /entry\.email === email && entry\.full_name && expectedNames\.has\(entry\.full_name\)/u
  )
  assert.match(spec, /const deletion = await adminPage\.evaluate\(async \(userId\) =>/u)
  assert.ok(
    spec.includes("fetch(`/api/v1/users/${encodeURIComponent(userId)}`"),
    "cleanup must target the exact generated account id from the browser context"
  )
  assert.match(spec, /credentials:\s*["']same-origin["']/u)
  assert.match(spec, /find\(\(part\) => part\.startsWith\(["']csrf_token=["']\)\)/u)
  assert.match(spec, /decodeURIComponent\(csrfCookie\.slice\(["']csrf_token=["']\.length\)\)/u)
  assert.match(spec, /headers:\s*\{\s*["']X-CSRF-Token["']:\s*csrfToken\s*\}/u)
  assert.match(spec, /return \{ status: response\.status, deleted: body\?\.deleted === true \}/u)
  assert.doesNotMatch(spec, /adminPage\.request\.delete\(/u)
  assert.doesNotMatch(spec, /return\s+csrfToken|console\.(?:log|info)\([^\n]*csrfToken/u)
  assert.doesNotMatch(spec, /page\.route|routeWebSocket|vi\.mock/u)
  assert.match(spec, /stubBreachedPasswordLookup\(page\)/u)
  assert.equal(
    (fixtures.match(/page\.route\(/gu) ?? []).length,
    1,
    "the live profile flow only intercepts its third-party password-range lookup"
  )
  assert.match(fixtures, /await page\.route\("https:\/\/api\.pwnedpasswords\.com\/\*\*"/u)
  assert.match(config, /testMatch:\s*\/\.\*\\\.live\\\.spec\\\.ts\$\//u)
  assert.match(config, /name:\s*["']desktop["']/u)
  assert.match(config, /name:\s*["']mobile["']/u)
  assert.match(config, /trace:\s*["']off["']/u)
  assert.match(config, /screenshot:\s*["']off["']/u)
  assert.match(config, /video:\s*["']off["']/u)
  const liveContractCommand = JSON.parse(packageJson).scripts["test:e2e:live:contract"]
  assert.ok(
    liveContractCommand
      .split(/\s+/u)
      .includes("tests/e2e-live/profile-persistence.contract.test.mjs"),
    "the dedicated source contract is part of the live acceptance contract command"
  )
})
