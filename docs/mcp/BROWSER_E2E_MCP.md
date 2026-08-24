# Browser E2E Automation Guide (Playwright & Chrome DevTools MCP)

## 1. Overview & Dual-Engine Strategy

The **University Ecosystem Platform** utilizes a dual-engine browser automation model to provide end-to-end user journey validation, accessibility auditing, and runtime performance profiling:

```
                          ┌───────────────────────────────┐
                          │   QA / E2E Automation Agent   │
                          └──────────────┬────────────────┘
                                         │
                 ┌───────────────────────┴───────────────────────┐
                 ▼                                               ▼
    ┌──────────────────────────┐                    ┌──────────────────────────┐
    │      Playwright MCP      │                    │  Chrome DevTools MCP     │
    │  (@executeautomation)    │                    │  (chrome-devtools-mcp)   │
    ├──────────────────────────┤                    ├──────────────────────────┤
    │ • User Journey Flow      │                    │ • Lighthouse WCAG Audits │
    │ • Form Input & Buttons   │                    │ • Low-level Trace Insights│
    │ • Response Assertions    │                    │ • Heap Memory Snapshots  │
    │ • Network Interception   │                    │ • Console Log Sniffing   │
    └──────────────────────────┘                    └──────────────────────────┘
```

- **Playwright MCP (`playwright`)**: High-level browser orchestration. Best for navigating pages, clicking elements, filling inputs, waiting for API responses, asserting HTTP status codes, and capturing visual regression screenshots.
- **Chrome DevTools MCP (`chrome-devtools-mcp`)**: Low-level runtime introspection via Chrome DevTools Protocol (CDP). Best for running Lighthouse accessibility and performance audits, recording performance traces, capturing heap memory snapshots, and extracting raw console errors.

---

## 2. Tool Reference & Signature Matrix

### 2.1 Playwright MCP Tools

| Tool Name | Parameters | Description |
|---|---|---|
| `playwright_navigate` | `url: string` | Navigates the browser to the specified URL. |
| `playwright_click` | `selector: string` | Clicks an element matched by CSS selector, text, or ARIA role. |
| `playwright_fill` | `selector: string`, `value: string` | Clears and inputs text into an input field or textarea. |
| `playwright_screenshot` | `name: string`, `selector?: string`, `width?: number`, `height?: number` | Captures a full-page or element screenshot as an image artifact. |
| `playwright_evaluate` | `script: string` | Executes custom JavaScript in the browser context and returns result. |
| `playwright_hover` | `selector: string` | Hovers over an element to trigger dropdowns or tooltip states. |
| `playwright_select` | `selector: string`, `value: string` | Selects an option from a `<select>` element. |
| `playwright_resize` | `width: number`, `height: number` | Resizes the browser viewport (e.g. `375x667` for mobile, `1920x1080` for desktop). |
| `playwright_expect_response` | `url: string` | Waits for a specific network request/response matching URL substring. |
| `playwright_assert_response` | `url: string`, `status: number` | Asserts that an intercepted network response returned the expected status code. |
| `playwright_console_logs` | *(none)* | Retrieves collected browser console logs, warnings, and errors. |

### 2.2 Chrome DevTools MCP Tools

| Tool Name | Parameters | Description |
|---|---|---|
| `navigate_page` | `url: string` | Navigates the active DevTools page to the target URL. |
| `click` | `selector: string` | Dispatches click event via CDP. |
| `fill_form` | `elements: Array<{selector: string, value: string}>` | Batches form field values and dispatches input events. |
| `take_screenshot` | `name: string`, `clip?: object` | Takes CDP-level viewport or clipped screenshot. |
| `lighthouse_audit` | `url: string`, `categories?: string[]` | Runs Google Lighthouse audit (`accessibility`, `performance`, `best-practices`, `seo`). |
| `list_console_messages`| *(none)* | Returns raw CDP console messages, stack traces, and unhandled exceptions. |
| `performance_start_trace` | `options?: object` | Starts recording a performance trace timeline. |
| `performance_stop_trace` | *(none)* | Stops trace recording and saves the timeline buffer. |
| `performance_analyze_insight` | *(none)* | Analyzes recorded trace for Core Web Vitals (LCP, FID/INP, CLS) and bottlenecks. |
| `take_heapsnapshot` | *(none)* | Takes a V8 heap snapshot for memory leak diagnostics. |

---

## 3. Practical E2E Recipes

### Recipe 1: User Authentication & Session Verification

This recipe validates the end-to-end login flow, ensuring that `access_token_v2` is set as an HttpOnly cookie with `cookie_samesite="lax"` and the CSRF cookie is properly acquired.

```json
// Step 1: Navigate to login page
{
  "ServerName": "playwright",
  "ToolName": "playwright_navigate",
  "Arguments": {
    "url": "http://localhost:3000/login"
  }
}

// Step 2: Fill credentials
{
  "ServerName": "playwright",
  "ToolName": "playwright_fill",
  "Arguments": {
    "selector": "input[name='email']",
    "value": "student.test@university.edu"
  }
}
{
  "ServerName": "playwright",
  "ToolName": "playwright_fill",
  "Arguments": {
    "selector": "input[name='password']",
    "value": "Argon2_Verified_Pass_2026!"
  }
}

// Step 3: Click login button & expect API response
{
  "ServerName": "playwright",
  "ToolName": "playwright_click",
  "Arguments": {
    "selector": "button[type='submit']"
  }
}
{
  "ServerName": "playwright",
  "ToolName": "playwright_assert_response",
  "Arguments": {
    "url": "/api/v1/auth/login",
    "status": 200
  }
}

// Step 4: Verify navigation to dashboard and capture screenshot
{
  "ServerName": "playwright",
  "ToolName": "playwright_screenshot",
  "Arguments": {
    "name": "auth_login_dashboard_success",
    "width": 1280,
    "height": 800
  }
}
```

---

### Recipe 2: Interactive Schedule Grid ARIA & Visual Inspection

Validates the schedule grid structure, checking for CSS `display: contents` on role rows, glow indicators for active classes, and responsive layout scaling.

```json
// Step 1: Navigate to Schedule view
{
  "ServerName": "playwright",
  "ToolName": "playwright_navigate",
  "Arguments": {
    "url": "http://localhost:3000/schedule"
  }
}

// Step 2: Evaluate ARIA Grid structure
{
  "ServerName": "playwright",
  "ToolName": "playwright_evaluate",
  "Arguments": {
    "script": "(() => {\n  const rows = document.querySelectorAll('[role=\"row\"]');\n  const hasContentsDisplay = Array.from(rows).every(r => window.getComputedStyle(r).display === 'contents' || r.tagName === 'TR');\n  const currentGlow = document.querySelectorAll('.sched-current-glow.sched-current-glow');\n  return { rowCount: rows.length, validAriaGrid: hasContentsDisplay, activeSlots: currentGlow.length };\n})()"
  }
}

// Step 3: Test mobile responsive viewport
{
  "ServerName": "playwright",
  "ToolName": "playwright_resize",
  "Arguments": {
    "width": 375,
    "height": 812
  }
}
{
  "ServerName": "playwright",
  "ToolName": "playwright_screenshot",
  "Arguments": {
    "name": "schedule_mobile_375px_view"
  }
}

// Step 4: Return to desktop viewport
{
  "ServerName": "playwright",
  "ToolName": "playwright_resize",
  "Arguments": {
    "width": 1920,
    "height": 1080
  }
}
```

---

### Recipe 3: Accessibility & WCAG 2.2 AA Auditing (Lighthouse)

Runs Google Lighthouse accessibility and best-practice audits against key pages to enforce zero-violation standards.

```json
// Step 1: Run Lighthouse audit on the News & Announcements page
{
  "ServerName": "chrome-devtools-mcp",
  "ToolName": "lighthouse_audit",
  "Arguments": {
    "url": "http://localhost:3000/news",
    "categories": ["accessibility", "best-practices"]
  }
}

// Step 2: Inspect accessibility tree for dialog modals
{
  "ServerName": "chrome-devtools-mcp",
  "ToolName": "evaluate_script",
  "Arguments": {
    "script": "(() => {\n  const dialogs = document.querySelectorAll('[role=\"dialog\"], [role=\"alertdialog\"]');\n  return Array.from(dialogs).map(d => ({\n    id: d.id,\n    ariaModal: d.getAttribute('aria-modal'),\n    ariaLabelledby: d.getAttribute('aria-labelledby'),\n    hasCloseButton: !!d.querySelector('button[aria-label=\"Close\"], button.close')\n  }));\n})()"
  }
}
```

---

### Recipe 4: React 19 Hydration Mismatch & Console Error Sniffing

Verifies that server-rendered HTML matches client-side hydration without triggering React error #418, missing suppressions, or console errors.

```json
// Step 1: Navigate to campus map or dynamic route
{
  "ServerName": "chrome-devtools-mcp",
  "ToolName": "navigate_page",
  "Arguments": {
    "url": "http://localhost:3000/map"
  }
}

// Step 2: Extract all console messages
{
  "ServerName": "chrome-devtools-mcp",
  "ToolName": "list_console_messages",
  "Arguments": {}
}

// Step 3: Assert window.__APP_HYDRATED flag is true and no React error #418
{
  "ServerName": "playwright",
  "ToolName": "playwright_evaluate",
  "Arguments": {
    "script": "(() => {\n  const hydrated = window.__APP_HYDRATED === true;\n  const errors = (window.__E2E_ERRORS || []);\n  return { hydrated, errorCount: errors.length, errors };\n})()"
  }
}
```

---

### Recipe 5: Performance Profiling & Core Web Vitals Analysis

Records a performance trace during heavy UI interaction (e.g. switching schedule weeks or filtering news) and verifies CLS <= 0.05 and smooth frame rendering.

```json
// Step 1: Start performance trace
{
  "ServerName": "chrome-devtools-mcp",
  "ToolName": "performance_start_trace",
  "Arguments": {
    "options": {
      "screenshots": true,
      "categories": ["blink.user_timing", "loading", "devtools.timeline"]
    }
  }
}

// Step 2: Trigger UI interaction
{
  "ServerName": "playwright",
  "ToolName": "playwright_click",
  "Arguments": {
    "selector": "button[data-testid='next-week-btn']"
  }
}

// Step 3: Stop trace and analyze insights
{
  "ServerName": "chrome-devtools-mcp",
  "ToolName": "performance_stop_trace",
  "Arguments": {}
}
{
  "ServerName": "chrome-devtools-mcp",
  "ToolName": "performance_analyze_insight",
  "Arguments": {}
}
```

---

## 4. Frontend Gotchas & Invariant Checklist for E2E

1. **Hydration Mismatches (React #418)**:
   - Always verify that components using `localStorage`, `matchMedia`, or portals use the `mounted` pattern (`const [mounted, setMounted] = useState(false); useEffect(() => setMounted(true), []);`).
2. **Double-Class Selectors for CSS Priority**:
   - The schedule current glow uses `.sched-current-glow.sched-current-glow` to avoid `!important`. Ensure E2E tests target this class selector.
3. **MapLibre Coordinates**:
   - `campusBuildings.ts` stores coordinates as `geoCoords: [lat, lng]`, whereas MapLibre expects `longitude={coords[1]}` and `latitude={coords[0]}`.
4. **Valibot Numeric Queries**:
   - In TanStack Router search params, numeric query params (e.g. `?z=16`) may be stringified. Ensure schemas accept string/number unions.
