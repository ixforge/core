# Guías de API

Recetas prácticas para operar IXForge contra la API REST del Core. Todos los
ejemplos usan `curl`; la referencia completa de endpoints está en
[../api.md](../api.md) y los conceptos en [../architecture.md](../architecture.md).

Convención usada en los ejemplos:

```bash
CORE=http://localhost:8000   # URL del Core
```

## Índice

- [Autenticación](autenticacion.md) - login JWT, API keys y cómo usarlas
- [Miembros](miembros.md) - crear, listar (paginación), consultar, modificar, cambiar estado, borrar
- [Aprovisionamiento](aprovisionamiento.md) - alta completa de un miembro: trunk → conexión → VLAN → IP → sesiones BGP → activar
- [Métricas y gráficos](metricas.md) - consultar tráfico y latencia desde VictoriaMetrics

## Notas comunes

- Los errores de la API usan el formato unificado `{"error": {"code", "message", "details"}}` (en los 422 de validación, `details` trae la lista de errores de Pydantic).
- Las operaciones de escritura (POST/PATCH/DELETE) sobre recursos de gestión requieren un usuario admin (JWT) salvo que se indique lo contrario.
- Los IDs son UUID. En los ejemplos se guardan en variables de shell (`MEMBER_ID=...`) para encadenar llamadas.
