/** @vitest-environment node */

import { renderToString } from "react-dom/server"
import { describe, expect, it } from "vitest"

import { useLocalStorage } from "../useLocalStorage"

const Probe = () => {
  const [value] = useLocalStorage("server-only-key", "server-fallback")
  return <span>{value}</span>
}

describe("useLocalStorage SSR guard", () => {
  it("uses the initial value without touching browser storage during server rendering", () => {
    expect(typeof window).toBe("undefined")
    expect(renderToString(<Probe />)).toContain("server-fallback")
  })
})
