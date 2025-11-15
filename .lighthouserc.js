{
  "ci": {
    "collect": {
      "numberOfRuns": 3,
      "beforeAllScript": "npm --prefix root/frontend run build && node root/frontend/scripts/prepare-lhci-routes.mjs",
      "staticDistDir": "root/frontend/dist",
      "chromePath": "root/frontend/node_modules/.bin/google-chrome-stable",
      "settings": {
        "budgetsPath": "budget.json",
        "chromeFlags": "--no-sandbox --disable-dev-shm-usage --allow-insecure-localhost --ignore-certificate-errors --test-type",
        "chromePath": "root/frontend/node_modules/.bin/google-chrome-stable"
      }
    },
    "upload": {
      "target": "temporary-public-storage"
    },
    "assert": {
      "assertions": {
        "categories:performance": ["error", { "minScore": 0.9 }],
        "budgets": ["error", { "budgetPath": "budget.json" }],
        "largest-contentful-paint": [
          "error",
          { "maxNumericValue": 3500, "aggregationMethod": "median" }
        ],
        "total-blocking-time": [
          "error",
          { "maxNumericValue": 300, "aggregationMethod": "median" }
        ],
        "cumulative-layout-shift": [
          "error",
          { "maxNumericValue": 0.1, "aggregationMethod": "median" }
        ]
      }
    }
  }
}
