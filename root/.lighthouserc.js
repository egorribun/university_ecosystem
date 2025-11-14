{
  "ci": {
    "collect": {
      "numberOfRuns": 1,
      "url": [
        "http://127.0.0.1:4174/",
        "http://127.0.0.1:4174/login"
      ],
      "beforeAllScript": "npm run build",
      "startServerCommand": "LHCI_PREVIEW_HOST=0.0.0.0 node scripts/lhci-preview.mjs",
      "startServerReadyPattern": "LHCI_READY",
      "startServerReadyTimeout": 120000,
      "settings": {
        "chromeFlags": "--no-sandbox --disable-dev-shm-usage --allow-insecure-localhost"
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
        "total-blocking-time": [
          "warn",
          { "maxNumericValue": 435, "aggregationMethod": "median" }
        ]
      }
    }
  }
}
