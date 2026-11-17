import assert from "node:assert/strict"
import { spawnSync } from "node:child_process"
import { readFile } from "node:fs/promises"
import process from "node:process"
import { URL } from "node:url"
import test from "node:test"

const specUrl = new URL("./map-zoom-longtask.live.spec.ts", import.meta.url)
const configUrl = new URL("../../playwright.live.config.ts", import.meta.url)
const mapFeatureUrl = new URL("../../src/features/map/MapFeature.tsx", import.meta.url)
const mapLibreUrl = new URL("../../src/components/map/MapLibreMap.tsx", import.meta.url)
const gestureSpecUrl = new URL("./map-gesture-isolation.live.spec.ts", import.meta.url)
const planUrl = new URL("../../../docs/superpowers/plans/MVP_MASTER_PLAN.md", import.meta.url)
const diagnosticUrl = new URL("./map-zoom-longtask-diagnostic.ts", import.meta.url)
const measurementUrl = new URL("./map-zoom-longtask-measurement.ts", import.meta.url)

function reportInChild(calls) {
  const result = spawnSync(
    process.execPath,
    [
      "--input-type=module",
      "--eval",
      `import { reportMapZoomLongTasks } from ${JSON.stringify(diagnosticUrl.href)};\n${calls}`,
    ],
    { encoding: "utf8" }
  )
  assert.equal(result.status, 0)
  assert.equal(result.stderr, "")
  return result.stdout
}

test("map zoom long-task acceptance observes the real MapLibre browser path", async () => {
  let spec
  try {
    spec = await readFile(specUrl, "utf8")
  } catch {
    assert.fail("the live map zoom long-task scenario must exist")
  }

  const [config, mapFeature, mapLibre, gestureSpec, plan] = await Promise.all([
    readFile(configUrl, "utf8"),
    readFile(mapFeatureUrl, "utf8"),
    readFile(mapLibreUrl, "utf8"),
    readFile(gestureSpecUrl, "utf8"),
    readFile(planUrl, "utf8"),
  ])

  assert.match(
    plan,
    /В v1\.1: полный lab protocol navbar CLS <0\.1, отсутствие map long tasks ≥50 ms/u
  )
  assert.match(mapFeature, /data-testid="map-activation-placeholder"/u)
  assert.match(mapFeature, /setMapReady\(true\)/u)
  assert.match(mapLibre, /https:\/\/tiles\.openfreemap\.org\/styles\/bright/u)
  assert.match(mapLibre, /if \(!map \|\| !map\.loaded\(\)\)/u)

  assert.match(spec, /live MapLibre zoom has no main-thread long task at or above 50 ms/u)
  assert.match(spec, /await loginAs\(page, "student"\)/u)
  assert.match(spec, /await page\.goto\(MAP_URL/u)
  assert.match(spec, /map-activation-placeholder/u)
  assert.match(spec, /waitForResponse\([\s\S]*?\/styles\//u)
  assert.match(spec, /waitForResponse\([\s\S]*?\/data\/v3\//u)
  assert.match(spec, /\.maplibregl-canvas/u)
  assert.match(spec, /waitForMapNetworkQuiescence/u)
  assert.match(spec, /requestAnimationFrame/u)
  assert.match(spec, /PerformanceObserver/u)
  assert.match(spec, /type:\s*["']longtask["']/u)
  assert.match(spec, /LONG_TASK_THRESHOLD_MS\s*=\s*50/u)
  assert.match(spec, /sample\.duration\s*>=\s*LONG_TASK_THRESHOLD_MS/u)
  assert.match(spec, /if \(blockingTasks\.length > 0\)[\s\S]*?reportMapZoomLongTasks\(/u)
  assert.match(spec, /blockingTasks\.map\(\(\{ step, phase, duration \}\)/u)
  assert.match(spec, /const ZOOM_STEPS\s*=\s*3/u)
  assert.match(spec, /getByRole\("button",\s*\{\s*name: \/Приблизить\|Zoom in\/u\s*\}\)/u)
  assert.match(spec, /await zoomIn\.click\(\)/u)
  assert.match(spec, /toEqual\(\s*\[\s*\]\s*\)/u)
  assert.match(spec, /browserName !== ["']chromium["']/u)
  // The only interception allowed is the pinned tile fixture for the external
  // public host; the stand must not depend on that host being reachable.
  assert.match(spec, /page\.route\(`https:\/\/\$\{MAP_RESOURCE_HOST\}\/styles\/\*\*`/u)
  assert.match(spec, /page\.route\(`https:\/\/\$\{MAP_RESOURCE_HOST\}\/data\/v3\/\*\*`/u)
  assert.doesNotMatch(spec, /routeWebSocket|useMockApi|waitForTimeout/u)
  assert.equal([...spec.matchAll(/page\.route\(/gu)].length, 2)
  assert.doesNotMatch(spec, /page\.request\.(?:post|put|patch|delete)/u)

  assert.match(gestureSpec, /page\.route\(["']https:\/\/tiles\.openfreemap\.org\/styles/u)
  assert.match(config, /testDir: "\.\/tests\/e2e-live"/u)
  assert.match(config, /testMatch:\s*\/\.\*\\\.live\\\.spec\\\.ts\$\//u)
  assert.match(config, /name: "desktop"/u)
  assert.match(config, /name: "mobile"/u)
})

test("map zoom diagnostics emit only bounded duration and phase records", () => {
  assert.equal(
    reportInChild(
      `reportMapZoomLongTasks('desktop', 0, [{step:0,phase:0,duration:50,rawTiming:15.25}, {step:2,phase:3,duration:62.4,origin:'private'}])`
    ),
    "UE_LIVE_MAP_ZOOM_V1 project=desktop attempt=0 sample=1 total=2 step=0 phase=0 duration_ms=50\n" +
      "UE_LIVE_MAP_ZOOM_V1 project=desktop attempt=0 sample=2 total=2 step=2 phase=3 duration_ms=63\n"
  )
})

test("map zoom diagnostics reject malformed inputs without coercion or leakage", () => {
  assert.equal(
    reportInChild(`
      const malicious = {toString(){throw new Error('private')}};
      const sample = {step:1,phase:1,duration:50};
      reportMapZoomLongTasks('desktop\\nprivate',0,[sample]);
      reportMapZoomLongTasks(malicious,0,[sample]);
      reportMapZoomLongTasks('desktop',2,[sample]);
      reportMapZoomLongTasks('desktop',0,[]);
      reportMapZoomLongTasks('desktop',0,null);
      reportMapZoomLongTasks('desktop',0,[null,'private']);
      reportMapZoomLongTasks('desktop',0,[{step:'1\\nprivate',phase:1,duration:50}]);
      reportMapZoomLongTasks('desktop',0,[{step:1.5,phase:1,duration:50}]);
      reportMapZoomLongTasks('desktop',0,[{step:1,phase:5,duration:50}]);
      reportMapZoomLongTasks('desktop',0,[{step:1,phase:1.5,duration:50}]);
      reportMapZoomLongTasks('desktop',0,[{step:0,phase:1,duration:50}]);
      reportMapZoomLongTasks('desktop',0,[{step:1,phase:4,duration:50}]);
      reportMapZoomLongTasks('desktop',0,[{step:1,phase:1,duration:49}]);
      reportMapZoomLongTasks('desktop',0,[{step:1,phase:1,duration:Infinity}]);
      reportMapZoomLongTasks('desktop',0,[{step:1,phase:1,duration:malicious}]);
    `),
    ""
  )
})

test("map zoom diagnostics cap the number of rows and durations", () => {
  const output = reportInChild(
    `reportMapZoomLongTasks('mobile', 1, Array.from({length:20},(_,i)=>({step:3,phase:4,duration:i===0?1000000:50+i})))`
  )
  const lines = output.trimEnd().split("\n")
  assert.equal(lines.length, 8)
  assert.equal(
    lines[0],
    "UE_LIVE_MAP_ZOOM_V1 project=mobile attempt=1 sample=1 total=20 step=3 phase=4 duration_ms=60000"
  )
  assert.match(lines[7], /sample=8 total=20 step=3 phase=4 duration_ms=57$/u)
})

test("map zoom diagnostics bound aggregate counts and tolerate a closed output stream", () => {
  const output = reportInChild(`
    reportMapZoomLongTasks('mobile', 0, Array.from({length:1000},()=>({step:1,phase:2,duration:50})));
    const write = process.stdout.write;
    process.stdout.write = () => { throw new Error('private'); };
    reportMapZoomLongTasks('desktop', 0, [{step:1,phase:2,duration:50}]);
    process.stdout.write = write;
  `)
  const lines = output.trimEnd().split("\n")
  assert.equal(lines.length, 8)
  assert.match(lines[0], /sample=1 total=999 step=1 phase=2 duration_ms=50$/u)
})

test("map phase attribution uses task start times and never returns timing origins", () => {
  const result = spawnSync(
    process.execPath,
    [
      "--input-type=module",
      "--eval",
      `import assert from 'node:assert/strict';
       import {stopLongTaskMeasurement} from ${JSON.stringify(measurementUrl.href)};
       const base = performance.now() - 1000;
       const marks = Array.from({length:9}, (_,i) => ({step:Math.floor(i/3)+1, phase:i%3+1, at:base+i*2}));
       let disconnected = false;
       globalThis.requestAnimationFrame = (callback) => callback();
       globalThis.window = {
         __mapZoomMeasurementStartedAt: base - 10,
         __mapZoomPhaseMarks: marks,
         __mapZoomLongTaskSamples: [
           {startTime:base-5,duration:50},
           {startTime:base+0.5,duration:61.2},
           {startTime:base+8.5,duration:72},
           {startTime:base-11,duration:99},
         ],
         __mapZoomLongTaskObserver: {
           takeRecords: () => [{entryType:'longtask',startTime:base+16.5,duration:80}, {entryType:'longtask',startTime:performance.now(),duration:90}, {entryType:'other',startTime:base+17,duration:100}],
           disconnect: () => { disconnected = true },
         },
       };
       const result = await stopLongTaskMeasurement({evaluate: (fn) => fn()});
       assert.deepEqual(result, [
         {duration:50,step:0,phase:0},
         {duration:61.2,step:1,phase:1},
         {duration:72,step:2,phase:2},
         {duration:80,step:3,phase:3},
         {duration:90,step:3,phase:4},
       ]);
       assert.equal(disconnected, true);
       assert.deepEqual(Object.keys(window), []);`,
    ],
    { encoding: "utf8" }
  )
  assert.equal(result.status, 0)
  assert.equal(result.stderr, "")
})

test("map phase attribution falls back to unknown for incomplete or unordered markers", () => {
  const result = spawnSync(
    process.execPath,
    [
      "--input-type=module",
      "--eval",
      `import assert from 'node:assert/strict';
       import {stopLongTaskMeasurement} from ${JSON.stringify(measurementUrl.href)};
       globalThis.requestAnimationFrame = (callback) => callback();
       for (const kind of ['missing','order','time','nonfinite']) {
         const base = performance.now() - 1000;
         const marks = Array.from({length:kind === 'missing' ? 8 : 9}, (_,i) => ({step:Math.floor(i/3)+1, phase:i%3+1, at:base+i*2}));
         if (kind === 'order') marks[2].phase = 1;
         if (kind === 'time') marks[2].at = base - 1;
         if (kind === 'nonfinite') marks[2].at = NaN;
         globalThis.window = {
           __mapZoomMeasurementStartedAt: base-10,
           __mapZoomPhaseMarks: marks,
           __mapZoomLongTaskSamples: [{startTime:base+4.5,duration:50}],
         };
         assert.deepEqual(await stopLongTaskMeasurement({evaluate:(fn)=>fn()}), [{duration:50,step:0,phase:0}]);
       }`,
    ],
    { encoding: "utf8" }
  )
  assert.equal(result.status, 0)
  assert.equal(result.stderr, "")
})

test("stopping an absent map observer returns no samples", () => {
  const result = spawnSync(
    process.execPath,
    [
      "--input-type=module",
      "--eval",
      `import assert from 'node:assert/strict';
       import {stopLongTaskMeasurement} from ${JSON.stringify(measurementUrl.href)};
       globalThis.requestAnimationFrame = (callback) => callback();
       globalThis.window = {};
       assert.deepEqual(await stopLongTaskMeasurement({evaluate:(fn)=>fn()}), []);
       assert.deepEqual(Object.keys(window), []);`,
    ],
    { encoding: "utf8" }
  )
  assert.equal(result.status, 0)
  assert.equal(result.stderr, "")
})
