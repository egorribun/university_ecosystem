import { readFile } from "node:fs/promises"
import { resolve } from "node:path"

import { JSDOM } from "jsdom"

import { expect, test } from "../../e2e/test"

/**
 * AUD-432 (full SSR): the server-rendered documents are checked by executing the production
 * SSR server and reading its HTML, not by matching the source text of the renderer. The
 * requested language comes from the `ue:language` cookie that the server reads for `<html lang>`.
 */

type Language = "ru" | "en"

async function authCatalog(
  language: Language
): Promise<{ actions: { signIn: string; signUp: string } }> {
  const path = resolve(process.cwd(), "src/i18n/locales", language, "auth.json")
  return JSON.parse(await readFile(path, "utf8")) as {
    actions: { signIn: string; signUp: string }
  }
}

function nonceFromPolicy(policy: string | undefined): string {
  const nonce = policy?.match(/script-src[^;]*'nonce-([^']+)'/u)?.[1]
  if (!nonce) throw new Error("SSR response is missing its CSP nonce")
  return nonce
}

test.describe("Production SSR document render", () => {
  for (const language of ["ru", "en"] as const) {
    for (const path of ["/login", "/register"] as const) {
      test(`${path} renders ${language} on the server with a bootstrap for hydration`, async ({
        request,
      }) => {
        const response = await request.get(path, {
          headers: { cookie: `ue:language=${language}` },
          maxRedirects: 0,
        })
        expect(response.status()).toBe(200)
        expect(response.headers()["content-type"]).toContain("text/html")
        const html = await response.text()
        const nonce = nonceFromPolicy(response.headers()["content-security-policy"])
        const { document } = new JSDOM(html).window

        // The document language is decided by the server from the cookie.
        expect(document.documentElement.getAttribute("lang")).toBe(language)

        // Translated text is present in the markup for the requested locale.
        const catalog = await authCatalog(language)
        const section = document.querySelector(`section.auth-shell--${path.slice(1)}`)
        expect(section, "the response must contain the rendered auth form").not.toBeNull()
        const form = section?.querySelector("form")
        expect(form).not.toBeNull()
        const submit = form?.querySelector(`button#${path.slice(1)}-submit[type="submit"]`)
        expect(submit).not.toBeNull()
        expect(submit?.textContent?.trim()).toBe(
          path === "/login" ? catalog.actions.signIn : catalog.actions.signUp
        )
        expect(submit?.hasAttribute("disabled")).toBe(true)
        for (const id of ["email", "password"]) {
          expect(form?.querySelector(`input#${id}`)?.hasAttribute("disabled")).toBe(true)
        }
        // Ignore embedded bootstrap/catalog data: it is not rendered form content.
        const rendered = section?.cloneNode(true) as Element
        rendered.querySelectorAll("script, style, template").forEach((node) => node.remove())
        const text = rendered.textContent ?? ""
        expect(text).toContain(path === "/login" ? catalog.actions.signIn : catalog.actions.signUp)

        // No raw translation key reaches the markup.
        expect(text).not.toMatch(/\b(?:auth|common|news):[a-z]+\.[a-zA-Z.]+/u)

        // Hydration markers: the CSP nonce is mirrored into the document and the trusted
        // inline bootstrap carries that same nonce.
        expect(document.querySelector('meta[property="csp-nonce"]')?.getAttribute("content")).toBe(
          nonce
        )
        // The pinned TanStack producer emits a classic inline self.$_TSR initializer.
        // Its stream boundary and completion scripts cannot bootstrap hydration.
        const trustedBootstrap = Array.from(document.querySelectorAll("script")).some(
          (script) =>
            !script.hasAttribute("src") &&
            script.type === "" &&
            !script.hasAttribute("nomodule") &&
            script.getAttribute("nonce") === nonce &&
            /(?:^|;)\s*self\.\$_TSR\s*=\s*\{/u.test(script.textContent ?? "")
        )
        expect(trustedBootstrap).toBe(true)
        expect(response.headers()["cache-control"]).toBe("no-store, private, max-age=0")
      })
    }
  }

  test("the requested language decides the server markup and not the other locale", async ({
    request,
  }) => {
    const english = await authCatalog("en")
    const russian = await authCatalog("ru")
    // Precondition: the two locales must differ, otherwise the negative below proves nothing.
    expect(english.actions.signIn).not.toBe(russian.actions.signIn)

    const response = await request.get("/login", {
      headers: { cookie: "ue:language=ru" },
      maxRedirects: 0,
    })
    expect(response.status()).toBe(200)
    const document = new JSDOM(await response.text()).window.document
    const submit = document.querySelector("section.auth-shell--login form button#login-submit")
    expect(submit).not.toBeNull()
    const text = submit?.textContent?.trim() ?? ""
    expect(text).toContain(russian.actions.signIn)
    expect(text).not.toContain(english.actions.signIn)
  })
})
