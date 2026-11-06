import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"
import { URL } from "node:url"

const specUrl = new URL("./zzz-aud174-prehydration-caddy-log.live.spec.ts", import.meta.url)
const runnerUrl = new URL("../../../scripts/live_stand.py", import.meta.url)
const packageUrl = new URL("../../package.json", import.meta.url)
const configUrl = new URL("../../playwright.live.config.ts", import.meta.url)
const authContractUrl = new URL("./auth-roles.contract.test.mjs", import.meta.url)
const aud178SpecUrl = new URL("./aud178-reset-referer-csp.live.spec.ts", import.meta.url)

test("pre-hydration login and project-correlated synthetic query use the real Core endpoint", async () => {
  const [spec, runner, packageSource, config, authContract] = await Promise.all([
    readFile(specUrl, "utf8"),
    readFile(runnerUrl, "utf8"),
    readFile(packageUrl, "utf8"),
    readFile(configUrl, "utf8"),
    readFile(authContractUrl, "utf8"),
  ])
  const packageJson = JSON.parse(packageSource)
  const contractCommand = packageJson.scripts?.["test:e2e:live:contract"] ?? ""

  assert.match(spec, /LIVE_CADDY_LOG_PROBE/u)
  assert.match(spec, /LIVE_CADDY_PROBE_IDS/u)
  assert.match(spec, /test\.use\(\{\s*javaScriptEnabled:\s*false\s*\}\)/u)
  assert.doesNotMatch(spec, /\.setJavaScriptEnabled\(/u)
  assert.match(spec, /await page\.goto\(["']\/login["']/u)
  assert.match(spec, /toHaveAttribute\(["']method["'],\s*["']post["']\)/u)
  assert.match(spec, /toBeDisabled\(\)/u)
  assert.match(spec, /__APP_HYDRATED/u)
  assert.match(spec, /loginDocumentRequests/u)
  assert.match(spec, /searchParams\.set\(["']probe["']/u)
  assert.match(spec, /searchParams\.set\(["']password["']/u)
  assert.match(spec, /page\.request\.get\(/u)
  assert.match(spec, /responseStatus !== 200/u)
  assert.match(
    spec,
    /const observation = \{\s*schema: "aud174-caddy-probe-v1",\s*project: projectName,\s*completed_at_ms: Date\.now\(\),\s*\}/u
  )
  assert.match(spec, /flag: "wx"/u)
  assert.doesNotMatch(
    spec,
    /page\.route\(|routeWebSocket|\.fulfill\(|useMockApi|console\.|process\.stdout|requestSubmit|\.click\(/u
  )
  assert.doesNotMatch(spec, /JSON\.stringify\(\{[^}]*correlation|JSON\.stringify\(\{[^}]*nonce/u)
  assert.match(config, /name:\s*["']desktop["']/u)
  assert.match(config, /name:\s*["']mobile["']/u)
  assert.match(authContract, /does not intercept auth traffic/u)
  assert.ok(/tests\/e2e-live\/zzz-aud174-prehydration-caddy-log\.live\.spec\.ts/u.test(runner))
  assert.match(contractCommand, /zzz-aud174-prehydration-caddy-log\.contract\.test\.mjs/u)
})

test("runner verifies exact per-project rows in complete, bounded windows from the owned Caddy container", async () => {
  const [runner, spec] = await Promise.all([readFile(runnerUrl, "utf8"), readFile(specUrl, "utf8")])
  const runnerHas = (pattern) => assert.ok(pattern.test(runner))
  runnerHas(/def _verified_live_core_caddy_container\(/u)
  runnerHas(/def _verify_live_caddy_probe_log\(/u)
  runnerHas(/_core_quiesce_container_inventory\(/u)
  runnerHas(/LIVE_CADDY_PROBE_IDS/u)
  runnerHas(/aud174-caddy-probe-v1/u)
  runnerHas(/completed_at_ms/u)
  runnerHas(/--since/u)
  runnerHas(/--until/u)
  assert.ok(!/--since["']?,\s*["']180s|--tail["']?,\s*["']256/u.test(runner))
  runnerHas(/timeout=10/u)
  runnerHas(/_LIVE_CADDY_PROBE_MAX_BYTES\s*=\s*1_048_576/u)
  runnerHas(/_LIVE_CADDY_ACCESS_LOGGER\s*=\s*"http\.log\.access\.log0"/u)
  runnerHas(/len\(output\) \+ len\(stderr\)/u)
  runnerHas(/nonce_bytes in output or nonce_bytes in stderr/u)
  runnerHas(/REDACTED/u)
  runnerHas(/set\(observed\) != set\(LIVE_CADDY_PROBE_PROJECTS\)/u)
  runnerHas(/_PLAYWRIGHT_SKIP_IDENTITY_LIMIT\s*=\s*220/u)
  assert.match(spec, /test\.describe\.configure\(\{\s*retries:\s*0\s*\}\)/u)
})

test("existing Core smoke selection supplies and verifies the Caddy probe", async () => {
  const runner = await readFile(runnerUrl, "utf8")
  assert.match(runner, /LIVE_E2E_SMOKE_FILES = \([\s\S]*?LIVE_CADDY_PROBE_SPEC,\s*\r?\n\)/u)
  assert.match(
    runner,
    /if mode == "smoke":\s*return LIVE_CADDY_PROBE_SPEC in LIVE_E2E_SMOKE_FILES/u
  )
  assert.match(runner, /probe_enabled = _live_e2e_probe_selected\(mode, selected_specs\)/u)
  assert.match(runner, /playwright_environment\["LIVE_CADDY_LOG_PROBE"\] = probe_nonce/u)
  assert.match(runner, /playwright_environment\["LIVE_CADDY_PROBE_IDS"\] = json\.dumps/u)
  assert.match(runner, /_verify_live_caddy_probe_log\(/u)
})

test("AUD178 binds both initial reset targets to bounded Caddy rows", async () => {
  const [resetSpec, runner] = await Promise.all([
    readFile(aud178SpecUrl, "utf8"),
    readFile(runnerUrl, "utf8"),
  ])

  assert.match(resetSpec, /LIVE_AUD178_PROBE_MARKERS/u)
  assert.match(resetSpec, /legacyTarget\.searchParams\.set\(["']token["'],\s*legacyMarker\)/u)
  assert.match(
    resetSpec,
    /legacyTarget\.pathname \+= `\/\$\{encodeURIComponent\(legacyMarker\)\}`/u
  )
  assert.match(
    resetSpec,
    /const isLegacyDocumentRequest =\s*route\.request\(\)\.isNavigationRequest\(\) &&\s*requestUrl\.pathname === legacyTarget\.pathname &&\s*requestUrl\.search === legacyTarget\.search/u
  )
  assert.match(
    resetSpec,
    /if \(isLegacyDocumentRequest\) \{\s*const requestHeaders = await route\.request\(\)\.allHeaders\(\)\s*requestHeaders\["x-aud178-correlation"\] = resetBinding\.correlationId/u
  )
  assert.match(resetSpec, /x-aud178-correlation/u)
  assert.match(resetSpec, /Reflect\.set\(requestHeaders, "x-aud178-correlation", undefined\)/u)
  assert.match(resetSpec, /aud178-reset-caddy-probe-\$\{project\}\.json/u)
  assert.match(resetSpec, /query_completed_at_ms/u)
  assert.match(resetSpec, /path_completed_at_ms/u)

  // Keep the browser wire assertions in the same spec that creates each log marker.
  assert.match(resetSpec, /expect\(earlyHealthHeaders\.referer === undefined\)\.toBe\(true\)/u)
  assert.match(resetSpec, /expect\(earlyReportHeaders\.referer === undefined\)\.toBe\(true\)/u)
  assert.match(resetSpec, /reportNamesResetDocument\(earlyReportBody, legacyTarget\.origin\)/u)
  assert.match(resetSpec, /earlyReportLeaks\)\.toEqual\(\[false, false\]\)/u)

  assert.match(runner, /LIVE_AUD178_RESET_PROBE_SPEC/u)
  assert.match(runner, /_new_live_aud178_reset_probe_values/u)
  assert.match(runner, /LIVE_AUD178_PROBE_MARKERS/u)
  assert.match(runner, /probe_kind="aud178"/u)
  assert.match(runner, /_assert_live_aud178_reset_probe_redaction\(/u)
  assert.match(runner, /marker_bytes in output or marker_bytes in stderr/u)
  assert.match(runner, /name\.casefold\(\) == "x-aud178-correlation"/u)
  assert.match(runner, /request\.get\("uri"\) != "\[REDACTED\]"/u)
  assert.match(runner, /payload\.get\("status"\) != 302/u)
  assert.match(runner, /since_ms \* 1_000_000 <= row_timestamp_ns <= until_ms \* 1_000_000/u)
  assert.match(runner, /reset_cases=4/u)
  assert.match(runner, /LIVE_CADDY_PROBE_SPEC not in selected_files/u)
})
