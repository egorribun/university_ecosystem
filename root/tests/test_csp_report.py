"""Tests for CSP violation reporting endpoint."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


class TestCSPReport:
    """Tests for the CSP violation reporting endpoint."""

    def test_receive_valid_csp_report(self, client):
        """Should accept and log a valid CSP violation report."""
        report = {
            "csp-report": {
                "document-uri": "https://example.com/page",
                "violated-directive": "script-src",
                "effective-directive": "script-src",
                "blocked-uri": "https://malicious.com/script.js",
                "source-file": "https://example.com/page",
                "line-number": 10,
                "column-number": 5,
            }
        }

        response = client.post(
            "/api/v1/csp-report",
            json=report,
            headers={"Content-Type": "application/csp-report"},
        )

        assert response.status_code == 204

    def test_receive_empty_body(self, client):
        """Should handle empty body gracefully."""
        response = client.post(
            "/api/v1/csp-report",
            content=b"",
        )

        assert response.status_code == 204

    def test_receive_invalid_json(self, client):
        """Should handle invalid JSON gracefully."""
        response = client.post(
            "/api/v1/csp-report",
            content=b"not valid json",
        )

        assert response.status_code == 204

    def test_receive_flat_report(self, client):
        """Should accept report without csp-report wrapper."""
        report = {
            "document-uri": "https://example.com/page",
            "violated-directive": "img-src",
            "blocked-uri": "data:",
        }

        response = client.post("/api/v1/csp-report", json=report)

        assert response.status_code == 204

    def test_truncates_long_fields(self, client):
        """Should handle reports with very long fields."""
        report = {
            "csp-report": {
                "document-uri": "https://example.com/page",
                "violated-directive": "script-src",
                "script-sample": "x" * 500,  # Very long sample
            }
        }

        response = client.post("/api/v1/csp-report", json=report)

        assert response.status_code == 204
