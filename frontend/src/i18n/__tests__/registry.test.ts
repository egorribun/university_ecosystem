import { describe, expect, it } from "vitest"

import { dynamicTranslationRegistry } from "@/i18n/registry"

describe("dynamic translation registry", () => {
  it("keeps every runtime pattern finite and mapped to concrete keys", () => {
    const entries = Object.entries(dynamicTranslationRegistry)

    expect(entries.length).toBeGreaterThan(0)
    expect(entries.every(([pattern, keys]) => pattern.length > 0 && keys.length > 0)).toBe(true)
    expect(entries.every(([, keys]) => keys.every((key) => key.includes(":")))).toBe(true)
    expect(dynamicTranslationRegistry["mfa.otp.methods.${method}"]).toEqual([
      "auth:mfa.otp.methods.totp",
      "auth:mfa.otp.methods.email_otp",
    ])
  })
})
