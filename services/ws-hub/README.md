# Hub transport message contract

The WebTransport adapter uses one client-opened bidirectional byte stream.
Each application message is one UTF-8 JSON object. Client objects are subject
to the same `join`/`leave` validation and authorization as WebSocket messages.
Optional JSON whitespace may separate objects; no newline or length prefix is
required. For example, both of these objects can share one stream write:

```json
{"type":"join","room_id":"room-1"}{"type":"leave","room_id":"room-1"}
```

Stream reads may split an object or combine several objects. The adapter
buffers incomplete objects and returns each complete object separately,
respecting braces inside strings and escaped quotes. Inbound objects are
bounded by `Session.SetReadLimit`; excessive inter-object whitespace is also
bounded. Malformed, non-object, truncated, or oversized input ends stream
message processing. Closing the session interrupts pending stream reads.

Outbound stream messages keep their existing raw JSON bytes. Clients must
likewise decode complete JSON objects rather than treating each stream read
as a message. Short writes are completed before the next object is written.
Each outbound fallback datagram contains one complete message and must satisfy
the pending write deadline. QUIC handles transport keep-alives.

This fixes message boundaries without introducing a new wire prefix or
delimiter. The first-party browser client currently uses WebSocket.

## Session lifetime

Upgrade tickets contain exactly `user_id:jti:expires_at_unix_seconds`. The
expiry is the authenticated session's immutable cutoff, not the ticket TTL or
a sliding cache timeout. Both transports retain it and refuse new action or outbound-frame
authorization at or after that cutoff. Legacy two-field tickets are rejected; deploy
the issuer and consumers together (unused tickets normally live for 15 seconds).

Inbound actions always check the dedicated security Redis. All outbound live,
replay and notification frames share the same final authorization boundary.
Successful delivery checks may be reused for at most one second per connection,
so broadcast volume does not cause one Redis request per frame. A missed Pub/Sub
notice leaves at most this bounded window before subsequent delivery must
revalidate. Idle sessions are also checked by a one-second timer, independently
of WebSocket pongs. Lookup failures fail closed and cannot be revived by another
pump. A terminated revocation subscription disconnects its active clients;
reconnect gaps are covered by the durable checks.

WebTransport retains read and write deadlines set before the peer opens its
first bidirectional stream. QUIC keep-alives do not extend session authority.

First-stream acceptance uses the earliest already-pending read/write deadline
or its ten-second acceptance cap. An expired pending deadline rejects before
transport I/O. Deadline setters remain serialized with an in-flight stream
accept: a setter invoked after acceptance starts waits for that operation and
does not shorten its captured context deadline. This adapter therefore does
not provide concurrent deadline-update interruption of an ongoing accept.

Session expiry is checked when a new action or outbound frame is authorized.
It does not retroactively cancel a transport write already authorized before
that cutoff: the existing ten-second write deadline also covers first-stream
acceptance, so such a frame may complete after session expiry. Write deadlines
are not clamped to the session cutoff; existing deadline-setter errors are
logged. Datagram fallback now refuses an expired write deadline or a failed
stream deadline application, while a valid fallback remains available.
