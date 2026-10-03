import assert from "node:assert/strict"
import test from "node:test"
import { JSDOM } from "jsdom"

import { renderNotFoundPage } from "./not-found-page.mjs"
import { getStrings } from "../public/static-shell-i18n.js"

const installGlobal = (name, value) => {
  const previous = Object.getOwnPropertyDescriptor(globalThis, name)
  Object.defineProperty(globalThis, name, {
    configurable: true,
    value,
    writable: true,
  })
  return () => {
    if (previous) Object.defineProperty(globalThis, name, previous)
    else Reflect.deleteProperty(globalThis, name)
  }
}

test("the generated 404 shell applies the selected RU/EN locale without raw keys", async () => {
  for (const language of ["ru", "en"]) {
    const dom = new JSDOM(renderNotFoundPage(), { url: "https://university.test/404" })
    dom.window.localStorage.setItem("ue:language", language)
    const restoreDocument = installGlobal("document", dom.window.document)
    const restoreWindow = installGlobal("window", dom.window)

    try {
      await import(
        new URL(`../public/not-found-i18n.js?language=${language}`, import.meta.url).href
      )

      const strings = getStrings(language).notFound
      const { document } = dom.window
      assert.equal(document.documentElement.lang, language)
      assert.equal(document.title, strings.pageTitle)
      assert.equal(
        document.querySelector('[data-i18n="notFound.title"]')?.textContent,
        strings.title
      )
      assert.equal(
        document.querySelector('[data-i18n="notFound.description"]')?.textContent,
        strings.description
      )
      assert.equal(document.querySelector('[data-i18n="notFound.home"]')?.textContent, strings.home)
      assert.equal(
        document.querySelector('[data-i18n="notFound.login"]')?.textContent,
        strings.login
      )

      const translatedNodes = [...document.querySelectorAll("[data-i18n]")]
      assert.equal(translatedNodes.length, 4)
      for (const node of translatedNodes) {
        assert.notEqual(node.textContent?.trim(), "")
        assert.notEqual(node.textContent, node.getAttribute("data-i18n"))
      }
      assert.equal(
        document.querySelector('a[data-i18n="notFound.home"]')?.getAttribute("href"),
        "/dashboard"
      )
      assert.equal(
        document.querySelector('a[data-i18n="notFound.login"]')?.getAttribute("href"),
        "/login"
      )
    } finally {
      restoreWindow()
      restoreDocument()
      dom.window.close()
    }
  }
})
