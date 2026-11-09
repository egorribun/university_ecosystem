import { JSDOM } from "jsdom"

import { expect, test, type Page } from "../../e2e/test"

type CspViolation = {
  directive: string
  disposition: string
  sample: string
}

type CspProbeOutcome = {
  status: "allowed" | "blocked" | "setup-blocked"
  errorName?: string
  value?: unknown
}

type BrowserCspProbe = {
  trustedTypesAvailable: boolean
  wasm: CspProbeOutcome
  rawEval: CspProbeOutcome
  appPolicyAllowed: boolean
  trustedScriptEval: CspProbeOutcome
  defaultPolicy: CspProbeOutcome
  rawStringSink: CspProbeOutcome
}

declare global {
  interface Window {
    __ueTrustedRan?: boolean
    __ueUntrustedRan?: boolean
    __ueViolations?: CspViolation[]
    __ueSsrBootstrap?: { nonce: string; source: string }
    __ueCspProbe?: Promise<BrowserCspProbe>
  }
}

type ServedDocument = {
  csp: string
  reportOnlyCsp: string
  nonce: string | undefined
  html: string
}

function directiveTokens(policy: string, directiveName: string) {
  const directive = policy
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith(`${directiveName} `))
  return directive?.split(/\s+/u) ?? []
}

async function interceptDocument(page: Page, baseURL: string | undefined, removeCsp: boolean) {
  if (!baseURL) throw new Error("Production SSR browser test requires a base URL")
  const origin = new URL(baseURL).origin
  let served: ServedDocument | undefined

  // Keep the production document and its local assets; no external service is needed.
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url())
    if (url.origin !== origin) {
      await route.abort()
      return
    }
    if (route.request().resourceType() !== "document" || url.pathname !== "/login") {
      await route.continue()
      return
    }

    const response = await route.fetch({ maxRedirects: 0 })
    const headers = response.headers()
    const csp = headers["content-security-policy"] ?? ""
    const reportOnlyCsp = headers["content-security-policy-report-only"] ?? ""
    const nonce = csp.match(/script-src[^;]*'nonce-([A-Za-z0-9+/_-]+={0,2})'/u)?.[1]
    const html = await response.text()
    served = { csp, reportOnlyCsp, nonce, html }

    // Both probes use the same HTML and scripts. The second test changes only
    // the policy headers to establish that the untrusted probe can execute.
    const nonceApprovedProbe = `
      window.__ueTrustedRan = true;
      const capture = (callback) => {
        try {
          return { status: "allowed", value: callback() };
        } catch (error) {
          return {
            status: "blocked",
            errorName: error instanceof Error ? error.name : "NonError",
          };
        }
      };
      window.__ueCspProbe = (async () => {
        let wasm;
        try {
          const module = await WebAssembly.compile(
            new Uint8Array([0x00, 0x61, 0x73, 0x6d, 0x01, 0x00, 0x00, 0x00])
          );
          wasm = { status: "allowed", value: WebAssembly.Module.exports(module).length };
        } catch (error) {
          wasm = {
            status: "blocked",
            errorName: error instanceof Error ? error.name : "NonError",
          };
        }

        const rawEval = capture(() => eval("1 + 1"));
        const appPolicy = capture(() =>
          trustedTypes.createPolicy("app", { createScript: (source) => source })
        );
        const trustedScriptEval = appPolicy.status === "allowed"
          ? capture(() => eval(appPolicy.value.createScript("1 + 1")))
          : { status: "setup-blocked", errorName: appPolicy.errorName };
        const rawStringSink = capture(() => {
          const element = document.createElement("div");
          element.innerHTML = "<strong>raw string control</strong>";
          return element.innerHTML;
        });
        const defaultPolicy = capture(() =>
          trustedTypes.createPolicy("default", { createHTML: (html) => html }).name
        );

        return {
          trustedTypesAvailable: typeof trustedTypes === "object",
          wasm,
          rawEval,
          appPolicyAllowed: appPolicy.status === "allowed",
          trustedScriptEval,
          defaultPolicy,
          rawStringSink,
        };
      })();
    `
    const injected = html.replace(
      "</body>",
      "<script>window.__ueUntrustedRan = true</script>" +
        `<script nonce="${nonce ?? ""}">${nonceApprovedProbe}</script></body>`
    )
    if (removeCsp) {
      delete headers["content-security-policy"]
      delete headers["content-security-policy-report-only"]
    }
    // The body is now decoded and longer than the original network response.
    delete headers["content-encoding"]
    delete headers["content-length"]
    await route.fulfill({ response, headers, body: injected })
  })

  await page.addInitScript(() => {
    const violations: CspViolation[] = []
    Object.defineProperty(window, "__ueViolations", { value: violations })
    // The SSR bootstrap removes its own global after hydration. Record the
    // parser-executed script, then restore ordinary writable-property semantics.
    Object.defineProperty(window, "$_TSR", {
      configurable: true,
      set(value: unknown) {
        const script = document.currentScript
        window.__ueSsrBootstrap = {
          nonce: script instanceof HTMLScriptElement ? script.nonce : "",
          source: script?.textContent ?? "",
        }
        Object.defineProperty(window, "$_TSR", {
          configurable: true,
          enumerable: true,
          writable: true,
          value,
        })
      },
    })
    document.addEventListener("securitypolicyviolation", (event) => {
      violations.push({
        directive: event.effectiveDirective,
        disposition: event.disposition,
        sample: event.sample,
      })
    })
  })

  return () => served
}

/** AUD-231: exercise the compiled SSR response and browser CSP enforcement. */
test.describe("SSR document CSP in a browser", () => {
  test.use({ serviceWorkers: "block" })

  test("blocks untrusted inline script while the server bootstrap hydrates", async ({
    page,
    baseURL,
  }) => {
    const getServedDocument = await interceptDocument(page, baseURL, false)
    const response = await page.goto("/login")
    expect(response?.status()).toBe(200)

    const served = getServedDocument()
    expect(served).toBeDefined()
    if (!served) throw new Error("Production SSR document was not intercepted")
    expect(served.nonce).toBeTruthy()
    expect(served.csp).toContain("script-src 'self' 'nonce-")
    const enforcedScriptSrc = directiveTokens(served.csp, "script-src")
    const reportOnlyScriptSrc = directiveTokens(served.reportOnlyCsp, "script-src")
    expect(enforcedScriptSrc).toContain("'wasm-unsafe-eval'")
    expect(reportOnlyScriptSrc).toContain("'wasm-unsafe-eval'")
    expect(enforcedScriptSrc).not.toContain("'unsafe-eval'")
    expect(reportOnlyScriptSrc).not.toContain("'unsafe-eval'")
    expect(directiveTokens(served.csp, "trusted-types")).toEqual([
      "trusted-types",
      "app",
      "dompurify-news",
      "goog#html",
      "'allow-duplicates'",
    ])
    expect(directiveTokens(served.reportOnlyCsp, "trusted-types")).toEqual([
      "trusted-types",
      "app",
      "dompurify-news",
      "goog#html",
      "'allow-duplicates'",
    ])
    expect(served.csp).toContain("require-trusted-types-for 'script'")
    expect(served.reportOnlyCsp).toContain("require-trusted-types-for 'script'")
    expect(served.html).toContain("</body>")

    // These are the original server bytes, before either probe is injected.
    const { document } = new JSDOM(served.html).window
    expect(document.querySelector("section.auth-shell--login form")).not.toBeNull()
    expect(
      document.querySelector("section.auth-shell--login form input#email")?.hasAttribute("disabled")
    ).toBe(true)
    expect(document.querySelector('meta[property="csp-nonce"]')?.getAttribute("content")).toBe(
      served.nonce
    )
    const bootstrap = Array.from(document.querySelectorAll("script:not([src])")).find(
      (script) =>
        script.getAttribute("nonce") === served.nonce && script.textContent?.includes("$_TSR")
    )
    expect(bootstrap).toBeDefined()
    if (!bootstrap) throw new Error("Server document is missing its nonce-bearing SSR bootstrap")

    // The nonce-bearing probe and actual application bootstrap both run; the
    // latter enables the form that was disabled in the server document.
    await expect.poll(() => page.evaluate(() => window.__ueTrustedRan === true)).toBe(true)
    const cspProbe = await page.evaluate(async () => (await window.__ueCspProbe) ?? null)
    expect(cspProbe).not.toBeNull()
    if (!cspProbe) throw new Error("Nonce-approved CSP capability probe did not finish")
    expect(cspProbe.trustedTypesAvailable).toBe(true)
    expect(cspProbe.wasm.status).toBe("allowed")
    expect(cspProbe.rawEval.status).toBe("blocked")
    expect(cspProbe.appPolicyAllowed).toBe(true)
    expect(cspProbe.trustedScriptEval.status).toBe("blocked")
    expect(cspProbe.defaultPolicy.status).toBe("blocked")
    expect(cspProbe.rawStringSink.status).toBe("blocked")
    expect(cspProbe.trustedScriptEval.errorName).toBe("EvalError")
    await expect
      .poll(() => page.evaluate(() => window.__ueSsrBootstrap))
      .toEqual({
        nonce: served.nonce,
        source: bootstrap.textContent,
      })
    await expect(page.locator("section.auth-shell--login input#email")).toBeEnabled()
    expect(await page.evaluate(() => window.__ueUntrustedRan)).toBeUndefined()
    await expect
      .poll(() =>
        page.evaluate(() =>
          window.__ueViolations?.some(
            (violation) =>
              violation.disposition === "enforce" &&
              violation.directive.startsWith("script-src") &&
              violation.sample.includes("__ueUntrustedRan")
          )
        )
      )
      .toBe(true)
  })

  test("the untrusted probe executes when the response policies are removed", async ({
    page,
    baseURL,
  }) => {
    const getServedDocument = await interceptDocument(page, baseURL, true)
    const response = await page.goto("/login")
    expect(response?.status()).toBe(200)
    expect(getServedDocument()?.nonce).toBeTruthy()
    await expect.poll(() => page.evaluate(() => window.__ueUntrustedRan === true)).toBe(true)
  })
})
