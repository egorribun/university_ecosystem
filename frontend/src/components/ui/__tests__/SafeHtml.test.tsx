import { beforeEach, describe, expect, it, vi } from "vitest"
import { act, render, screen } from "@testing-library/react"
import type { ReactElement } from "react"
import { renderToStaticMarkup } from "react-dom/server"
import { hydrateRoot, type Root } from "react-dom/client"

const { sanitize, ensureWasmSanitizerInitialized } = vi.hoisted(() => ({
  sanitize: vi.fn<(html: string) => string | null>(),
  ensureWasmSanitizerInitialized: vi.fn<() => Promise<boolean>>(),
}))

vi.mock("wasm-sanitizer", () => ({
  default: vi.fn(async () => undefined),
  sanitize_rich_text: sanitize,
}))
vi.mock("@/utils/wasmSanitizer", () => ({ ensureWasmSanitizerInitialized }))

import SafeHtml from "@/components/ui/SafeHtml"

async function renderWithWasmReady(element: ReactElement) {
  ensureWasmSanitizerInitialized.mockResolvedValue(true)
  const result = render(element)
  await act(async () => {
    await Promise.resolve()
  })
  return result
}

class FakeTrustedHTML {
  constructor(readonly value: string) {}

  toString(): string {
    return this.value
  }
}

function enforceTrustedTypes() {
  const innerHTML = Object.getOwnPropertyDescriptor(Element.prototype, "innerHTML")
  if (!innerHTML?.set) throw new Error("Missing innerHTML setter")
  const originalSet = innerHTML.set
  const rawWrites: string[] = []
  const trustedWrites: FakeTrustedHTML[] = []
  Object.defineProperty(Element.prototype, "innerHTML", {
    ...innerHTML,
    set(this: Element, value: unknown) {
      if (!(value instanceof FakeTrustedHTML)) {
        rawWrites.push(String(value))
        throw new TypeError("TrustedHTML required")
      }
      trustedWrites.push(value)
      originalSet.call(this, String(value))
    },
  })

  const policyNames: string[] = []
  const createPolicy = vi.fn((name: string, rules: { createHTML?: (value: string) => string }) => {
    policyNames.push(name)
    return {
      createHTML: (value: string) => new FakeTrustedHTML(rules.createHTML?.(value) ?? value),
      createScriptURL: (value: string) => value,
    }
  })
  Object.defineProperty(window, "trustedTypes", {
    configurable: true,
    value: { createPolicy },
  })

  return {
    createPolicy,
    policyNames,
    rawWrites,
    trustedWrites,
    restore: () => {
      Object.defineProperty(Element.prototype, "innerHTML", innerHTML)
      Reflect.deleteProperty(window, "trustedTypes")
      Reflect.deleteProperty(window, "__ttAppPolicy")
    },
  }
}

// wasm-sanitizer is initialized in setupTests.ts. Assertions stay robust whether
// the sanitizer renders the cleaned <div> or the regex text-only fallback path —
// in both cases the visible text content is identical.

describe("SafeHtml", () => {
  beforeEach(() => {
    sanitize.mockReset().mockImplementation((html) => html)
    ensureWasmSanitizerInitialized.mockReset().mockResolvedValue(false)
  })

  it("renders the text content of clean HTML", async () => {
    await renderWithWasmReady(<SafeHtml html="<p>Hello world</p>" />)
    expect(screen.getByText("Hello world")).toBeInTheDocument()
  })

  it("renders the fallback node when sanitized output is empty", async () => {
    await renderWithWasmReady(<SafeHtml html="" fallback={<span data-testid="fb">FB</span>} />)
    expect(screen.getByTestId("fb")).toBeInTheDocument()
  })

  it("renders a text-only span when empty with no fallback", async () => {
    const { container } = await renderWithWasmReady(<SafeHtml html="" className="so" />)
    expect(container.querySelector("span.so")).not.toBeNull()
  })

  it("uses the text-only fallback while the WASM sanitizer is unavailable", () => {
    sanitize.mockImplementation(() => {
      throw new Error("WASM not initialized")
    })

    render(<SafeHtml html="<strong>Still readable</strong>" />)
    expect(screen.getByText("Still readable")).toBeInTheDocument()
    expect(sanitize).not.toHaveBeenCalled()
    expect(ensureWasmSanitizerInitialized).toHaveBeenCalledTimes(1)
  })

  it.each(["<script>alert(1)</script><p>Safe text</p>", '<p onclick="boom()">Safe text</p>'])(
    "fails closed when sanitized output still contains an injection pattern [case %#]",
    async (maliciousOutput) => {
      sanitize.mockReturnValue(maliciousOutput)

      const { container } = await renderWithWasmReady(
        <SafeHtml html="<p>Safe text</p>" className="safe-text" />
      )
      expect(container.querySelector("span.safe-text")).toHaveTextContent("Safe text")
      expect(container.querySelector("script")).not.toBeInTheDocument()
    }
  )
})

describe("SafeHtml rendering paths", () => {
  beforeEach(() => {
    sanitize.mockReset().mockImplementation((html) => html)
    ensureWasmSanitizerInitialized.mockReset().mockResolvedValue(false)
  })

  it("renders the sanitizer output as markup after WASM initialization", async () => {
    sanitize.mockReturnValue("<p><strong>Bold</strong> text</p>")
    const { container } = await renderWithWasmReady(<SafeHtml html="<p>raw</p>" className="rich" />)

    expect(sanitize).toHaveBeenCalledWith("<p>raw</p>")
    const root = container.querySelector("div.rich")
    expect(root?.innerHTML).toBe("<p><strong>Bold</strong> text</p>")
    expect(container.querySelector("span.rich")).toBeNull()
  })

  it("renders text on the server without initializing or calling the browser sanitizer", () => {
    sanitize.mockReturnValue("<p><strong>Safe</strong></p>")
    vi.stubGlobal("window", undefined)
    try {
      const markup = renderToStaticMarkup(<SafeHtml html="<p>raw</p>" />)
      expect(markup).toContain("<span>raw</span>")
      expect(markup).not.toContain("<p><strong>Safe</strong></p>")
      expect(sanitize).not.toHaveBeenCalled()
      expect(ensureWasmSanitizerInitialized).not.toHaveBeenCalled()
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it("upgrades a hydrated text fallback after the browser sanitizer initializes", async () => {
    let wasmReady = false
    let finishInitialization: ((ready: boolean) => void) | undefined
    const initialization = new Promise<boolean>((resolve) => {
      finishInitialization = resolve
    })
    ensureWasmSanitizerInitialized.mockReturnValue(initialization)
    sanitize.mockImplementation(() => {
      if (!wasmReady) throw new Error("WASM is cold")
      return "<p><strong>Hydrated rich content</strong></p>"
    })

    const serverMarkup = renderToStaticMarkup(<SafeHtml html="<p>source content</p>" />)
    expect(serverMarkup).toContain("source content")
    const container = document.createElement("div")
    container.innerHTML = serverMarkup
    document.body.append(container)
    const recoverableError = vi.fn()
    let root: Root | undefined
    try {
      await act(async () => {
        root = hydrateRoot(container, <SafeHtml html="<p>source content</p>" />, {
          onRecoverableError: recoverableError,
        })
      })
      expect(container.querySelector("strong")).toBeNull()
      expect(container.querySelector("span")).toHaveTextContent("source content")

      await act(async () => {
        wasmReady = true
        finishInitialization?.(true)
        await initialization
      })

      expect(recoverableError).not.toHaveBeenCalled()
      expect(container.querySelector("strong")).toHaveTextContent("Hydrated rich content")
      expect(ensureWasmSanitizerInitialized).toHaveBeenCalledTimes(1)
    } finally {
      await act(async () => root?.unmount())
      container.remove()
    }
  })

  it("keeps a cold sanitizer fallback after the component unmounts", async () => {
    let finishInitialization: ((ready: boolean) => void) | undefined
    const initialization = new Promise<boolean>((resolve) => {
      finishInitialization = resolve
    })
    ensureWasmSanitizerInitialized.mockReturnValue(initialization)
    sanitize.mockImplementation(() => {
      throw new Error("WASM is cold")
    })

    const { container, unmount } = render(<SafeHtml html="<strong>Readable</strong>" />)
    expect(container.querySelector("span")).toHaveTextContent("Readable")
    expect(ensureWasmSanitizerInitialized).toHaveBeenCalledTimes(1)
    unmount()

    await act(async () => {
      finishInitialization?.(true)
      await initialization
    })

    expect(sanitize).not.toHaveBeenCalled()
    expect(container.querySelector("strong")).toBeNull()
  })

  it("uses the existing app policy before writing markup when Trusted Types is available", async () => {
    sanitize.mockReturnValue("<p><strong>Bold</strong> text</p>")
    const createHTML = vi.fn((value: string) => ({ toString: () => value }))
    vi.stubGlobal("trustedTypes", {})
    vi.stubGlobal("__ttAppPolicy", { createHTML })
    try {
      const { container } = await renderWithWasmReady(
        <SafeHtml html="<p>raw</p>" className="rich" />
      )
      expect(createHTML).toHaveBeenCalledWith("<p><strong>Bold</strong> text</p>")
      expect(container.querySelector("strong")).toHaveTextContent("Bold")
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it("creates only the existing app policy and passes TrustedHTML to the enforced sink", async () => {
    sanitize.mockReturnValue("<p><strong>Branded</strong> markup</p>")
    const enforcement = enforceTrustedTypes()
    try {
      const { container } = await renderWithWasmReady(
        <SafeHtml html="<p>input</p>" className="branded" />
      )

      expect(enforcement.policyNames).toEqual(["app"])
      expect(enforcement.createPolicy).toHaveBeenCalledWith("app", expect.any(Object))
      expect(enforcement.rawWrites).toEqual([])
      expect(enforcement.trustedWrites).toHaveLength(1)
      expect(container.querySelector("strong")).toHaveTextContent("Branded")
    } finally {
      enforcement.restore()
    }
  })

  it("renders plain text when Trusted Types is available but the app policy is unavailable", async () => {
    sanitize.mockReturnValue("<p><strong>Bold</strong> text</p>")
    vi.stubGlobal("trustedTypes", {})
    vi.stubGlobal("__ttAppPolicy", false)
    try {
      const { container } = await renderWithWasmReady(
        <SafeHtml html="<p>raw</p>" className="rich" />
      )
      expect(container.querySelector("div.rich")).toBeNull()
      expect(container.querySelector("span.rich")).toHaveTextContent("raw")
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it("renders plain text when the existing app policy rejects markup", async () => {
    sanitize.mockReturnValue("<p>safe</p>")
    vi.stubGlobal("trustedTypes", {})
    vi.stubGlobal("__ttAppPolicy", {
      createHTML: () => {
        throw new TypeError("policy rejected HTML")
      },
    })
    try {
      const { container } = await renderWithWasmReady(
        <SafeHtml html="<b>raw</b>" className="rich" />
      )
      expect(container.querySelector("div.rich")).toBeNull()
      expect(container.querySelector("span.rich")).toHaveTextContent("raw")
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it("renders the caller fallback when the app policy is unavailable", async () => {
    sanitize.mockReturnValue("<p>safe</p>")
    vi.stubGlobal("trustedTypes", {})
    vi.stubGlobal("__ttAppPolicy", false)
    try {
      await renderWithWasmReady(
        <SafeHtml html="<p>raw</p>" fallback={<span>Policy unavailable</span>} />
      )
      expect(screen.getByText("Policy unavailable")).toBeInTheDocument()
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it("uses the policy if it becomes available before a later render", async () => {
    sanitize.mockReturnValue("<p><strong>Bold</strong></p>")
    vi.stubGlobal("trustedTypes", {})
    vi.stubGlobal("__ttAppPolicy", false)
    let finishInitialization: ((ready: boolean) => void) | undefined
    const initialization = new Promise<boolean>((resolve) => {
      finishInitialization = resolve
    })
    ensureWasmSanitizerInitialized.mockReturnValue(initialization)
    try {
      const { container, rerender } = render(<SafeHtml html="<p>raw</p>" />)
      expect(container.querySelector("strong")).toBeNull()

      await act(async () => {
        finishInitialization?.(true)
        await initialization
      })
      expect(container.querySelector("strong")).toBeNull()

      vi.stubGlobal("__ttAppPolicy", {
        createHTML: (value: string) => ({ toString: () => value }),
      })
      rerender(<SafeHtml html="<p>raw</p>" />)
      expect(container.querySelector("strong")).toHaveTextContent("Bold")
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it("re-sanitizes when the html prop changes", async () => {
    const { container, rerender } = await renderWithWasmReady(
      <SafeHtml html="<p>first</p>" className="rich" />
    )
    rerender(<SafeHtml html="<p>second</p>" className="rich" />)

    expect(container.querySelector("div.rich")?.innerHTML).toBe("<p>second</p>")
    expect(sanitize).toHaveBeenLastCalledWith("<p>second</p>")
  })

  it("falls back to plain text when the sanitizer throws, without markup", async () => {
    sanitize.mockImplementation(() => {
      throw new Error("WASM not initialized")
    })
    const { container } = await renderWithWasmReady(
      <SafeHtml html="<b>Readable</b>" className="rich" />
    )

    expect(container.querySelector("span.rich")?.innerHTML).toBe("Readable")
    expect(container.querySelector("div.rich")).toBeNull()
  })

  it.each([
    ["a script tag with attributes", '<script src="x.js"></script><p>Safe</p>'],
    ["an upper-case script tag", "<SCRIPT>alert(1)</SCRIPT><p>Safe</p>"],
    ["a handler with a space before '='", '<p onclick ="boom()">Safe</p>'],
    ["a handler with a tab before '='", '<p onmouseover\t="boom()">Safe</p>'],
  ])("falls back to text when the output still contains %s", async (_label, output) => {
    sanitize.mockReturnValue(output)
    const { container } = await renderWithWasmReady(
      <SafeHtml html="<p>Safe</p>" className="rich" />
    )

    expect(container.querySelector("div.rich")).toBeNull()
    expect(container.querySelector("span.rich")).toHaveTextContent("Safe")
  })

  it.each([["a script-like word", "<p>scripting guide</p>"]])(
    "keeps markup for %s",
    async (_label, output) => {
      sanitize.mockReturnValue(output)
      const { container } = await renderWithWasmReady(<SafeHtml html="<p>x</p>" className="rich" />)

      expect(container.querySelector("div.rich")?.innerHTML).toBe(output)
    }
  )
})
