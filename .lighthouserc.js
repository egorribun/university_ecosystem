const { execSync } = require("node:child_process");
const path = require("node:path");

const frontendDir = path.join(__dirname, "frontend");
const chromePath = path.join(
  frontendDir,
  "node_modules",
  ".bin",
  "google-chrome-stable",
);
const buildEnv = {
  ...process.env,
  FORCE_COLOR: "0",
  CI: "1",
  VITE_LHCI: "true",
};

if (!process.env.LHCI_SKIP_PREPARE) {
  execSync("npx playwright install-deps chromium", {
    cwd: frontendDir,
    stdio: "inherit",
    env: buildEnv,
  });
  execSync("npm run build -- --logLevel error", {
    cwd: frontendDir,
    stdio: "inherit",
    env: buildEnv,
  });
  execSync("node scripts/prepare-lhci-routes.mjs", {
    cwd: frontendDir,
    stdio: "inherit",
    env: buildEnv,
  });
}

module.exports = {
  ci: {
    collect: {
      url: ["/"],
      numberOfRuns: 3,
      staticDistDir: path.join(__dirname, "frontend/dist"),
      isSinglePageApplication: true,
      chromePath,
      settings: {
        budgetPath: path.join(__dirname, "budget.json"),
        chromeFlags:
          "--no-sandbox --disable-dev-shm-usage --allow-insecure-localhost --ignore-certificate-errors --test-type --disable-gpu --headless=new",
        chromePath,
        maxWaitForFcp: 45000,
        maxWaitForLoad: 60000,
      },
    },
    upload: {
      target: "temporary-public-storage",
    },
    // This assertion-only gate consumes LHRs collected by run-lhci.mjs.
    // Keep its severity and thresholds aligned with that canonical Linux
    // calibration: metric drift stays visible without turning the known
    // runner baseline into a false blocking failure.
    assert: {
      assertions: {
        "categories:performance": ["warn", { minScore: 0.4 }],
        "categories:accessibility": ["error", { minScore: 0.95 }],
        "categories:best-practices": ["error", { minScore: 0.95 }],
        "categories:seo": ["error", { minScore: 0.9 }],
        "largest-contentful-paint": [
          "warn",
          { maxNumericValue: 2500, aggregationMethod: "median" },
        ],
        "total-blocking-time": [
          "warn",
          { maxNumericValue: 200, aggregationMethod: "median" },
        ],
        "cumulative-layout-shift": [
          "error",
          { maxNumericValue: 0.05, aggregationMethod: "median" },
        ],
      },
    },
  },
};
