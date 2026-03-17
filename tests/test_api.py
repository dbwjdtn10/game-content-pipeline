"""Tests for FastAPI application, middleware, and health endpoints."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def client():
    """Create a test client with mocked DB/Redis connections."""
    # Patch engine creation before importing app
    with (
        patch("src.api.main.engine") as mock_engine,
        patch("src.api.main.SessionLocal"),
        patch("src.api.main.Base"),
    ):
        mock_engine.connect.return_value.__enter__ = MagicMock()
        mock_engine.connect.return_value.__exit__ = MagicMock()

        from src.api.main import app

        return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Health check tests
# ---------------------------------------------------------------------------


class TestHealthEndpoints:
    """Test health check endpoints."""

    def test_liveness_probe(self, client: TestClient) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_readiness_probe_returns_checks(self, client: TestClient) -> None:
        """Readiness probe should return DB and Redis check results."""
        with (
            patch("src.api.main._check_db", return_value={"status": "healthy"}),
            patch("src.api.main._check_redis", return_value={"status": "healthy"}),
        ):
            response = client.get("/health/ready")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ready"
            assert "database" in data["checks"]
            assert "redis" in data["checks"]

    def test_readiness_degraded_when_db_unhealthy(self, client: TestClient) -> None:
        with (
            patch(
                "src.api.main._check_db",
                return_value={"status": "unhealthy", "error": "connection refused"},
            ),
            patch("src.api.main._check_redis", return_value={"status": "healthy"}),
        ):
            response = client.get("/health/ready")
            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "degraded"


# ---------------------------------------------------------------------------
# Middleware tests
# ---------------------------------------------------------------------------


class TestRequestIDMiddleware:
    """Test that request IDs are generated and propagated."""

    def test_response_has_request_id_header(self, client: TestClient) -> None:
        response = client.get("/health")
        assert "X-Request-ID" in response.headers

    def test_response_has_timing_header(self, client: TestClient) -> None:
        response = client.get("/health")
        assert "X-Response-Time-Ms" in response.headers

    def test_custom_request_id_propagated(self, client: TestClient) -> None:
        response = client.get("/health", headers={"X-Request-ID": "custom-123"})
        assert response.headers["X-Request-ID"] == "custom-123"


class TestRateLimitMiddleware:
    """Test rate limiting headers and behavior."""

    def test_rate_limit_headers_present(self, client: TestClient) -> None:
        response = client.get("/health")
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers


# ---------------------------------------------------------------------------
# API versioning tests
# ---------------------------------------------------------------------------


class TestAPIVersioning:
    """Test API versioning routes exist."""

    def test_v1_health(self, client: TestClient) -> None:
        """Non-versioned health endpoint should work."""
        response = client.get("/health")
        assert response.status_code == 200

    def test_docs_endpoint(self, client: TestClient) -> None:
        response = client.get("/docs")
        assert response.status_code == 200

    def test_redoc_endpoint(self, client: TestClient) -> None:
        response = client.get("/redoc")
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Global exception handler test
# ---------------------------------------------------------------------------


class TestGlobalExceptionHandler:
    """Test that unhandled exceptions produce structured JSON errors."""

    def test_unhandled_exception_returns_500_json(self, client: TestClient) -> None:
        """Simulate an unhandled error in a route."""
        from src.api.main import app

        @app.get("/_test_error")
        def raise_error():
            raise RuntimeError("test boom")

        response = client.get("/_test_error")
        assert response.status_code == 500
        data = response.json()
        assert data["detail"] == "Internal server error"
        assert "request_id" in data
