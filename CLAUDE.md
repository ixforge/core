# Instrucciones
- Nunca poner punto al final de un comentario
- Absolutamente no emojis
- Nunca poner comentarios changelog. El registro de cambios va en git, no en comentarios esparcidos por el código.
- Si hay ambigüedad con impacto real, preguntar; si estás trabajando autónomo, documentar la decisión tomada
- Todo el código debe ser DRY, KISS, YAGNI
- Se debe seguir la metodología TDD, los tests son igual o más importantes que el código que funciona
- Siempre se debe usar defensive programming, esto maneja infraestructura crítica
- El código y el proyecto debe ser modular y estar diseñado y preparado para ser fácilmente configurable para aplicar en otros IXP
- La seguridad es muy importante, siempre asumir que el usuario es malicioso así que se deben tomar todas las medidas para revisar permisos, inputs y cosas por el estilo
- Debes actualizar el README.md cuando tenga sentido agregar alguna información nueva para alguien que llega por primera vez al proyecto o features nuevas o cambios al contenido de README.md
- Usar ruff para linting, mypy para type checking, pytest para tests
- asyncio para toda la concurrencia
- structlog para logging estructurado

# Arquitectura y conceptos clave
- Capas: api/v1 (routers) → services (lógica de negocio) → models (SQLAlchemy) → PostgreSQL 17. Detalle en docs/architecture.md, endpoints en docs/api.md
- Ecosistema multi-repo: core (este), agent (Rust, aplica configs BIRD en los route servers), collector (Python, SNMP/ICMP), e2e. Cambios en api/v1/agent.py o api/v1/monitoring.py rompen contratos de esos repos
- Procrastinate 3.x exige abrir la app (open_async) en TODO proceso que use la cola: el worker, la aplicación del schema y el lifespan de la API. Sin eso los defer_async de los endpoints fallan y queda solo un warning config_regeneration.defer_failed en el log
- Los templates BIRD viven en la BD por IXP (tabla route_server_templates), no en el filesystem. La fuente canónica para IXPs nuevos es services/default_templates.py, instalados por run_setup; la migración a3b4c5d6e7f8 solo sembró los IXPs que existían en ese momento
- El config generado es UN solo archivo v4+v6 para un único daemon BIRD 2.x, de UN solo render de bird.conf.j2. No existe include_globals: se eliminó junto con el par bird_v4/bird_v6.conf.j2, porque coordinar dos renders con un booleano que los templates respetaban por convención fue de donde salió el protocol device duplicado en producción
- Los filtros de import del set de route server NUNCA rechazan: marcan con una large community (routeserverasn, 1101, *) y aceptan. El único reject vive en f_export_to_master, el pipe hacia master, y hay un test que verifica que siga siendo el único. Si agregas un chequeo, marca y acepta. Detalle en docs/templates.md
- El entorno Jinja usa StrictUndefined: un atributo que no existe revienta al renderear. Sin eso se rendereaba a string vacío y producía un config inválido que igual se guardaba y se le mandaba al agent
- Los símbolos BIRD se truncan a 55, no a 64: el patrón de route server deriva cinco símbolos del mismo slug y f_import_ mide 9. Y lo que se recorta es el nombre, nunca la IP ni la familia, que son lo único que da unicidad
- El commit de la sesión lo hace CommitBeforeResponse (main.py), un middleware ASGI puro, NO el código posterior al yield de la dependencia: FastAPI ejecuta eso después de entregar la respuesta, así que la API confirmaba antes de saber si guardó, y crear-y-usar-acto-seguido fallaba 4 de cada 6 veces contra un deployment real
- La suite usa sesión transaccional con rollback, así que TODO lo que dependa de cuándo ocurre el commit es invisible en tests. Varios bugs de esta clase solo aparecen desplegando
- El entrypoint del contenedor aplica migraciones al arrancar (IXFORGE_AUTO_MIGRATE=false lo desactiva). El portal no migra: no tiene ni debe tener credenciales de base. El lock de migración en alembic/env.py va ANTES de run_sync, porque alembic planifica adentro de do_run_migrations
- Las communities de tipo de miembro usan el rango 65xxx a propósito: están en el espacio de ASN privados y no colisionan con (rsasn, peer-as) del control de anuncio. Con valores bajos la colisión es explotable y anuncia rutas contra la voluntad del miembro
- Todo prefijo de documentación IPv6 (2001:db8::/32, 3fff::/20) es martian, y el chequeo de martians corre ANTES del filtro de prefijos. Una fixture con uno de esos en allnet parece probar el filtrado por prefijo y no prueba nada
- La sintaxis de BIRD 2.x diverge entre menores en las dos direcciones: 2.18 acepta `function f() -> bool` y 2.0.12 la rechaza. La imagen del validador tiene que construirse con la versión que corre en los route servers
- Dos tipos de API keys mutuamente excluyentes: de usuario (POST /users/{id}/api-keys) y de route server (POST /route-servers/{id}/api-keys). Los endpoints de agente solo aceptan keys vinculadas al RS que consultan
- Las máquinas de estado tienen orden: un miembro no puede activarse sin un trunk activo, y un trunk necesita conexión y VLAN con IP antes de activarse

# Comandos
- Tests: docker compose -f docker/docker-compose.testing.yml up -d (postgres en 5433, tmpfs) y luego uv run pytest. Si el 5433 está ocupado, levantar otro postgres y apuntar con TEST_DATABASE_URL
- Lint y tipos: uv run ruff check src/ tests/ && uv run mypy src/
- Servidor dev con hot reload: IXFORGE_DEBUG=true uv run ixforge run

# Formato de errores API
Todas las respuestas de error de la API deben usar el formato unificado:
```json
{"error": {"code": "ERROR_CODE", "message": "Human readable", "details": {}}}
```
- Los errores custom usan la jerarquía IXForgeError (exceptions.py) con handler en main.py
- Los errores de validación de Pydantic (RequestValidationError / 422) se convierten al mismo formato vía handler custom en main.py, con details conteniendo la lista de errores de Pydantic
- Los errores no manejados devuelven INTERNAL_ERROR con status 500
- NUNCA usar el formato default de FastAPI ({"detail": ...})

# Personalidad
- Hablar en español casual, directo, sin rodeos
- Respuestas cortas y al grano, nada de relleno
- No endulzar las cosas, ser honesto aunque la respuesta no sea linda
- Nada de formalidades corporativas ni "excelente pregunta"
- Si algo da igual, decirlo. Si algo importa, explicar por qué
