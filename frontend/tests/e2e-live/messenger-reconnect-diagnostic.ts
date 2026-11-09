import type { CDPSession, Page, WebSocket } from "@playwright/test"

const PREFIX = "UE_LIVE_RECONNECT_V1 "
const MAX_SESSIONS = 32
const MAX_EVENTS = 24
const MAX_ELAPSED_MS = 120_000
const PROBE_BUDGET_MS = 1_000
const STAGES = new Set([
  "setup",
  "baseline",
  "offline-call",
  "old-close-wait",
  "offline-confirm",
  "missed-send",
  "online-call",
  "new-join-wait",
  "replay-check",
  "final-check",
])
const EVENTS = new Set([
  "socket-created",
  "room-joined",
  "socket-closed",
  "offline-called",
  "offline-returned",
  "online-called",
  "online-returned",
])
const KEYS = [
  "schema",
  "scenario",
  "project",
  "attempt",
  "stage",
  "selected",
  "sessions",
  "sessionsCapped",
  "joined",
  "closed",
  "elapsedMs",
  "elapsedCapped",
  "offlineEvents",
  "onlineEvents",
  "online",
  "probe",
  "nativeState",
  "buffered",
  "eventsCapped",
  "events",
  "sampleAfterFailureMs",
]

type LifecycleEvent = { sequence: number; kind: string; session: number; elapsedMs: number }
export type ReconnectObservedSession = {
  ordinal: number
  joinedChat: boolean
  closed: boolean
  socket: WebSocket
}
type Probe = {
  offlineEvents: number | null
  onlineEvents: number | null
  online: boolean | null
  probe: "unique" | "missing" | "ambiguous" | "overflow" | "unavailable"
  nativeState: number | null
  buffered: "zero" | "nonzero" | null
}
const unavailable = (): Probe => ({
  offlineEvents: null,
  onlineEvents: null,
  online: null,
  probe: "unavailable",
  nativeState: null,
  buffered: null,
})

function captureObject(value: unknown, keys: string[]): Record<string, unknown> | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return null
  const prototype = Object.getPrototypeOf(value)
  if (prototype !== Object.prototype && prototype !== null) return null
  const actual = Reflect.ownKeys(value)
  if (actual.length !== keys.length) return null
  const captured: Record<string, unknown> = Object.create(null)
  for (const key of keys) {
    const descriptor = Object.getOwnPropertyDescriptor(value, key)
    if (!descriptor || !("value" in descriptor)) return null
    captured[key] = descriptor.value
  }
  return captured
}
function integer(value: unknown, max: number): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0 && value <= max
}
function validProbe(value: unknown): value is Probe {
  if (!value || typeof value !== "object") return false
  const captured = captureObject(value, [
    "offlineEvents",
    "onlineEvents",
    "online",
    "probe",
    "nativeState",
    "buffered",
  ])
  if (!captured) return false
  const probe = captured
  if (
    !["unique", "missing", "ambiguous", "overflow", "unavailable"].includes(probe.probe as string)
  )
    return false
  if (
    ![probe.offlineEvents, probe.onlineEvents].every(
      (count) => count === null || integer(count, 32)
    )
  )
    return false
  if (probe.online !== null && typeof probe.online !== "boolean") return false
  if (probe.probe === "unique")
    return (
      integer(probe.nativeState, 3) && (probe.buffered === "zero" || probe.buffered === "nonzero")
    )
  return probe.nativeState === null && probe.buffered === null
}

/** No unknown fields, coercion, arbitrary strings, native objects or exception data. */
export function serializeReconnectDiagnostic(input: unknown): string | null {
  try {
    const value = captureObject(input, KEYS)
    if (!value || value.schema !== 1 || value.scenario !== "direct-message-replay") return null
    if ((value.project !== "desktop" && value.project !== "mobile") || !integer(value.attempt, 1))
      return null
    if (typeof value.stage !== "string" || !STAGES.has(value.stage)) return null
    if (!integer(value.sessions, MAX_SESSIONS) || !integer(value.selected, value.sessions))
      return null
    for (const key of ["sessionsCapped", "joined", "closed", "elapsedCapped", "eventsCapped"]) {
      if (typeof value[key] !== "boolean") return null
    }
    if (value.selected === 0 && (value.joined || value.closed || value.probe === "unique"))
      return null
    if (value.sessionsCapped && value.sessions !== MAX_SESSIONS) return null
    if (
      !integer(value.elapsedMs, MAX_ELAPSED_MS) ||
      (value.elapsedCapped && value.elapsedMs !== MAX_ELAPSED_MS)
    )
      return null
    if (
      value.sampleAfterFailureMs !== null &&
      !integer(value.sampleAfterFailureMs, PROBE_BUDGET_MS)
    )
      return null
    if (
      value.sampleAfterFailureMs === null &&
      (value.probe !== "unavailable" ||
        value.offlineEvents !== null ||
        value.onlineEvents !== null ||
        value.online !== null)
    )
      return null
    if (
      !validProbe({
        offlineEvents: value.offlineEvents,
        onlineEvents: value.onlineEvents,
        online: value.online,
        probe: value.probe,
        nativeState: value.nativeState,
        buffered: value.buffered,
      })
    )
      return null
    if (!Array.isArray(value.events) || Object.getPrototypeOf(value.events) !== Array.prototype)
      return null
    const length = Object.getOwnPropertyDescriptor(value.events, "length")?.value
    if (
      !integer(length, MAX_EVENTS) ||
      (value.eventsCapped && length !== MAX_EVENTS) ||
      Reflect.ownKeys(value.events).length !== length + 1
    )
      return null
    const events = []
    let lastElapsed = 0
    for (let index = 0; index < length; index += 1) {
      const descriptor = Object.getOwnPropertyDescriptor(value.events, String(index))
      if (!descriptor || !("value" in descriptor)) return null
      const event = captureObject(descriptor.value, ["sequence", "kind", "session", "elapsedMs"])
      if (!event || event.sequence !== index + 1) return null
      if (
        typeof event.kind !== "string" ||
        !EVENTS.has(event.kind) ||
        !integer(event.session, value.sessions)
      )
        return null
      if (!integer(event.elapsedMs, value.elapsedMs) || event.elapsedMs < lastElapsed) return null
      if (event.kind.startsWith("socket-") || event.kind === "room-joined") {
        if (event.session === 0) return null
      } else if (event.session !== 0) return null
      lastElapsed = event.elapsedMs
      events.push(event)
    }
    const line = PREFIX + JSON.stringify({ ...value, events }) + "\n"
    return Buffer.byteLength(line, "utf8") <= 4096 ? line : null
  } catch {
    return null
  }
}

/** Passive counters only. Never replace WebSocket, its methods, or connectivity state. */
export function armReconnectConnectivity(page: Page): () => boolean {
  let ready = false
  // Never await this diagnostic on the acceptance path. A delayed evaluation
  // installs nothing; the existing context cleanup settles any pending request.
  const deadline = Date.now() + 250
  try {
    void page
      .evaluate((expires) => {
        if (Date.now() > expires) return false
        const target = window as Window & {
          __ueReconnectConnectivity?: { offline: number; online: number }
        }
        const counts = { offline: 0, online: 0 }
        target.__ueReconnectConnectivity = counts
        window.addEventListener("offline", () => {
          counts.offline = Math.min(32, counts.offline + 1)
        })
        window.addEventListener("online", () => {
          counts.online = Math.min(32, counts.online + 1)
        })
        return true
      }, deadline)
      .then(
        (installed) => {
          ready = installed === true
        },
        () => {}
      )
  } catch {
    // A closed page or a synchronous protocol error is unavailable evidence.
  }
  return () => ready
}

/** Called after failure only. URLs remain private matching inputs and never enter the record. */
export async function probeReconnectSocket(
  page: Page,
  selected: ReconnectObservedSession | undefined,
  sessions: readonly ReconnectObservedSession[],
  connectivityArmed = false
): Promise<Probe> {
  let cdp: CDPSession | undefined
  let expired = false
  let timeout: ReturnType<typeof setTimeout> | undefined
  const group = "ue-live-reconnect-failure"
  const collect = async (): Promise<Probe> => {
    try {
      const selectedUrl = selected?.socket.url()
      // A reused URL cannot bind a collected original to a surviving replacement.
      const uniqueObservedUrl =
        selectedUrl !== undefined &&
        sessions.filter((session) => session.socket.url() === selectedUrl).length === 1
      cdp = await page.context().newCDPSession(page)
      if (expired) return unavailable()
      const prototype = await cdp.send("Runtime.evaluate", {
        expression: "WebSocket.prototype",
        objectGroup: group,
        silent: true,
        returnByValue: false,
        timeout: PROBE_BUDGET_MS,
      })
      if (expired || !prototype.result.objectId || prototype.exceptionDetails) return unavailable()
      const objects = await cdp.send("Runtime.queryObjects", {
        prototypeObjectId: prototype.result.objectId,
        objectGroup: group,
      })
      if (expired || !objects.objects.objectId) return unavailable()
      const result = await cdp.send("Runtime.callFunctionOn", {
        objectId: objects.objects.objectId,
        objectGroup: group,
        silent: true,
        returnByValue: true,
        arguments: [
          { value: uniqueObservedUrl ? selectedUrl : null },
          { value: connectivityArmed },
        ],
        functionDeclaration: `function (selectedUrl, connectivityArmed) {
          const counts = connectivityArmed ? window.__ueReconnectConnectivity : null;
          const result = {
            offlineEvents: counts && Number.isInteger(counts.offline) && counts.offline >= 0 && counts.offline <= 32 ? counts.offline : null,
            onlineEvents: counts && Number.isInteger(counts.online) && counts.online >= 0 && counts.online <= 32 ? counts.online : null,
            online: typeof navigator.onLine === "boolean" ? navigator.onLine : null,
            probe: "unavailable", nativeState: null, buffered: null
          };
          if (selectedUrl === null) return result;
          if (this.length > 32) { result.probe = "overflow"; return result; }
          const url = Object.getOwnPropertyDescriptor(WebSocket.prototype, "url").get;
          const state = Object.getOwnPropertyDescriptor(WebSocket.prototype, "readyState").get;
          const buffered = Object.getOwnPropertyDescriptor(WebSocket.prototype, "bufferedAmount").get;
          const matches = this.filter(socket => url.call(socket) === selectedUrl);
          if (matches.length !== 1) { result.probe = matches.length ? "ambiguous" : "missing"; return result; }
          const readyState = state.call(matches[0]);
          const bufferedAmount = buffered.call(matches[0]);
          if (!Number.isInteger(readyState) || readyState < 0 || readyState > 3 ||
              !Number.isSafeInteger(bufferedAmount) || bufferedAmount < 0) return result;
          result.probe = "unique"; result.nativeState = readyState;
          result.buffered = bufferedAmount === 0 ? "zero" : "nonzero";
          return result;
        }`,
      })
      return !expired && !result.exceptionDetails && validProbe(result.result.value)
        ? result.result.value
        : unavailable()
    } catch {
      return unavailable()
    } finally {
      if (cdp) {
        if (!expired)
          await cdp.send("Runtime.releaseObjectGroup", { objectGroup: group }).catch(() => {})
        await cdp.detach().catch(() => {})
      }
    }
  }
  try {
    return await Promise.race([
      collect(),
      new Promise<Probe>((resolve) => {
        timeout = setTimeout(() => {
          expired = true
          // Detaching ends the session and releases its object handles. A late attach
          // takes the expired branch above and is detached without further evaluation.
          void cdp?.detach().catch(() => {})
          resolve(unavailable())
        }, PROBE_BUDGET_MS)
      }),
    ])
  } finally {
    clearTimeout(timeout)
  }
}

export function createReconnectDiagnostic(
  project: string,
  attempt: number,
  now = () => performance.now(),
  emit = (line: string) => {
    process.stdout.write(line)
  }
) {
  const started = now()
  const events: LifecycleEvent[] = []
  let sessions = 0
  let sessionsCapped = false
  let selected = 0
  let stage = "setup"
  let eventsCapped = false
  let emitted = false
  let connectivityArmed = false
  const elapsed = () => Math.min(MAX_ELAPSED_MS, Math.max(0, Math.floor(now() - started)))
  const note = (kind: string, session = 0) => {
    if (
      !EVENTS.has(kind) ||
      !integer(session, sessions) ||
      (session === 0 && (kind.startsWith("socket-") || kind === "room-joined"))
    )
      return
    if (events.length === MAX_EVENTS) {
      eventsCapped = true
      return
    }
    events.push({ sequence: events.length + 1, kind, session, elapsedMs: elapsed() })
  }
  return {
    socketCreated() {
      if (sessions === MAX_SESSIONS) {
        sessionsCapped = true
        return 0
      }
      sessions += 1
      note("socket-created", sessions)
      return sessions
    },
    note,
    select(ordinal: number) {
      if (integer(ordinal, sessions)) selected = ordinal
    },
    stage(value: string) {
      if (STAGES.has(value)) stage = value
    },
    connectivityReady(value: boolean) {
      connectivityArmed = value === true
    },
    async reportFailure(page: Page, observed: readonly ReconnectObservedSession[]) {
      if (emitted) return
      emitted = true
      try {
        const active = observed.find((session) => session.ordinal === selected && selected !== 0)
        // Freeze observations before native probing and, critically, before test cleanup.
        const record = {
          schema: 1,
          scenario: "direct-message-replay",
          project,
          attempt,
          stage,
          selected,
          sessions,
          sessionsCapped,
          joined: active?.joinedChat ?? false,
          closed: active?.closed ?? false,
          elapsedMs: elapsed(),
          elapsedCapped: now() - started > MAX_ELAPSED_MS,
          eventsCapped,
          events: events.map((event) => ({ ...event })),
        }
        const probeStarted = performance.now()
        let probe = await probeReconnectSocket(page, active, observed, connectivityArmed)
        // Native state/counters are later observations. This completion delay
        // bounds their sampling window, rather than dating them to the failure.
        const delay = Math.ceil(performance.now() - probeStarted)
        const sampleAfterFailureMs = delay <= PROBE_BUDGET_MS ? delay : null
        if (sampleAfterFailureMs === null) probe = unavailable()
        const line = serializeReconnectDiagnostic({ ...record, ...probe, sampleAfterFailureMs })
        if (line !== null) emit(line)
      } catch {
        // Diagnostics must never change or replace the acceptance failure.
      }
    },
  }
}
