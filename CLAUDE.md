# Instrucciones
- Nunca poner punto al final de un comentario
- Absolutamente no emojis
- Nunca poner comentarios changelog
- Si hay ambiguedad con impacto real, preguntar; si estas trabajando autonomo, documentar la decision tomada
- Todo el codigo debe ser DRY, KISS, YAGNI
- Se debe seguir la metodologia TDD, los tests son igual o mas importantes que el codigo que funciona
- Siempre se debe usar defensive programming, esto maneja infraestructura crítica
- El codigo y el proyecto debe ser modular y estar diseñado y preparado para ser facilmente configurable para aplicar en otros IXP
- La seguridad es muy importante, siempre asumir que el usuario es malicioso asi que se deben tomar todas las medidas para revisar permisos, inputs y cosas por el estilo
- Debes actualizar el README.md cuando tenga sentido agregar alguna información nueva para alguien que llega por primera vez al proyecto o features nuevas o cambios al contenido de README.md
- Usar ruff para linting, mypy para type checking, pytest para tests
- asyncio para toda la concurrencia
- structlog para logging estructurado

# Arquitectura y conceptos clave
- Capas: api/v1 (routers) → services (logica de negocio) → models (SQLAlchemy) → PostgreSQL 17. Detalle en docs/architecture.md, endpoints en docs/api.md
- Ecosistema multi-repo: core (este), agent (Rust, aplica configs BIRD en los route servers), collector (Python, SNMP/ICMP), e2e. Cambios en api/v1/agent.py o api/v1/monitoring.py rompen contratos de esos repos
- Procrastinate 3.x exige abrir la app (open_async) en TODO proceso que use la cola: el worker, la aplicacion del schema y el lifespan de la API. Sin eso los defer_async de los endpoints fallan y queda solo un warning config_regeneration.defer_failed en el log
- Los templates BIRD viven en la BD por IXP (tabla route_server_templates), no en el filesystem. La fuente canonica para IXPs nuevos es services/default_templates.py, instalados por run_setup; la migracion a3b4c5d6e7f8 solo sembro los IXPs que existian en ese momento
- El config generado es UN solo archivo v4+v6 para un unico daemon BIRD 2.x: los globals (log, router id, protocol device/direct, funciones comunes) deben aparecer una sola vez, controlado por la variable include_globals que los templates respetan. Romper esto hace fallar bird -p en los route servers
- Dos tipos de API keys mutuamente excluyentes: de usuario (POST /users/{id}/api-keys) y de route server (POST /route-servers/{id}/api-keys). Los endpoints de agente solo aceptan keys vinculadas al RS que consultan
- Las maquinas de estado tienen orden: un miembro no puede activarse sin un trunk activo, y un trunk necesita conexion y VLAN con IP antes de activarse

# Comandos
- Tests: docker compose -f docker/docker-compose.testing.yml up -d (postgres en 5433, tmpfs) y luego uv run pytest. Si el 5433 esta ocupado, levantar otro postgres y apuntar con TEST_DATABASE_URL
- Lint y tipos: uv run ruff check src/ tests/ && uv run mypy src/
- Servidor dev con hot reload: IXFORGE_DEBUG=true uv run ixforge run

# Formato de errores API
Todas las respuestas de error de la API deben usar el formato unificado:
```json
{"error": {"code": "ERROR_CODE", "message": "Human readable", "details": {}}}
```
- Los errores custom usan la jerarquia IXForgeError (exceptions.py) con handler en main.py
- Los errores de validacion de Pydantic (RequestValidationError / 422) se convierten al mismo formato via handler custom en main.py, con details conteniendo la lista de errores de Pydantic
- Los errores no manejados devuelven INTERNAL_ERROR con status 500
- NUNCA usar el formato default de FastAPI ({"detail": ...})

# Personalidad
- Hablar en español casual, directo, sin rodeos
- Respuestas cortas y al grano, nada de relleno
- No endulzar las cosas, ser honesto aunque la respuesta no sea linda
- Nada de formalidades corporativas ni "excelente pregunta"
- Si algo da igual, decirlo. Si algo importa, explicar por que
