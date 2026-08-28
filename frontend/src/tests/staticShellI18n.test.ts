import { describe, expect, it } from "vitest"
import { JSDOM } from "jsdom"
import fs from "node:fs/promises"
import path from "node:path"
import { fileURLToPath } from "node:url"

import {
  applyDocumentLanguage,
  applyMetaTranslations,
  applyNotFoundTranslations,
  applyOfflineTranslations,
  getManifestPath,
  getManifestStrings,
  getStrings,
} from "../../public/static-shell-i18n.js"
import type { ManifestShortcutStrings } from "../../public/static-shell-i18n.js"

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const publicDir = path.resolve(__dirname, "../../public")

describe("static shell i18n integration", () => {
  it("applies english meta tags", () => {
    const dom = new JSDOM(`<!doctype html><html lang="ru"><head>
      <meta name="description" content="" />
      <meta property="og:title" content="" />
      <meta property="og:description" content="" />
      <meta property="og:locale" content="ru_RU" />
      <meta name="twitter:title" content="" />
      <meta name="twitter:description" content="" />
      <link rel="manifest" href="/manifest.webmanifest" crossorigin="use-credentials" />
      <title></title>
    </head><body></body></html>`)

    const { document } = dom.window
    applyDocumentLanguage(document, "en")
    applyMetaTranslations(document, "en")

    const metaStrings = getStrings("en").meta
    expect(document.documentElement.lang).toBe("en")
    expect(document.title).toBe(metaStrings?.title)
    expect(document.querySelector('meta[name="description"]')?.getAttribute("content")).toBe(
      metaStrings?.description
    )
    expect(document.querySelector('meta[property="og:locale"]')?.getAttribute("content")).toBe(
      metaStrings?.ogLocale
    )
    expect(document.querySelector('meta[property="og:description"]')?.getAttribute("content")).toBe(
      metaStrings?.ogDescription
    )
    expect(document.querySelector('meta[name="twitter:title"]')?.getAttribute("content")).toBe(
      metaStrings?.twitterTitle
    )
    expect(
      document.querySelector('meta[name="twitter:description"]')?.getAttribute("content")
    ).toBe(metaStrings?.twitterDescription)
    expect(document.querySelector('link[rel="manifest"]')?.getAttribute("href")).toBe(
      getManifestPath("en")
    )
  })

  it("populates the offline fallback in english", () => {
    const dom = new JSDOM(`<!doctype html><html lang="ru"><head><title></title></head><body>
      <main>
        <h1 data-i18n="offline.title"></h1>
        <p data-i18n="offline.description"></p>
        <ul>
          <li data-i18n="offline.hints.0"></li>
          <li data-i18n="offline.hints.1"></li>
        </ul>
        <button data-i18n="offline.retry"></button>
        <small data-i18n="offline.footer"></small>
      </main>
    </body></html>`)

    const { document } = dom.window
    applyDocumentLanguage(document, "en")
    applyOfflineTranslations(document, "en")

    const offlineStrings = getStrings("en").offline
    expect(document.documentElement.lang).toBe("en")
    expect(document.title).toBe(offlineStrings?.pageTitle)
    expect(document.querySelector('[data-i18n="offline.title"]')?.textContent).toBe(
      offlineStrings?.title
    )
    expect(document.querySelector('[data-i18n="offline.description"]')?.textContent).toBe(
      offlineStrings?.description
    )
    expect(document.querySelector('[data-i18n="offline.hints.0"]')?.textContent).toBe(
      offlineStrings?.hints?.[0]
    )
    expect(document.querySelector('[data-i18n="offline.hints.1"]')?.textContent).toBe(
      offlineStrings?.hints?.[1]
    )
    expect(document.querySelector('[data-i18n="offline.retry"]')?.textContent).toBe(
      offlineStrings?.retry
    )
    expect(document.querySelector('[data-i18n="offline.footer"]')?.textContent).toBe(
      offlineStrings?.footer
    )
  })

  it("ships an english manifest variant", async () => {
    const manifestPath = path.join(publicDir, "manifest.en.webmanifest")
    const content = await fs.readFile(manifestPath, "utf-8")
    const manifest = JSON.parse(content)
    const manifestStrings = getManifestStrings("en")

    expect(manifest.lang).toBe("en")
    expect(manifest.name).toBe(manifestStrings?.name)
    expect(manifest.short_name).toBe(manifestStrings?.short_name)
    expect(manifest.description).toBe(manifestStrings?.description)
    expect(
      manifest.shortcuts?.map((shortcut: ManifestShortcutStrings) => ({
        name: shortcut.name,
        description: shortcut.description,
      }))
    ).toEqual(manifestStrings?.shortcuts)
  })

  it("populates the not-found fallback in english", () => {
    const dom = new JSDOM(`<!doctype html><html lang="ru"><head><title></title></head><body>
      <main>
        <h1 data-i18n="notFound.title"></h1>
        <p data-i18n="notFound.description"></p>
        <a data-i18n="notFound.home"></a>
        <a data-i18n="notFound.login"></a>
      </main>
    </body></html>`)

    const { document } = dom.window
    applyDocumentLanguage(document, "en")
    applyNotFoundTranslations(document, "en")

    const notFoundStrings = getStrings("en").notFound
    expect(document.documentElement.lang).toBe("en")
    expect(document.title).toBe(notFoundStrings?.pageTitle)
    expect(document.querySelector('[data-i18n="notFound.title"]')?.textContent).toBe(
      notFoundStrings?.title
    )
    expect(document.querySelector('[data-i18n="notFound.description"]')?.textContent).toBe(
      notFoundStrings?.description
    )
    expect(document.querySelector('[data-i18n="notFound.home"]')?.textContent).toBe(
      notFoundStrings?.home
    )
    expect(document.querySelector('[data-i18n="notFound.login"]')?.textContent).toBe(
      notFoundStrings?.login
    )
  })
})
