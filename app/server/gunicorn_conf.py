"""Compatibility config; the image CMD also selects this worker explicitly.

No SDK connection, certificate files or thread may be created in the master.
The worker performs strict flag/config validation and initializes after fork.
"""

worker_class = "app.server.spiffe_worker.BackendWorker"
