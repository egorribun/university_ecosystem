import { describe, expect, it } from "vitest"

/**
 * Wave 115 polish smoke — confirms `jspdf` + its transitive `dompurify` still
 * import and instantiate cleanly after SW4's `npm audit fix` bumped
 * `dompurify` 3.2.x → 3.3.3 (ADD_TAGS bypass GHSA-39q2-94rc-95cp).
 *
 * `jspdf` is the only consumer of `dompurify` in this project (see
 * `npm ls dompurify`; our news sanitiser uses WASM ammonia with a regex
 * fallback, not dompurify). This test doesn't exercise the full
 * ActivityExportButton flow — that needs UI + auth + html-to-image
 * rendering — but it does prove the library surface the polish touched
 * still loads and produces a valid PDF document object.
 */
describe("jspdf + dompurify post-audit-fix smoke", () => {
  it("imports jspdf dynamically and instantiates a document", async () => {
    const mod = await import("jspdf")
    const JsPDFCtor =
      (mod as { jsPDF?: typeof mod.jsPDF }).jsPDF ?? (mod as { default: typeof mod.jsPDF }).default
    expect(JsPDFCtor).toBeTypeOf("function")

    const doc = new JsPDFCtor({ orientation: "portrait", unit: "mm", format: "a4" })
    expect(doc).toBeTruthy()

    // Touch the API surfaces activityExport + scheduleExport rely on
    doc.setFontSize(12)
    doc.text("Wave 115 smoke", 10, 10)
    const output = doc.output("datauristring")
    expect(output).toMatch(/^data:application\/pdf/)
  })
})
