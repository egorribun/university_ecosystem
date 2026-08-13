# Standalone Logo Loader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver one dependency-free, integration-ready `C:\Users\egorribun\Documents\logo-loader.html` implementing the approved Clean Signature animation, responsive layout, themes, progress API, accessibility, and graceful lifecycle behavior.

**Architecture:** Keep the automatic experience CSS-first with one six-second master timeline and inline SVG. Add a small defensive controller that switches between automatic and determinate modes, manages completion/restart/theme operations, and pauses the timeline when the document is hidden. Verification uses temporary Node contract and Playwright scripts outside the repository so the only user-facing artifact is the requested HTML file.

**Tech Stack:** HTML5, inline SVG, CSS custom properties/keyframes, browser JavaScript, Node.js built-ins, Playwright 1.58.2.

---

## File map

- Modify: `C:\Users\egorribun\Documents\logo-loader.html` — the sole deliverable and preview page.
- Create temporarily: `C:\Temp\logo-loader-verification\verify-contract.cjs` — static single-file and API contract checks.
- Create temporarily: `C:\Temp\logo-loader-verification\verify-browser.cjs` — browser, responsive, accessibility, theme, and lifecycle checks.
- Create temporarily: `C:\Temp\logo-loader-verification\screenshots\*.png` — visual evidence at representative viewports.
- Preserve: `C:\Temp\logo-loader-before-20260813.html` — recoverable copy of the input file.

### Task 1: Establish the failing integration contract

**Files:**
- Create: `C:\Temp\logo-loader-verification\verify-contract.cjs`
- Test: `C:\Users\egorribun\Documents\logo-loader.html`

- [ ] **Step 1: Copy the original file to the recovery location**

Run:

```powershell
Copy-Item -LiteralPath 'C:\Users\egorribun\Documents\logo-loader.html' -Destination 'C:\Temp\logo-loader-before-20260813.html' -Force
```

Expected: the backup exists and has the same SHA-256 hash as the pre-edit source.

- [ ] **Step 2: Write the static contract verifier**

```javascript
const assert = require("node:assert/strict");
const fs = require("node:fs");

const target = "C:\\Users\\egorribun\\Documents\\logo-loader.html";
const html = fs.readFileSync(target, "utf8");

assert.match(html, /--navy:\s*#033167/i);
assert.match(html, /--red:\s*#e40137/i);
assert.match(html, /--cycle-duration:\s*6s/i);
assert.match(html, /data-theme="light"/i);
assert.match(html, /data-mode="automatic"/i);
assert.match(html, /@keyframes\s+mark-exit/i);
assert.match(html, /window\.logoLoader\s*=/i);
for (const method of ["setProgress", "startAutomatic", "complete", "restart", "setTheme"]) {
  assert.match(html, new RegExp(`${method}\\s*\\(`));
}
assert.match(html, /prefers-reduced-motion:\s*reduce/i);
assert.match(html, /visibilitychange/i);
assert.doesNotMatch(html, /@keyframes\s+pulse/i);
assert.doesNotMatch(html, /transform:\s*scale\s*\(/i);
assert.doesNotMatch(html, /<(?:script|link|img)\b[^>]+(?:src|href)=["']https?:/i);
console.log("contract: ok");
```

- [ ] **Step 3: Run the verifier and confirm the old file fails**

Run:

```powershell
node C:\Temp\logo-loader-verification\verify-contract.cjs
```

Expected: FAIL on the first missing approved color or integration contract.

### Task 2: Build the final standalone loader

**Files:**
- Modify: `C:\Users\egorribun\Documents\logo-loader.html`
- Test: `C:\Temp\logo-loader-verification\verify-contract.cjs`

- [ ] **Step 1: Replace the document with semantic standalone markup**

Use one `.logo-loader` root with `data-theme="light"`, `data-mode="automatic"`, `aria-live="polite"`, and `aria-busy="true"`. Preserve the six approved SVG paths, assign explicit `body-path`, `accent-outer`, and `accent-inner` classes, and wrap both color groups in one `.mark` group so exit opacity is shared.

```html
<main class="logo-loader" data-theme="light" data-mode="automatic" aria-live="polite" aria-busy="true">
  <div class="loader-content">
    <div class="mark-holder">
      <svg viewBox="65 65 960 960" role="img" aria-labelledby="loader-title loader-description">
        <title id="loader-title">Загрузка</title>
        <desc id="loader-description">Анимированный логотип сервиса</desc>
        <g class="mark">
          <g class="navy-group">
            <path class="navy body-path" pathLength="1000" d="M 432.53,279.03 A 102.77 102.77 0 0 0 356.91,313.10 L 184.73,504.69 A 20.43 20.43 0 0 0 215.20,532.06 L 384.10,343.81 A 68.71 68.71 0 0 1 434.70,320.99 L 813.00,318.00 A 46.0 46.0 0 0 1 823.00,405.00 L 458.17,405.16 A 23.73 23.73 0 0 0 440.53,413.02 L 358.13,504.69 A 22.39 22.39 0 0 0 374.96,542.05 L 761.598,539.011 A 2 2 0 0 0 763.069,538.349 L 870.501,419.037 A 85.7985 85.7985 0 0 0 806.844,276.072 Z"/>
            <path class="navy accent-path accent-outer" pathLength="1000" d="M 260.0,528.7 L 392.6,373.0 Q 413.0,349.0 444.5,349.2 L 804.0,351.0"/>
            <path class="navy accent-path accent-inner" pathLength="1000" d="M 312.9,515.8 L 409.8,400.1 Q 427.5,379.0 455.0,379.1 L 804.0,381.0"/>
          </g>
          <g class="red-group" transform="rotate(180 540.6 544.9)">
            <path class="red body-path" pathLength="1000" d="M 432.53,279.03 A 102.77 102.77 0 0 0 356.91,313.10 L 184.73,504.69 A 20.43 20.43 0 0 0 215.20,532.06 L 384.10,343.81 A 68.71 68.71 0 0 1 434.70,320.99 L 813.00,318.00 A 46.0 46.0 0 0 1 823.00,405.00 L 458.17,405.16 A 23.73 23.73 0 0 0 440.53,413.02 L 358.13,504.69 A 22.39 22.39 0 0 0 374.96,542.05 L 761.598,539.011 A 2 2 0 0 0 763.069,538.349 L 870.501,419.037 A 85.7985 85.7985 0 0 0 806.844,276.072 Z"/>
            <path class="red accent-path accent-outer" pathLength="1000" d="M 260.0,528.7 L 392.6,373.0 Q 413.0,349.0 444.5,349.2 L 804.0,351.0"/>
            <path class="red accent-path accent-inner" pathLength="1000" d="M 312.9,515.8 L 409.8,400.1 Q 427.5,379.0 455.0,379.1 L 804.0,381.0"/>
          </g>
        </g>
      </svg>
    </div>
    <div class="status"><span class="status-label">Загрузка</span><span class="dots" aria-hidden="true"><span>.</span><span>.</span><span>.</span></span></div>
  </div>
</main>
```

- [ ] **Step 2: Implement the fixed master timeline and Clean Signature finish**

Use exact absolute phase percentages derived from the six-second cycle: red reaches final fill at 43.5%, the full hold ends at 85.1667%, and shared exit ends at 92.6667%. Body strokes fade to zero while fills reach one; the `.mark` opacity alone controls exit.

```css
:root {
  --navy: #033167;
  --red: #e40137;
  --cycle-duration: 6s;
  --mark-size: clamp(9rem, 22vmin, 18rem);
  --optical-x: 0.45%;
  --optical-y: 0.15%;
}

.mark { animation: mark-exit var(--cycle-duration) linear infinite; }
@keyframes mark-exit {
  0%, 85.1667% { opacity: 1; }
  92.6667%, 100% { opacity: 0; }
}
```

Define separate navy/red body and accent keyframes so the red construction begins 0.45 seconds later but shares the 85.1667% exit boundary. Start outer and inner accent lines 70 ms and 140 ms after each body. Do not animate a transform on the completed mark.

- [ ] **Step 3: Implement responsive themes and lifecycle classes**

Use `min-height: 100dvh`, safe-area padding, `width: min(100%, var(--mark-size))`, landscape-specific spacing, and theme variables for light, dark, and transparent backgrounds. Apply `translate(var(--optical-x), var(--optical-y))` once as static placement. Add `.is-paused`, `.is-finishing`, and `[hidden]` states without introducing whole-logo motion.

- [ ] **Step 4: Implement the defensive integration controller**

```javascript
window.logoLoader = (() => {
  const root = document.querySelector(".logo-loader");
  const statusLabel = root?.querySelector(".status-label");
  const mark = root?.querySelector(".mark");
  const paths = root ? [...root.querySelectorAll(".body-path, .accent-path")] : [];
  const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");
  let completionPromise = null;

  const ranges = [
    [".navy-group .body-path", 0.00, 0.46, 0.58, 0.88],
    [".red-group .body-path", 0.10, 0.58, 0.68, 1.00],
    [".navy-group .accent-outer", 0.03, 0.52],
    [".navy-group .accent-inner", 0.06, 0.56],
    [".red-group .accent-outer", 0.13, 0.64],
    [".red-group .accent-inner", 0.16, 0.68]
  ];

  const segment = (value, start, end) => Math.min(1, Math.max(0, (value - start) / (end - start)));

  function renderProgress(value) {
    for (const [selector, drawStart, drawEnd, fillStart, fillEnd] of ranges) {
      const path = root.querySelector(selector);
      const draw = segment(value, drawStart, drawEnd);
      path.style.opacity = draw > 0 ? "1" : "0";
      path.style.strokeDashoffset = String(1000 * (1 - draw));
      if (path.classList.contains("body-path")) {
        const fill = segment(value, fillStart, fillEnd);
        path.style.fillOpacity = String(fill);
        path.style.strokeOpacity = String(1 - fill);
      }
    }
  }

  function clearProgressStyles() {
    for (const path of paths) {
      for (const property of ["opacity", "stroke-dashoffset", "fill-opacity", "stroke-opacity"]) {
        path.style.removeProperty(property);
      }
    }
  }

  function finalize() {
    root.hidden = true;
    root.setAttribute("aria-busy", "false");
    root.dispatchEvent(new CustomEvent("logo-loader:complete"));
    return true;
  }

  function setProgress(percent) {
    const value = Number(percent);
    if (!root || !Number.isFinite(value)) return null;
    const normalized = Math.min(100, Math.max(0, value));
    root.dataset.mode = "determinate";
    root.setAttribute("role", "progressbar");
    root.setAttribute("aria-valuemin", "0");
    root.setAttribute("aria-valuemax", "100");
    root.setAttribute("aria-valuenow", String(Math.round(normalized)));
    statusLabel.textContent = `Загрузка ${Math.round(normalized)}%`;
    renderProgress(normalized / 100);
    return normalized;
  }

  function startAutomatic() {
    if (!root) return false;
    root.hidden = false;
    root.dataset.mode = "automatic";
    root.classList.remove("is-finishing");
    root.setAttribute("role", "status");
    root.setAttribute("aria-busy", "true");
    for (const name of ["aria-valuemin", "aria-valuemax", "aria-valuenow"]) root.removeAttribute(name);
    statusLabel.textContent = "Загрузка";
    clearProgressStyles();
    return true;
  }

  function complete() {
    if (!root || root.hidden) return Promise.resolve(true);
    if (completionPromise) return completionPromise;
    completionPromise = new Promise(resolve => {
      const done = () => resolve(finalize());
      if (reducedMotion.matches) {
        requestAnimationFrame(done);
      } else if (root.dataset.mode === "determinate") {
        setProgress(100);
        setTimeout(() => {
          root.classList.add("is-finishing");
          setTimeout(done, 450);
        }, 2500);
      } else {
        mark.addEventListener("animationiteration", done, { once: true });
      }
    });
    return completionPromise;
  }

  function restart(options = {}) {
    if (!root) return false;
    completionPromise = null;
    root.hidden = false;
    root.classList.remove("is-finishing");
    return options.automatic === false ? setProgress(0) : startAutomatic();
  }

  function setTheme(theme) {
    if (!root) return null;
    if (["light", "dark", "transparent"].includes(theme)) root.dataset.theme = theme;
    return root.dataset.theme;
  }

  document.addEventListener("visibilitychange", () => {
    root?.classList.toggle("is-paused", document.hidden);
  });

  return { setProgress, startAutomatic, complete, restart, setTheme };
})();
```

Use `.is-finishing .mark` and `.is-finishing .status` to apply the shared 450 ms opacity transition in determinate mode. The CSS automatic timeline remains the no-JavaScript fallback.

- [ ] **Step 5: Run the static verifier**

Run:

```powershell
node C:\Temp\logo-loader-verification\verify-contract.cjs
```

Expected: `contract: ok`.

### Task 3: Verify browser behavior and all target resolutions

**Files:**
- Create: `C:\Temp\logo-loader-verification\verify-browser.cjs`
- Test: `C:\Users\egorribun\Documents\logo-loader.html`

- [ ] **Step 1: Write the browser verifier**

The script starts an ephemeral local server, imports Playwright from the repository's installed package, opens the exact deliverable, records non-local requests, and checks every supported state.

```javascript
const assert = require("node:assert/strict");
const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");
const { chromium } = require("C:\\Users\\egorribun\\Documents\\university_ecosystem\\frontend\\node_modules\\playwright");

const htmlPath = "C:\\Users\\egorribun\\Documents\\logo-loader.html";
const shotDir = "C:\\Temp\\logo-loader-verification\\screenshots";
fs.mkdirSync(shotDir, { recursive: true });

const server = http.createServer((request, response) => {
  response.writeHead(200, { "content-type": "text/html; charset=utf-8" });
  response.end(fs.readFileSync(htmlPath));
});

server.listen(0, "127.0.0.1", async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const port = server.address().port;
    const page = await browser.newPage();
    const external = [];
    page.on("request", request => {
      if (!request.url().startsWith(`http://127.0.0.1:${port}`)) external.push(request.url());
    });

    for (const [width, height] of [[320, 568], [568, 320], [768, 1024], [1440, 900], [3840, 2160]]) {
      await page.setViewportSize({ width, height });
      await page.goto(`http://127.0.0.1:${port}/`, { waitUntil: "load" });
      const metrics = await page.evaluate(() => {
        const mark = document.querySelector(".mark-holder").getBoundingClientRect();
        return { overflow: document.documentElement.scrollWidth > innerWidth, markWidth: mark.width, hidden: document.querySelector(".logo-loader").hidden };
      });
      assert.equal(metrics.overflow, false);
      assert.equal(metrics.hidden, false);
      assert.ok(metrics.markWidth >= 143 && metrics.markWidth <= 289);
      await page.screenshot({ path: path.join(shotDir, `${width}x${height}.png`), fullPage: true });
    }

    assert.equal(await page.evaluate(() => window.logoLoader.setProgress(50)), 50);
    assert.equal(await page.locator(".logo-loader").getAttribute("aria-valuenow"), "50");
    assert.equal(await page.evaluate(() => window.logoLoader.setTheme("dark")), "dark");
    assert.equal(await page.evaluate(() => window.logoLoader.setTheme("invalid")), "dark");
    await page.evaluate(() => window.logoLoader.restart({ automatic: false }));
    await page.evaluate(() => window.logoLoader.setProgress(100));
    await page.evaluate(() => window.logoLoader.complete());
    assert.equal(await page.locator(".logo-loader").getAttribute("hidden"), "");
    assert.deepEqual(external, []);
    console.log("browser: ok");
  } finally {
    await browser.close();
    server.close();
  }
});
```

- [ ] **Step 2: Run the browser verifier**

Run:

```powershell
node C:\Temp\logo-loader-verification\verify-browser.cjs
```

Expected: `browser: ok`, five screenshots, no console errors, and no external requests.

- [ ] **Step 3: Verify reduced motion separately**

Add a Playwright context with `reducedMotion: "reduce"`, assert that `.mark` has animation name `none`, call `complete()`, and assert the root is hidden on the next animation frame.

- [ ] **Step 4: Verify the exact hold and shared exit boundaries**

Pause the `.mark` animation through Playwright, set its current time to 2610 ms, 5110 ms, and 5560 ms, and assert respectively: full opacity at hold start, full opacity at hold end, and zero opacity at exit end. Confirm navy and red paths share the same parent opacity animation and have no delayed exit animation.

### Task 4: Final visual and delivery verification

**Files:**
- Inspect: `C:\Temp\logo-loader-verification\screenshots\*.png`
- Inspect: `C:\Users\egorribun\Documents\logo-loader.html`

- [ ] **Step 1: Open the exact deliverable in the in-app browser**

Serve the Documents directory locally, open `logo-loader.html`, and inspect one construction phase, the full 2.5-second hold, the synchronized exit, light theme, and dark theme.

- [ ] **Step 2: Check source cleanliness**

Run:

```powershell
Get-Item 'C:\Users\egorribun\Documents\logo-loader.html' | Format-List FullName,Length,LastWriteTime
Get-FileHash 'C:\Users\egorribun\Documents\logo-loader.html' -Algorithm SHA256
```

Expected: one readable HTML file with a stable SHA-256 hash and no companion runtime files.

- [ ] **Step 3: Report integration usage**

Hand off the absolute file link and the five public calls:

```javascript
logoLoader.setProgress(42);
logoLoader.startAutomatic();
await logoLoader.complete();
logoLoader.restart({ automatic: true });
logoLoader.setTheme("dark");
```

State that the recovery copy remains at `C:\Temp\logo-loader-before-20260813.html`.
