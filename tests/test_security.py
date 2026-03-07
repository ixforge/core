"""Tests for security: CORS config, security headers, metrics path normalization."""

from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ixforge.config import Settings
from ixforge.main import MetricsMiddleware, create_app

# ---------------------------------------------------------------------------
# CORS configuration
# ---------------------------------------------------------------------------


class TestCORSConfig:
    def test_cors_debug_mode_no_wildcard(self):
        """En debug mode, cors_origins no debe contener '*'"""
        settings = Settings(debug=True, secret_key="a" * 32)
        assert "*" not in settings.cors_origins
        assert len(settings.cors_origins) > 0  # tiene origenes especificos

    def test_cors_production_mode_empty_by_default(self):
        """En produccion sin configuracion, cors_origins es vacio"""
        settings = Settings(debug=False, secret_key="a" * 32)
        assert settings.cors_origins == []


# ---------------------------------------------------------------------------
# Security headers
# ---------------------------------------------------------------------------


class TestSecurityHeaders:
    def test_security_headers_present(self):
        """Todas las respuestas deben incluir security headers"""
        app = create_app(enable_rate_limit=False)
        client = TestClient(app, raise_server_exceptions=False)

        # openapi.json no requiere DB ni auth
        response = client.get("/api/v1/openapi.json")

        assert response.headers.get("x-content-type-options") == "nosniff"
        assert response.headers.get("x-frame-options") == "DENY"
        assert "strict-origin-when-cross-origin" in response.headers.get(
            "referrer-policy", ""
        )

    def test_security_headers_on_404(self):
        """Security headers presentes incluso en respuestas 404"""
        app = create_app(enable_rate_limit=False)
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get("/nonexistent-path")

        assert response.headers.get("x-content-type-options") == "nosniff"
        assert response.headers.get("x-frame-options") == "DENY"
        assert "strict-origin-when-cross-origin" in response.headers.get(
            "referrer-policy", ""
        )


# ---------------------------------------------------------------------------
# Metrics path normalization
# ---------------------------------------------------------------------------


class TestMetricsPathNormalization:
    def test_metrics_uses_route_template_not_raw_path(self):
        """MetricsMiddleware debe usar el route template para evitar cardinality explosion"""
        app = FastAPI()

        @app.get("/items/{item_id}")
        async def get_item(item_id: str):
            return {"id": item_id}

        app.add_middleware(MetricsMiddleware)

        # Patchear los contadores para capturar los labels usados
        recorded_labels: list[dict[str, str]] = []

        class FakeCounter:
            def __init__(self, **kwargs: str):
                self.kwargs = kwargs
                recorded_labels.append(kwargs)

            def inc(self, amount: float = 1) -> None:
                pass

        class FakeHistogramChild:
            def __init__(self, **kwargs: str):
                pass

            def observe(self, amount: float) -> None:
                pass

        with (
            patch(
                "ixforge.main.http_requests_total.labels",
                side_effect=lambda **kw: FakeCounter(**kw),
            ),
            patch(
                "ixforge.main.http_request_duration_seconds.labels",
                side_effect=lambda **kw: FakeHistogramChild(**kw),
            ),
        ):
            client = TestClient(app)
            client.get("/items/123")
            client.get("/items/456")

        paths = [entry["path"] for entry in recorded_labels]
        assert "/items/{item_id}" in paths
        assert "/items/123" not in paths
        assert "/items/456" not in paths
