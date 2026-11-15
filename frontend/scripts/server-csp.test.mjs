import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import path from "node:path"
import test from "node:test"
import { fileURLToPath } from "node:url"

import {
  applyNodeCspToHtmlResponse,
  buildNodeCspHeaders,
  shouldUpgradeInsecureRequests,
} from "./server-csp.mjs"

const SCRIPTS_DIRECTORY = path.dirname(fileURLToPath(import.meta.url))
const FRONTEND_ROOT = path.resolve(SCRIPTS_DIRECTORY, "..")
const NONCE = "AAAAAAAAAAAAAAAAAAAAAA=="
const UPGRADE = "upgrade-insecure-requests"

test("loopback literal hosts over plain http omit upgrade-insecure-requests", () => {
  const loopbackHosts = [
    "127.0.0.1",
    "127.0.0.1:5173",
    "localhost",
    "localhost:4175",
    "[::1]",
    "[::1]:5173",
    "::1",
  ]
  for (const host of loopbackHosts) {
    assert.equal(shouldUpgradeInsecureRequests({ host }), false, `${host} without a proto header`)
    assert.equal(
      shouldUpgradeInsecureRequests({ host, forwardedProto: "http" }),
      false,
      `${host} marked http`
    )
    assert.equal(
      shouldUpgradeInsecureRequests({ host, forwardedProto: " HTTP " }),
      false,
      `${host} marked http with case and whitespace`
    )
  }
})

test("loopback hosts marked as https keep upgrade-insecure-requests", () => {
  for (const forwardedProto of ["https", "HTTPS", " https ", "https, http", "", ["http"]]) {
    assert.equal(
      shouldUpgradeInsecureRequests({ host: "127.0.0.1:5173", forwardedProto }),
      true,
      `forwarded proto ${JSON.stringify(forwardedProto)} must fail closed`
    )
  }
  assert.equal(shouldUpgradeInsecureRequests({ host: "localhost", forwardedProto: "https" }), true)
  assert.equal(shouldUpgradeInsecureRequests({ host: "[::1]", forwardedProto: "https" }), true)
})

test("real production hosts keep upgrade-insecure-requests on every protocol", () => {
  for (const host of [
    "app.example.com",
    "app.example.com:443",
    "university.example.org:8443",
    "10.0.0.5:8080",
  ]) {
    assert.equal(shouldUpgradeInsecureRequests({ host }), true, `${host} without a proto header`)
    assert.equal(
      shouldUpgradeInsecureRequests({ host, forwardedProto: "http" }),
      true,
      `${host} marked http`
    )
    assert.equal(
      shouldUpgradeInsecureRequests({ host, forwardedProto: "https" }),
      true,
      `${host} marked https`
    )
  }
})

test("host header spoofs that only contain a loopback literal keep the directive", () => {
  const spoofedHosts = [
    "127.0.0.1.evil.com",
    "127.0.0.1.evil.com:5173",
    "localhost.evil.com",
    "localhost.evil.com:5173",
    "evil.com:127.0.0.1",
    "evil.com/127.0.0.1",
    "127.0.0.1@evil.com",
    "user@127.0.0.1",
    "[::1].evil.com",
    "[::1]evil.com",
    "xlocalhost",
    "127.0.0.2",
    "127.0.0.1:5173:5173",
    "127.0.0.1 ",
    " localhost",
  ]
  for (const host of spoofedHosts) {
    assert.equal(shouldUpgradeInsecureRequests({ host }), true, `${JSON.stringify(host)}`)
  }
})

test("missing or non-string hosts keep the directive", () => {
  for (const host of [undefined, null, "", 127, ["127.0.0.1"]]) {
    assert.equal(shouldUpgradeInsecureRequests({ host }), true, String(host))
  }
  assert.equal(shouldUpgradeInsecureRequests(), true)
})

test("IPv6 loopback is only recognised in its exact bracketed or bare form", () => {
  assert.equal(shouldUpgradeInsecureRequests({ host: "[::1]:5173" }), false)
  assert.equal(shouldUpgradeInsecureRequests({ host: "[::2]" }), true)
  assert.equal(shouldUpgradeInsecureRequests({ host: "[0:0:0:0:0:0:0:1]" }), true)
  assert.equal(shouldUpgradeInsecureRequests({ host: "::1:5173" }), true)
  assert.equal(shouldUpgradeInsecureRequests({ host: "[fe80::1]" }), true)
})

test("the default builder keeps upgrade-insecure-requests in the enforcing policy only", () => {
  const headers = buildNodeCspHeaders(NONCE)
  const enforced = headers["content-security-policy"]
  const reportOnly = headers["content-security-policy-report-only"]
  assert.equal(enforced.split("; ").filter((directive) => directive === UPGRADE).length, 1)
  assert.equal(reportOnly.includes(UPGRADE), false)
  assert.equal(
    buildNodeCspHeaders(NONCE, { upgradeInsecureRequests: true })["content-security-policy"],
    enforced
  )
})

test("opting out removes the directive from the enforcing policy and keeps everything else", () => {
  const enforced = buildNodeCspHeaders(NONCE)["content-security-policy"]
  const headers = buildNodeCspHeaders(NONCE, { upgradeInsecureRequests: false })
  assert.equal(headers["content-security-policy"], enforced.replace(`; ${UPGRADE}`, ""))
  assert.equal(headers["content-security-policy"].includes(UPGRADE), false)
  assert.equal(headers["content-security-policy-report-only"].includes(UPGRADE), false)
  assert.throws(() => buildNodeCspHeaders(NONCE, { upgradeInsecureRequests: "false" }), TypeError)
})

test("the HTML response helper threads the upgrade option to the enforcing header", async () => {
  const response = () =>
    new Response("<!doctype html><html></html>", {
      headers: { "content-type": "text/html; charset=utf-8" },
    })

  const upgraded = applyNodeCspToHtmlResponse(response(), NONCE)
  assert.ok(upgraded.headers.get("content-security-policy").includes(UPGRADE))

  const loopback = applyNodeCspToHtmlResponse(response(), NONCE, {
    upgradeInsecureRequests: false,
  })
  assert.equal(loopback.headers.get("content-security-policy").includes(UPGRADE), false)
  assert.equal(loopback.headers.get("content-security-policy-report-only").includes(UPGRADE), false)
  assert.ok(loopback.headers.get("content-security-policy").includes(`'nonce-${NONCE}'`))
})

test("the SSR and static HTML callers derive the option from the request headers", async () => {
  const serverSource = await readFile(path.join(FRONTEND_ROOT, "src", "server.ts"), "utf8")
  const serverProdSource = await readFile(path.join(SCRIPTS_DIRECTORY, "server-prod.mjs"), "utf8")
  assert.match(
    serverSource,
    /applyNodeCspToHtmlResponse\(\s*response,\s*nonce,\s*\{\s*upgradeInsecureRequests:\s*shouldUpgradeInsecureRequests\(\{\s*host:\s*request\.headers\.get\("host"\),\s*forwardedProto:\s*request\.headers\.get\("x-forwarded-proto"\),?\s*\}\),?\s*\}\s*\)/u
  )
  const prodCallers = serverProdSource.match(
    /upgradeInsecureRequests:\s*shouldUpgradeInsecureRequests\(/gu
  )
  assert.equal(
    prodCallers?.length,
    3,
    "the static HTML, 404 and 500 documents all derive the option"
  )
})
