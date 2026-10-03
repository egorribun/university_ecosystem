import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { URL } from "node:url"
import test from "node:test"

const specUrl = new URL("./admin-stories-rbac.live.spec.ts", import.meta.url)
const configUrl = new URL("../../playwright.live.config.ts", import.meta.url)
const adminRouteUrl = new URL("../../src/routes/_admin/admin.stories.tsx", import.meta.url)
const adminLayoutUrl = new URL("../../src/routes/_admin.tsx", import.meta.url)
const storyApiUrl = new URL("../../../app/api/stories.py", import.meta.url)
const storySchemaUrl = new URL("../../../app/schemas/stories.py", import.meta.url)
const authDependenciesUrl = new URL("../../../app/api/deps/auth.py", import.meta.url)

test("admin story management is denied to both non-admin live roles", async () => {
  let spec
  try {
    spec = await readFile(specUrl, "utf8")
  } catch {
    assert.fail("the dedicated admin stories RBAC live spec must exist")
  }

  const [config, adminRoute, adminLayout, storyApi, storySchema, authDependencies] =
    await Promise.all([
      readFile(configUrl, "utf8"),
      readFile(adminRouteUrl, "utf8"),
      readFile(adminLayoutUrl, "utf8"),
      readFile(storyApiUrl, "utf8"),
      readFile(storySchemaUrl, "utf8"),
      readFile(authDependenciesUrl, "utf8"),
    ])

  assert.match(spec, /for \(const role of \["student", "teacher"\] as const\)/u)
  assert.match(spec, /await loginAs\(page, role\)/u)
  assert.match(spec, /page\.goto\("\/admin\/stories"\)/u)
  assert.match(spec, /toHaveURL\(\s*\/\\\/dashboard\$\/u/u)
  assert.match(
    spec,
    /getByRole\("heading",[\s\S]{0,180}name:\s*\/Stories management\|Управление сторис\/u,[\s\S]{0,120}toHaveCount\(0\)/u
  )
  assert.match(spec, /adminPage\.goto\("\/admin\/stories"\)/u)
  assert.match(spec, /adminPage\)\.toHaveURL\(\s*\/\\\/admin\\\/stories\$\/u/u)
  assert.match(
    spec,
    /adminPage\.getByRole\("heading",[\s\S]{0,180}name:\s*\/Stories management\|Управление сторис\/u,[\s\S]{0,120}toBeVisible\(\)/u
  )
  assert.match(spec, /adminPage\.getByText\(ownedTitle,[\s\S]{0,100}toBeVisible\(\)/u)
  assert.match(spec, /page\.request\.post\("\/api\/v1\/stories"/u)
  assert.match(spec, /expect\(response\.status\(\)[\s\S]*?\.toBe\(403\)/u)
  assert.match(spec, /page\.request\.patch\([\s\S]*?nonExistentStoryId/u)
  assert.match(spec, /PATCH \/api\/v1\/stories must be forbidden[\s\S]*?\.toBe\(403\)/u)
  assert.match(spec, /page\.request\.delete\([\s\S]*?ownedStoryId/u)
  assert.match(spec, /DELETE \/api\/v1\/stories must be forbidden[\s\S]*?\.toBe\(403\)/u)
  assert.match(spec, /adminPage\.request\.get\([\s\S]*?__live_verify/u)
  assert.match(spec, /adminStories\.find\(\(entry\) => entry\.id === createdBody\.id\)/u)
  assert.match(spec, /expect\(\s*ownedStory,[\s\S]*?toBeDefined\(\)/u)
  assert.match(spec, /adminPage\.request\.post\("\/api\/v1\/stories"/u)
  assert.match(spec, /const ownedTitle = `Live RBAC admin-owned story/u)
  assert.match(
    spec,
    /unauthorizedCreateMayHaveSucceeded = response\.ok\(\) \|\| response\.status\(\) >= 500/u
  )
  assert.match(spec, /cleanupCreatedStory\(adminPage, ownedTitle, ownedShortText, ownedStoryId\)/u)
  assert.match(
    spec,
    /cleanupCreatedStory\(\s*adminPage,\s*attemptedTitle,\s*attemptedShortText,\s*unauthorizedStoryId\s*\)/u
  )
  assert.match(spec, /matches\.length !== 1[\s\S]*?refusing cleanup[\s\S]*?ambiguous/u)
  assert.doesNotMatch(spec, /for \(const match of matches\)/u)
  assert.match(spec, /method: "DELETE"/u)
  assert.doesNotMatch(spec, /page\.route|routeWebSocket|vi\.mock|fixture.*role.*override/iu)

  assert.match(adminRoute, /createFileRoute\("\/_admin\/admin\/stories"\)/u)
  assert.match(
    adminLayout,
    /beforeLoad:\s*\(\)\s*=>\s*evaluateAdminGuard\(useAuthStore\.getState\(\)\)/u
  )
  const routes = storyApi.split(/(?=^@router\.)/mu)
  for (const [routePattern, handler] of [
    [/^@router\.post\(\s*""/u, "create_story"],
    [/^@router\.patch\(\s*"\/\{story_id\}"/u, "update_story"],
    [/^@router\.delete\(\s*"\/\{story_id\}"/u, "delete_story"],
  ]) {
    const route = routes.find((section) => routePattern.test(section))
    assert.ok(route, `${handler} must remain bound to its story mutation endpoint`)
    const signature = route.match(new RegExp(`^async def ${handler}\\(([\\s\\S]*?)^\\)`, "mu"))?.[1]
    assert.ok(signature, `${handler} must have an explicit dependency signature`)
    assert.match(
      signature,
      /user:\s*models\.User\s*=\s*Depends\(get_current_admin_user_from_dishka\)/u,
      `${handler} must authorize through the admin dependency before its body runs`
    )
  }
  const adminDependency = authDependencies.match(
    /^async def get_current_admin_user_from_dishka\([\s\S]*?(?=^(?:async )?def )/mu
  )?.[0]
  assert.ok(adminDependency, "the route admin dependency must be defined")
  assert.match(adminDependency, /await ensure_admin\(checker, user, request\)\s+return user/u)
  const adminGuard = authDependencies.match(
    /^async def ensure_admin\([\s\S]*?(?=^async def )/mu
  )?.[0]
  assert.ok(adminGuard, "the shared admin guard must be defined")
  assert.match(adminGuard, /await checker\.check_admin\(str\(user\.id\), user=user\)/u)
  assert.match(
    adminGuard,
    /except SpiceDBUnavailableError:\s*raise HTTPException\(\s*status_code=status\.HTTP_503_SERVICE_UNAVAILABLE/u
  )
  assert.match(adminGuard, /if not is_admin_user:\s*raise_forbidden\(/u)
  assert.doesNotMatch(adminGuard, /if\s+user\.role\s*(?:==|!=)/u)
  assert.match(
    storySchema,
    /class StoryCreate\(BaseModel\)[\s\S]*?title: str[\s\S]*?short_text: str/u
  )
  assert.match(config, /testDir: "\.\/tests\/e2e-live"/u)
  assert.match(config, /name: "desktop"/u)
  assert.match(config, /name: "mobile"/u)
})
