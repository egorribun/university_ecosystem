import assert from "node:assert/strict"
import { execFileSync } from "node:child_process"
import { createHash } from "node:crypto"
import {
  existsSync,
  lstatSync,
  mkdtempSync,
  readFileSync,
  realpathSync,
  rmSync,
  writeFileSync,
} from "node:fs"
import { createServer } from "node:http"
import { createRequire } from "node:module"
import { tmpdir } from "node:os"
import { dirname, isAbsolute, join, relative, resolve } from "node:path"
import { pathToFileURL } from "node:url"

const VERSIONS = Object.freeze({
  "@lhci/cli": "0.15.1",
  "@lhci/utils": "0.15.1",
  lighthouse: "13.5.0",
  "puppeteer-core": "25.13.0",
  "chromium-bidi": "157.0.8090-0",
  zod: "4.6.7",
  playwright: "1.64.1",
  "playwright-core": "1.64.1",
})
const FIXTURE_VALUE = "browser-dependency-smoke"

function regularBytes(path, limit) {
  assert.equal(realpathSync(path), path)
  const stat = lstatSync(path)
  assert(stat.isFile() && !stat.isSymbolicLink())
  assert(stat.size > 0 && stat.size <= limit)
  const bytes = readFileSync(path)
  assert.equal(bytes.length, stat.size)
  return bytes
}

export function inspectBrowserDependencies(frontend) {
  assert.equal(realpathSync(frontend), frontend)
  const rootManifest = join(frontend, "package.json")
  regularBytes(rootManifest, 65536)
  const manifests = new Map()
  const inspect = (name, parent = rootManifest) => {
    const path = createRequire(parent).resolve(name + "/package.json")
    assert.equal(path, join(frontend, "node_modules", name, "package.json"))
    const manifest = JSON.parse(regularBytes(path, 65536))
    assert.equal(manifest.name, name)
    assert.equal(manifest.version, VERSIONS[name])
    manifests.set(name, path)
    return path
  }
  const cli = inspect("@lhci/cli")
  const utils = inspect("@lhci/utils", cli)
  const lighthouse = inspect("lighthouse", cli)
  assert.equal(inspect("lighthouse", utils), lighthouse)
  const puppeteer = inspect("puppeteer-core", lighthouse)
  const bidi = inspect("chromium-bidi", puppeteer)
  inspect("zod", bidi)
  const playwright = inspect("playwright")
  const core = inspect("playwright-core", playwright)
  const registry = JSON.parse(regularBytes(join(dirname(core), "browsers.json"), 65536))
  assert(Array.isArray(registry.browsers))
  const chromium = registry.browsers.filter((browser) => browser.name === "chromium")
  assert.equal(chromium.length, 1)
  assert.match(chromium[0].revision, /^[1-9][0-9]{0,31}$/)
  const entry = (name, parent) => {
    const path = createRequire(parent).resolve(name)
    const packageRoot = dirname(manifests.get(name))
    const inside = relative(packageRoot, path)
    assert(inside && !inside.startsWith("..") && !isAbsolute(inside))
    regularBytes(path, 16 * 1024 * 1024)
    return path
  }
  return {
    versions: { ...VERSIONS },
    chromiumRevision: chromium[0].revision,
    entrypoints: {
      lighthouse: entry("lighthouse", cli),
      puppeteer: entry("puppeteer-core", lighthouse),
      playwright: entry("playwright", rootManifest),
    },
  }
}

export function browserLaunchOptions(executablePath, userDataDir, protocol) {
  assert(typeof executablePath === "string" && isAbsolute(executablePath))
  assert(typeof userDataDir === "string" && isAbsolute(userDataDir))
  assert(protocol === "cdp" || protocol === "webDriverBiDi")
  return {
    executablePath,
    userDataDir,
    protocol,
    headless: true,
    debuggingPort: 0,
    timeout: 15000,
    protocolTimeout: 10000,
    // Match the existing hosted Playwright sandbox policy, only for owned HTML.
    args: ["--no-sandbox", "--disable-background-networking"],
    env: { HOME: userDataDir, TMPDIR: userDataDir, LANG: "C.UTF-8", TZ: "UTC" },
  }
}

export async function createLoopbackFixture() {
  const html =
    '<!doctype html><html lang="en"><head><meta charset="utf-8">' +
    "<title>Browser dependency smoke</title></head>" +
    '<body><main id="smoke">browser-dependency-smoke</main></body></html>'
  const server = createServer((request, response) => {
    const owned = request.method === "GET" && request.url === "/"
    response.writeHead(owned ? 200 : 404, {
      "content-type": "text/html; charset=utf-8",
      "cache-control": "no-store",
      "content-security-policy": "default-src 'none'",
    })
    response.end(owned ? html : "")
  })
  server.requestTimeout = 5000
  server.headersTimeout = 5000
  server.keepAliveTimeout = 1000
  server.maxConnections = 4
  await new Promise((resolveListen, rejectListen) => {
    server.once("error", rejectListen)
    server.listen(0, "127.0.0.1", resolveListen)
  })
  const address = server.address()
  assert(address && typeof address === "object" && address.address === "127.0.0.1")
  return {
    url: "http://127.0.0.1:" + address.port + "/",
    async close() {
      if (!server.listening) return
      const closed = new Promise((resolveClose, rejectClose) => {
        server.close((error) => (error ? rejectClose(error) : resolveClose()))
      })
      server.closeAllConnections()
      await closed
    },
  }
}

export async function runBrowserChecks(libraries, executablePath, fixtureUrl) {
  const fixture = new URL(fixtureUrl)
  assert.equal(fixture.protocol, "http:")
  assert.equal(fixture.hostname, "127.0.0.1")
  assert(fixture.port && Number(fixture.port) > 0)
  assert.equal(fixture.pathname, "/")
  assert(!fixture.username && !fixture.password && !fixture.search && !fixture.hash)
  async function withBrowser(protocol, check) {
    const profile = mkdtempSync(join(tmpdir(), "browser-dependency-smoke-"))
    let browser
    try {
      browser = await libraries.puppeteer.launch(
        browserLaunchOptions(executablePath, profile, protocol)
      )
      assert.equal(browser.protocol, protocol)
      return await check(browser)
    } finally {
      try {
        if (browser) await browser.close()
      } finally {
        rmSync(profile, { recursive: true, force: true })
      }
    }
  }
  const browserVersion = await withBrowser("cdp", async (browser) => {
    const endpoint = new URL(browser.wsEndpoint())
    assert.equal(endpoint.protocol, "ws:")
    assert.equal(endpoint.hostname, "127.0.0.1")
    assert(endpoint.port && Number(endpoint.port) > 0)
    assert(!endpoint.username && !endpoint.password && !endpoint.search && !endpoint.hash)
    const result = await libraries.lighthouse(fixtureUrl, {
      hostname: "127.0.0.1",
      port: Number(endpoint.port),
      logLevel: "error",
      output: "json",
      onlyAudits: ["document-title"],
      throttlingMethod: "provided",
      maxWaitForLoad: 15000,
      disableStorageReset: true,
    })
    assert(result?.lhr && !result.lhr.runtimeError)
    assert.equal(result.lhr.lighthouseVersion, VERSIONS.lighthouse)
    assert.equal(result.lhr.requestedUrl, fixtureUrl)
    assert.equal(result.lhr.finalDisplayedUrl, fixtureUrl)
    assert.equal(result.lhr.audits?.["document-title"]?.score, 1)
    return browser.version()
  })
  await withBrowser("webDriverBiDi", async (browser) => {
    const page = await browser.newPage()
    const response = await page.goto(fixtureUrl, { waitUntil: "load", timeout: 10000 })
    assert.equal(response?.status(), 200)
    const value = await page.evaluate(
      () => globalThis.document.getElementById("smoke")?.textContent
    )
    assert.equal(value, FIXTURE_VALUE)
  })
  return { browserVersion, lighthouseDocumentTitle: true, bidiDomValue: FIXTURE_VALUE }
}

export function buildSmokeReport(input) {
  assert.match(input.sourceSha, /^[0-9a-f]{40}$/)
  assert.match(input.lockSha256, /^[0-9a-f]{64}$/)
  assert.match(input.runId, /^[1-9][0-9]{0,19}$/)
  assert.match(input.runAttempt, /^[1-9][0-9]{0,19}$/)
  assert.deepEqual(input.versions, VERSIONS)
  assert.match(input.chromiumRevision, /^[1-9][0-9]{0,31}$/)
  assert.match(input.results.browserVersion, /^(?:Headless)?Chrome\/[0-9]+(?:\.[0-9]+){3}$/)
  assert(input.results.browserVersion.length <= 80)
  assert.equal(input.results.lighthouseDocumentTitle, true)
  assert.equal(input.results.bidiDomValue, FIXTURE_VALUE)
  const report = {
    schemaVersion: 1,
    purpose: "browser-dependency-compatibility",
    sourceSha: input.sourceSha,
    lockSha256: input.lockSha256,
    runId: input.runId,
    runAttempt: input.runAttempt,
    versions: { ...VERSIONS },
    chromiumRevision: input.chromiumRevision,
    browserVersion: input.results.browserVersion,
    checks: { lighthouseDocumentTitle: true, bidiDomValue: FIXTURE_VALUE },
    performanceAcceptance: false,
  }
  assert(Buffer.byteLength(JSON.stringify(report)) < 2048)
  return report
}

async function main() {
  let stage = "preflight"
  let fixture
  try {
    assert.equal(process.argv.length, 2)
    assert.equal(process.platform, "linux")
    assert.equal(process.env.GITHUB_REPOSITORY, "egorribun/university_ecosystem")
    const sourceSha = process.env.SOURCE_SHA
    const runId = process.env.SMOKE_RUN_ID
    const runAttempt = process.env.SMOKE_RUN_ATTEMPT
    assert.match(sourceSha ?? "", /^[0-9a-f]{40}$/)
    assert.match(runId ?? "", /^[1-9][0-9]{0,19}$/)
    assert.match(runAttempt ?? "", /^[1-9][0-9]{0,19}$/)
    const workspace = realpathSync(process.env.GITHUB_WORKSPACE)
    const frontend = join(workspace, "frontend")
    assert.equal(realpathSync(process.cwd()), frontend)
    const head = execFileSync("/usr/bin/git", ["rev-parse", "HEAD"], {
      cwd: workspace,
      env: { PATH: "/usr/bin:/bin" },
      encoding: "utf8",
      timeout: 5000,
      maxBuffer: 1024,
    }).trim()
    assert.equal(head, sourceSha)
    const outputRoot = realpathSync(process.env.RUNNER_TEMP)
    assert.equal(outputRoot, resolve(process.env.RUNNER_TEMP))
    const reportPath = join(
      outputRoot,
      "browser-dependency-smoke-" + runId + "-" + runAttempt + "-" + sourceSha + ".json"
    )
    assert(!existsSync(reportPath))
    const lockPath = join(frontend, "package-lock.json")
    const lockBytes = regularBytes(lockPath, 4 * 1024 * 1024)
    const lock = JSON.parse(lockBytes)
    for (const [name, version] of Object.entries(VERSIONS)) {
      assert.equal(lock.packages["node_modules/" + name]?.version, version)
    }

    stage = "installed dependency inspection"
    const inspected = inspectBrowserDependencies(frontend)
    const lighthouseModule = await import(pathToFileURL(inspected.entrypoints.lighthouse).href)
    const puppeteerModule = await import(pathToFileURL(inspected.entrypoints.puppeteer).href)
    const playwrightModule = await import(pathToFileURL(inspected.entrypoints.playwright).href)
    const lighthouse = lighthouseModule.default
    const puppeteer = puppeteerModule.default
    const playwright = playwrightModule.default ?? playwrightModule
    assert.equal(typeof lighthouse, "function")
    assert.equal(typeof puppeteer.launch, "function")
    const executablePath = playwright.chromium.executablePath()
    assert.equal(realpathSync(executablePath), executablePath)
    assert(lstatSync(executablePath).isFile())
    assert(executablePath.split("/").includes("chromium-" + inspected.chromiumRevision))

    stage = "owned browser compatibility"
    fixture = await createLoopbackFixture()
    const results = await runBrowserChecks({ lighthouse, puppeteer }, executablePath, fixture.url)
    await fixture.close()
    fixture = undefined

    stage = "bounded evidence"
    assert.deepEqual(regularBytes(lockPath, 4 * 1024 * 1024), lockBytes)
    const report = buildSmokeReport({
      sourceSha,
      lockSha256: createHash("sha256").update(lockBytes).digest("hex"),
      runId,
      runAttempt,
      versions: inspected.versions,
      chromiumRevision: inspected.chromiumRevision,
      results,
    })
    const bytes = JSON.stringify(report, null, 2) + "\n"
    assert(Buffer.byteLength(bytes) < 2048)
    writeFileSync(reportPath, bytes, { flag: "wx", mode: 0o600 })
    console.log("Browser dependency smoke passed; performance acceptance not assessed.")
  } catch {
    process.exitCode = 1
    console.error("Browser dependency smoke rejected at stage: " + stage)
  } finally {
    if (fixture) {
      try {
        await fixture.close()
      } catch {
        process.exitCode = 1
        console.error("Browser dependency smoke rejected at stage: fixture cleanup")
      }
    }
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  await main()
}
