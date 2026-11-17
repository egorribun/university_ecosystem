import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import postcss, { type AnyNode } from "postcss"
import { describe, expect, it } from "vitest"

import compiledCss from "@/styles/tailwind.css?inline"

const stylesheet = postcss.parse(compiledCss)
const authoredSource = readFileSync(resolve(process.cwd(), "src/styles/tailwind.css"), "utf8")

function zIndexRules(className: string) {
  const rules: { value: string; layers: string[] }[] = []
  stylesheet.walkRules((rule) => {
    if (!rule.selectors.includes(`.${className}`)) return
    const layers: string[] = []
    let parent: AnyNode | undefined = rule.parent
    while (parent) {
      if (parent.type === "atrule" && parent.name === "layer") layers.push(parent.params)
      parent = parent.parent
    }
    rule.walkDecls("z-index", (declaration) => {
      rules.push({ value: declaration.value, layers })
    })
  })
  return rules
}

function tokenValue(name: string) {
  const values: string[] = []
  stylesheet.walkDecls(name, (declaration) => {
    values.push(declaration.value)
  })
  expect(values).toHaveLength(1)
  return Number(values[0])
}

describe("semantic stacking utilities", () => {
  it.each([
    ["z-negative", "--z-negative"],
    ["z-floating", "--z-floating"],
  ])("emits %s from its existing token in the utilities layer", (className, token) => {
    expect(zIndexRules(className)).toEqual([{ value: `var(${token})`, layers: ["utilities"] }])
  })

  it.each([
    ["z-negative", "--z-negative"],
    ["z-floating", "--z-floating"],
  ])("declares %s exactly once in the authored stylesheet", (className, token) => {
    const declaration = `@utility ${className} {\n  z-index: var(${token});\n}`
    expect(authoredSource.split(declaration)).toHaveLength(2)
  })

  it("keeps the indicator and floating layers ordered around their neighboring layers", () => {
    expect(tokenValue("--z-negative")).toBeLessThan(tokenValue("--z-hide"))
    expect(tokenValue("--z-hide")).toBeLessThan(tokenValue("--z-base"))
    expect(tokenValue("--z-floating")).toBeGreaterThan(tokenValue("--z-modal"))
    expect(tokenValue("--z-floating")).toBeLessThan(tokenValue("--z-toast"))
  })
})
