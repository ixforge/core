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
- El config generado es UN solo archivo v4+v6 para un unico daemon BIRD 2.x, de UN solo render de bird.conf.j2. No existe include_globals: se elimino junto con el par bird_v4/bird_v6.conf.j2, porque coordinar dos renders con un booleano que los templates respetaban por convencion fue de donde salio el protocol device duplicado en produccion
- Los filtros de import del set euro-ix NUNCA rechazan: marcan con una large community (routeserverasn, 1101, *) y aceptan. El unico reject vive en f_export_to_master, el pipe hacia master, y hay un test que verifica que siga siendo el unico. Si agregas un chequeo, marca y acepta. Detalle en docs/templates.md
- El entorno Jinja usa StrictUndefined: un atributo que no existe revienta al renderear. Sin eso se rendereaba a string vacio y producia un config invalido que igual se guardaba y se le mandaba al agent
- Los simbolos BIRD se truncan a 55, no a 64: el patron euro-ix deriva cinco simbolos del mismo slug y f_import_ mide 9. Y lo que se recorta es el nombre, nunca la IP ni la familia, que son lo unico que da unicidad
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
