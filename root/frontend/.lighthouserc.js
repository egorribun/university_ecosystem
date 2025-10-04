const LOCAL_PREVIEW_PORT = 4174
const base = process.env.PREVIEW_URL || process.env.LHCI_URL || ""
const useRemotePreview = Boolean(base)

const collect = {
  numberOfRuns: 3,
  url: useRemotePreview
    ? [base, `${base}/login`]
    : [
        `http://127.0.0.1:${LOCAL_PREVIEW_PORT}/`,
        `http://127.0.0.1:${LOCAL_PREVIEW_PORT}/login`,
      ],
  settings: {
    preset: "desktop",
    chromeFlags: "--no-sandbox --disable-dev-shm-usage",
  },
}

if (!useRemotePreview) {
  collect.beforeAllScript = "npm run build"
  collect.startServerCommand = "node scripts/lhci-preview.mjs"
  collect.startServerReadyPattern = "LHCI_READY"
  collect.startServerReadyTimeout = 120000
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
