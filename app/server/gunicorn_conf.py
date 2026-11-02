"""Gunicorn settings for the backend listener (AUD-373).

The backend Deployment activates this module with
``GUNICORN_CMD_ARGS=--config=python:app.server.gunicorn_conf`` only when
``internalHttpMTLS.enabled`` is true. Without it the image default command keeps
the plaintext listener used by local development. Invalid material raises during
import, so the Gunicorn master exits before any worker accepts a connection.
"""

import os
import ssl

from app.server.internal_mtls import load_internal_http_mtls

_material = load_internal_http_mtls(os.environ)

if _material is not None:
    certfile = _material.certfile
    keyfile = _material.keyfile
    ca_certs = _material.ca_certs
    cert_reqs = int(ssl.CERT_REQUIRED)
