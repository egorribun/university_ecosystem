const base = process.env.PREVIEW_URL || process.env.LHCI_URL || ""
const explicitUrls = base ? [base, `${base}/login`] : undefined

const collect = {
  numberOfRuns: 3,
  url: explicitUrls ?? ["/", "/login"],
  staticDistDir: "dist",
  isSinglePageApplication: true,
  settings: {
    preset: "desktop",
    chromeFlags: "--no-sandbox --disable-dev-shm-usage",
  },
}

if (explicitUrls) {
  delete collect.isSinglePageApplication
  collect.staticDistDir = undefined
}

const config = {
  ci: {
    collect,
    assert: {
      assertions: {
        "categories:performance": ["error", { minScore: 0.8 }],
        "categories:accessibility": ["error", { minScore: 0.8 }],
        "categories:best-practices": ["error", { minScore: 0.8 }],
        "categories:seo": ["error", { minScore: 0.8 }],
        "total-blocking-time": ["warn", { maxNumericValue: 435, aggregationMethod: "median" }],
      },
    },
    upload: { target: "temporary-public-storage" },
  },
}

export const ci = config.ci
export default config

// Provide CommonJS compatibility for tools that still use require()
// eslint-disable-next-line no-undef -- module is only defined in CJS environments.
if (typeof module !== "undefined") {
  module.exports = config
}
