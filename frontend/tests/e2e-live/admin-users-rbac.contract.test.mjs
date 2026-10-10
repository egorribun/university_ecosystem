import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { URL } from "node:url"
import test from "node:test"

const specUrl = new URL("./admin-users-rbac.live.spec.ts", import.meta.url)
const configUrl = new URL("../../playwright.live.config.ts", import.meta.url)
const adminRouteUrl = new URL("../../src/routes/_admin/admin.users.tsx", import.meta.url)
const adminLayoutUrl = new URL("../../src/routes/_admin.tsx", import.meta.url)
const adminUsersHookUrl = new URL("../../src/api/hooks/adminUsers.ts", import.meta.url)
const backendUsersRouteUrl = new URL("../../../app/api/users.py", import.meta.url)
const userSchemasUrl = new URL("../../../app/schemas/users.py", import.meta.url)
const identitySchemasUrl = new URL("../../../app/schemas/identity.py", import.meta.url)
const userDtoUrl = new URL("../../../app/schemas/dtos/user.py", import.meta.url)
const authModelsUrl = new URL("../../../app/models/auth.py", import.meta.url)
const spotifyModelUrl = new URL("../../../app/models/spotify.py", import.meta.url)
const userProfileServiceUrl = new URL(
  "../../../app/services/user/profile_service.py",
  import.meta.url
)

test("admin users live acceptance covers role-filtered reads and non-admin denial", async () => {
  const [spec, config] = await Promise.all([
    readFile(specUrl, "utf8").catch(() => null),
    readFile(configUrl, "utf8"),
  ])
  assert.ok(spec, "the dedicated admin users RBAC live spec must exist")

  assert.match(spec, /await loginAs\(page, "admin"\)/u)
  assert.match(spec, /page\.goto\("\/admin\/users"\)/u)
  assert.match(spec, /roleFilter\.selectOption\(role\)/u)
  assert.match(spec, /\/api\/v1\/users\?role=\$\{role\}/u)
  assert.match(spec, /record\.role === role/u)
  assert.match(spec, /ROLES\[role\]\.email/u)
  assert.match(spec, /const payload: unknown = await response\.json\(\)/u)
  assert.match(spec, /assertNoCredentialFields\(payload,/u)
  assert.match(spec, /Array\.isArray\(current\)/u)
  assert.match(spec, /Object\.entries\(current\)/u)
  const forbiddenFields = spec.match(/const credentialFieldNames = new Set\(\[([\s\S]*?)\]\)/u)?.[1]
  assert.ok(forbiddenFields, "the live spec must enumerate credential-bearing fields")
  for (const field of [
    "password",
    "hashedpassword",
    "secret",
    "token",
    "tokenhash",
    "tokendigest",
    "accesstoken",
    "refreshtoken",
    "signingkey",
    "codehash",
  ]) {
    assert.match(forbiddenFields, new RegExp(`["']${field}["']`, "u"))
  }
  assert.doesNotMatch(
    forbiddenFields,
    /recovery_codes_left|recoverycodesleft/u,
    "the public count of remaining recovery codes is not itself a credential"
  )
  assert.match(spec, /for \(const role of \["student", "teacher"\] as const\)/u)
  assert.match(spec, /GET \/api\/v1\/users status`\)\.toBe\(403\)/u)
  assert.match(spec, /GET \/api\/v1\/users\?role=admin status`\)\.toBe\(403\)/u)
  assert.match(spec, /\/admin\/users/u)
  assert.match(spec, /mutatingRequests\)\.toEqual\(\[\]\)/u)
  assert.doesNotMatch(
    spec,
    /\b(?:page\.route|routeWebSocket|vi\.mock|\.delete\(|\.patch\(|\.post\()/u,
    "the users-management acceptance must use real read-only role sessions"
  )
  assert.match(config, /testDir:\s*["']\.\/tests\/e2e-live["']/u)
  assert.match(config, /testMatch:\s*\/\.\*\\\.live\\\.spec\\\.ts\$\//u)
})

test("users page and unfiltered user directory retain their existing admin gate", async () => {
  const [adminRoute, adminLayout, usersHook, usersRoute, profileService] = await Promise.all([
    readFile(adminRouteUrl, "utf8"),
    readFile(adminLayoutUrl, "utf8"),
    readFile(adminUsersHookUrl, "utf8"),
    readFile(backendUsersRouteUrl, "utf8"),
    readFile(userProfileServiceUrl, "utf8"),
  ])

  assert.match(adminRoute, /createFileRoute\("\/_admin\/admin\/users"\)/u)
  assert.match(
    adminLayout,
    /beforeLoad:\s*\(\{\s*context\s*\}\)\s*=>\s*evaluateAdminGuard\(\s*import\.meta\.env\.SSR\s*\?\s*\{\s*user:\s*context\.auth\.isAuth\s*\?\s*context\.auth\.user\s*:\s*null,\s*loading:\s*context\.auth\.loading,\s*\}\s*:\s*useAuthStore\.getState\(\)\s*\)/u
  )
  assert.match(usersHook, /api\.get<AdminUser\[\]>\("\/users",\s*\{\s*params,\s*signal\s*\}\)/u)
  assert.match(usersRoute, /@users_router\.get\(/u)
  assert.match(usersRoute, /current_user:\s*UserDTO\s*=\s*Depends\(deps\.get_current_user_dto\)/u)
  assert.match(
    profileService,
    /current_user\.role\s*!=\s*"admin"\s*and\s*name_query\s+is\s+None[\s\S]{0,100}raise PermissionDenied\(\)/u
  )
})

test("credential denylist follows the current response, identity and auth fields", async () => {
  const [userSchemas, identitySchemas, userDto, authModels, spotifyModel] = await Promise.all([
    readFile(userSchemasUrl, "utf8"),
    readFile(identitySchemasUrl, "utf8"),
    readFile(userDtoUrl, "utf8"),
    readFile(authModelsUrl, "utf8"),
    readFile(spotifyModelUrl, "utf8"),
  ])

  assert.match(userSchemas, /class UserOut\([\s\S]*?recovery_codes_left: int/u)
  assert.match(userDto, /class UserAuthDTO\([\s\S]*?hashed_password: str/u)
  assert.match(identitySchemas, /class MfaChallengeOut\([\s\S]*?token: str/u)
  assert.match(identitySchemas, /class Token\([\s\S]*?access_token: str/u)
  assert.match(identitySchemas, /class SessionSigningKeyOut\([\s\S]*?signing_key: str/u)
  assert.match(authModels, /class MfaTotpEnrollment\([\s\S]*?secret: Mapped\[str\]/u)
  assert.match(authModels, /class MfaChallenge\([\s\S]*?token_digest: Mapped\[str\]/u)
  assert.match(authModels, /class RecoveryCode\([\s\S]*?code_hash: Mapped\[str\]/u)
  assert.match(spotifyModel, /access_token: Mapped\[str \| None\]/u)
  assert.match(spotifyModel, /refresh_token: Mapped\[str \| None\]/u)
})
