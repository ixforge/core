# Guías de API

Recetas prácticas para operar IXForge contra la API REST del Core. Todos los
ejemplos usan `curl` (y `jq` para extraer campos); la referencia completa de
endpoints está en [../api.md](../api.md) y los conceptos en
[../architecture.md](../architecture.md).

Convención usada en los ejemplos:

```bash
CORE=http://localhost:8000   # URL del Core
```

## Índice

- [Autenticación](autenticacion.md): login JWT, API keys y cómo usarlas
- [Miembros](miembros.md): crear, listar (paginación), consultar, modificar, cambiar de estado y borrar
- [Aprovisionamiento](aprovisionamiento.md): alta completa de un miembro, trunk -> conexión -> VLAN -> IP -> sesiones BGP -> activar
- [Métricas y gráficos](metricas.md): tráfico, latencia y prefijos anunciados, por la API del Core o directo en VictoriaMetrics

## Notas comunes

- Los errores de la API usan el formato unificado `{"error": {"code", "message", "details"}}` (en los 422 de validación, `details` trae la lista de errores de Pydantic).
- Las operaciones de escritura (POST/PUT/PATCH/DELETE) sobre recursos de gestión requieren un usuario admin, por JWT o con una API key de un admin que tenga el scope `write` del recurso, salvo que se indique lo contrario.
- Los IDs son UUID. En los ejemplos se guardan en variables de shell (`MEMBER_ID=...`) para encadenar llamadas.
