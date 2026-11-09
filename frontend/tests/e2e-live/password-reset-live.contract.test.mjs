import assert from "node:assert/strict"
import { Buffer } from "node:buffer"
import console from "node:console"
import { readFileSync } from "node:fs"
import { URL, fileURLToPath } from "node:url"
import { performance } from "node:perf_hooks"
import process from "node:process"
import test from "node:test"
import { runInNewContext } from "node:vm"

const specPath = fileURLToPath(new URL("./password-reset.live.spec.ts", import.meta.url))
const configPath = fileURLToPath(new URL("../../playwright.live.config.ts", import.meta.url))
const fixturePath = fileURLToPath(new URL("./fixtures.ts", import.meta.url))
const urlStateUrl = new URL("./password-reset-url-state.ts", import.meta.url)

test("password reset rejects redirect abuse, reuse, and cleanup outside its own user", () => {
  const source = readFileSync(specPath, "utf8")
  const config = readFileSync(configPath, "utf8")

  assert.match(source, /createOwnedResetAccount\(testInfo\.project\.name, randomUUID\(\)\)/u)
  assert.match(source, /waitForResponse\([\s\S]*?\/auth\/register/u)
  assert.doesNotMatch(source, /registrationBody\.id/u)
  assert.match(source, /createdUser\.id = await readOwnedResetUserId\(/u)
  assert.match(source, /awaitMail\(email, RESET_LINK\)/u)
  assert.match(source, /new URL\(resetMatch\[0\], page\.url\(\)\)/u)
  assert.match(source, /redirect-target\.invalid/u)
  assert.match(source, /searchParams\.set\("redirect"/u)
  assert.match(source, /openResetLink\(page, resetUrl\.href\)/u)
  assert.match(readFileSync(urlStateUrl, "utf8"), /searchParams\.has\("token"\)/u)
  assert.match(source, /await page\.goBack\(\)/u)
  assert.match(source, /toHaveURL\(new URL\("\/login", resetOrigin\)\.href\)/u)
  assert.match(source, /new URL\(page\.url\(\)\)\.search === ""/u)
  assert.match(source, /expect\(replayFeedback\.containsResetToken\)\.toBe\(false\)/u)
  assert.match(source, /const replayResponse = page\.waitForResponse\(/u)
  assert.match(source, /replayResponse[\s\S]*?status\(\)[\s\S]*?\.toBe\(400\)/u)
  for (const submitId of ["login-submit", "reset-submit-btn"]) {
    assert.match(
      source,
      new RegExp(
        `page\\s*\\.locator\\("form"\\)\\s*\\.filter\\(\\{ has: page\\.locator\\("#${submitId}"\\) \\}\\)\\s*\\.getByRole\\("alert"\\)`,
        "u"
      )
    )
  }
  assert.doesNotMatch(source, /page\.getByRole\("alert"\)|\.first\(\)/u)
  assert.match(source, /encodeURIComponent\(userId\)/u)
  assert.match(source, /"X-CSRF-Token"/u)
  assert.match(source, /finally/u)
  assert.doesNotMatch(source, /console\.(?:log|info|warn|error)\(/u)
  assert.match(config, /trace: "off"/u)
  assert.match(config, /screenshot: "off"/u)
  assert.match(config, /video: "off"/u)
})

test("password reset uses live auth APIs and confines its password-check stub to HIBP", () => {
  const source = readFileSync(specPath, "utf8")
  const fixtures = readFileSync(fixturePath, "utf8")
  const lookupStub = fixtures.match(
    /export async function stubBreachedPasswordLookup\(page: Page\): Promise<void> \{[\s\S]*?\n\}/u
  )?.[0]

  assert.ok(lookupStub, "the external password-breach lookup helper exists")
  assert.equal(
    [...lookupStub.matchAll(/page\.route\(/gu)].length,
    1,
    "the fixture has only one route interception in the permitted helper"
  )
  assert.match(lookupStub, /page\.route\(["']https:\/\/api\.pwnedpasswords\.com\/\*\*["']/u)
  assert.match(
    lookupStub,
    /route\.fulfill\(\{\s*status:\s*200,\s*contentType:\s*["']text\/plain["']/u
  )
  assert.doesNotMatch(lookupStub, /\/api\/v1\/|\/auth\/|localhost|LIVE_BASE_URL/u)
  assert.doesNotMatch(source, /page\.route\(|routeWebSocket\(|\.fulfill\(|useMockApi/u)
  assert.match(source, /waitForResponse\([\s\S]*?\/auth\/register/u)
  assert.match(source, /await submitLogin\(page, email, firstPassword\)/u)
  assert.match(source, /await loginWith\(page, email, newPassword\)/u)
})

test("password reset registration keeps admission and observes only a finite failure step", () => {
  const source = readFileSync(specPath, "utf8")
  const registration = source.slice(
    source.indexOf("  const registered ="),
    source.indexOf("  expect(registered.ok())")
  )
  assert.match(
    registration,
    /withLiveRegistrationAdmission\(page, 1, \(\) =>\s*runPasswordResetRegistrationAction\(/u
  )
  assert.match(registration, /response\.request\(\)\.method\(\) === "POST"/u)
  assert.match(
    registration,
    /new URL\(response\.url\(\)\)\.pathname\.endsWith\("\/auth\/register"\)/u
  )
  assert.match(
    registration,
    /\(\) => page\.getByRole\("button", \{ name: "Зарегистрироваться" \}\)\.click\(\)/u
  )
  assert.match(
    registration,
    /\(step\) => reportLivePasswordResetRegistrationFailure\(testInfo\.project\.name, step\)/u
  )
  assert.doesNotMatch(
    registration,
    /setTimeout|waitForTimeout|\.message|\.stack|\.post\(|\.evaluate\(/u
  )
})

test("password reset installs one bounded event observer before typing without delaying the armed click", () => {
  const source = readFileSync(specPath, "utf8")
  const goto = source.indexOf('  await page.goto("/register")')
  const setup = source.indexOf("await registrationTimeline.setup()", goto)
  const fill = source.indexOf(".fill(fullName)", goto)
  const admission = source.indexOf("withLiveRegistrationAdmission(page, 1", fill)
  const click = source.indexOf(
    '.getByRole("button", { name: "Зарегистрироваться" }).click()',
    admission
  )
  assert.ok(
    goto >= 0 && goto < setup && setup < fill && fill < admission && admission < click,
    "observer setup precedes typing and the admitted action"
  )
  assert.doesNotMatch(source, /registrationTimeline\.capture\(/u)
  assert.match(source, /withPasswordResetRegistrationTimeline\([\s\S]*?registrationTimeline\s*\)/u)
  assert.match(
    source,
    /withRegistrationTimeline\(registrationTimeline, async \(\) => \{[\s\S]*?await registrationTimeline\.setup\(\)[\s\S]*?return withLiveRegistrationAdmission\(/u
  )
  assert.doesNotMatch(source, /(?:test|testInfo)\.setTimeout|test\.slow\(/u)
})

test("password reset waits for document hydration before typing after reload", () => {
  const source = readFileSync(specPath, "utf8")
  const config = readFileSync(configPath, "utf8")
  const reloadIndex = source.indexOf("  await page.reload()")
  const fillIndex = source.indexOf(
    '  await page.getByLabel("Пароль", { exact: true }).fill(newPassword)',
    reloadIndex
  )
  assert.ok(reloadIndex >= 0 && fillIndex > reloadIndex, "the reset reload precedes its fields")
  const beforeFill = source.slice(reloadIndex, fillIndex)

  assert.match(
    beforeFill,
    /await page\.waitForFunction\(\s*\(\) => window\.__APP_HYDRATED === true,\s*undefined,\s*\{\s*timeout: RESET_REPLAY_ACTION_TIMEOUT_MS,?\s*\}\s*\)/u
  )
  assert.match(source, /const RESET_REPLAY_ACTION_TIMEOUT_MS = 15_000/u)
  assert.doesNotMatch(beforeFill, /waitForTimeout|addInitScript|__APP_HYDRATED\s*=(?!=)/u)
  assert.doesNotMatch(source, /(?:test|testInfo)\.setTimeout|test\.slow\(/u)
  assert.match(config, /timeout: 60_000,/u)
  assert.match(config, /actionTimeout: 15_000,/u)
  assert.match(config, /failOnFlakyTests: Boolean\(process\.env\.CI\)/u)
})

const ownedResetHelperUrl = new URL("./password-reset-account-identity.ts", import.meta.url)

test("password reset binds cleanup to its owned account before response parsing", () => {
  const source = readFileSync(specPath, "utf8")
  assert.match(
    source,
    /const account = createOwnedResetAccount\(testInfo\.project\.name, randomUUID\(\)\)/u
  )
  assert.match(source, /const \{ email, fullName \} = account/u)
  assert.match(source, /\.getByLabel\("Имя", \{ exact: true \}\)\.fill\(fullName\)/u)
  assert.match(source, /\.getByRole\("textbox", \{ name: "E-mail" \}\)\.fill\(email\)/u)
  assert.doesNotMatch(source, /registrationBody\.id/u)
  assert.match(
    source,
    /const RegistrationReceipt = v\.strictObject\(\{ status: v\.literal\("ok"\) \}\)/u
  )
  assert.match(source, /if \(!v\.safeParse\(RegistrationReceipt, registrationBody\)\.success\)/u)
  assert.match(
    source,
    /throw new Error\("Synthetic account registration returned an invalid receipt"\)/u
  )
  assert.doesNotMatch(source, /expect\(registrationBody\)/u)
  assert.match(source, /const createdUser: \{ id: string \| undefined \} = \{ id: undefined \}/u)

  const success = source.indexOf("  expect(registered.ok()).toBe(true)")
  const cleanup = source.indexOf("  registerOwnedSessionCleanup(", success)
  const parsed = source.indexOf("await registered.json()", cleanup)
  const login = source.indexOf("  await loginWith(page, email, firstPassword)", parsed)
  const deadline = source.indexOf(
    "  const identityDeadlineAtMs = readPlaywrightTestSlotDeadlineAtMs(",
    login
  )
  const guard = source.indexOf("  if (identityDeadlineAtMs === null)", deadline)
  const read = source.indexOf("createdUser.id = await readOwnedResetUserId(", guard)
  const cookies = source.indexOf("  await page.context().clearCookies()", read)
  assert.ok(
    success >= 0 && success < cleanup && cleanup < parsed && parsed < login,
    "cleanup is registered after successful registration and before parsing or login can fail"
  )
  assert.ok(
    login < deadline && deadline < guard && guard < read && read < cookies,
    "identity is read under the existing student session only with an available deadline"
  )
  assert.match(
    source.slice(guard, read),
    /if \(identityDeadlineAtMs === null\) throw new Error\("Owned reset account deadline unavailable"\)/u
  )
  assert.match(source.slice(read, cookies), /boundedReplayTimeout\(identityDeadlineAtMs, 5_000\)/u)
  assert.match(
    source.slice(read, cookies),
    /readOwnedResetUserId\(\s*page\.request,\s*ownedSessionOrigin\(\),\s*account,/u
  )

  const cleanupEnd = source.indexOf("\n  })", cleanup)
  assert.ok(cleanupEnd > cleanup && cleanupEnd < parsed)
  const cleanupBody = source.slice(cleanup, cleanupEnd + 5)
  assert.equal([...cleanupBody.matchAll(/await loginAs\(cleanupPage, "admin",/gu)].length, 1)
  assert.match(
    cleanupBody,
    /const cleanupUserId =\s*createdUser\.id \?\?\s*\(await findOwnedResetUserId\(\s*cleanupPage\.request,\s*ownedSessionOrigin\(\),\s*account,/u
  )
  assert.match(cleanupBody, /userId: cleanupUserId/u)
  assert.doesNotMatch(
    cleanupBody,
    /registrationBody|URLSearchParams|searchParams\.set|\/auth\/register/u
  )
  assert.equal([...source.matchAll(/registerOwnedSessionCleanup\(/gu)].length, 1)
  assert.equal([...source.matchAll(/await loginWith\(page, email, firstPassword\)/gu)].length, 1)
})

test("owned reset identity HTTP receipts", { timeout: 10_000 }, async (t) => {
  // The actual TypeScript module is loaded by the pinned Node native TS loader.
  // The HTTP double replaces only APIRequestContext transport, never parsing or validation.
  const { createOwnedResetAccount, readOwnedResetUserId, findOwnedResetUserId } = await import(
    ownedResetHelperUrl.href
  )
  const origin = "https://127.0.0.1:38443"
  const nonce = "12345678-1234-4234-9234-123456789abc"
  const secondNonce = "87654321-4321-4321-a321-cba987654321"
  const userId = "22222222-2222-4222-8222-abcdefabcdef"
  const secondUserId = "33333333-3333-4333-8333-333333333333"
  const account = {
    email: "live-reset-desktop-12345678-1234-4234-9234-123456789abc@university.dev",
    fullName: "Live Reset desktop 12345678-1234-4234-9234-123456789abc",
  }
  const secondAccount = {
    email: "live-reset-mobile-87654321-4321-4321-a321-cba987654321@university.dev",
    fullName: "Live Reset mobile 87654321-4321-4321-a321-cba987654321",
  }
  const user = {
    id: userId,
    email: account.email,
    full_name: account.fullName,
    role: "student",
    is_active: true,
    about: null,
    preferences: null,
    mfa_required: false,
    recovery_codes_left: 0,
    totp_enrollments: [],
  }
  const privateMarker = "upstream-private-receipt-must-not-escape"

  function assertSafeError(error) {
    assert.ok(error instanceof Error)
    assert.ok(
      error.message === "Invalid owned reset account identity" ||
        error.message === "Owned reset account identity unavailable",
      "only fixed identity errors may escape"
    )
    assert.equal("cause" in error, false)
    assert.deepEqual(Object.keys(error), [], "upstream details must not be attached to the error")
    assert.doesNotMatch(String(error), /upstream-private|university\.dev|https?:\/\//u)
    return true
  }

  function exchange(payload, options = {}) {
    const calls = []
    let disposed = 0
    let bodyReads = 0
    const body = Buffer.isBuffer(payload) ? payload : Buffer.from(JSON.stringify(payload))
    const response = {
      status() {
        if (options.statusError) throw new Error(privateMarker)
        return options.status ?? 200
      },
      async body() {
        bodyReads += 1
        if (options.bodyError) throw new Error(privateMarker)
        return body
      },
      async json() {
        throw new Error("JSON must not be parsed before the byte limit")
      },
      async dispose() {
        disposed += 1
        if (options.disposeError) throw new Error(privateMarker)
      },
    }
    return {
      calls,
      disposed: () => disposed,
      bodyReads: () => bodyReads,
      api: {
        async get(url, requestOptions) {
          calls.push({ url, options: requestOptions })
          if (options.getError) throw new Error(privateMarker)
          return response
        },
      },
    }
  }

  function assertRequest(receipt, path, timeout = 3_000, expectedOrigin = origin) {
    assert.equal(receipt.calls.length, 1, "one bounded GET, with no helper retry")
    const request = receipt.calls[0]
    const url = new URL(request.url)
    assert.equal(url.origin, expectedOrigin)
    assert.equal(url.pathname, path)
    assert.deepEqual(request.options, {
      timeout,
      maxRedirects: 0,
      maxRetries: 0,
    })
    return url
  }

  async function rejected(read, receipt, expected = account, target = origin, timeout = 3_000) {
    await assert.rejects(() => read(receipt.api, target, expected, timeout), assertSafeError)
  }

  await t.test("derives distinct owned project and nonce identities without normalization", () => {
    assert.deepEqual(createOwnedResetAccount("desktop", nonce), account)
    assert.deepEqual(createOwnedResetAccount("mobile", secondNonce), secondAccount)
    assert.notEqual(createOwnedResetAccount("desktop", secondNonce).email, account.email)
  })

  await t.test("rejects unknown project inputs before they enter an account identity", () => {
    for (const project of ["", "admin", "../desktop", "Desktop", null, 1, {}]) {
      assert.throws(() => createOwnedResetAccount(project, nonce), assertSafeError)
    }
  })

  await t.test("rejects noncanonical or injected nonce inputs without coercion", () => {
    for (const value of ["", nonce.toUpperCase(), nonce + "/x", nonce + "\n", null, 1, {}]) {
      assert.throws(() => createOwnedResetAccount("desktop", value), assertSafeError)
    }
  })

  await t.test("reads only the authenticated owned student from users me", async () => {
    const receipt = exchange(user)
    assert.equal(await readOwnedResetUserId(receipt.api, origin, account, 3_000), userId)
    const url = assertRequest(receipt, "/api/v1/users/me")
    assert.equal(url.search, "")
    assert.equal(receipt.disposed(), 1)
    assert.equal(receipt.bodyReads(), 1)
  })

  await t.test("fallback validates one bounded exact-name student page", async () => {
    const receipt = exchange([user])
    assert.equal(await findOwnedResetUserId(receipt.api, origin, account, 3_000), userId)
    const url = assertRequest(receipt, "/api/v1/users")
    assert.deepEqual([...url.searchParams].sort(), [
      ["full_name", "Live Reset desktop 12345678-1234-4234-9234-123456789abc"],
      ["limit", "2"],
      ["role", "student"],
    ])
    assert.equal(receipt.disposed(), 1)
  })

  await t.test("rejects an identity from another email, name or role", async () => {
    for (const change of [
      { email: secondAccount.email },
      { full_name: secondAccount.fullName },
      { role: "admin" },
      { role: "teacher" },
      { email: account.email.toUpperCase() },
    ]) {
      const changed = { ...user, ...change }
      for (const read of [readOwnedResetUserId, findOwnedResetUserId]) {
        const receipt = exchange(read === readOwnedResetUserId ? changed : [changed])
        await rejected(read, receipt)
        assert.equal(receipt.disposed(), 1)
      }
    }
  })

  await t.test("rejects malformed or noncanonical account identifiers", async () => {
    for (const id of ["", "not-a-uuid", userId.toUpperCase(), userId + " ", null, 7]) {
      const changed = { ...user, id }
      for (const read of [readOwnedResetUserId, findOwnedResetUserId]) {
        const receipt = exchange(read === readOwnedResetUserId ? changed : [changed])
        await rejected(read, receipt)
        assert.equal(receipt.disposed(), 1)
      }
    }
  })

  await t.test("rejects absent required ownership fields in either receipt shape", async () => {
    for (const field of ["id", "email", "full_name", "role"]) {
      const incomplete = { ...user }
      delete incomplete[field]
      for (const read of [readOwnedResetUserId, findOwnedResetUserId]) {
        const receipt = exchange(read === readOwnedResetUserId ? incomplete : [incomplete])
        await rejected(read, receipt)
        assert.equal(receipt.disposed(), 1)
      }
    }
  })

  await t.test("fallback does not accept an empty page", async () => {
    const receipt = exchange([])
    await rejected(findOwnedResetUserId, receipt)
    assert.equal(receipt.calls.length, 1)
    assert.equal(receipt.disposed(), 1)
  })

  await t.test("fallback rejects duplicate rows rather than selecting the first", async () => {
    const receipt = exchange([user, { ...user, id: secondUserId }])
    await rejected(findOwnedResetUserId, receipt)
    assert.equal(receipt.calls.length, 1)
    assert.equal(receipt.disposed(), 1)
  })

  await t.test("fallback rejects rather than filters a mixed page", async () => {
    const receipt = exchange([user, { ...user, email: secondAccount.email }])
    await rejected(findOwnedResetUserId, receipt)
    assert.equal(receipt.disposed(), 1)
  })

  await t.test("rejects envelopes, scalars and arrays at the wrong endpoint boundary", async () => {
    for (const payload of [null, 0, "user", [], { items: [user] }]) {
      const receipt = exchange(payload)
      await rejected(readOwnedResetUserId, receipt)
      assert.equal(receipt.disposed(), 1)
    }
    for (const payload of [null, user, { items: [user] }]) {
      const receipt = exchange(payload)
      await rejected(findOwnedResetUserId, receipt)
      assert.equal(receipt.disposed(), 1)
    }
  })

  await t.test("rejects redirects and non-200 statuses without another request", async () => {
    for (const status of [201, 204, 301, 302, 401, 403, 429, 500]) {
      const receipt = exchange(user, { status })
      await rejected(readOwnedResetUserId, receipt)
      assertRequest(receipt, "/api/v1/users/me")
      assert.equal(receipt.bodyReads(), 0)
      assert.equal(receipt.disposed(), 1)
    }
  })

  await t.test("rejects malformed JSON and disposes its response", async () => {
    for (const read of [readOwnedResetUserId, findOwnedResetUserId]) {
      const receipt = exchange(Buffer.from("{" + privateMarker))
      await rejected(read, receipt)
      assert.equal(receipt.disposed(), 1)
    }
  })

  await t.test("rejects more than 65536 buffered bytes before parsing", async () => {
    const raw = Buffer.from(JSON.stringify(user) + " ".repeat(65_537))
    const receipt = exchange(raw)
    await rejected(readOwnedResetUserId, receipt)
    assert.equal(receipt.disposed(), 1)
  })

  await t.test("counts UTF-8 bytes rather than JavaScript string length", async () => {
    const raw = JSON.stringify({ ...user, about: "Ж".repeat(33_000) })
    assert.ok(raw.length < 65_536)
    assert.ok(Buffer.byteLength(raw) > 65_536)
    const receipt = exchange(Buffer.from(raw))
    await rejected(readOwnedResetUserId, receipt)
    assert.equal(receipt.disposed(), 1)
  })

  await t.test("accepts a valid JSON receipt at the exact parse-byte boundary", async () => {
    const json = JSON.stringify(user)
    const receipt = exchange(Buffer.from(json + " ".repeat(65_536 - Buffer.byteLength(json))))
    assert.equal(await readOwnedResetUserId(receipt.api, origin, account, 3_000), userId)
    assert.equal(receipt.disposed(), 1)
  })

  await t.test("confines requests to explicit-port loopback origins before transport", async () => {
    const credentialTarget = new URL(origin)
    credentialTarget.username = "fixture"
    credentialTarget.password = nonce
    for (const target of ["http://localhost:38080", "https://127.0.0.1:38443/"]) {
      const receipt = exchange(user)
      assert.equal(await readOwnedResetUserId(receipt.api, target, account, 3_000), userId)
      assertRequest(receipt, "/api/v1/users/me", 3_000, new URL(target).origin)
      assert.equal(receipt.disposed(), 1)
    }
    for (const target of [
      "https://example.com:38443",
      "https://127.0.0.1",
      credentialTarget.href,
      "https://127.0.0.1:38443/path",
      "https://127.0.0.1:38443?query=value",
      "https://127.0.0.1:38443#fragment",
      "https://127.0.0.1:38443?",
      "https://127.0.0.1:38443#",
      "//127.0.0.1:38443",
      "file:///tmp/identity",
      " https://127.0.0.1:38443",
      "https://127.0.0.1:38443\n",
    ]) {
      const receipt = exchange(user)
      await rejected(readOwnedResetUserId, receipt, account, target)
      assert.equal(receipt.calls.length, 0)
    }
  })

  await t.test("rejects invalid request timeout budgets before transport", async () => {
    for (const timeout of [0, -1, 5_001, 1.5, NaN, Infinity, "5000", undefined]) {
      const receipt = exchange(user)
      await assert.rejects(
        () => readOwnedResetUserId(receipt.api, origin, account, timeout),
        assertSafeError
      )
      assert.equal(receipt.calls.length, 0)
    }
  })

  await t.test("forwards both request-timeout bounds without widening", async () => {
    for (const timeout of [1, 5_000]) {
      const receipt = exchange(user)
      assert.equal(await readOwnedResetUserId(receipt.api, origin, account, timeout), userId)
      assertRequest(receipt, "/api/v1/users/me", timeout)
      assert.equal(receipt.disposed(), 1)
    }
  })

  await t.test("rejects forged or mixed owned-account descriptors before transport", async () => {
    for (const expected of [
      null,
      {},
      { email: account.email, fullName: secondAccount.fullName },
      { email: "other@university.dev", fullName: account.fullName },
      { email: account.email, fullName: "Live Acceptance" },
    ]) {
      const receipt = exchange(user)
      await rejected(readOwnedResetUserId, receipt, expected)
      assert.equal(receipt.calls.length, 0)
    }
  })

  await t.test("sanitizes a rejected GET without retrying or inventing a response", async () => {
    const receipt = exchange(user, { getError: true })
    await rejected(readOwnedResetUserId, receipt)
    assert.equal(receipt.calls.length, 1)
    assert.equal(receipt.disposed(), 0)
  })

  await t.test("disposes responses when status or body access throws", async () => {
    for (const options of [{ statusError: true }, { bodyError: true }]) {
      const receipt = exchange(user, options)
      await rejected(readOwnedResetUserId, receipt)
      assert.equal(receipt.disposed(), 1)
    }
  })

  await t.test("refuses identity when disposal fails after a valid receipt", async () => {
    for (const read of [readOwnedResetUserId, findOwnedResetUserId]) {
      const payload = read === readOwnedResetUserId ? user : [user]
      const receipt = exchange(payload, { disposeError: true })
      await rejected(read, receipt)
      assert.equal(receipt.disposed(), 1)
    }
  })

  await t.test("keeps concurrent owned identities isolated across readers", async () => {
    const first = exchange(user)
    const second = exchange([
      {
        ...user,
        id: secondUserId,
        email: secondAccount.email,
        full_name: secondAccount.fullName,
      },
    ])
    assert.deepEqual(
      await Promise.all([
        readOwnedResetUserId(first.api, origin, account, 3_000),
        findOwnedResetUserId(second.api, origin, secondAccount, 3_000),
      ]),
      [userId, secondUserId]
    )
    assert.equal(first.disposed(), 1)
    assert.equal(second.disposed(), 1)
  })

  await t.test("does not log private identity, response or disposal failures", async () => {
    const output = []
    const originals = new Map(
      ["log", "info", "warn", "error", "debug"].map((name) => [name, console[name]])
    )
    for (const name of originals.keys()) console[name] = (...args) => output.push(args)
    try {
      const success = exchange(user)
      assert.equal(await readOwnedResetUserId(success.api, origin, account, 3_000), userId)
      const failed = exchange(Buffer.from(privateMarker), { disposeError: true })
      await rejected(findOwnedResetUserId, failed)
      assert.equal(failed.disposed(), 1)
    } finally {
      for (const [name, original] of originals) console[name] = original
    }
    assert.deepEqual(output, [])
  })
})

test("password reset observes both cleanup phases without changing the original poll", () => {
  const source = readFileSync(specPath, "utf8")
  const start = source.indexOf("const expectResetTokenRemovedFromUrl =")
  const end = source.indexOf("\n}", start)
  assert.ok(start >= 0 && end > start)
  const removal = source.slice(start, end + 2)
  assert.match(removal, /await withPasswordResetUrlDiagnostic\(\s*project,\s*phase,/u)
  assert.match(removal, /\(\) => page\.evaluate\(readPasswordResetUrlState, token\)/u)
  assert.match(removal, /const state = await observe\(\)/u)
  assert.match(
    removal,
    /state\.resetRoute\s*&&\s*state\.tokenQueryAbsent\s*&&\s*state\.tokenFragmentAbsent\s*&&\s*state\.tokenUrlAbsent/u
  )
  assert.equal([...removal.matchAll(/\.poll\(/gu)].length, 1)
  assert.match(removal, /\.toBe\(true\)/u)
  assert.doesNotMatch(removal, /timeout|catch|console|JSON\.stringify|toBeTruthy|soft/u)
  for (const phase of ["history", "reopen"]) {
    assert.equal(
      source.split(
        'await expectResetTokenRemovedFromUrl(page, token, testInfo.project.name, "' + phase + '")'
      ).length - 1,
      1
    )
  }
})

test("reset URL snapshots serialize safely and distinguish the four predicates", async (t) => {
  const { readPasswordResetUrlState } = await import(urlStateUrl.href)
  const source = Function.prototype.toString.call(readPasswordResetUrlState)
  const candidate = "reset-private-canary"
  const origin = "https://reset-diagnostic.invalid"
  const keys = ["resetRoute", "tokenQueryAbsent", "tokenFragmentAbsent", "tokenUrlAbsent"]
  const cases = [
    ["clean reset route", "/reset-password?redirect=%2Flogin#section", [true, true, true, true]],
    ["wrong clean route", "/login", [false, true, true, true]],
    ["empty token query", "/reset-password?token=", [true, false, true, true]],
    ["encoded token query key", "/reset-password?%74oken=", [true, false, true, true]],
    [
      "retained fragment candidate",
      "/reset-password#token=" + candidate,
      [true, true, false, false],
    ],
    [
      "candidate in another query field",
      "/reset-password?hint=" + candidate,
      [true, true, true, false],
    ],
    ["candidate in token query", "/reset-password?token=" + candidate, [true, false, true, false]],
    ["case-sensitive route", "/RESET-PASSWORD", [false, true, true, true]],
  ]

  for (const [name, path, expected] of cases) {
    await t.test(name, () => {
      const output = []
      const browserConsole = Object.fromEntries(
        ["log", "info", "warn", "error", "debug"].map((level) => [
          level,
          (...args) => output.push(args),
        ])
      )
      const href = origin + path
      // Exercise the actual serialized function, with no module closure.
      // This is trusted test code, not a sandbox for untrusted input.
      const snapshot = runInNewContext(
        "(" + source + ")(candidate)",
        {
          URL,
          window: Object.freeze({ location: Object.freeze({ href }) }),
          candidate,
          console: browserConsole,
        },
        { timeout: 1_000 }
      )
      assert.deepEqual(Reflect.ownKeys(snapshot), keys)
      assert.deepEqual(
        Object.values(snapshot).map((value) => typeof value),
        ["boolean", "boolean", "boolean", "boolean"]
      )
      assert.deepEqual(
        keys.map((key) => snapshot[key]),
        expected
      )
      assert.deepEqual(output, [])
      const encoded = JSON.stringify(snapshot)
      assert.equal(encoded.includes(candidate), false)
      // Parse each URL-shaped token rather than substring-matching the origin:
      // a substring test also matches unrelated hosts such as `origin.example`.
      const diagnostic = new URL(href)
      for (const [token] of encoded.matchAll(/[a-z][a-z\d+.-]*:\/\/[^"\s]+/giu)) {
        assert.notEqual(new URL(token).origin, diagnostic.origin)
        assert.notEqual(new URL(token).href, diagnostic.href)
      }
    })
  }
})

test("reset URL failure observation emits only a bounded canonical stdout protocol", async (t) => {
  const canonical =
    "UE_LIVE_RESET_URL_V1 project=desktop phase=reopen reset_route=false " +
    "token_query_absent=true token_fragment_absent=true token_url_absent=true\n"
  const valid = {
    resetRoute: false,
    tokenQueryAbsent: true,
    tokenFragmentAbsent: true,
    tokenUrlAbsent: true,
  }
  const privateMarker = "private-reset-detail-must-not-escape"

  async function fresh(label) {
    return import(urlStateUrl.href + "?contract=" + label)
  }

  async function capture(action) {
    const output = []
    const original = process.stdout.write
    process.stdout.write = (chunk) => {
      output.push(String(chunk))
      return true
    }
    try {
      await action()
    } finally {
      process.stdout.write = original
    }
    return output
  }

  async function rejected(observe, read, project = "desktop", phase = "reopen") {
    const original = new Error(privateMarker)
    await assert.rejects(
      () =>
        observe(project, phase, read, async (sample) => {
          await sample()
          throw original
        }),
      (error) => error === original
    )
  }

  await t.test("actual emitter produces the exact parser-bound record", async () => {
    const { withPasswordResetUrlDiagnostic: observe } = await fresh("canonical")
    const output = await capture(() => rejected(observe, async () => valid))
    assert.deepEqual(output, [canonical])
    assert.equal(output.join("").includes(privateMarker), false)
  })

  await t.test("validated primitive values are not read again while formatting", async () => {
    const { withPasswordResetUrlDiagnostic: observe } = await fresh("single-read")
    let reads = 0
    const state = {
      ...valid,
      get resetRoute() {
        reads += 1
        return reads === 1 ? false : privateMarker
      },
    }
    const output = await capture(() => rejected(observe, async () => state))
    assert.equal(reads, 1)
    assert.deepEqual(output, [canonical])
  })

  await t.test("successful assertions emit nothing and read only when polled", async () => {
    const { withPasswordResetUrlDiagnostic: observe } = await fresh("success")
    let reads = 0
    const output = await capture(() =>
      observe(
        "desktop",
        "reopen",
        async () => {
          reads += 1
          return valid
        },
        async (sample) => {
          assert.equal(reads, 0)
          assert.equal(await sample(), valid)
          assert.equal(reads, 1)
        }
      )
    )
    assert.equal(reads, 1)
    assert.deepEqual(output, [])
  })

  await t.test("no completed read or a later failed read cannot fabricate a snapshot", async () => {
    const { withPasswordResetUrlDiagnostic: observe } = await fresh("read-failure")
    for (const readsBeforeFailure of [0, 1]) {
      const original = new Error(privateMarker)
      let reads = 0
      const output = await capture(async () => {
        await assert.rejects(
          () =>
            observe(
              "desktop",
              "reopen",
              async () => {
                if (reads++ === readsBeforeFailure) throw original
                return valid
              },
              async (sample) => {
                await sample()
                await sample()
              }
            ),
          (error) => error === original
        )
      })
      assert.deepEqual(output, [])
    }
    const original = new Error(privateMarker)
    const output = await capture(async () => {
      await assert.rejects(
        () =>
          observe(
            "desktop",
            "reopen",
            async () => valid,
            async () => {
              throw original
            }
          ),
        (error) => error === original
      )
    })
    assert.deepEqual(output, [])
  })

  await t.test("only the last completed poll observation is reported", async () => {
    const { withPasswordResetUrlDiagnostic: observe } = await fresh("latest")
    const original = new Error(privateMarker)
    let reads = 0
    const output = await capture(async () => {
      await assert.rejects(
        () =>
          observe(
            "desktop",
            "reopen",
            async () => (reads++ === 0 ? { ...valid, resetRoute: true } : valid),
            async (sample) => {
              await sample()
              await sample()
              throw original
            }
          ),
        (error) => error === original
      )
    })
    assert.equal(reads, 2)
    assert.deepEqual(output, [canonical])
  })

  await t.test("unknown enums, extra fields and nonboolean values never enter stdout", async () => {
    const { withPasswordResetUrlDiagnostic: observe } = await fresh("invalid")
    const output = await capture(async () => {
      for (const project of ["", "private", "desktop\n", null, {}]) {
        await rejected(observe, async () => valid, project)
      }
      for (const phase of ["", "private", "reopen\n", null, {}]) {
        await rejected(observe, async () => valid, "desktop", phase)
      }
      const malformed = [undefined, null, [], {}, { ...valid, extra: privateMarker }]
      for (const key of Object.keys(valid)) {
        for (const value of [undefined, null, 0, 1, "true", privateMarker]) {
          malformed.push({ ...valid, [key]: value })
        }
      }
      for (const state of malformed) await rejected(observe, async () => state)
    })
    assert.deepEqual(output, [])
  })

  await t.test("only the first observation per project and phase is emitted", async () => {
    const { withPasswordResetUrlDiagnostic: observe } = await fresh("bounded")
    const output = await capture(async () => {
      for (const project of ["desktop", "mobile"]) {
        for (const phase of ["history", "reopen"]) {
          await rejected(observe, async () => valid, project, phase)
          await rejected(observe, async () => ({ ...valid, resetRoute: true }), project, phase)
        }
      }
    })
    assert.equal(output.length, 4)
    assert.equal(new Set(output).size, 4)
    assert.ok(output.every((row) => row.length <= 160 && row.endsWith("\n")))
  })

  await t.test("a broken diagnostic stream preserves the identical assertion failure", async () => {
    const { withPasswordResetUrlDiagnostic: observe } = await fresh("broken-stream")
    const originalWrite = process.stdout.write
    process.stdout.write = () => {
      throw new Error(privateMarker)
    }
    try {
      await rejected(observe, async () => valid)
    } finally {
      process.stdout.write = originalWrite
    }
  })
})

const forgotDiagnosticUrl = new URL("./password-forgot-diagnostic.ts", import.meta.url)
const forgotSnapshot = () => ({
  forgotRoute: true,
  hydrated: true,
  formPresent: true,
  formInvalid: false,
  formAlert: false,
  submitPresent: true,
  submitDisabled: false,
  submitBusy: false,
  successMarkerVisible: false,
})
const forgotStat = () => ({
  requests: "0",
  responses: "0",
  completed: "0",
  failed: "0",
  status: "none",
  responsePhase: "none",
})
const forgotRecord = () => ({
  scope: "main-frame-navigation-window",
  schema: 1,
  project: "mobile",
  attempt: 0,
  phase: "success",
  elapsed: "ge15s",
  auth: forgotStat(),
  csrf: forgotStat(),
  forgot: forgotStat(),
  snapshot: forgotSnapshot(),
})
const loadForgotDiagnostic = (name) => import(forgotDiagnosticUrl.href + "?contract=" + name)

test("forgot observation preserves the existing four awaits and gate configuration", () => {
  const source = readFileSync(specPath, "utf8")
  const block = source.slice(
    source.indexOf("  await withPasswordForgotDiagnostics("),
    source.indexOf("  const resetMatch =")
  )
  for (const statement of [
    'await page.goto("/forgot-password")',
    'await page.getByRole("textbox", { name: "E-mail" }).fill(email)',
    'await page.getByRole("button", { name: "Отправить ссылку" }).click()',
    'await expect(page.getByText("Проверьте почту")).toBeVisible()',
  ])
    assert.equal(block.split(statement).length - 1, 1)
  assert.match(block, /deadlineAtMs: identityDeadlineAtMs/u)
  assert.match(block, /attempt: testInfo.retry/u)
  assert.doesNotMatch(
    block,
    /waitFor|setTimeout|\.route\(|\.post\(|setTimeout|setDefaultTimeout|test\.slow|\.skip\(/u
  )
  const config = readFileSync(configPath, "utf8")
  assert.match(config, /retries: process.env.CI \? 1 : 0/u)
  assert.match(config, /failOnFlakyTests: Boolean\(process.env.CI\)/u)
  assert.match(config, /expect: \{ timeout: 15_000 \}/u)
  assert.match(config, /timeout: 60_000/u)
})

test("forgot schema rejects private values, getters, symbols and inconsistent counts", async () => {
  const { validatedPasswordForgotRecord: validate } = await loadForgotDiagnostic("schema")
  assert.deepEqual(validate(forgotRecord()), forgotRecord())
  const invalid = [
    { ...forgotRecord(), email: "private-canary@example.invalid" },
    { ...forgotRecord(), schema: true },
    { ...forgotRecord(), attempt: 2 },
    { ...forgotRecord(), phase: "private-canary" },
    { ...forgotRecord(), elapsed: Infinity },
    { ...forgotRecord(), auth: { ...forgotStat(), status: "401" } },
    { ...forgotRecord(), csrf: { ...forgotStat(), completed: "1" } },
    { ...forgotRecord(), forgot: { ...forgotStat(), requests: "1", failed: "many" } },
    { ...forgotRecord(), forgot: { ...forgotStat(), headers: "private-canary" } },
    { ...forgotRecord(), snapshot: { ...forgotSnapshot(), hydrated: "true" } },
    { ...forgotRecord(), snapshot: { ...forgotSnapshot(), formPresent: false } },
    { ...forgotRecord(), snapshot: { ...forgotSnapshot(), token: "private-canary" } },
  ]
  let getters = 0
  const getter = forgotRecord()
  Object.defineProperty(getter, "project", {
    get() {
      getters++
      throw Error("private-canary")
    },
  })
  invalid.push(getter)
  const symbol = forgotRecord()
  symbol[Symbol("private-canary")] = true
  invalid.push(symbol)
  for (const value of invalid) assert.equal(validate(value), null)
  assert.equal(getters, 0)
  assert.deepEqual(validate({ ...forgotRecord(), snapshot: null }), {
    ...forgotRecord(),
    snapshot: null,
  })
})

test("forgot sink emits at most one safe frame per project and attempt", async (t) => {
  const { reportPasswordForgotFailure } = await loadForgotDiagnostic("sink")
  const output = []
  t.mock.method(process.stdout, "write", (line) => {
    output.push(line)
    return true
  })
  for (const project of ["desktop", "mobile"])
    for (const attempt of [0, 1]) {
      reportPasswordForgotFailure({ ...forgotRecord(), project, attempt })
      reportPasswordForgotFailure({ ...forgotRecord(), project, attempt, phase: "click" })
    }
  reportPasswordForgotFailure({ ...forgotRecord(), attempt: 3 })
  reportPasswordForgotFailure({ ...forgotRecord(), private: "secret-canary" })
  assert.equal(output.length, 4)
  for (const line of output) {
    assert.match(line, /^UE_LIVE_PASSWORD_FORGOT_V1 [\x20-\x7e]+\n$/u)
    assert.ok(Buffer.byteLength(line, "utf8") <= 2048)
    assert.doesNotMatch(line, /secret-canary|https?:|@|token/u)
  }
})

test("forgot observer correlates exact transport events and preserves original failure", async (t) => {
  const { EventEmitter } = await import("node:events")
  const { withPasswordForgotDiagnostics } = await loadForgotDiagnostic("events")
  const output = []
  t.mock.method(process.stdout, "write", (line) => {
    output.push(line)
    return true
  })
  const page = new EventEmitter()
  let evaluations = 0
  page.evaluate = async () => {
    evaluations++
    return forgotSnapshot()
  }
  const origin = "https://127.0.0.1:30443"
  const mainFrame = { url: () => origin + "/forgot-password" }
  page.mainFrame = () => mainFrame
  let forbiddenReads = 0
  const forbidden = () => {
    forbiddenReads++
    throw Error("private-canary")
  }
  const request = (path, method = "GET") => ({
    url: () => origin + path,
    method: () => method,
    frame: () => mainFrame,
    headers: forbidden,
    postData: forbidden,
    failure: forbidden,
  })
  const response = (req, status) => ({
    request: () => req,
    status: () => status,
    headers: forbidden,
    text: forbidden,
    json: forbidden,
    body: forbidden,
  })
  const failure = Error("private-canary")
  await assert.rejects(
    withPasswordForgotDiagnostics(
      page,
      {
        project: "mobile",
        attempt: 0,
        ownedOrigin: origin,
        deadlineAtMs: performance.now() + 5_000,
      },
      async (mark) => {
        const previousDocument = request("/api/v1/users/me")
        page.emit("request", previousDocument)
        page.emit("framenavigated", mainFrame)
        page.emit("response", response(previousDocument, 200))
        const foreignFrame = { ...request("/api/v1/users/me"), frame: () => ({}) }
        page.emit("request", foreignFrame)
        page.emit("response", response(foreignFrame, 200))
        const auth = request("/api/v1/users/me")
        const csrf = request("/api/v1/auth/csrf-cookie")
        page.emit("request", auth)
        page.emit("response", response(auth, 401))
        page.emit("requestfinished", auth)
        page.emit("request", csrf)
        for (const alias of [
          "/api/v1/password/forgot?email=private-canary",
          "/api/v1/x/../password/forgot",
          "/api/v1/password/%66orgot",
          "/api/v1/password/forgot#private-canary",
        ]) {
          page.emit("request", request(alias, "POST"))
        }
        mark("click")
        page.emit("response", response(csrf, 204))
        page.emit("requestfinished", csrf)
        const first = request("/api/v1/password/forgot", "POST")
        const second = request("/api/v1/password/forgot", "POST")
        page.emit("request", first)
        page.emit("response", response(first, 429))
        page.emit("requestfinished", first)
        page.emit("request", second)
        page.emit("response", response(second, 200))
        page.emit("requestfinished", second)
        const failed = request("/api/v1/password/forgot", "POST")
        page.emit("request", failed)
        page.emit("requestfailed", failed)
        mark("success")
        throw failure
      }
    ),
    (error) => error === failure
  )
  assert.equal(evaluations, 1)
  assert.equal(forbiddenReads, 0)
  assert.equal(output.length, 1)
  const record = JSON.parse(output[0].slice("UE_LIVE_PASSWORD_FORGOT_V1 ".length))
  assert.equal(record.scope, "main-frame-navigation-window")
  assert.equal(record.auth.requests, "1")
  assert.equal(record.auth.status, "401")
  assert.equal(record.auth.responsePhase, "before-click")
  assert.equal(record.csrf.responsePhase, "after-click")
  assert.deepEqual(record.forgot, {
    requests: "many",
    responses: "many",
    completed: "many",
    failed: "1",
    status: "mixed",
    responsePhase: "after-click",
  })
  assert.equal(page.eventNames().length, 0)
  assert.doesNotMatch(output.join(""), /private-canary|https?:|@/u)
})

test("forgot failure snapshot does not start after the existing deadline", async (t) => {
  const { EventEmitter } = await import("node:events")
  const { withPasswordForgotDiagnostics } = await loadForgotDiagnostic("expired")
  const page = new EventEmitter()
  const output = []
  let evaluations = 0
  page.evaluate = async () => {
    evaluations++
    return forgotSnapshot()
  }
  t.mock.method(process.stdout, "write", (line) => {
    output.push(line)
    return true
  })
  const failure = Error("original")
  await assert.rejects(
    withPasswordForgotDiagnostics(
      page,
      {
        project: "mobile",
        attempt: 0,
        ownedOrigin: "https://127.0.0.1:30443",
        deadlineAtMs: performance.now() - 1,
      },
      async () => {
        throw failure
      }
    ),
    (error) => error === failure
  )
  assert.equal(evaluations, 0)
  assert.equal(JSON.parse(output[0].slice("UE_LIVE_PASSWORD_FORGOT_V1 ".length)).snapshot, null)
  assert.equal(page.eventNames().length, 0)
})

test("forgot success and diagnostic failures cannot change action outcome or leave listeners", async (t) => {
  const { EventEmitter } = await import("node:events")
  const { withPasswordForgotDiagnostics } = await loadForgotDiagnostic("outcome")
  const page = new EventEmitter()
  let calls = 0
  let evaluations = 0
  let writes = 0
  page.evaluate = async () => {
    evaluations++
    throw Error("private-canary")
  }
  t.mock.method(process.stdout, "write", () => {
    writes++
    throw Error("sink-private-canary")
  })
  const options = {
    project: "desktop",
    attempt: 0,
    ownedOrigin: "https://127.0.0.1:30443",
    deadlineAtMs: performance.now() + 1000,
  }
  assert.equal(
    await withPasswordForgotDiagnostics(page, options, async () => {
      calls++
      return 123
    }),
    123
  )
  assert.equal(calls, 1)
  assert.equal(evaluations, 0)
  assert.equal(writes, 0)
  assert.equal(page.eventNames().length, 0)
  const failure = Error("original")
  await assert.rejects(
    withPasswordForgotDiagnostics(page, options, async () => {
      calls++
      throw failure
    }),
    (error) => error === failure
  )
  assert.equal(calls, 2)
  assert.equal(evaluations, 1)
  assert.equal(writes, 1)
  assert.equal(page.eventNames().length, 0)
})

test("forgot snapshot rechecks the deadline immediately before starting evaluation", async (t) => {
  const { EventEmitter } = await import("node:events")
  const { withPasswordForgotDiagnostics } = await loadForgotDiagnostic("expires-before-start")
  const page = new EventEmitter()
  let evaluations = 0
  let reads = 0
  page.evaluate = async () => {
    evaluations++
    return forgotSnapshot()
  }
  // Wrapper start, failure elapsed, entry budget, then deferred evaluation.
  t.mock.method(performance, "now", () => [100, 100, 100, 102][reads++] ?? 102)
  t.mock.method(process.stdout, "write", () => true)
  const failure = Error("original")
  await assert.rejects(
    withPasswordForgotDiagnostics(
      page,
      {
        project: "mobile",
        attempt: 0,
        ownedOrigin: "https://127.0.0.1:30443",
        deadlineAtMs: 101,
      },
      async () => {
        throw failure
      }
    ),
    (error) => error === failure
  )
  assert.equal(evaluations, 0)
  assert.equal(page.eventNames().length, 0)
})

test("forgot snapshot wait is bounded by remaining budget and owns late rejection", async (t) => {
  const { EventEmitter } = await import("node:events")
  const { withPasswordForgotDiagnostics } = await loadForgotDiagnostic("pending-snapshot")
  const page = new EventEmitter()
  let rejectEvaluation
  let timer
  let timerCleared = false
  page.evaluate = () =>
    new Promise((_resolve, reject) => {
      rejectEvaluation = reject
    })
  t.mock.method(performance, "now", () => 100)
  t.mock.method(globalThis, "setTimeout", (callback, milliseconds) => {
    timer = { callback, milliseconds }
    return 1
  })
  t.mock.method(globalThis, "clearTimeout", () => {
    timerCleared = true
  })
  t.mock.method(process.stdout, "write", () => true)
  const failure = Error("original")
  const checked = assert.rejects(
    withPasswordForgotDiagnostics(
      page,
      {
        project: "mobile",
        attempt: 0,
        ownedOrigin: "https://127.0.0.1:30443",
        deadlineAtMs: 125,
      },
      async () => {
        throw failure
      }
    ),
    (error) => error === failure
  )
  await Promise.resolve()
  await Promise.resolve()
  assert.equal(timer.milliseconds, 25)
  timer.callback()
  await checked
  assert.equal(timerCleared, true)
  rejectEvaluation(Error("late-private-canary"))
  await Promise.resolve()
  await Promise.resolve()
  assert.equal(page.eventNames().length, 0)
})

test("forgot partial listener setup still invokes the original action exactly once", async (t) => {
  const { EventEmitter } = await import("node:events")
  const { withPasswordForgotDiagnostics } = await loadForgotDiagnostic("partial-setup")
  const page = new EventEmitter()
  const originalOn = page.on.bind(page)
  page.on = (event, listener) => {
    if (event === "response") throw Error("setup-private-canary")
    return originalOn(event, listener)
  }
  let calls = 0
  let evaluations = 0
  let writes = 0
  page.evaluate = async () => {
    evaluations++
    return forgotSnapshot()
  }
  t.mock.method(process.stdout, "write", () => {
    writes++
    return true
  })
  const options = {
    project: "mobile",
    attempt: 0,
    ownedOrigin: "https://127.0.0.1:30443",
    deadlineAtMs: performance.now() + 1000,
  }
  assert.equal(
    await withPasswordForgotDiagnostics(page, options, async () => {
      calls++
      return 123
    }),
    123
  )
  const failure = Error("original")
  await assert.rejects(
    withPasswordForgotDiagnostics(page, options, async () => {
      calls++
      throw failure
    }),
    (error) => error === failure
  )
  assert.equal(calls, 2)
  assert.equal(evaluations, 0)
  assert.equal(writes, 0)
  assert.equal(page.eventNames().length, 0)
})

test("forgot actual browser read returns only booleans and never reads private DOM or storage", async (t) => {
  const { EventEmitter } = await import("node:events")
  const { withPasswordForgotDiagnostics } = await loadForgotDiagnostic("dom-read")
  const page = new EventEmitter()
  const output = []
  let privateReads = 0
  const privateRead = () => {
    privateReads++
    throw Error("private-canary")
  }
  const form = {
    matches: (selector) => selector === ":invalid",
    querySelector: (selector) => (selector === '[role="alert"]' ? {} : null),
  }
  class Button {}
  const submit = Object.assign(new Button(), {
    disabled: true,
    closest: () => form,
    getAttribute: (name) => (name === "aria-busy" ? "true" : null),
  })
  const marker = { getBoundingClientRect: () => ({ width: 12, height: 12 }) }
  const document = {
    getElementById: (id) =>
      id === "forgot-submit-btn" ? submit : id === "forgot-back-to-login" ? marker : null,
  }
  const window = {
    __APP_HYDRATED: true,
    location: { pathname: "/forgot-password" },
    getComputedStyle: () => ({ visibility: "visible" }),
  }
  for (const target of [document, form, submit, marker]) {
    for (const key of ["textContent", "innerHTML", "outerHTML", "value", "cookie"])
      Object.defineProperty(target, key, { get: privateRead })
  }
  for (const key of ["localStorage", "sessionStorage"])
    Object.defineProperty(window, key, { get: privateRead })
  page.evaluate = async (read) =>
    JSON.parse(
      JSON.stringify(
        runInNewContext(
          "(" + Function.prototype.toString.call(read) + ")()",
          { document, window, HTMLButtonElement: Button },
          { timeout: 1000 }
        )
      )
    )
  t.mock.method(process.stdout, "write", (line) => {
    output.push(line)
    return true
  })
  const failure = Error("original")
  await assert.rejects(
    withPasswordForgotDiagnostics(
      page,
      {
        project: "desktop",
        attempt: 0,
        ownedOrigin: "https://127.0.0.1:30443",
        deadlineAtMs: performance.now() + 5000,
      },
      async () => {
        throw failure
      }
    ),
    (error) => error === failure
  )
  const snapshot = JSON.parse(output[0].slice("UE_LIVE_PASSWORD_FORGOT_V1 ".length)).snapshot
  assert.deepEqual(Object.keys(snapshot), Object.keys(forgotSnapshot()))
  assert.ok(Object.values(snapshot).every((value) => typeof value === "boolean"))
  assert.equal(snapshot.hydrated, true)
  assert.equal(snapshot.formInvalid, true)
  assert.equal(snapshot.submitBusy, true)
  assert.equal(snapshot.successMarkerVisible, true)
  assert.equal(privateReads, 0)
})

test("forgot unavailable frame observations remain finite and all listeners detach", async (t) => {
  const { EventEmitter } = await import("node:events")
  const { withPasswordForgotDiagnostics } = await loadForgotDiagnostic("unavailable-frame")
  const page = new EventEmitter()
  const output = []
  const origin = "https://127.0.0.1:30443"
  const mainFrame = {
    url: () => {
      throw Error("frame-private-canary")
    },
  }
  page.mainFrame = () => mainFrame
  page.evaluate = async () => forgotSnapshot()
  t.mock.method(process.stdout, "write", (line) => {
    output.push(line)
    return true
  })
  const failure = Error("original")
  await assert.rejects(
    withPasswordForgotDiagnostics(
      page,
      {
        project: "mobile",
        attempt: 0,
        ownedOrigin: origin,
        deadlineAtMs: performance.now() + 1000,
      },
      async () => {
        page.emit("framenavigated", mainFrame)
        page.emit("request", {
          url: () => origin + "/api/v1/password/forgot",
          method: () => "POST",
          frame: () => {
            throw Error("request-frame-private-canary")
          },
        })
        throw failure
      }
    ),
    (error) => error === failure
  )
  const record = JSON.parse(output[0].slice("UE_LIVE_PASSWORD_FORGOT_V1 ".length))
  assert.equal(record.scope, "unconfirmed")
  for (const route of ["auth", "csrf", "forgot"]) assert.deepEqual(record[route], forgotStat())
  assert.equal(page.eventNames().length, 0)
  assert.doesNotMatch(output.join(""), /private-canary/u)
})

test("forgot a request with unavailable frame is not attributed to the observed page", async (t) => {
  const { EventEmitter } = await import("node:events")
  const { withPasswordForgotDiagnostics } = await loadForgotDiagnostic("request-frame")
  const page = new EventEmitter()
  const output = []
  const origin = "https://127.0.0.1:30443"
  const mainFrame = { url: () => origin + "/forgot-password" }
  page.mainFrame = () => mainFrame
  page.evaluate = async () => forgotSnapshot()
  t.mock.method(process.stdout, "write", (line) => {
    output.push(line)
    return true
  })
  const failure = Error("original")
  await assert.rejects(
    withPasswordForgotDiagnostics(
      page,
      {
        project: "mobile",
        attempt: 0,
        ownedOrigin: origin,
        deadlineAtMs: performance.now() + 1000,
      },
      async () => {
        page.emit("framenavigated", mainFrame)
        page.emit("request", {
          url: () => origin + "/api/v1/password/forgot",
          method: () => "POST",
          frame: () => {
            throw Error("request-frame-private-canary")
          },
        })
        throw failure
      }
    ),
    (error) => error === failure
  )
  const record = JSON.parse(output[0].slice("UE_LIVE_PASSWORD_FORGOT_V1 ".length))
  assert.equal(record.scope, "main-frame-navigation-window")
  for (const route of ["auth", "csrf", "forgot"]) assert.deepEqual(record[route], forgotStat())
  assert.equal(page.eventNames().length, 0)
  assert.doesNotMatch(output.join(""), /private-canary/u)
})
