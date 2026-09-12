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

# El conteo por sesion que reporta el agente. Existe como metrica y no solo como
# columna porque la columna se sobreescribe en cada reporte: para graficarlo en
# el tiempo hace falta que alguien lo guarde con su timestamp
#
# Una sesion sin conteo BORRA su serie en vez de publicar cero. Un gauge que se
# queda pegado sigue reportando los prefijos de un peer que ya no esta, y un
# cero se lee como "conectado sin anunciar nada", que es otra cosa. Sin serie
# el grafico dibuja un hueco, que es lo que de verdad pasa
bgp_session_prefixes_imported = Gauge(
    "ixforge_bgp_session_prefixes_imported",
    "Prefixes received from the peer on this session",
    ["route_server_id", "peer_asn", "af"],
)

bgp_session_prefixes_exported = Gauge(
    "ixforge_bgp_session_prefixes_exported",
    "Prefixes advertised to the peer on this session",
    ["route_server_id", "peer_asn", "af"],
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
