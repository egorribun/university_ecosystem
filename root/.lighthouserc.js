{
  "ci": {
    "collect": {
      "numberOfRuns": 1,
      "beforeAllScript": "npm run build && node scripts/prepare-lhci-routes.mjs",
      "staticDistDir": "dist",
      "chromePath": "/usr/bin/google-chrome-stable",
      "settings": {
        "chromeFlags": "--no-sandbox --disable-dev-shm-usage --allow-insecure-localhost --ignore-certificate-errors --test-type",
        "chromePath": "/usr/bin/google-chrome-stable"
      }
    },
    "upload": {
      "target": "filesystem",
      "outputDir": ".lighthouseci",
      "reportFilenamePattern": "%%DATETIME%%-%%PATHNAME%%.report.html"
    },
    "assert": {
      "assertions": {
        "categories:performance": ["error", { "minScore": 0.8 }],
        "categories:accessibility": ["error", { "minScore": 0.8 }],
        "categories:best-practices": ["error", { "minScore": 0.8 }],
        "categories:seo": ["error", { "minScore": 0.8 }],
        "total-blocking-time": ["warn", { "maxNumericValue": 435, "aggregationMethod": "median" }]
      }
    }
  }
}
