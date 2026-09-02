import { Readable } from "node:stream"

export async function pipeResponseBody(webResponse, destination, logger = console) {
  if (!webResponse.body) {
    destination.end()
    return
  }

  const source = Readable.fromWeb(webResponse.body)
  await new Promise((resolve) => {
    let settled = false

    const cleanup = () => {
      source.off("error", onSourceError)
      destination.off("error", onDestinationError)
      destination.off("finish", onFinish)
      destination.off("close", onClose)
    }
    const settle = () => {
      if (settled) return
      settled = true
      cleanup()
      resolve()
    }
    const onSourceError = (error) => {
      logger.error("server-prod: response stream error:", error)
      // A source failure means the SSR body is truncated. Ending the response
      // would turn a partial document into an apparently successful HTTP 200;
      // abort the transport so clients and edge proxies observe the failure.
      // Destroy without forwarding `error`: it has already been observed here,
      // and forwarding it would schedule a second unhandled error after cleanup.
      if (!destination.destroyed) destination.destroy()
      settle()
    }
    const onDestinationError = (error) => {
      logger.error("server-prod: destination stream error:", error)
      // The destination error is already observed and logged. Destroy the
      // source without forwarding that same error, otherwise Node can emit a
      // second asynchronous source error after listeners have been cleaned up.
      if (!source.destroyed) source.destroy()
      settle()
    }
    const onFinish = () => settle()
    const onClose = () => {
      if (!destination.writableFinished && !source.destroyed) source.destroy()
      settle()
    }

    source.once("error", onSourceError)
    destination.once("error", onDestinationError)
    destination.once("finish", onFinish)
    destination.once("close", onClose)
    source.pipe(destination)
  })
}
