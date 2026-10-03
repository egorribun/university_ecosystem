import { cleanup, render } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { LanguageProvider, useLanguage } from "@/contexts/LanguageContext"
import { extractLangFromRequest } from "@/ssrTheme"

type LiveCase = (
  fixtures: { page: unknown; context: unknown },
  info: { project: { name: string } }
) => Promise<void>

const registeredCases = vi.hoisted(() => new Map<string, LiveCase>())

// Run the real acceptance setup without launching Playwright or sending login
// traffic. The page adapter below pauses hydration at the storage-write boundary.
vi.mock("../../../tests/e2e-live/fixtures", () => {
  const test = Object.assign((name: string, body: LiveCase) => registeredCases.set(name, body), {
    describe: Object.assign((_name: string, body: () => void) => body(), {
      configure: () => undefined,
    }),
    skip: () => undefined,
  })
  return { test, expect, loginAs: () => undefined, ROLES: { student: {}, teacher: {} } }
})

const Probe = () => <span>{useLanguage().language}</span>

afterEach(() => {
  cleanup()
  vi.unstubAllEnvs()
  localStorage.clear()
  document.cookie = "ue:language=; Max-Age=0; Path=/"
  delete window.__UE_SELECTED_LANG__
})

describe("rejected-login live locale setup", () => {
  it.each([
    ["ru", "desktop", "student", 401],
    ["en", "mobile", "teacher", 401],
    ["ru", "desktop", "student", 403],
    ["en", "mobile", "teacher", 500],
  ] as const)(
    "keeps %s through %s hydration for %s and independently checks HTTP %i",
    async (language, project, role, responseStatus) => {
      await import("../../../tests/e2e-live/auth-roles.live.spec")
      vi.stubEnv("LIVE_BASE_URL", "http://localhost:3000")
      localStorage.clear()
      document.cookie = "ue:language=; Max-Age=0; Path=/"
      delete window.__UE_SELECTED_LANG__

      const readyForFeedback = new Error("locale and response checks complete")
      const initializers: Array<() => void> = []
      let mounted = false
      const mount = () => {
        if (mounted) return
        render(
          <LanguageProvider>
            <Probe />
          </LanguageProvider>
        )
        mounted = true
      }
      const openDocument = () => {
        cleanup()
        mounted = false
        for (const initialize of initializers) initialize()
        // The document's bootstrap locale is chosen before React mounts.
        window.__UE_SELECTED_LANG__ = extractLangFromRequest(
          new Request("http://localhost/login", { headers: { cookie: document.cookie } })
        )
      }
      const context = {
        addCookies: async (cookies: Array<{ name: string; value: string }>) => {
          for (const cookie of cookies) {
            document.cookie = `${cookie.name}=${cookie.value}; Path=/`
          }
        },
      }
      const response = {
        url: () => "http://localhost/api/v1/auth/login",
        request: () => ({ method: () => "POST" }),
        status: () => responseStatus,
      }
      let releaseResponse: ((value: typeof response) => void) | undefined
      let responseRegisteredBeforeClick = false
      const page = {
        context: () => context,
        addInitScript: async (initialize: (value: string) => void, value: string) => {
          initializers.push(() => initialize(value))
        },
        goto: async () => openDocument(),
        evaluate: async (evaluate: (value: string) => void, value: string) => {
          evaluate(value)
          // A pending effect from the already-open document can run after
          // Playwright changes storage and before its following reload.
          mount()
        },
        reload: async () => openDocument(),
        waitForFunction: async () => mount(),
        waitForResponse: (matches: (value: typeof response) => boolean) => {
          expect(matches(response)).toBe(true)
          expect(matches({ ...response, request: () => ({ method: () => "GET" }) })).toBe(false)
          expect(matches({ ...response, url: () => "http://localhost/api/v1/users/me" })).toBe(
            false
          )
          return new Promise<typeof response>((resolve) => {
            releaseResponse = resolve
          })
        },
        locator: (selector: string) => {
          mount()
          if (selector === "html") return document.documentElement
          return {
            fill: async () => undefined,
            click: async () => {
              responseRegisteredBeforeClick = releaseResponse !== undefined
              releaseResponse?.(response)
            },
          }
        },
        getByRole: () => {
          // Stop before inspecting UI copy: the independent status above must
          // pass first, so expected feedback can never manufacture HTTP 401.
          throw readyForFeedback
        },
      }
      const run = registeredCases.get(
        `${role} receives generic ${language} feedback for one rejected login`
      )
      expect(run).toBeDefined()
      const result = run!({ page, context }, { project: { name: project } })
      if (responseStatus === 401) {
        await expect(result).rejects.toBe(readyForFeedback)
      } else {
        await expect(result).rejects.toThrow("rejected login must return HTTP 401")
      }

      expect(responseRegisteredBeforeClick).toBe(true)
      expect(document.documentElement).toHaveAttribute("lang", language)
      expect(localStorage.getItem("ue:language")).toBe(language)
      expect(document.cookie).toContain(`ue:language=${language}`)
    }
  )
})
