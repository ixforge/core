# Setup / Installer Page

> **Estado: IMPLEMENTADO (documento historico).** Esta spec describe el diseño ya
> presente en el codigo (`api/v1/setup.py`, `services/setup.py`, `ui/routes/setup.py`).

Página de configuración inicial que se muestra cuando la base de datos está vacía (0 IXPs). Permite crear el IXP y la cuenta de administrador en un solo formulario.

## Flujo

1. Usuario visita cualquier ruta de la UI (incluyendo `/login`)
2. Middleware (clase Starlette en `app.py`) detecta que no hay IXP configurado → redirige a `/setup`
3. `GET /setup` → muestra formulario
4. `POST /setup` (UI) → `POST /api/v1/setup` (API) — llamada sin token via `APIClient.post_public()`
5. API valida que IXP count == 0, crea IXP + admin user en una transacción
6. Éxito → redirige a `/login` con flash "Instalación completada"
7. Si ya existe un IXP, `/setup` redirige a `/login` (tanto en GET como en POST — si el POST recibe 409 porque otro admin completó el setup, se muestra flash "El sistema ya fue configurado" y redirige a `/login`)

Nota: `/login` no está exento del middleware. Si no hay IXP, el usuario es redirigido a `/setup` incluso si intenta acceder a `/login` directamente.

## API Endpoint

### `POST /api/v1/setup`

Sin autenticación. No usa las dependencias `IXPId`, `CurrentUser` ni `AdminUser`. Solo funciona cuando no existe ningún IXP en la DB.

**Request:**

```json
{
  "ixp": {
    "name": "PatagoniaIX",
    "short_name": "PTGIX",
    "asn": 65000,
    "website": "https://patagoniaix.net",
    "country": "CL",
    "city": "Santiago"
  },
  "admin": {
    "full_name": "Juan Admin",
    "email": "admin@patagoniaix.net",
    "password": "supersecreta123"
  }
}
```

- `ixp.website` es opcional, el resto es obligatorio
- `ixp.country` y `ixp.city` son obligatorios en setup aunque el modelo IXP los permite como null (decisión intencional: el setup requiere datos completos)
- `ixp.asn` debe ser un entero positivo
- `admin.password` mínimo 8 caracteres (misma regla que `UserCreate`)

**Responses:**

| Status | Code | Descripción |
|--------|------|-------------|
| 201 | — | `{"message": "Setup completed"}` — no retorna el recurso creado porque no hay sesión autenticada |
| 409 | `CONFLICT` | `{"error": {"code": "CONFLICT", "message": "IXP already configured", "details": {}}}` — usa `ConflictError` estándar |
| 422 | — | Errores de validación (formato estándar) |

**Guard:** Usar `pg_advisory_xact_lock(1)` al inicio de la transacción para serializar llamadas concurrentes, luego verificar `SELECT count(*) FROM ixps`. Si > 0, retornar 409. Se usa advisory lock en vez de `LOCK TABLE` porque es compatible con savepoints (necesario para los tests que usan transacciones anidadas).

### `GET /api/v1/setup/status`

Sin autenticación. Retorna si el sistema ya fue configurado.

```json
{"configured": false}
```

Usado por el middleware de la UI para decidir si redirigir a `/setup`.

## UI

### Página `/setup`

- Layout: `layouts/auth.html` (centrado, sin sidebar, mismo que login)
- Formulario con dos secciones:
  - **Datos del IXP**: name, short_name, asn, website, country, city
  - **Cuenta de Administrador**: full_name, email, password, confirmar password
- Botón: "Iniciar IXForge"
- Validación de contraseña coincidente en el frontend antes de enviar
- Errores de la API se muestran en el mismo formato que los demás formularios

### Middleware de redirección

- Clase Starlette middleware en `app.py`
- Antes de procesar cualquier ruta (excepto `/setup`, `/static`, `/media`):
  - Llamar a `GET /api/v1/setup/status` via `APIClient.get_public()` para verificar si hay un IXP configurado
  - Si no hay IXP → redirigir a `/setup`
  - Si la API no responde → dejar pasar el request (fail open). El error se mostrará en la ruta que intente usar la API.
- `/setup` también verifica: si ya hay un IXP → redirigir a `/login`
- Cache: cachear `configured=True` en `app.state` para no consultar en cada request. Una vez configurado, nunca vuelve a false. El handler POST de `/setup` en la UI marca el cache como True después del setup exitoso.

### APIClient

- Agregar método `post_public(path, json)` que hace POST sin header `Authorization`. Necesario porque en el momento del setup no existe ningún usuario ni token.
- Agregar método `get_public(path, params)` que hace GET sin header `Authorization`. Usado por el middleware para consultar `/api/v1/setup/status`.

## Archivos

### Nuevos

| Archivo | Descripción |
|---------|-------------|
| `src/ixforge/api/v1/setup.py` | Endpoints `POST /api/v1/setup` y `GET /api/v1/setup/status` |
| `src/ixforge/schemas/setup.py` | Schemas de request/response |
| `src/ixforge/services/setup.py` | Lógica de negocio (crear IXP + admin) |
| `src/ixforge/ui/routes/setup.py` | Handlers `GET/POST /setup` |
| `src/ixforge/ui/templates/setup.html` | Template del formulario |
| `tests/test_setup.py` | Tests del endpoint y servicio (usa DB vacía sin IXP pre-seeded, a diferencia de los demás tests) |

### Modificar

| Archivo | Cambio |
|---------|--------|
| `src/ixforge/api/v1/router.py` | Registrar ruta setup (sin dependencias de tenant/auth) |
| `src/ixforge/ui/app.py` | Registrar ruta `/setup` + agregar middleware `SetupRedirectMiddleware` |
| `src/ixforge/ui/api_client.py` | Agregar métodos `post_public()` y `get_public()` |

## CLI

- El comando `seed` se elimina de `cli.py`: eliminar `_seed_data()`, `_run_seed()`, y la entrada en `_COMMANDS`. El setup page lo reemplaza.
- El comando `createsuperuser` se mantiene como utilidad pero se agrega validación: verificar que exista al menos un IXP antes de crear el usuario, abortar con mensaje de error si no.

## Testing

- Test: `POST /api/v1/setup` con datos válidos → 201, IXP y user creados
- Test: `POST /api/v1/setup` cuando ya hay IXP → 409
- Test: `GET /api/v1/setup/status` con DB vacía → `{"configured": false}`
- Test: `GET /api/v1/setup/status` con IXP → `{"configured": true}`
- Test: validación de campos obligatorios → 422
- Test: servicio crea IXP y admin en una transacción (rollback si falla)
- Nota: los tests de setup necesitan una DB vacía (sin IXP pre-seeded), a diferencia de los demás tests que usan fixtures con IXP ya creado
