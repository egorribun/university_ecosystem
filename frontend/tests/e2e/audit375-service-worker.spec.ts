import { createServer, type IncomingMessage, type ServerResponse } from "node:http"
import { resolve } from "node:path"
import { fileURLToPath } from "node:url"
import { expect, test, type CDPSession, type Page } from "@playwright/test"
import { build } from "vite"
import { REPLAY_LEASE_POLL_MS } from "../../src/sw/replayPolicy"

const frontendRoot = fileURLToPath(new URL("../..", import.meta.url))
const lockName = "ecosystem-offline-queue-replay"
const databaseName = "notification-interactions"
const csrfCookie = "csrf.fixture%2Eproof"
const csrfHeader = "csrf.fixture.proof"

/** Bundle the actual worker and page responder with only a test barrier around the worker. */
async function bundleFixture(source: string): Promise<string> {
  const result = await build({
    configFile: false,
    root: frontendRoot,
    mode: "production",
    logLevel: "silent",
    define: { "self.__WB_MANIFEST": "[]" },
    resolve: { alias: { "@": resolve(frontendRoot, "src") } },
    plugins: [
      {
        name: "audit375-browser-fixture",
        resolveId(id) {
          if (id === "virtual:audit375") return "\0audit375"
        },
        load(id) {
          if (id === "\0audit375") return source
        },
      },
    ],
    build: {
      write: false,
      minify: false,
      rollupOptions: { input: "virtual:audit375", output: { format: "iife" } },
    },
  })
  if (Array.isArray(result) || !("output" in result)) {
    throw new Error("Expected one fixture bundle")
  }
  const chunk = result.output.find((output) => output.type === "chunk")
  if (!chunk) throw new Error("Fixture bundle was not emitted")
  return chunk.code
}

function gate<T>() {
  let resolveGate!: (value: T) => void
  const promise = new Promise<T>((resolvePromise) => {
    resolveGate = resolvePromise
  })
  return { promise, resolve: resolveGate }
}

interface Attempt {
  method: string | undefined
  csrf: string | undefined
  cookie: string | undefined
  idempotencyKey: string | undefined
  body: string
}

/** A local HTTP endpoint records what the browser sent and can hold either response. */
async function fixtureServer(worker: string, pageScript: string, holdSecond = false) {
  const attempts: Attempt[] = []
  const firstAttempt = gate<void>()
  const secondAttempt = gate<void>()
  const firstResponse = gate<void>()
  const secondResponse = gate<void>()
  const server = createServer(async (request: IncomingMessage, response: ServerResponse) => {
    if (request.url === "/a/sw.js" || request.url === "/b/sw.js") {
      response.writeHead(200, {
        "Content-Type": "application/javascript",
        "Cache-Control": "no-store",
      })
      response.end(worker)
      return
    }
    if (request.url === "/page.js") {
      response.writeHead(200, {
        "Content-Type": "application/javascript",
        "Cache-Control": "no-store",
      })
      response.end(pageScript)
      return
    }
    if (request.url === "/a/" || request.url === "/b/") {
      response.writeHead(200, { "Content-Type": "text/html", "Cache-Control": "no-store" })
      response.end('<!doctype html><script src="/page.js"></script>')
      return
    }
    if (request.url === "/api/v1/profile" && request.method === "PATCH") {
      let body = ""
      for await (const chunk of request) body += String(chunk)
      attempts.push({
        method: request.method,
        csrf: request.headers["x-csrf-token"] as string | undefined,
        cookie: request.headers.cookie,
        idempotencyKey: request.headers["idempotency-key"] as string | undefined,
        body,
      })
      if (attempts.length === 1) {
        firstAttempt.resolve()
        await firstResponse.promise
      } else if (attempts.length === 2) {
        secondAttempt.resolve()
        if (holdSecond) await secondResponse.promise
      }
      response.writeHead(403)
      response.end()
      return
    }
    response.writeHead(404)
    response.end()
  })
  await new Promise<void>((resolveListen, reject) => {
    server.once("error", reject)
    server.listen(0, "127.0.0.1", resolveListen)
  })
  const address = server.address()
  if (!address || typeof address === "string") throw new Error("Fixture server has no TCP port")
  return {
    url: `http://127.0.0.1:${address.port}`,
    attempts,
    firstAttempt: firstAttempt.promise,
    secondAttempt: secondAttempt.promise,
    releaseFirst: () => firstResponse.resolve(),
    releaseSecond: () => secondResponse.resolve(),
    async close() {
      firstResponse.resolve()
      secondResponse.resolve()
      server.closeAllConnections()
      await new Promise<void>((resolveClose, reject) =>
        server.close((error) => (error ? reject(error) : resolveClose()))
      )
    },
  }
}

async function startWorker(page: Page, base: string, scope: "a" | "b") {
  await page.goto(`${base}/${scope}/`)
  await page.evaluate(async (workerScope) => {
    await navigator.serviceWorker.register(`/${workerScope}/sw.js`, { scope: `/${workerScope}/` })
    await navigator.serviceWorker.ready
  }, scope)
  await page.waitForFunction((expectedScriptUrl) => {
    const controller = navigator.serviceWorker.controller
    return controller?.state === "activated" && controller.scriptURL === expectedScriptUrl
  }, `${base}/${scope}/sw.js`)
  await barrier(page)
}

/** The barrier queues behind prior real message-triggered passes and acknowledges their completion. */
async function barrier(page: Page) {
  await page.evaluate(
    () =>
      new Promise<void>((resolveBarrier, reject) => {
        const channel = new MessageChannel()
        channel.port1.onmessage = ({ data }) => {
          channel.port1.close()
          if (data !== "done") return reject(new Error(`Worker barrier failed: ${String(data)}`))
          resolveBarrier()
        }
        const controller = navigator.serviceWorker.controller
        if (!controller) return reject(new Error("Worker does not control this page"))
        controller.postMessage({ type: "AUD375_TEST_BARRIER" }, [channel.port2])
      })
  )
}

async function trigger(page: Page) {
  await page.evaluate(() => {
    if (!navigator.serviceWorker.controller) throw new Error("Worker does not control this page")
    navigator.serviceWorker.controller.postMessage({ type: "PROCESS_OFFLINE_QUEUES" })
  })
}

async function withDatabase<T>(page: Page, operation: "enqueue" | "records" | "lease" | "expire") {
  return page.evaluate(
    ({ name, action }) =>
      new Promise<T>((resolveOperation, reject) => {
        const open = indexedDB.open(name, 5)
        open.onerror = () => reject(open.error)
        open.onsuccess = () => {
          const db = open.result
          const storeName =
            action === "enqueue" || action === "records" ? "pending-mutations" : "replay-lease"
          const tx = db.transaction(
            storeName,
            action === "records" || action === "lease" ? "readonly" : "readwrite"
          )
          const store = tx.objectStore(storeName)
          let result: unknown
          if (action === "enqueue") {
            store.add({
              url: "/api/v1/profile",
              method: "PATCH",
              payload: { displayName: "queued" },
              mutationId: "browser-mutation",
              idempotencyKey: "browser-operation",
              timestamp: Date.now(),
              retryCount: 0,
              category: "profile",
              sessionNonce: localStorage.getItem("audit375.session"),
            })
          } else if (action === "records") {
            const request = store.getAll()
            request.onsuccess = () => {
              result = request.result
            }
          } else {
            const request = store.get("replay")
            request.onsuccess = () => {
              result = request.result
              if (action === "expire" && request.result) {
                store.put({ ...request.result, expiresAt: Date.now() - 1 })
              }
            }
          }
          tx.oncomplete = () => {
            db.close()
            resolveOperation(result as T)
          }
          tx.onerror = () => {
            db.close()
            reject(tx.error)
          }
          tx.onabort = () => {
            db.close()
            reject(tx.error)
          }
        }
      }),
    { name: databaseName, action: operation }
  )
}

test.describe("AUD-375 real service-worker replay", () => {
  test.skip(
    ({ browserName }) => browserName !== "chromium",
    "The lifecycle control uses Chromium CDP"
  )
  let workerScript: string
  let pageScript: string

  test.beforeAll(async () => {
    const sw = JSON.stringify(resolve(frontendRoot, "src/sw.ts"))
    const offline = JSON.stringify(resolve(frontendRoot, "src/sw/offline.ts"))
    const responder = JSON.stringify(resolve(frontendRoot, "src/sw/replayCredentialResponder.ts"))
    const session = JSON.stringify(resolve(frontendRoot, "src/stores/sessionEpoch.ts"))
    ;[workerScript, pageScript] = await Promise.all([
      bundleFixture(`
        import ${sw};
        import { processOfflineQueues } from ${offline};
        self.addEventListener("message", (event) => {
          const port = event.ports[0];
          if (event.data?.type !== "AUD375_TEST_BARRIER" || !port) return;
          event.waitUntil((async () => {
            try {
              // Bootstrap publishes this immediately before scheduling its initial replay.
              const deadline = Date.now() + 10_000;
              while (!self.__SW_TESTING__) {
                if (Date.now() >= deadline) throw new Error("Worker bootstrap did not complete");
                await new Promise((resolveWait) => setTimeout(resolveWait, 25));
              }
              await processOfflineQueues();
              port.postMessage("done");
            } catch (error) {
              port.postMessage(String(error));
            }
          })());
        });
      `),
      bundleFixture(`
        import { installReplayCredentialResponder } from ${responder};
        import { rotateBrowserSession, acceptBrowserSessionGeneration, getBrowserSessionGeneration } from ${session};
        if (location.pathname.startsWith("/a/")) rotateBrowserSession();
        else acceptBrowserSessionGeneration();
        localStorage.setItem("audit375.session", getBrowserSessionGeneration());
        document.cookie = "csrf_token=${csrfCookie}; path=/";
        installReplayCredentialResponder(navigator.serviceWorker);
      `),
    ])
  })

  test("forwards the cookie proof and deletes a terminal 403 while two active workers contend", async ({
    page,
    context,
  }) => {
    const fixture = await fixtureServer(workerScript, pageScript)
    try {
      await startWorker(page, fixture.url, "a")
      const other = await context.newPage()
      await startWorker(other, fixture.url, "b")
      await withDatabase(page, "enqueue")

      await trigger(page)
      await fixture.firstAttempt
      await trigger(other)
      await expect
        .poll(() =>
          page.evaluate(async (name) => {
            const locks = await navigator.locks.query()
            return {
              held: locks.held?.filter((lock) => lock.name === name).length,
              pending: locks.pending?.filter((lock) => lock.name === name).length,
            }
          }, lockName)
        )
        .toEqual({ held: 1, pending: 1 })
      expect(fixture.attempts).toHaveLength(1)
      expect(fixture.attempts[0]).toEqual({
        method: "PATCH",
        csrf: csrfHeader,
        cookie: `csrf_token=${csrfCookie}`,
        idempotencyKey: "browser-operation",
        body: JSON.stringify({ displayName: "queued" }),
      })

      fixture.releaseFirst()
      await barrier(other)
      await barrier(page)
      expect(await withDatabase(page, "records")).toEqual([])
      expect(fixture.attempts).toHaveLength(1)
    } finally {
      await fixture.close()
    }
  })

  test("an abandoned worker's lease blocks its successor until forced expiry, then the successor drains the row", async ({
    page,
    context,
  }) => {
    const fixture = await fixtureServer(workerScript, pageScript, true)
    let cdp: CDPSession | undefined
    try {
      cdp = await context.newCDPSession(page)
      const workerVersions = new Map<string, { versionId: string; runningStatus: string }>()
      cdp.on("ServiceWorker.workerVersionUpdated", ({ versions }) => {
        for (const version of versions) workerVersions.set(version.scriptURL, version)
      })
      await cdp.send("ServiceWorker.enable")
      await startWorker(page, fixture.url, "a")
      const other = await context.newPage()
      await startWorker(other, fixture.url, "b")
      await withDatabase(page, "enqueue")
      const firstScript = `${fixture.url}/a/sw.js`
      await expect.poll(() => workerVersions.get(firstScript)?.versionId).toBeTruthy()

      await trigger(page)
      await fixture.firstAttempt
      const firstVersion = workerVersions.get(firstScript)
      if (!firstVersion) throw new Error("First worker version was not observed")
      await cdp.send("ServiceWorker.stopWorker", { versionId: firstVersion.versionId })
      await expect.poll(() => workerVersions.get(firstScript)?.runningStatus).toBe("stopped")
      const lease = await withDatabase<{ owner: string; expiresAt: number }>(other, "lease")
      expect(lease.owner).toBeTruthy()
      expect(lease.expiresAt).toBeGreaterThan(Date.now())

      await trigger(other)
      await expect
        .poll(() =>
          other.evaluate(
            async (name) =>
              (await navigator.locks.query()).held?.filter((lock) => lock.name === name).length,
            lockName
          )
        )
        .toBe(1)
      // Give the successor more than one lease-poll interval while the orphan is still live.
      await new Promise((resolveWait) => setTimeout(resolveWait, 2 * REPLAY_LEASE_POLL_MS + 100))
      expect(fixture.attempts).toHaveLength(1)
      expect(await withDatabase(other, "records")).toHaveLength(1)
      expect(await withDatabase(other, "lease")).toEqual(lease)

      // The stopped worker cannot renew. Advancing the persisted expiry avoids a 30 s sleep.
      await withDatabase(other, "expire")
      await fixture.secondAttempt
      const successorLease = await withDatabase<{ owner: string; expiresAt: number }>(
        other,
        "lease"
      )
      expect(successorLease.owner).not.toBe(lease.owner)
      expect(successorLease.expiresAt).toBeGreaterThan(Date.now())
      expect(await withDatabase(other, "records")).toHaveLength(1)
      fixture.releaseSecond()
      await barrier(other)
      expect(await withDatabase(other, "records")).toEqual([])
      expect(await withDatabase(other, "lease")).toBeUndefined()
      expect(fixture.attempts).toHaveLength(2)
      expect(fixture.attempts[1]).toEqual(fixture.attempts[0])
    } finally {
      try {
        await cdp?.detach()
      } finally {
        await fixture.close()
      }
    }
  })
})
