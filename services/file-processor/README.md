# File processor job contract

The implemented operation is `image_resize`. gRPC `ProcessFile`, the GraphQL
`processFile` mutation, and NATS `files.process` delivery all use this operation
name. `width` and `height` default to 800 and 600 when absent; existing image
dimension, pixel-count, storage-key, and authorization limits still apply.

`image_compress`, `pdf_preview`, and `video_transcode` have no implementation.
They are rejected before a Temporal workflow starts: gRPC returns
`InvalidArgument`, GraphQL returns an unsupported-file-type error, and the NATS
consumer terminates the invalid delivery. They must not be used as aliases for
resizing. Unsupported GraphQL type strings are also rejected.

This corrects earlier ingress allowlists that advertised unimplemented
operations and sent all of them to the resize activity. Producers must use
`image_resize` only when resizing is intended. Workflow replay structure is
unchanged; already-started workflows retain their recorded activity path.

Invalid resize dimensions are classified as `InvalidInputError`, matching the
workflow's non-retryable activity policy.
