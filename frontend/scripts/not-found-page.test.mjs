import assert from "node:assert/strict"
import test from "node:test"

import { escapeHtml, normalizeNotFoundLanguage, renderNotFoundPage } from "./not-found-page.mjs"

test("the default not-found document is a lightweight Russian product page", () => {
  const html = renderNotFoundPage()

  assert.match(html, /<!doctype html>/iu)
  assert.match(html, /<html lang="ru" data-not-found-page>/u)
  assert.match(html, /Страница не найдена/u)
  assert.match(html, /href="\/dashboard"/u)
  assert.match(html, /href="\/login"/u)
  assert.match(html, /src="\/not-found-i18n\.js"/u)
  assert.doesNotMatch(html, /assets\/index-[^"']+\.js/u)
  assert.doesNotMatch(html, /react(?:-|\.)/iu)
})

test("the not-found renderer supports English without shipping the application shell", () => {
  const html = renderNotFoundPage("en")

  assert.match(html, /<html lang="en" data-not-found-page>/u)
  assert.match(html, /Page not found/u)
  assert.match(html, /Return to dashboard/u)
  assert.match(html, /Sign in/u)
  assert.doesNotMatch(html, /Экосистема/u)
  assert.doesNotMatch(html, /static-spa/u)
})

test("language normalization fails closed to Russian", () => {
  assert.equal(normalizeNotFoundLanguage("en-US"), "en")
  assert.equal(normalizeNotFoundLanguage("ru-RU"), "ru")
  assert.equal(normalizeNotFoundLanguage("de"), "ru")
  assert.equal(normalizeNotFoundLanguage(undefined), "ru")
})

test("HTML escaping protects reusable template values", () => {
  assert.equal(
    escapeHtml(`<script>alert("x")</script> & 'quoted'`),
    "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt; &amp; &#39;quoted&#39;"
  )
})
