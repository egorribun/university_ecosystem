# Docker log proxy runtime contract

The proxy runs as UID/GID 65532, drops every Linux capability, keeps its root
filesystem read-only, and receives only the numeric supplementary group needed
to connect to the host Docker socket. Set DOCKER_SOCKET_GID to the socket's
group ID on rootful Linux Docker Engine; the default 0 supports a root:root
socket. Rootless and user-namespace-remapped sockets are unsupported. The bind
mount stays read-only in both supported Compose files.

The image health check invokes /docker-log-proxy --healthcheck. That mode
uses a fixed loopback /healthz request with a two-second timeout and does not
contact the Docker socket. The API proxy itself exposes only the read-only
Docker endpoints required by Alloy discovery and log streaming.
