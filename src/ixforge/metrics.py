"""Prometheus metrics registry and definitions."""

from prometheus_client import Counter, Gauge, Histogram

http_requests_total = Counter(
    "ixforge_http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
)

http_request_duration_seconds = Histogram(
    "ixforge_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path"],
)

bgp_sessions_active = Gauge(
    "ixforge_bgp_sessions_active",
    "Number of active BGP sessions",
    ["route_server_id"],
)

task_queue_enqueued = Gauge(
    "ixforge_task_queue_enqueued",
    "Number of enqueued tasks",
)

task_queue_completed = Counter(
    "ixforge_task_queue_completed_total",
    "Total completed tasks",
)

task_queue_failed = Counter(
    "ixforge_task_queue_failed_total",
    "Total failed tasks",
)
